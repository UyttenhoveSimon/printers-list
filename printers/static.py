"""What search engines and language models read without running the script.

The list itself is empty until the script has loaded ``printers.json``.

``printers build`` adds a canonical link, Open Graph tags, structured data and
links to the brand pages to ``index.html``; one static page per brand listing
its models, and one per model with its specifications, cartridges and
countries, so a search for a model name can land on it; ``sitemap.xml``; and
``llms.txt``, which points language models at the JSON. These pages are
English only (labels from ``i18n.js``): they are for crawlers, the list is
where people go.
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
SITE = Path(__file__).resolve().parent.parent / "site"
#: English names of the markets: the page asks the browser, Python has no list
COUNTRIES = {
    "AE": "United Arab Emirates", "AF": "Afghanistan", "AM": "Armenia",
    "AR": "Argentina", "AS": "American Samoa", "AT": "Austria", "AU": "Australia",
    "BA": "Bosnia and Herzegovina", "BE": "Belgium", "BG": "Bulgaria",
    "BO": "Bolivia", "BR": "Brazil", "BS": "Bahamas", "BY": "Belarus",
    "CA": "Canada", "CH": "Switzerland", "CL": "Chile", "CN": "China",
    "CO": "Colombia", "CY": "Cyprus", "CZ": "Czechia", "DE": "Germany",
    "DK": "Denmark", "DZ": "Algeria", "EE": "Estonia", "EG": "Egypt",
    "ES": "Spain", "FI": "Finland", "FR": "France", "GB": "United Kingdom",
    "GR": "Greece", "HK": "Hong Kong", "HR": "Croatia", "HU": "Hungary",
    "IE": "Ireland", "IN": "India", "IS": "Iceland", "IT": "Italy",
    "JM": "Jamaica", "JP": "Japan", "KW": "Kuwait", "KZ": "Kazakhstan",
    "LK": "Sri Lanka", "LT": "Lithuania", "LU": "Luxembourg", "LV": "Latvia",
    "MX": "Mexico", "MY": "Malaysia", "NL": "Netherlands", "NO": "Norway",
    "NZ": "New Zealand", "PA": "Panama", "PE": "Peru", "PH": "Philippines",
    "PL": "Poland", "PR": "Puerto Rico", "PT": "Portugal", "RE": "Réunion",
    "RO": "Romania", "RU": "Russia", "SE": "Sweden", "SG": "Singapore",
    "SI": "Slovenia", "SK": "Slovakia", "TH": "Thailand", "TR": "Türkiye",
    "UA": "Ukraine", "US": "United States", "VI": "U.S. Virgin Islands",
    "ZA": "South Africa",
}  # fmt: skip


def english_labels() -> dict[str, str]:
    """The page's English strings, so a spec reads the same on both."""
    text = (SITE / "i18n.js").read_text(encoding="utf-8")
    english = text[text.index("  en: {") : text.index("  fr: {")]
    pairs = re.finditer(r'^    (\w+): ("(?:[^"\\]|\\.)*"),?$', english, re.MULTILINE)
    return {m.group(1): json.loads(m.group(2)) for m in pairs}


def spec_rows() -> list[str]:
    """The detail view's rows, in its order (``SPEC_ROWS`` in logic.js)."""
    text = (SITE / "logic.js").read_text(encoding="utf-8")
    block = re.search(r"SPEC_ROWS = \[(.*?)\];", text, re.DOTALL)
    if not block:
        msg = "SPEC_ROWS not found in logic.js"
        raise ValueError(msg)
    return re.findall(r'"(\w+)"', block.group(1))


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


def row(p: dict[str, Any], paths: dict[str, str]) -> str:
    link = f"../{paths[p['id']]}"
    cells = [
        f'<th scope="row"><a href="{link}">{escape(p["name"])}</a></th>',
        escape(p.get("technology") or ""),
        "colour" if p.get("color") else "mono",
        functions(p),
        two_sided(p),
        escape(p.get("max_paper") or ""),
        speed(p),
        connectivity(p),
        escape(", ".join(p.get("markets") or [])),
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


def page(
    title: str,
    description: str,
    canonical: str,
    body: str,
    ld: dict,
    image: str | None = None,
) -> str:
    og_image = (
        f'<meta property="og:image" content="{escape(image, quote=True)}">\n'
        if image
        else ""
    )
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
{og_image}<link rel="stylesheet" href="../style.css">
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
    paths: dict[str, str],
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
    rows = "\n".join(row(p, paths) for p in printers)
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
<meta property="og:image" content="{url}preview.png">
<meta name="twitter:card" content="summary_large_image">
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


#: supply codes in a model page's description; the page lists them all
SUPPLIES_SHOWN = 5


def model_paths(by_brand: dict[str, list]) -> dict[str, str]:
    """Each printer's page, named by its name: the name is what people search."""
    paths: dict[str, str] = {}
    taken: set[str] = set()
    for models in by_brand.values():
        for p in models:
            name = slug(p["name"]) or p["id"]
            if name in taken:
                name = f"{name}-{p['id']}"
            taken.add(name)
            paths[p["id"]] = f"models/{name}.html"
    return paths


def number(value: float) -> str:
    return f"{value:g}" if isinstance(value, float) else str(value)


def spec_value(key: str, value: object, labels: dict[str, str]) -> str:
    if key == "color":
        return "Colour" if value else "Mono"
    if key == "technology":
        return labels.get(value, str(value).capitalize())
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return number(value) if isinstance(value, (int, float)) else str(value)


def supply_line(c: dict[str, Any], labels: dict[str, str]) -> str:
    kind = labels.get(f"kind_{c.get('kind')}", "")
    parts = [
        f"<strong>{escape(c.get('code') or '')}</strong>",
        escape(c.get("name") or ""),
    ]
    return f"<li>{escape(kind)}: " + " · ".join(p for p in parts if p) + "</li>"


def summary(p: dict[str, Any]) -> str:
    """One sentence a search result can quote."""
    kind = "multifunction printer" if p.get("scan") or p.get("copy") else "printer"
    tech = {"laser": "laser", "inkjet": "inkjet"}.get(p.get("technology") or "", "")
    if p.get("ink_tank"):
        tech = "ink tank"
    traits = [t for t in (("colour" if p.get("color") else "mono"), tech) if t]
    bits = []
    if p.get("duplex_print"):
        bits.append("two-sided printing")
    if p.get("duplex_scan"):
        bits.append("two-sided scanning")
    if p.get("ppm_black"):
        bits.append(f"{number(p['ppm_black'])} pages a minute")
    if p.get("max_paper"):
        bits.append(f"paper up to {p['max_paper']}")
    links = [n for n, k in (("Wi-Fi", "wifi"), ("Ethernet", "ethernet")) if p.get(k)]
    if links:
        bits.append(" and ".join(links))
    with_ = f" with {', '.join(bits)}" if bits else ""
    model = f"{p['brand']} {p['code']}" if p.get("code") else p["name"]
    return f"The {model} is a {' '.join(traits)} {kind}{with_}."


def sold_in(countries: list[str]) -> str:
    if not countries:
        return ""
    if len(countries) == 1:
        return f" Sold in {countries[0]}."
    if len(countries) <= COUNTRIES_NAMED:
        return f" Sold in {', '.join(countries[:-1])} and {countries[-1]}."
    return f" Sold in {len(countries)} countries."


#: countries named in a description; more are counted
COUNTRIES_NAMED = 4


def model_page(
    p: dict[str, Any],
    detail: dict[str, Any],
    labels: dict[str, str],
    rows: list[str],
    path: str,
    updated: str | None,
) -> str:
    canonical = f"{SITE_URL}{path}"
    brand = p["brand"]
    countries = sorted(COUNTRIES.get(m, m) for m in p.get("markets") or [])
    own = [c for c in detail.get("consumables", []) if c.get("own") is not False]
    title = f"{p['name']}: specifications, cartridges and where it is sold"
    description = summary(p) + sold_in(countries)
    codes = list(dict.fromkeys(c["code"] for c in own if c.get("code")))
    if codes:
        shown = ", ".join(codes[:SUPPLIES_SHOWN])
        more = (
            f" and {len(codes) - SUPPLIES_SHOWN} more"
            if len(codes) > SUPPLIES_SHOWN
            else ""
        )
        description += f" Supplies: {shown}{more}."
    ld: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": p["name"],
        "brand": {"@type": "Brand", "name": brand},
        "mpn": p.get("code"),
        "category": "Printers",
        "description": summary(p),
        "url": canonical,
    }
    if p.get("image"):
        ld["image"] = p["image"]
    specs = "".join(
        f'<tr><th scope="row">{escape(labels.get(k, k))}</th>'
        f"<td>{escape(spec_value(k, p[k], labels))}</td></tr>"
        for k in rows
        if p.get(k) is not None
    )
    supplies = (
        "<ul>" + "".join(supply_line(c, labels) for c in own) + "</ul>"
        if own
        else f'<p class="muted">{escape(labels.get("supplies_none", ""))}</p>'
    )
    alt = escape(p["name"], quote=True)
    image = (
        f'<img src="{escape(p["image"], quote=True)}" alt="{alt}"'
        ' width="240" height="180" loading="lazy">'
        if p.get("image")
        else ""
    )
    links = [
        (
            f'<a href="../#q={quote(p.get("code") or p["name"])}&amp;year=all">'
            "Compare it with similar printers</a>"
        )
    ]
    if p.get("url"):
        url = escape(p["url"], quote=True)
        links.append(f'<a href="{url}" rel="nofollow">Data sheet</a>')
    crumbs = (
        f'<a href="../">{NAME}</a> &rsaquo; '
        f'<a href="../brands/{slug(brand)}.html">{escape(brand)} printers</a>'
    )
    body = f"""<main class="wrap static">
<p>{crumbs}</p>
<div class="detail-head">{image}<div>
<h1>{escape(p["name"])}</h1>
<p>{escape(description)}</p>
<p>{" · ".join(links)}</p>
</div></div>
<h2>{escape(labels.get("supplies", "Supplies"))}</h2>
{supplies}
<h2>{escape(labels.get("sold_in", "Sold in"))}</h2>
<p>{escape(", ".join(countries)) or "Unknown"}</p>
<h2>Specifications</h2>
<table class="specs">{specs}</table>
<p class="muted">Specifications from Open Icecat and the maker's site, checked
every week{f"; last on {updated}" if updated else ""}.</p>
</main>"""
    return page(title, description, canonical, body, ld, p.get("image"))


def sitemap(
    by_brand: dict[str, list], paths: dict[str, str], updated: str | None
) -> str:
    urls = (
        [SITE_URL]
        + [f"{SITE_URL}brands/{slug(b)}.html" for b in by_brand]
        + [f"{SITE_URL}{path}" for path in paths.values()]
    )
    lastmod = f"<lastmod>{updated}</lastmod>" if updated else ""
    entries = "\n".join(f"  <url><loc>{u}</loc>{lastmod}</url>" for u in urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{entries}\n</urlset>\n"
    )


def write(out: Path, site: dict[str, Any], details: dict[str, dict]) -> None:
    """Write the crawlers' files; ``site`` holds the full records, not the lean."""
    printers, updated = site["printers"], site.get("updated")
    by_brand = brands(printers)
    paths = model_paths(by_brand)
    labels, rows = english_labels(), spec_rows()
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
    (out / "models").mkdir(exist_ok=True)
    for brand, models in by_brand.items():
        (out / "brands" / f"{slug(brand)}.html").write_text(
            brand_page(brand, models, by_brand, paths, updated), encoding="utf-8"
        )
        for p in models:
            html = model_page(
                p, details.get(p["id"], {}), labels, rows, paths[p["id"]], updated
            )
            (out / paths[p["id"]]).write_text(html, encoding="utf-8")
    (out / "sitemap.xml").write_text(
        sitemap(by_brand, paths, updated), encoding="utf-8"
    )
    (out / "llms.txt").write_text(llms_txt(by_brand, total, updated), encoding="utf-8")
