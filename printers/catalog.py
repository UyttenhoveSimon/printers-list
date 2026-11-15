"""The catalogue: what every source saw, merged into one record per product.

Two files under ``data/``, both rewritten by every run:

- ``products.json``: one record per product (its Icecat id, or
  ``source:code`` for a printer only its maker's site describes) with its
  specifications, its *sightings* (the ``source:market`` pairs that listed it
  and when) and its *checks* (the fields a maker's site states otherwise).
- ``state.json``: what Icecat answered for each lookup (so a code Icecat does
  not know is not asked again every week), the sources' own caches, and the
  date each ``source:market`` last answered.

A product is available when a sighting of it is as recent as the last
successful read of that ``source:market``. A source that is down for a week
therefore leaves its products as they were instead of retiring them all.
"""

import json
import logging
import re
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

from . import icecat
from .browser import Browser
from .fetch import BotWallError, Fetcher, FetchError, Reader
from .sources import Candidate, Source, brother_support, canon_uk, hp_shop, kyocera
from .specs import FILLABLE, SCHEMA, disagreements, office_copier, out_of_scope

logger = logging.getLogger(__name__)

#: how long a lookup that found nothing is trusted before Icecat is asked again
RETRY_AFTER = timedelta(days=30)
#: how long a record with empty fields is trusted: Icecat sheets start thin
#: and editors fill them in later
REFRESH_AFTER = timedelta(days=30)
#: candidates between two saves of the catalogue during a run
CHECKPOINT = 500
#: Icecat lookups in flight at once, each with its own courtesy pause
WORKERS = 4
#: makers' sites that fill the gaps Icecat leaves, by brand
ENRICHERS = {
    "Brother": brother_support,
    "HP": hp_shop,
    "Canon": canon_uk,
    "KYOCERA": kyocera,
}
#: how long a maker page read for its gaps is trusted
ENRICH_AGAIN_AFTER = timedelta(days=90)
#: maker pages read per run for gaps at most
ENRICH_PAGES = 400
#: brands Open Icecat does not carry: their makers' pages are the record
NOT_IN_OPEN_ICECAT = frozenset({"Lexmark"})


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

    def needs_lookup(self, candidate: Candidate) -> bool:
        """Whether Icecat must be asked about a candidate.

        It must when it never was, when a miss has gone stale, when the
        product was read under an older mapping (``schema``), or when its
        record still has empty fields a month on (``refreshing``).
        """
        if candidate.brand in NOT_IN_OPEN_ICECAT:
            return False
        known = self.state["lookups"].get(candidate.key)
        if known is None:
            return True
        product = self.products.get(str(known.get("id")))
        if not known.get("reason") and product is not None:
            return product.get("schema", 1) < SCHEMA or self.refreshing(candidate)
        if known.get("id") is not None:
            return False  # a product Icecat has, out of scope: it stays so
        return self.today - date.fromisoformat(known["checked"]) >= RETRY_AFTER

    def refreshing(self, candidate: Candidate) -> bool:
        """Whether a known record with gaps is due to be read again from Icecat.

        A field a maker's page filled counts too: Icecat may have it now,
        and Icecat's value is the one the page prefers.
        """
        known = self.state["lookups"].get(candidate.key) or {}
        product = self.products.get(str(known.get("id")))
        if product is None or known.get("reason"):
            return False
        if self.today - date.fromisoformat(known["checked"]) < REFRESH_AFTER:
            return False
        filled = product.get("filled", {})
        return any(product.get(f) is None or f in filled for f in FILLABLE)

    def lookup_all(self, candidates: list[Candidate]) -> dict[str, icecat.Lookup]:
        """Ask Icecat about several candidates at once, a few at a time.

        Each worker has its own session and keeps the courtesy pause between
        its own requests; a lookup that fails on the network is left for the
        next run.
        """
        local = threading.local()

        def one(candidate: Candidate) -> tuple[str, icecat.Lookup | None]:
            if not hasattr(local, "fetcher"):
                local.fetcher = Fetcher()
            try:
                return candidate.key, icecat.lookup(
                    local.fetcher,
                    icecat_id=candidate.icecat_id,
                    brand=candidate.brand,
                    code=candidate.code,
                    gtin=candidate.gtin,
                )
            except FetchError as error:
                logger.debug(f"{candidate.key}: {error}")
                return candidate.key, None

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            return {key: found for key, found in pool.map(one, candidates) if found}

    def resolve(
        self, candidate: Candidate, fresh: dict[str, icecat.Lookup]
    ) -> str | None:
        """The product id of a candidate in scope, or ``None``.

        It comes from this run's lookups or from the cache; ``None`` means out
        of scope, or not known yet.
        """
        result = fresh.get(candidate.key)
        if result is not None:
            record = result.record
            self.state["lookups"][candidate.key] = {
                "id": record["icecat_id"] if record else None,
                "reason": result.reason,
                "checked": self.today.isoformat(),
            }
            if record is None or result.reason:
                return None
            return self.store(str(record["icecat_id"]), record)
        known = self.state["lookups"].get(candidate.key)
        if known is None or known.get("reason"):
            return None
        product_id = str(known.get("id"))
        return product_id if product_id in self.products else None

    def store(self, product_id: str, record: dict[str, Any]) -> str:
        """Put a fresh record in, keeping what earlier runs learnt about it."""
        previous = self.products.get(product_id, {})
        kept = {"added": previous["added"]} if "added" in previous else {}
        self.products[product_id] = (
            record
            | kept
            | {
                "first_seen": previous.get("first_seen", self.today.isoformat()),
                "sightings": previous.get("sightings", {}),
                "checks": previous.get("checks", {}),
            }
        )
        return product_id

    def adopt(self, candidate: Candidate) -> str | None:
        """A printer Icecat lacks, described by its maker's own page."""
        record = candidate.record
        if not record or "name" not in record or out_of_scope(record):
            return None
        return self.store(f"{candidate.source}:{candidate.code}", record)

    def check(self, product_id: str, candidate: Candidate) -> None:
        """Compare the maker's page with Icecat, field by field."""
        if not candidate.record or not product_id.isdigit():
            return
        product = self.products[product_id]
        product.setdefault("checks", {})[candidate.source] = {
            "date": self.today.isoformat(),
            "differ": disagreements(product, candidate.record),
        }
        self.fill(product_id, candidate.source, candidate.record)

    def fill(self, product_id: str, source: str, record: dict[str, Any]) -> int:
        """Fill the fields Icecat left empty from a maker's page; return how many."""
        product = self.products[product_id]
        filled = 0
        for name in FILLABLE:
            if product.get(name) is None and record.get(name) is not None:
                product[name] = record[name]
                product.setdefault("filled", {})[name] = source
                filled += 1
        return filled

    def enrich(
        self, fetcher: Fetcher, report: Report, browser: Browser | None = None
    ) -> None:
        """Read the makers' own spec pages for printers Icecat left with gaps.

        A maker that refuses plain HTTP (``BROWSER``) is read through
        ``browser``, and skipped when the run has none.
        """
        for brand, enricher in ENRICHERS.items():
            if not getattr(enricher, "BROWSER", False):
                self.enrich_brand(brand, enricher, fetcher, report)
            elif browser is not None:
                self.enrich_brand(brand, enricher, browser, report)

    def enrich_brand(
        self, brand: str, enricher: ModuleType, reader: Reader, report: Report
    ) -> None:
        """One maker's pages, at most ``ENRICH_PAGES`` read, the rest cached."""
        cache = self.state["caches"].setdefault(enricher.NAME, {})
        budget, filled, failures = ENRICH_PAGES, 0, 0
        for product_id, product in self.products.items():
            key = gap_key(brand, enricher, product)
            if not key:
                continue
            # a maker whose site lists its pages says which printers it covers:
            # the others cost no page of the budget
            covers = getattr(enricher, "covers", None)
            try:
                if covers is not None and not covers(reader, product):
                    continue
            except FetchError as error:
                # its list of pages is unreadable: nothing to do this run
                report.sources[f"{enricher.NAME}:ALL"] = {
                    "status": "error",
                    "detail": str(error),
                }
                logger.warning(f"{enricher.NAME}: {error}")
                return
            entry: dict[str, Any] | None = cache.get(key)
            stale = (
                entry is None
                or self.today - date.fromisoformat(entry["checked"])
                >= ENRICH_AGAIN_AFTER
            )
            if stale:
                if budget <= 0:
                    continue
                budget -= 1
                try:
                    record = enricher.enrich(reader, product) or {}
                # a page laid out unexpectedly fails alone, not the whole run
                except (FetchError, ValueError) as error:
                    failures += 1
                    logger.debug(f"{enricher.NAME} {key}: {error}")
                    continue
                entry = cache[key] = {
                    "checked": self.today.isoformat(),
                    "record": record,
                }
            if self.fill(product_id, enricher.NAME, entry["record"]):
                filled += 1
        read = ENRICH_PAGES - budget
        status = "error" if read and failures == read else "ok"
        report.sources[f"{enricher.NAME}:ALL"] = {"status": status, "found": filled}
        self.state["runs"][f"{enricher.NAME}:ALL"] = self.today.isoformat()
        logger.info(f"{enricher.NAME}: {read} pages read, {filled} printers filled")

    # the run -----------------------------------------------------------------

    def update(
        self,
        fetcher: Fetcher,
        sources: list[Source],
        max_lookups: int,
        browser: Browser | None = None,
    ) -> Report:
        report = Report()
        known_before = set(self.products)
        found = self.discover(fetcher, sources, report)
        # new models come first: refreshes only take what they leave
        first = sum(
            1
            for candidates in found.values()
            for c in candidates
            if self.needs_lookup(c) and not self.refreshing(c)
        )
        budget, refreshes = max_lookups, max(max_lookups - first, 0)
        for where, candidates in found.items():
            # the source answered: what it lists now is what is on sale
            self.state["runs"][where] = self.today.isoformat()
            for start in range(0, len(candidates), CHECKPOINT):
                chunk = candidates[start : start + CHECKPOINT]
                asked = {c.key: c for c in chunk if self.needs_lookup(c)}
                new = [c for c in asked.values() if not self.refreshing(c)]
                again = [c for c in asked.values() if self.refreshing(c)]
                again = again[:refreshes]
                refreshes -= len(again)
                wanted = (new + again)[: max(budget, 0)]
                budget -= len(wanted)
                fresh = self.lookup_all(wanted) if wanted else {}
                for candidate in chunk:
                    self.place(where, candidate, fresh)
                # a first fill takes hours: a crash must not lose it all
                self.save()
                done = min(start + CHECKPOINT, len(candidates))
                logger.info(f"{where}: {done}/{len(candidates)} resolved")
        self.enrich(fetcher, report, browser)
        self.save()
        report.lookups = max_lookups - max(budget, 0)
        report.new = sorted(set(self.products) - known_before)
        report.pending = sum(
            1
            for candidates in found.values()
            for candidate in candidates
            if self.needs_lookup(candidate)
        )
        self.state["report"] = {
            "date": self.today.isoformat(),
            "sources": report.sources,
            "lookups": report.lookups,
            "new": len(report.new),
            "pending": report.pending,
        }
        return report

    def place(self, where: str, candidate: Candidate, fresh: dict) -> None:
        """Resolve one candidate and record where it was seen today."""
        product_id = self.resolve(candidate, fresh)
        if product_id is None and candidate.brand in NOT_IN_OPEN_ICECAT:
            product_id = self.adopt(candidate)
        elif product_id is not None:
            self.check(product_id, candidate)
        if product_id is None:
            return
        today = self.today.isoformat()
        product = self.products[product_id]
        if candidate.added and candidate.added < product.get("added", "9999"):
            product["added"] = candidate.added
        sightings = product["sightings"]
        previous = sightings.get(where)
        markets = set(candidate.markets)
        if previous and previous["date"] == today:
            # several regional SKUs of the source fold into one product
            markets |= set(previous["markets"])
        sightings[where] = {
            "date": today,
            "markets": sorted(markets),
            "url": (previous or {}).get("url") or candidate.url,
        }

    # the page ----------------------------------------------------------------

    def current(self, where: str, sighting: dict[str, Any]) -> bool:
        return sighting["date"] == self.state["runs"].get(where)

    def site_record(self, product_id: str, product: dict[str, Any]) -> dict[str, Any]:
        sightings = product["sightings"]
        live = {w: s for w, s in sightings.items() if self.current(w, s)}
        markets = sorted({m for s in live.values() for m in s["markets"]})
        urls = [s["url"] for w, s in sightings.items() if s.get("url")]
        checks = product.get("checks", {})
        record = {
            key: value
            for key, value in product.items()
            if key
            not in {
                "sightings",
                "checks",
                "title",
                "category",
                "gtin",
                "schema",
                "filled",
            }
        }
        icecat_id = product.get("icecat_id")
        return record | {
            "id": product_id,
            "available": bool(live),
            "markets": markets,
            "sources": sorted({w.split(":")[0] for w in sightings}),
            "url": urls[0]
            if urls
            else icecat.product_url(icecat_id)
            if icecat_id
            else "",
            "office": office_copier(product),
            "filled": product.get("filled", {}),
            # the makers' sites that state the same as Icecat on every field
            "confirmed": sorted(s for s, c in checks.items() if not c["differ"]),
            "differs": {s: c["differ"] for s, c in checks.items() if c["differ"]},
        }

    def site(self) -> dict[str, Any]:
        """The page's data: regional variants of one model folded into one row.

        Icecat files a model once per regional SKU (the same DCP-T430W sold in
        Europe and in Mexico): they share a brand and a name, and only their
        markets differ. HP's SKUs of one model differ only after a ``#`` (its
        localisation), whatever Icecat names them. A field one variant's sheet
        leaves empty is taken from another's.
        """
        records = [self.site_record(i, p) for i, p in self.products.items()]
        printers = [fold(variants) for variants in variant_groups(records)]
        printers.sort(key=lambda r: (r["brand"], r["name"]))
        return {
            "updated": self.state.get("report", {}).get("date"),
            "started": self.state["started"],
            "report": self.state.get("report", {}),
            "printers": printers,
        }


def gap_key(brand: str, enricher: ModuleType, product: dict[str, Any]) -> str:
    """What a maker's page for a printer with gaps is cached under, or ""."""
    if product.get("brand") != brand:
        return ""
    if all(product.get(f) is not None for f in enricher.FIELDS):
        return ""
    return enricher.key(product)


def variant_key(record: dict[str, Any]) -> str | None:
    """What HP's regional SKUs of one model share: the code before the ``#``."""
    code = record.get("code") or ""
    if record["brand"] == "HP" and "#" in code:
        return code.split("#")[0].upper()
    return None


#: the part of a code shared by a model's pack variants: Epson's C11CK77401BM
#: is the C11CK77401, the WF-M5399DW
BASE_CODE = {"Epson": re.compile(r"^(C1[01]C[A-Z0-9]{6})[A-Z0-9]{1,3}$")}
#: a model in a name: "WF-M5399DW", "ET-2850", "MFC-L3740CDW"
MODEL_IN_NAME = re.compile(r"\b[A-Z]{1,4}-?[A-Z]?\d{3,5}[A-Z]*\b")


def bare(record: dict[str, Any]) -> bool:
    """A sheet Icecat names after its code alone: "Epson C11CK77401BM printer"."""
    code = record.get("code") or ""
    return bool(code) and code in record["name"]


def base_code(record: dict[str, Any]) -> str:
    pattern = BASE_CODE.get(record["brand"])
    code = (record.get("code") or "").upper()
    match = pattern.match(code) if pattern else None
    return match.group(1) if match else code if pattern else ""


def bare_siblings(records: list[dict[str, Any]]) -> dict[int, int]:
    """Bare sheet -> a named record of its model, when its siblings agree.

    Siblings share the base code; a bare sheet joins them only when every
    named sibling names the same model, as old ranges reuse a base for two.
    """
    named: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)
    for i, record in enumerate(records):
        base = base_code(record)
        models = MODEL_IN_NAME.findall(record["name"].upper())
        if base and models and not bare(record):
            named[(record["brand"], base)].setdefault(models[0], i)
    joined = {}
    for i, record in enumerate(records):
        models = named.get((record["brand"], base_code(record)), {})
        if bare(record) and len(models) == 1:
            joined[i] = next(iter(models.values()))
    return joined


def same_model_keys(record: dict[str, Any]) -> list[tuple[str, ...]]:
    """What two records of one model can share; one match is enough."""
    brand = record["brand"].lower()
    keys = [("name", brand, record["name"].lower())]
    # Icecat names one model several ways: "Epson Expression XP-630",
    # "Epson Premium XP-630"; the model code says they are one
    models = MODEL_IN_NAME.findall(record["name"].upper())
    if models:
        keys.append(("model", brand, models[0]))
    if record["brand"] == "HP":
        keys.append(("hp", variant_key(record) or (record.get("code") or "").upper()))
    return keys


def variant_groups(records: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Records that are one model.

    They share a name, a model code in their names, HP's base code, or are a
    bare sheet whose siblings name one model.
    """
    parent = list(range(len(records)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    first: dict[tuple[str, ...], int] = {}
    for i, record in enumerate(records):
        keys = same_model_keys(record)
        for key in keys:
            if key in first:
                parent[root(i)] = root(first[key])
            else:
                first[key] = i
    for i, sibling in bare_siblings(records).items():
        parent[root(i)] = root(sibling)
    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for i, record in enumerate(records):
        groups[root(i)].append(record)
    return list(groups.values())


def fold(variants: list[dict[str, Any]]) -> dict[str, Any]:
    """One row for a model's variants: the most sold one, its gaps filled."""
    variants.sort(key=lambda r: (not r["available"], -len(r["markets"])))
    merged = dict(variants[0])
    merged["filled"] = dict(merged.get("filled") or {})
    for other in variants[1:]:
        for name, value in other.items():
            if merged.get(name) is None and value is not None:
                merged[name] = value
                if name in (other.get("filled") or {}):
                    merged["filled"][name] = other["filled"][name]
    # Icecat names a bare sheet after its code ("HP 58D77A multifunction
    # printer"): a variant with a real model name names the row
    named = [v for v in variants if (v.get("code") or "") not in v["name"]]
    if named:
        merged["name"] = named[0]["name"]
    merged["markets"] = sorted({m for v in variants for m in v["markets"]})
    merged["available"] = any(v["available"] for v in variants)
    # a sign of a copier on one variant's sheet holds for the model
    merged["office"] = any(v["office"] for v in variants)
    merged["first_seen"] = min(v["first_seen"] for v in variants)
    merged["sources"] = sorted({s for v in variants for s in v["sources"]})
    merged["confirmed"] = sorted({s for v in variants for s in v["confirmed"]})
    merged["variants"] = len(variants)
    return merged
