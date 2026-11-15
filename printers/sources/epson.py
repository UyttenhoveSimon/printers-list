"""Epson: the product sitemap lists every printer page, current and past.

A page URL carries a slug and a numeric product id, not the SKU Icecat knows
(``C11CL63409``); the SKU and the spec table are read from the UK page, once
per product id, and the other markets reuse them (see ``pages``).
Professional ranges (photo, large format, labels, point of sale, dot matrix)
are skipped by their URL path. The specifications are compared with Icecat's.
"""

import re
from collections import Counter
from typing import Any

from ..fetch import Fetcher, FetchError
from ..specs import decimal, number
from . import Candidate, pages
from .pages import clean, compact

NAME = "epson"
SITES = {
    "GB": "https://www.epson.co.uk",
    "BE": "https://www.epson.be",
    "NL": "https://www.epson.nl",
    "FR": "https://www.epson.fr",
    "DE": "https://www.epson.de",
    "IT": "https://www.epson.it",
    "ES": "https://www.epson.es",
}
#: the market whose English paths say which pages are printers; it runs first
REFERENCE = "GB"
MARKETS = tuple(SITES)
PRODUCT_ID = re.compile(r"/p/(?P<id>\d+)$")
PRINTER_PAGE = re.compile(
    r"/products/printers/(?P<range>[a-z0-9/-]+?)/[^/]+/p/(?P<id>\d+)$"
)
SKIPPED_RANGES = re.compile(
    r"prophoto|large-format|label|pos|dot-matrix|sublimation|industrial|photo-and-graphic"
)
#: the base SKU Icecat files; pages add a country suffix (C11CL63409B2)
SKU = re.compile(r"\b(C1[01]C[A-Z0-9]{6})[A-Z0-9]{0,3}\b")
#: where discover keeps the models each market lists, in the source's cache
MODELS = "models"
#: a model code in a URL slug, its hyphen kept: "WF-3920", "ET-2850", "L3351"
MODEL_SLUG = re.compile(
    r"(?<![A-Z0-9])(?:[A-Z]{1,3}-)?[A-Z]{0,2}\d{3,5}[A-Z0-9]*(?![A-Z0-9])"
)
#: width, depth and height
DIMENSIONS = 3
SPEC = re.compile(
    r'specification-heading">\s*([^<]+?)\s*</h5>\s*'
    r'<span class="technical-specifications__specification-value">(.*?)</span>',
    re.DOTALL,
)


def discover(fetcher: Fetcher, market: str, cache: dict[str, Any]) -> list[Candidate]:
    site = SITES[market]
    index = fetcher.text(f"{site}/sitemap.xml")
    product_maps = [url for url in pages.locs(index) if "/Product-" in url]
    if not product_maps:
        raise FetchError(f"{site}: no product sitemap in the index")
    sitemap = fetcher.text(product_maps[0])
    # the models Epson lists, whichever SKU its pages carry: Icecat may file
    # the model under a sibling SKU (C11CM01402 for the page's C11CM01401)
    cache.setdefault(MODELS, {})[market] = sorted(
        {model for url in printer_pages(sitemap).values() for model in models_in(url)}
    )
    return pages.discover(
        fetcher,
        name=NAME,
        brand="Epson",
        market=market,
        reference=market == REFERENCE,
        sitemap=sitemap,
        printer_pages=printer_pages,
        product_id=PRODUCT_ID,
        read_page=read_page,
        cache=cache,
    )


def models_in(url: str) -> set[str]:
    """Model codes in a page's URL: ".../workforce-pro-wf-3920-a4-.../p/56721"."""
    slug = url.rsplit("/p/", 1)[0].rsplit("/", 1)[-1].upper()
    return set(MODEL_SLUG.findall(slug))


def printer_pages(sitemap: str) -> dict[str, str]:
    """Product id -> page URL, for the home and office printer ranges."""
    found: dict[str, str] = {}
    for url in pages.locs(sitemap):
        match = PRINTER_PAGE.search(url)
        if match and not SKIPPED_RANGES.search(match["range"]):
            found.setdefault(match["id"], url)
    return found


def page_sku(html: str) -> str:
    """The SKU a page names most: related products are named once or twice."""
    counts = Counter(SKU.findall(html))
    return counts.most_common(1)[0][0] if counts else ""


def spec_table(html: str) -> dict[str, str]:
    return {heading: clean(value) for heading, value in SPEC.findall(html)}


def read_page(html: str, url: str) -> tuple[str, dict[str, Any]] | None:
    sku = page_sku(html)
    if not sku:
        return None
    return sku, specifications(spec_table(html), url)


def specifications(spec: dict[str, str], url: str) -> dict[str, Any]:
    """The fields Epson's table states, in catalogue terms; silence is unknown."""
    functions = spec.get("All-in-One Functions", "")
    interfaces = spec.get("Interfaces", "")
    duplex = spec.get("Duplex", "")
    colours = number(spec.get("Number of colours"))
    return compact(
        {
            "technology": "laser" if "/laser/" in url else "inkjet",
            "color": colours > 1 if colours else None,
            "duplex_print": duplex.startswith(("Yes", "Auto")) if duplex else None,
            "scan": "Scan" in functions if functions else None,
            "fax": "Fax" in functions if functions else None,
            "wifi": ("Wi-Fi" in interfaces or "Wireless" in interfaces)
            if interfaces
            else None,
            "ethernet": "Ethernet" in interfaces if interfaces else None,
            "ppm_iso": number(spec.get("Printing Speed ISO/IEC 24734")),
            "ppm_black": number(after_word(spec.get("Printing Speed"), "Monochrome")),
            "ppm_color": number(after_word(spec.get("Printing Speed"), "Colour")),
            "first_page_s": decimal(
                first(r"Monochrome\s*(\d+(?:\.\d+)?)", spec.get("First Page Out"))
            ),
            "paper_input": number(spec.get("Paper Tray Capacity")),
            "paper_output": number(spec.get("Output Tray Capacity")),
            "weight_kg": decimal(spec.get("Product weight")),
            "noise_db": decimal(
                first(r"(\d+(?:\.\d+)?)\s*dB\s*\(A\)", spec.get("Noise Level"))
            ),
            "print_dpi": number(spec.get("Printing Resolution")),
            "scan_dpi": number(spec.get("Optical Resolution")),
            # the first figure is printing or copying; sleep and ready follow
            "power_w": decimal(
                first(r"(\d+(?:\.\d+)?)\s*Watt", spec.get("Energy Use"))
            ),
            "max_paper": largest_paper(spec.get("Paper Formats")),
            **dimensions(spec.get("Product dimensions", "")),
        }
    )


def largest_paper(text: str | None) -> str | None:
    """The largest A size a printer takes: "A4 (21.0x29.7 cm), A5, A6" is A4."""
    # A3 to A6: "A2" in a list of formats is an envelope (HP's Spanish sheets)
    sizes = [int(n) for n in re.findall(r"\bA([3-6])\b", text or "")]
    return f"A{min(sizes)}" if sizes else None


def first(pattern: str, text: str | None) -> str | None:
    """The first group of the first match of ``pattern``, or None."""
    match = re.search(pattern, text or "")
    return match.group(1) if match else None


def after_word(text: str | None, word: str) -> str:
    """The figure before ``word``: "33 pages/min Monochrome, 15 pages/min Colour"."""
    match = re.search(rf"(\d+)\s*pages/min\s*{word}", text or "")
    return match.group(1) if match else ""


def dimensions(text: str) -> dict[str, float | None]:
    """Read "361 x 317 x 162 mm (Width x Depth x Height)" as catalogue fields."""
    found = (
        re.findall(r"\d+(?:\.\d+)?", text.split("mm", maxsplit=1)[0])
        if "mm" in text
        else []
    )
    if len(found) != DIMENSIONS:
        return {}
    width, depth, height = (float(n) for n in found)
    return {"width_mm": width, "depth_mm": depth, "height_mm": height}
