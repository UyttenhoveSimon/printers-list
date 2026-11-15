# AGENTS.md

Guidance for AI coding agents (and humans in a hurry) working in this
repository. Read this first; the README is the user-facing documentation.

## What this is

A static page on GitHub Pages listing every home and small-office printer on
sale, filterable by every spec, with its cartridges and the countries it is
sold in. A weekly GitHub Actions run refreshes the catalogue in `data/` and
redeploys: <https://uyttenhovesimon.github.io/printers-list/>.

Python 3.15, managed with **uv**. No framework on the page: `site/` is plain
HTML, CSS and ES modules, with no build step beyond `printers build`.

## Commands

```bash
uv sync                                      # everything, dev tools included
uv run python -m rustwright install chromium # once: the page tests use it
uv run pytest                                # offline tests, page in Chromium (~2 min)
uv run pytest --cov                          # with coverage; CI requires >= 90 %
uv run pytest -m live                        # against the real sites (network)
uv run prek run --all-files                  # ruff, ty, uv-lock, whitespace: what CI runs
uv run ruff check --fix . && uv run ruff format .
uv run ty check

set -a; source .env; set +a                  # ICECAT_USER, ICECAT_PASSWORD, ICECAT_KEY
uv run printers update                       # refresh data/: only new models are looked up
uv run printers update --source epson        # one source
uv run printers build                        # write _site/
uv run printers check                        # each source's status; fails if one broke
python -m http.server -d _site               # http://localhost:8000
```

Use **prek**, never `pre-commit`: the project prefers Rust-based tools (uv,
ruff, ty, prek, rustwright). Run `uv run prek run --all-files` before every
commit; it only checks files git tracks, so `git add` new files first.

## Map

```
printers/
  cli.py            printers update | build | check; the lean list and details.json
  catalog.py        the merge: lookups cache, sightings, availability, checks, the page's data
  icecat.py         Icecat JSON lookup and data-sheet mapping, consumables
  specs.py          the record's fields, number readers, SCHEMA, cross-check rules
  fetch.py          polite HTTP: honest user agent, pauses, wall detection
  browser.py        the same through headless Chromium, for sites that want a browser
  sources/
    __init__.py     Candidate, the Source protocol, all_sources(), KNOWN_WALLS
    icecat_index.py on_market.index.xml.gz streamed: every printer on sale, its countries
    pages.py        shared reader for maker sites with a sitemap and per-model pages
    epson.py        Epson, 7 countries: SKU and spec sheet (cross-checks Icecat)
    lexmark.py      Lexmark, 9 countries: the record itself (not in Open Icecat)
    brother_support.py  support.brother.com spec pages: fills Brother's gaps
    hp_shop.py      HP's UK shop spec sheets, through browser.py: fills HP's gaps
    hp.py, brother.py  model lists; both refuse non-browser clients today
site/
  index.html        the shell; strings filled from i18n.js
  app.js            the DOM: panel, cards, pager, comparison, detail, sources table
  logic.js          no DOM: filters, matching, sorts, URL state, pages (unit-tested)
  i18n.js           English, French, Dutch, German; country names from Intl
data/
  products.json     one record per product, its sightings and checks (committed)
  state.json        Icecat answers per lookup, source caches, last run per source
tests/              offline; fixtures/ holds trimmed real captures
.github/workflows/  tests (push, PR); update (weekly: update, commit, deploy, check)
```

## How a run works

1. Each source's `discover(fetcher, market, cache)` returns `Candidate`s: a
   way to look the model up in Icecat (Icecat id, GTIN, or brand + code), the
   markets it was seen in, and optionally the maker's own specs (`record`).
2. `Catalog.update` looks up only what `needs_lookup` says: never asked, a
   miss older than 30 days, or a record with an older `SCHEMA`. Four workers,
   each with its own session and pause. It saves every 500 candidates.
3. A candidate is *placed*: resolved to a product, cross-checked against the
   maker's record, and given a sighting (`source:market`, date, countries).
4. `Catalog.enrich` then reads makers' support pages (`ENRICHERS`, Brother
   today) for printers whose `FIELDS` Icecat left empty, cached 90 days. A
   maker's page only ever fills an empty field (`fill`), never overwrites
   Icecat, and the record notes the source in `filled`.
5. A product is available when one of its sightings is as recent as the last
   successful read of that `source:market`. A source that fails or suddenly
   lists nothing leaves its products as they were.
6. `printers build` folds regional SKUs of one model into one row and writes
   `printers.json` (lean: false and empty fields dropped) and `details.json`
   (cartridges, checks), each named by content hash in the page.

## Rules of this repository

- **Walls are detected and reported.** `fetch.py` raises `BotWallError` on a
  wall, and the README's source table states each site's status. A walled site may
  be read through a real browser (rustwright's Chromium) when its data is
  needed; keep the pauses either way.
- **Never hit the network in unit tests.** Sources, Icecat and HTTP are
  replaced by fixtures or fakes. Live checks go in `tests/test_live.py`,
  marked `live`.
- **Fixtures are real captures, trimmed.** A payload written by hand must say
  it is synthetic in its test's docstring.
- **Bump `pages.PAGE_VERSION`** when a maker page reader takes new fields:
  cached pages are read again (`printers update --max-pages 1000` does it in
  one run).
- **Bump `specs.SCHEMA`** when a mapping in `icecat.py` or a maker reader
  changes the fields a record holds: the next run reads those records again
  (about 25 minutes for the whole catalogue).
- **Page logic goes in `logic.js`**, not `app.js`, and gets a test in
  `tests/test_site.py`. Every control must keep passing the "every control"
  tests, which compare the page's count with one computed in Python.
- **Every UI string goes through `i18n.js`** in all four languages;
  `missingKeys()` is tested to be empty.
- **Ruff runs with `select = ["ALL"]`.** An ignore needs a reason, in
  `pyproject.toml` or on the `noqa` line.
- **Comments say why, not what.**
- **Commits**: atomic, a short imperative subject and a body saying why,
  authored as the repository owner. No tool attribution in messages or PRs.
  The weekly workflow commits `data/` as `github-actions[bot]`, on purpose.

## Adding a source

1. Write `printers/sources/<name>.py` with `NAME`, `MARKETS` and
   `discover(fetcher, market, cache)`. A maker site with a sitemap and a page
   per model can reuse `pages.discover` (see `epson.py`, `lexmark.py`).
2. Return the maker's specs in `Candidate.record`, in the fields of
   `specs.py`, leaving out what the page does not state (`pages.compact`).
3. Register it in `all_sources()` and in the page's `SOURCES` list in
   `site/app.js`, with its strings in `i18n.js`.
4. Trim a real capture into `tests/fixtures/` and test the reader on it.
5. Add it to the README's source table.

## Pitfalls already met

- Epson's normal pages load Imperva's `_Incapsula_Resource` script: only its
  block page ("Incapsula incident ID") is a wall.
- HP has no online shop in Belgium: the product list URL answers with a PNG.
- Brother France files support pages under `/services-et-supports/`.
- Icecat's `On_Market` flag keeps some models from 2013 "on the market": the
  page defaults to the last ten years, by release date or else Icecat's
  `Date_Added`. Undated printers stay visible.
- Icecat relates compatible supplies from other brands; `own` tells them apart.
- Release dates are rare in Icecat (about one printer in five).
- Brother's spec pages cover a model family: a cell lists values per model
  group, and a row's label may name the models it applies to (the ADF row).
- Canon refuses honest clients on every regional site tried; HP's support
  site keeps its spec data behind paths its robots.txt disallows.
- Office copiers are classed (`specs.office_copier`) by range name, Icecat
  positioning, any A3 laser, or 50 kg+: any one sign.
- rustwright's `page.url` does not follow `history.replaceState`: tests read
  `location.hash`.
