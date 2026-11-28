"""What search engines and language models read without running the script.

The list itself is empty until the script has loaded ``printers.json``.

``printers build`` adds a canonical link, Open Graph tags, structured data and
links to the brand pages to ``index.html``; one static page per brand listing
every model, so each model name is in plain HTML; ``sitemap.xml``; and
``llms.txt``, which points language models at the JSON. The brand pages are
English only: they are for crawlers, the list is where people go.
"""

import json
import re
from collections import defaultdict
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote

SITE_URL = "https://uyttenhovesimon.github.io/printers-list/"
REPO_URL = "https://github.com/UyttenhoveSimon/printers-list"
NAME = "Printers List"
DESCRIPTION = (
    "Every home and small-office printer on sale, filterable by two-sided "
    "printing and scanning, technology, functions, connectivity, speed, size, "
    "year and country, with their cartridges. Refreshed every week."
)
#: brands in the catalogue that are Icecat's test entries, not makers
NOT_BRANDS = re.compile(r"test", re.IGNORECASE)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def brands(printers: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_brand: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for printer in printers:
        if printer.get("brand") and not NOT_BRANDS.search(printer["brand"]):
            by_brand[printer["brand"]].append(printer)
    return dict(sorted(by_brand.items(), key=lambda item: item[0].lower()))


def functions(p: dict[str, Any]) -> str:
    names = ["print"] + [f for f in ("scan", "copy", "fax") if p.get(f)]
    return ", ".join(names)


def two_sided(p: dict[str, Any]) -> str:
    sides = [
        w for w, k in (("print", "duplex_print"), ("scan", "duplex_scan")) if p.get(k)
    ]
    return ", ".join(sides) or "no"


def connectivity(p: dict[str, Any]) -> str:
    links = (
        ("Wi-Fi", "wifi"),
        ("Ethernet", "ethernet"),
        ("USB", "usb"),
        ("AirPrint", "airprint"),
    )
    return ", ".join(name for name, key in links if p.get(key))


def speed(p: dict[str, Any]) -> str:
    ppm = [
        f"{p[k]} ppm {w}"
        for w, k in (("black", "ppm_black"), ("colour", "ppm_color"))
        if p.get(k)
    ]
    return ", ".join(ppm)


def row(p: dict[str, Any]) -> str:
    link = f"../#q={quote(p['name'])}&amp;year=all"
    cells = [
        f'<th scope="row"><a href="{link}">{escape(p["name"])}</a></th>',
        escape(p.get("technology") or ""),
        "colour" if p.get("color") else "mono",
        functions(p),
        two_sided(p),
        escape(p.get("max_paper") or ""),
        speed(p),
        connectivity(p),
        escape(", ".join(p.get("markets", []))),
    ]
    return (
        "<tr>"
        + "".join(c if c.startswith("<th") else f"<td>{c}</td>" for c in cells)
        + "</tr>"
    )


COLUMNS = (
    "Model",
    "Technology",
    "Colour",
    "Functions",
    "Two-sided",
    "Max paper",
    "Speed",
    "Connectivity",
    "On sale in",
)


def page(title: str, description: str, canonical: str, body: str, ld: dict) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<meta name="description" content="{escape(description, quote=True)}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:title" content="{escape(title, quote=True)}">
<meta property="og:description" content="{escape(description, quote=True)}">
<meta property="og:url" content="{canonical}">
<link rel="stylesheet" href="../style.css">
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
</head>
<body>
{body}
</body>
</html>
"""


def brand_page(
    brand: str,
    printers: list[dict[str, Any]],
    by_brand: dict[str, list],
    updated: str | None,
) -> str:
    canonical = f"{SITE_URL}brands/{slug(brand)}.html"
    title = f"{brand} printers: every model and its specifications | {NAME}"
    description = (
        f"All {len(printers)} {brand} printers on sale: "
        "technology, colour, two-sided printing and scanning, paper size, speed, "
        "connectivity and the countries each model is sold in."
    )
    ld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": f"{brand} printers",
        "description": description,
        "url": canonical,
        "isPartOf": {"@type": "WebSite", "name": NAME, "url": SITE_URL},
        "about": {"@type": "Brand", "name": brand},
        "dateModified": updated,
    }
    rows = "\n".join(row(p) for p in printers)
    head = "".join(f'<th scope="col">{c}</th>' for c in COLUMNS)
    body = f"""<main class="wrap static">
<p><a href="../">&larr; {NAME}</a></p>
<h1>{escape(brand)} printers</h1>
<p>{escape(description)} Data from Open Icecat and the manufacturer's own site,
refreshed every week{f", last on {updated}" if updated else ""}. Open a model
in the <a href="../#brand={quote(brand)}&amp;year=all">interactive list</a>
to filter, compare and see its cartridges.</p>
<div class="table-scroll"><table class="specs listing">
<thead><tr>{head}</tr></thead>
<tbody>
{rows}
</tbody>
</table></div>
<p class="muted">Other brands: {brand_links(by_brand, "")}</p>
</main>"""
    return page(title, description, canonical, body, ld)


def brand_links(by_brand: dict[str, list], prefix: str) -> str:
    return ", ".join(
        f'<a href="{prefix}{slug(b)}.html">{escape(b)}</a> ({len(ps)})'
        for b, ps in by_brand.items()
    )


def website_ld(updated: str | None, total: int) -> dict:
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "name": NAME,
                "url": SITE_URL,
                "description": DESCRIPTION,
                "inLanguage": ["en", "fr", "nl", "de"],
            },
            {
                "@type": "Dataset",
                "name": "Home and small-office printer catalogue",
                "description": (
                    "Specifications, cartridges and countries of sale of "
                    f"{total} printers. {DESCRIPTION}"
                ),
                "url": SITE_URL,
                "license": f"{REPO_URL}/blob/main/LICENSE",
                "isAccessibleForFree": True,
                "dateModified": updated,
                "keywords": [
                    "printer",
                    "duplex scanning",
                    "multifunction printer",
                    "ink tank",
                    "laser printer",
                    "cartridges",
                ],
                "creator": {"@type": "Person", "name": "Simon Uyttenhove"},
                "distribution": [
                    {
                        "@type": "DataDownload",
                        "encodingFormat": "application/json",
                        "contentUrl": f"{SITE_URL}printers.json",
                    }
                ],
            },
        ],
    }


HEAD = """<link rel="canonical" href="{url}">
<meta property="og:type" content="website">
<meta property="og:title" content="{name}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{url}">
<meta name="twitter:card" content="summary">
<script type="application/ld+json">{ld}</script>
"""


def llms_txt(by_brand: dict[str, list], total: int, updated: str | None) -> str:
    brand_lines = "\n".join(
        f"- [{b} printers]({SITE_URL}brands/{slug(b)}.html): {len(ps)} models"
        for b, ps in by_brand.items()
    )
    return f"""# {NAME}

> {DESCRIPTION}

A catalogue of {total} home and small-office printers, last refreshed
{updated or "weekly"}. The page is a single-page app; its data is plain JSON.

## Data

- [printers.json]({SITE_URL}printers.json): every printer, one record each
  (brand, name, technology, color, scan, copy, fax, duplex_print, duplex_scan,
  adf, max_paper, ppm_black, ppm_color, connectivity flags, dimensions,
  markets as ISO country codes, available)
- [details.json]({SITE_URL}details.json): per printer id, its consumables
  (cartridges, yields) and which maker sites confirm the specifications

## Printers by brand

{brand_lines}

## Source

- [GitHub repository]({REPO_URL}): code, README and the committed catalogue
"""


def sitemap(by_brand: dict[str, list], updated: str | None) -> str:
    urls = [SITE_URL] + [f"{SITE_URL}brands/{slug(b)}.html" for b in by_brand]
    lastmod = f"<lastmod>{updated}</lastmod>" if updated else ""
    entries = "\n".join(f"  <url><loc>{u}</loc>{lastmod}</url>" for u in urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{entries}\n</urlset>\n"
    )


def write(out: Path, site: dict[str, Any]) -> None:
    printers, updated = site["printers"], site.get("updated")
    by_brand = brands(printers)
    total = len(printers)

    index = out / "index.html"
    text = index.read_text(encoding="utf-8")
    head = HEAD.format(
        url=SITE_URL,
        name=NAME,
        description=escape(DESCRIPTION, quote=True),
        ld=json.dumps(website_ld(updated, total), ensure_ascii=False),
    )
    text = text.replace("</head>", head + "</head>", 1)
    text = text.replace(
        '<p id="brand-pages"></p>',
        f'<p id="brand-pages">{brand_links(by_brand, "brands/")}</p>',
        1,
    )
    index.write_text(text, encoding="utf-8")

    (out / "brands").mkdir(exist_ok=True)
    for brand, models in by_brand.items():
        (out / "brands" / f"{slug(brand)}.html").write_text(
            brand_page(brand, models, by_brand, updated), encoding="utf-8"
        )
    (out / "sitemap.xml").write_text(sitemap(by_brand, updated), encoding="utf-8")
    (out / "llms.txt").write_text(llms_txt(by_brand, total, updated), encoding="utf-8")
