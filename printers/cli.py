"""``printers update`` refreshes the catalogue; ``printers build`` writes the site."""

import argparse
import hashlib
import json
import logging
import shutil
from pathlib import Path

from .catalog import Catalog
from .fetch import Fetcher
from .sources import KNOWN_WALLS, all_sources

ROOT = Path(__file__).resolve().parent.parent
#: Icecat lookups per run: a first run spreads over a few weeks, then the
#: weekly increment is far below it
MAX_LOOKUPS = 4000


def update(args: argparse.Namespace) -> None:
    catalog = Catalog(args.data)
    sources = [s for s in all_sources() if not args.source or s.NAME in args.source]
    report = catalog.update(Fetcher(), sources, args.max_lookups)
    catalog.save()
    print(f"{report.lookups} Icecat lookups, {len(report.new)} new printers")
    print(f"{report.pending} candidates left for the next run")
    for where, outcome in report.sources.items():
        print(f"  {where}: {outcome['status']} {outcome.get('found', '')}")


def build(args: argparse.Namespace) -> None:
    catalog = Catalog(args.data)
    out: Path = args.out
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "site", out)
    site = catalog.site()
    # the page reads a missing field as "no": dropping them halves the download
    site["printers"] = [
        {k: v for k, v in record.items() if v not in (False, None, "", [])}
        for record in site["printers"]
    ]
    payload = json.dumps(site, ensure_ascii=False, separators=(",", ":"))
    (out / "printers.json").write_text(payload, encoding="utf-8")
    bust_caches(out)
    print(f"site written to {out}")


def bust_caches(out: Path) -> None:
    """Point the page at its files by content hash.

    GitHub Pages lets browsers keep a file for ten minutes; a fresh deploy
    would otherwise show the new page with the old script or data.
    """
    versions: dict[str, str] = {}
    # app.js names the data file: it is rewritten before its own hash is taken
    for name, referrer in (
        ("printers.json", "app.js"),
        ("style.css", "index.html"),
        ("printers.json", "index.html"),
        ("app.js", "index.html"),
    ):
        if name not in versions:
            content = (out / name).read_bytes()
            versions[name] = hashlib.sha256(content).hexdigest()[:10]
        path = out / referrer
        text = path.read_text(encoding="utf-8")
        text = text.replace(f'"{name}"', f'"{name}?v={versions[name]}"')
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
