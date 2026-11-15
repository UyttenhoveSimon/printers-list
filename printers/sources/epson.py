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
    return pages.discover(
        fetcher,
        name=NAME,
        brand="Epson",
        market=market,
        reference=market == REFERENCE,
        sitemap=fetcher.text(product_maps[0]),
        printer_pages=printer_pages,
        product_id=PRODUCT_ID,
        read_page=read_page,
        cache=cache,
    )


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
            "paper_input": number(spec.get("Paper Tray Capacity")),
            "weight_kg": decimal(spec.get("Product weight")),
        }
    )
