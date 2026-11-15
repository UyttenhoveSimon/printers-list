<div align="center">

# 🖨️ Printers List

**Every home and small-office printer on sale, on one page you can filter: two-sided printing, two-sided scanning, laser or inkjet, colour, fax, Wi-Fi, speed, year and the country it is sold in. Refreshed every week.**

[![Tests](https://github.com/UyttenhoveSimon/printers-list/actions/workflows/tests.yml/badge.svg)](https://github.com/UyttenhoveSimon/printers-list/actions/workflows/tests.yml)
[![Update](https://github.com/UyttenhoveSimon/printers-list/actions/workflows/update.yml/badge.svg)](https://github.com/UyttenhoveSimon/printers-list/actions/workflows/update.yml)
![Python](https://img.shields.io/badge/python-3.15-blue?logo=python&logoColor=white)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
<br>
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![ty](https://img.shields.io/badge/types-ty-261230)](https://github.com/astral-sh/ty)
[![prek](https://img.shields.io/badge/hooks-prek-orange)](https://github.com/j178/prek)

**[Open the list →](https://uyttenhovesimon.github.io/printers-list/)**

[Features](#-features) •
[How it works](#-how-it-works) •
[Sources](#-sources) •
[Run it yourself](#-run-it-yourself) •
[Development](#-development)

</div>

---

I could not find an easy way to find a printer with the specs I wanted, so I built my own list.

## ✨ Features

- 🔁 **Two-sided printing and scanning**: automatic duplex only. A "manual duplex" that asks you to turn the stack over does not count.
- 🧰 **Every spec is a filter** in the side panel: technology (laser, LED, inkjet, ink tank), colour, scan, copy, fax, ADF, borderless, A3, paper capacity, connectivity (Wi-Fi, Wi-Fi Direct, Ethernet, USB, AirPrint, Mopria, NFC, Bluetooth), display, speed, time to first page, duty cycle, resolution, size, weight, noise, power, release year, country and brand.
- 🖋️ **Cartridges**: the ink, toner and drums each printer takes, with the starter cartridge yield.
- 🌍 **Where it is sold**: the countries each model is marketed in, with country names in your language.
- ✅ **Cross-checked**: printers whose maker's site states the same specs as Icecat are marked as confirmed, and any disagreement is shown.
- ⚖️ **Comparator**: tick up to four printers and compare them side by side, all specs or only the differences.
- 🗣️ **International**: English, French, Dutch and German, picked from your browser.
- 📄 **Paginated**: 48 printers a page, so thousands of models stay fast.
- 🆕 **New this week**: models first seen in the latest weekly run.
- 🔗 **Shareable**: the filters, page and comparison live in the URL.
- 🚀 **Fast**: a static page with no framework or build step. The list loads one compact file, and the cartridges load only when you open a printer.

## ⚙️ How it works

```
 Monday 05:00 UTC, GitHub Actions
 ┌──────────────────────────┐    ┌───────────────────────┐    ┌─────────────────────┐
 │ sources: what is on sale │ ─▶ │ Icecat: specifications │ ─▶ │ data/*.json, commit │
 │ Icecat index, Epson, ... │    │ only for new models    │    │ build, GitHub Pages │
 └──────────────────────────┘    └───────────────────────┘    └─────────────────────┘
```

1. **Discover.** Each source lists the printers it sells, per market. Manufacturer sites also give their own spec sheet.
2. **Look up.** A model not seen before is looked up in [Open Icecat](https://icecat.biz) and its data sheet is mapped to the filters. What Icecat answered is remembered in `data/state.json`, so each week only the **delta** is fetched. A code Icecat does not know is asked again after a month.
3. **Merge.** `data/products.json` keeps one record per product with its sightings, meaning which source listed it, where and when. When a maker's page and Icecat disagree on a field such as two-sided printing, fax or speed, the record notes it. A brand Icecat lacks (Lexmark) gets its record from its own pages. Regional SKUs of one model (the same DCP-T430W in Europe and in Mexico) are folded into a single row.
4. **Publish.** `printers build` writes the page, a compact `printers.json` for the list and a `details.json` for cartridges and checks, each versioned by content hash. GitHub Pages serves them.

A printer stays **on sale** while one of its sources still lists it. When a source is down, walled or suddenly returns nothing, its printers keep their status instead of disappearing, and the run reports the problem.

## 🔎 Sources

| Source | What it gives | Status |
| --- | --- | --- |
| Icecat on-market index | Every printer from the brands that sponsor Open Icecat (HP, Canon, Brother, Epson, Kyocera, Xerox...) with its countries | ✅ needs an Icecat account |
| epson.co.uk, .be, .nl, .fr, .de, .it, .es | Epson's catalogue per country, with its spec sheets to cross-check Icecat | ✅ |
| lexmark.com (GB, BE, NL, FR, DE, CH, IT, ES, US) | Lexmark's printers and full specs; Lexmark is not in Open Icecat | ✅ |
| hp.com (GB, FR, DE) | HP's shop list | ⛔ refuses non-browser clients |
| brother.* (GB, BE, FR, DE) | Brother's support sitemap | ⛔ 403 |
| Canon, Galaxus, Digitec | | ⛔ 403 |
| Amazon | | ⛔ forbids automated access |
| Kyocera | Pages answer, but list no product code Icecat knows | 🔜 |

Anti-bot walls are **reported, never bypassed**. The fetcher says who it is in its user agent, pauses between requests and gives up on a site that refuses it. The weekly [update](.github/workflows/update.yml) ends with `printers check`, which fails the run when a source that used to answer stops, so a broken site is reported rather than silently shrinking the list.

## 🚀 Run it yourself

With [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/UyttenhoveSimon/printers-list
cd printers-list
uv sync

# an Icecat account (free, icecat.biz) for the index; without it only the
# manufacturer sites are read and the Icecat demo account fills the specs
cat > .env <<'EOF'
ICECAT_USER=your-login
ICECAT_PASSWORD=your-password
ICECAT_KEY=your-api-access-token   # optional
EOF
set -a; source .env; set +a

uv run printers update            # refresh data/ (only new models are looked up)
uv run printers build             # write the site to _site/
uv run printers check             # list each source's status; fails if one broke
python -m http.server -d _site    # open http://localhost:8000
```

`printers update --source epson` reads a single source. `--max-lookups 500` caps the Icecat calls of a run, and the next run continues where it stopped.

### Deploying your own copy

1. Fork the repository.
2. Add the `ICECAT_USER`, `ICECAT_PASSWORD` and, optionally, `ICECAT_KEY` repository secrets.
3. Under **Settings → Pages**, set the source to **GitHub Actions**.
4. Run the **update and deploy** workflow once by hand.

## 🧑‍💻 Development

```bash
uv sync                          # everything, dev tools included
uv run python -m rustwright install chromium   # once, for the page tests
uv run pytest                    # offline tests: trimmed real captures, and the page in Chromium
uv run pytest -m live            # against the real sites (network)
uv run prek install              # run the hooks on every commit
uv run prek run --all-files      # what CI runs: ruff, ty, uv-lock, whitespace
```

```
printers/
  fetch.py           polite HTTP, wall detection
  icecat.py          Icecat lookup and data-sheet mapping
  catalog.py         merge, availability, the page's data
  cli.py             printers update | build | check
  specs.py           the record's fields, number readers, cross-check
  sources/           icecat_index, epson, lexmark, hp, brother; pages (shared)
site/                index.html, app.js (DOM), logic.js (filters, URL, pages), i18n.js
data/                products.json, state.json (rewritten weekly)
tests/fixtures/      real captures, trimmed
```

**Adding a source:** write a module in `printers/sources/` with `NAME`, `MARKETS` and `discover(fetcher, market, cache)` returning `Candidate`s. A candidate is found by brand and code, EAN or Icecat id. Register the module in `all_sources()`, then add a trimmed capture to `tests/fixtures/` and a test.

## 📄 License

[Apache 2.0](LICENSE). Product data and images come from [Open Icecat](https://icecat.biz) under its open content licence.
