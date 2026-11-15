"""Epson: the product sitemap lists every printer page, current and past.

A page URL carries a slug and a numeric product id, not the SKU Icecat knows
(``C11CL63409``); the SKU is read from the UK page itself, once per product
id, and remembered in the cache; the other markets reuse it. Professional
ranges (photo, large format, labels, point of sale, dot matrix) are skipped
by their URL path.
"""

import re
from collections import Counter

from ..fetch import Fetcher, FetchError
from . import Candidate

NAME = "epson"
SITES = {
    "GB": "https://www.epson.co.uk",
    "BE": "https://www.epson.be",
    "FR": "https://www.epson.fr",
    "DE": "https://www.epson.de",
}
#: the market whose English paths say which pages are printers; it runs first
REFERENCE = "GB"
MARKETS = tuple(SITES)
LOC = re.compile(r"<loc>([^<]+)</loc>")
PRODUCT_ID = re.compile(r"/p/(?P<id>\d+)$")
PRINTER_PAGE = re.compile(
    r"/products/printers/(?P<range>[a-z0-9/-]+?)/[^/]+/p/(?P<id>\d+)$"
)
SKIPPED_RANGES = re.compile(
    r"prophoto|large-format|label|pos|dot-matrix|sublimation|industrial|photo-and-graphic"
)
#: the base SKU Icecat files; pages add a country suffix (C11CL63409B2)
SKU = re.compile(r"\b(C1[01]C[A-Z0-9]{6})[A-Z0-9]{0,3}\b")
#: product pages read per run at most, so a first run stays reasonable
MAX_PAGES = 400


def discover(fetcher: Fetcher, market: str, cache: dict[str, str]) -> list[Candidate]:
    site = SITES[market]
    index = fetcher.text(f"{site}/sitemap.xml")
    product_maps = [url for url in LOC.findall(index) if "/Product-" in url]
    if not product_maps:
        raise FetchError(f"{site}: no product sitemap in the index")
    sitemap = fetcher.text(product_maps[0])
    if market != REFERENCE:
        return known_pages(sitemap, market, cache)
    pages = printer_pages(sitemap)
    found: dict[str, Candidate] = {}
    budget = MAX_PAGES
    for product_id, url in pages.items():
        if product_id not in cache:
            if budget == 0:
                continue
            budget -= 1
            try:
                cache[product_id] = page_sku(fetcher.text(url))
            except FetchError:
                continue
        sku = cache[product_id]
        if sku:
            found.setdefault(
                sku, Candidate(NAME, "Epson", sku, url=url, markets=(market,))
            )
    return list(found.values())


def known_pages(sitemap: str, market: str, cache: dict[str, str]) -> list[Candidate]:
    """Printers of another market, matched by product id to the reference one.

    The paths are translated (``/nl_BE/producten/printers/...``,
    ``/de_DE/produkte/drucker/...``) but the product ids are shared, so the
    reference market's SKUs carry over without reading the pages again.
    """
    found: dict[str, Candidate] = {}
    for url in LOC.findall(sitemap):
        match = PRODUCT_ID.search(url)
        sku = cache.get(match["id"], "") if match else ""
        if sku:
            found.setdefault(
                sku,
                Candidate(
                    NAME, "Epson", sku, url=url.replace("&amp;", "&"), markets=(market,)
                ),
            )
    return list(found.values())


def printer_pages(sitemap: str) -> dict[str, str]:
    """Product id -> page URL, for the home and office printer ranges."""
    pages: dict[str, str] = {}
    for url in LOC.findall(sitemap):
        match = PRINTER_PAGE.search(url)
        if match and not SKIPPED_RANGES.search(match["range"]):
            pages.setdefault(match["id"], url.replace("&amp;", "&"))
    return pages


def page_sku(html: str) -> str:
    """The SKU a page names most: related products are named once or twice."""
    counts = Counter(SKU.findall(html))
    return counts.most_common(1)[0][0] if counts else ""
