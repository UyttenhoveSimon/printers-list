"""``printers update`` refreshes the catalogue; ``printers build`` writes the site."""

import argparse
import hashlib
import json
import logging
import shutil
from pathlib import Path

from . import catalog as catalog_module
from .catalog import Catalog
from .fetch import Fetcher
from .sources import KNOWN_WALLS, all_sources, pages

ROOT = Path(__file__).resolve().parent.parent
#: Icecat lookups per run: a first run spreads over a few weeks, then the
#: weekly increment is far below it
MAX_LOOKUPS = 4000


def update(args: argparse.Namespace) -> None:
    if args.max_pages is not None:
        pages.MAX_PAGES = args.max_pages
        catalog_module.ENRICH_PAGES = args.max_pages
    catalog = Catalog(args.data)
    sources = [s for s in all_sources() if not args.source or s.NAME in args.source]
    report = catalog.update(Fetcher(), sources, args.max_lookups)
    catalog.save()
    print(f"{report.lookups} Icecat lookups, {len(report.new)} new printers")
    print(f"{report.pending} candidates left for the next run")
    for where, outcome in report.sources.items():
        print(f"  {where}: {outcome['status']} {outcome.get('found', '')}")


#: what the detail view and the comparison need, fetched only when opened
DETAIL_FIELDS = ("consumables", "supplies", "confirmed", "differs", "filled")
#: detail fields the list needs as well: the "confirmed" filter and badge
LIST_DETAIL_FIELDS = frozenset({"confirmed"})
#: sent although false: "mono" is a filter value, not an unknown
KEPT_FALSE = frozenset({"color"})


def lean(record: dict) -> dict:
    """The row of the list: no detail field, nothing false, null or empty.

    The page reads a missing flag as "no"; leaving them out halves the file.
    """
    return {
        key: value
        for key, value in record.items()
        if (key not in DETAIL_FIELDS or key in LIST_DETAIL_FIELDS)
        and (value not in (False, None, "", [], {}) or key in KEPT_FALSE)
    }


def build(args: argparse.Namespace) -> None:
    catalog = Catalog(args.data)
    out: Path = args.out
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "site", out)
    site = catalog.site()
    details = {
        record["id"]: {key: record[key] for key in DETAIL_FIELDS if record.get(key)}
        for record in site["printers"]
    }
    site["printers"] = [lean(record) for record in site["printers"]]
    for name, payload in (("printers.json", site), ("details.json", details)):
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        (out / name).write_text(text, encoding="utf-8")
    bust_caches(out)
    print(f"site written to {out}: {len(site['printers'])} printers")


#: each file and the files that name it, in an order where a file is
#: versioned only once every file it names has been
REFERENCES = (
    ("printers.json", ("app.js", "index.html")),
    ("details.json", ("app.js",)),
    ("i18n.js", ("app.js",)),
    ("logic.js", ("app.js",)),
    ("style.css", ("index.html",)),
    ("app.js", ("index.html",)),
)


def bust_caches(out: Path) -> None:
    """Point the page at its files by content hash.

    GitHub Pages lets browsers keep a file for ten minutes; a fresh deploy
    would otherwise show the new page with the old script or data. A script
    is hashed after its own references are rewritten, so a new data file
    gives the script that loads it a new name too.
    """
    for name, referrers in REFERENCES:
        version = hashlib.sha256((out / name).read_bytes()).hexdigest()[:10]
        for referrer in referrers:
            path = out / referrer
            text = path.read_text(encoding="utf-8")
            for quoted in (f'"{name}"', f'"./{name}"'):
                text = text.replace(quoted, f'{quoted[:-1]}?v={version}"')
            path.write_text(text, encoding="utf-8")


def check(args: argparse.Namespace) -> None:
    """Fail when a source that used to answer broke in the last run.

    This is the canary: the update itself never fails on a source, so that
    one broken site does not hold back the others.
    """
    catalog = Catalog(args.data)
    sources = catalog.state.get("report", {}).get("sources", {})
    broken = {
        where: outcome
        for where, outcome in sources.items()
        if outcome["status"] != "ok" and where.split(":")[0] not in KNOWN_WALLS
    }
    for where, outcome in sorted(sources.items()):
        mark = "FAIL" if where in broken else outcome["status"]
        print(
            f"{mark:>7}  {where}  {outcome.get('detail') or outcome.get('found', '')}"
        )
    if broken:
        raise SystemExit(f"{len(broken)} source(s) broke: {', '.join(sorted(broken))}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="printers")
    parser.add_argument("--data", type=Path, default=ROOT / "data")
    parser.add_argument("-v", "--verbose", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)

    update_parser = commands.add_parser("update", help="refresh the catalogue")
    update_parser.add_argument("--max-lookups", type=int, default=MAX_LOOKUPS)
    update_parser.add_argument(
        "--max-pages",
        type=int,
        help="maker pages read per source and run (default: a few hundred)",
    )
    update_parser.add_argument(
        "--source", action="append", help="only this source (repeatable)"
    )
    update_parser.set_defaults(run=update)

    build_parser = commands.add_parser("build", help="write the static site")
    build_parser.add_argument("--out", type=Path, default=ROOT / "_site")
    build_parser.set_defaults(run=build)

    check_parser = commands.add_parser("check", help="fail if a source broke")
    check_parser.set_defaults(run=check)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args.run(args)


if __name__ == "__main__":
    main()
