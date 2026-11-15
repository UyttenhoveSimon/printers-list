"""The catalogue: what every source saw, merged into one record per product.

Two files under ``data/``, both rewritten by every run:

- ``products.json``: one record per Icecat id with its specifications and
  its *sightings*, the ``source:market`` pairs that listed it and when.
- ``state.json``: what Icecat answered for each lookup (so a code Icecat does
  not know is not asked again every week), the sources' own caches, and the
  date each ``source:market`` last answered.

A product is available when a sighting of it is as recent as the last
successful read of that ``source:market``. A source that is down for a week
therefore leaves its products as they were instead of retiring them all.
"""

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from . import icecat
from .fetch import BotWallError, Fetcher, FetchError
from .sources import Candidate, Source

logger = logging.getLogger(__name__)

#: how long a lookup that found nothing is trusted before Icecat is asked again
RETRY_AFTER = timedelta(days=30)
#: lookups between two saves of the catalogue during a run
CHECKPOINT = 500


def load(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True)
    path.write_text(text + "\n", encoding="utf-8")


@dataclass
class Report:
    """What a run did, per source and in total, for the log and the page."""

    sources: dict[str, dict[str, Any]] = field(default_factory=dict)
    lookups: int = 0
    new: list[str] = field(default_factory=list)
    pending: int = 0


@dataclass
class Catalog:
    data_dir: Path
    today: date = field(default_factory=date.today)
    products: dict[str, dict[str, Any]] = field(init=False)
    state: dict[str, Any] = field(init=False)

    def __post_init__(self) -> None:
        self.products = load(self.data_dir / "products.json", {})
        self.state = load(
            self.data_dir / "state.json",
            {"lookups": {}, "caches": {}, "runs": {}, "started": None},
        )
        self.state["started"] = self.state["started"] or self.today.isoformat()

    def save(self) -> None:
        save(self.data_dir / "products.json", self.products)
        save(self.data_dir / "state.json", self.state)

    # discovery ---------------------------------------------------------------

    def discover(
        self, fetcher: Fetcher, sources: list[Source], report: Report
    ) -> dict[str, list[Candidate]]:
        """Ask every source about every market; a failure is reported, not fatal."""
        found: dict[str, list[Candidate]] = {}
        for source in sources:
            cache = self.state["caches"].setdefault(source.NAME, {})
            for market in source.MARKETS:
                where = f"{source.NAME}:{market}"
                try:
                    candidates = source.discover(fetcher, market, cache)
                except BotWallError as error:
                    report.sources[where] = {"status": "walled", "detail": str(error)}
                    logger.warning(f"{where}: {error}")
                    continue
                except FetchError as error:
                    report.sources[where] = {"status": "error", "detail": str(error)}
                    logger.warning(f"{where}: {error}")
                    continue
                if not candidates:
                    # an empty list is a changed page, not a brand that stopped
                    report.sources[where] = {"status": "empty", "detail": ""}
                    logger.warning(f"{where}: no printer found, markup changed?")
                    continue
                found[where] = candidates
                report.sources[where] = {"status": "ok", "found": len(candidates)}
                logger.info(f"{where}: {len(candidates)} printers")
        return found

    # lookups -----------------------------------------------------------------

    def resolve(
        self, fetcher: Fetcher, candidate: Candidate, budget: list[int]
    ) -> str | None:
        """Return the Icecat id of a candidate in scope, looking it up if needed.

        ``budget`` is a one-item list of lookups still allowed in this run;
        candidates past it stay unresolved until the next run.
        """
        known = self.state["lookups"].get(candidate.key)
        if known is not None:
            product_id = str(known.get("id"))
            if not known.get("reason") and product_id in self.products:
                return product_id
            checked = date.fromisoformat(known["checked"])
            if known.get("id") is not None or self.today - checked < RETRY_AFTER:
                return None
        if budget[0] <= 0:
            return None
        budget[0] -= 1
        try:
            result = icecat.lookup(
                fetcher,
                icecat_id=candidate.icecat_id,
                brand=candidate.brand,
                code=candidate.code,
                gtin=candidate.gtin,
            )
        except FetchError as error:
            logger.debug(f"{candidate.key}: {error}")
            return None
        record = result.record
        self.state["lookups"][candidate.key] = {
            "id": record["icecat_id"] if record else None,
            "reason": result.reason,
            "checked": self.today.isoformat(),
        }
        if record is None or result.reason:
            return None
        product_id = str(record["icecat_id"])
        previous = self.products.get(product_id, {})
        self.products[product_id] = record | {
            "first_seen": previous.get("first_seen", self.today.isoformat()),
            "sightings": previous.get("sightings", {}),
        }
        return product_id

    # the run -----------------------------------------------------------------

    def update(
        self, fetcher: Fetcher, sources: list[Source], max_lookups: int
    ) -> Report:
        report = Report()
        known_before = set(self.products)
        found = self.discover(fetcher, sources, report)
        budget = [max_lookups]
        today = self.today.isoformat()
        sightings: dict[tuple[str, str], dict[str, Any]] = {}
        for where, candidates in found.items():
            for count, candidate in enumerate(candidates, 1):
                spent = budget[0]
                product_id = self.resolve(fetcher, candidate, budget)
                if budget[0] != spent and budget[0] % CHECKPOINT == 0:
                    # a first fill takes hours: a crash must not lose it all
                    self.save()
                if count % 250 == 0:
                    logger.info(f"{where}: {count}/{len(candidates)} resolved")
                if product_id is None:
                    continue
                sighting = sightings.setdefault(
                    (product_id, where),
                    {"date": today, "markets": set(), "url": candidate.url},
                )
                sighting["markets"].update(candidate.markets)
            self.state["runs"][where] = today
        for (product_id, where), sighting in sightings.items():
            sighting["markets"] = sorted(sighting["markets"])
            self.products[product_id]["sightings"][where] = sighting
        report.lookups = max_lookups - budget[0]
        report.new = sorted(set(self.products) - known_before)
        report.pending = sum(
            1
            for candidates in found.values()
            for candidate in candidates
            if candidate.key not in self.state["lookups"]
        )
        self.state["report"] = {
            "date": today,
            "sources": report.sources,
            "lookups": report.lookups,
            "new": len(report.new),
            "pending": report.pending,
        }
        return report

    # the page ----------------------------------------------------------------

    def current(self, where: str, sighting: dict[str, Any]) -> bool:
        return sighting["date"] == self.state["runs"].get(where)

    def site_record(self, product: dict[str, Any]) -> dict[str, Any]:
        sightings = product["sightings"]
        live = {w: s for w, s in sightings.items() if self.current(w, s)}
        markets = sorted({m for s in live.values() for m in s["markets"]})
        urls = [s["url"] for s in sightings.values() if s.get("url")]
        record = {
            key: value
            for key, value in product.items()
            if key not in {"sightings", "title", "category", "gtin"}
        }
        return record | {
            "available": bool(live),
            "markets": markets,
            "sources": sorted({w.split(":")[0] for w in sightings}),
            "url": urls[0] if urls else icecat.product_url(product["icecat_id"]),
        }

    def site(self) -> dict[str, Any]:
        """The page's data: regional variants of one model folded into one row.

        Icecat files a model once per regional SKU (the same DCP-T430W sold in
        Europe and in Mexico): they share a brand and a name, and only their
        markets differ.
        """
        groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for product in self.products.values():
            record = self.site_record(product)
            groups[(record["brand"].lower(), record["name"].lower())].append(record)
        printers = []
        for variants in groups.values():
            variants.sort(key=lambda r: (not r["available"], -len(r["markets"])))
            merged = dict(variants[0])
            merged["markets"] = sorted({m for v in variants for m in v["markets"]})
            merged["available"] = any(v["available"] for v in variants)
            merged["first_seen"] = min(v["first_seen"] for v in variants)
            merged["sources"] = sorted({s for v in variants for s in v["sources"]})
            merged["variants"] = len(variants)
            printers.append(merged)
        printers.sort(key=lambda r: (r["brand"], r["name"]))
        return {
            "updated": self.state.get("report", {}).get("date"),
            "started": self.state["started"],
            "report": self.state.get("report", {}),
            "printers": printers,
        }
