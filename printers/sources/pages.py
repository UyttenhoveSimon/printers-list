"""Manufacturer sites that publish a sitemap and a spec page per printer.

Epson and Lexmark work alike: the pages share a numeric product id across
countries, only their paths are translated. One *reference* market, whose
English paths tell printers from scanners and supplies, has its new pages
read (a few hundred per run at most) and the result is cached by product id:
the product code and the specifications. The other markets only need their
sitemap: a product id seen there is that printer, sold there.
"""

import re
from collections.abc import Callable
from typing import Any

from ..fetch import Fetcher, FetchError
from . import Candidate

LOC = re.compile(r"<loc>([^<]+)</loc>")
#: product pages read per run at most, so a first run stays reasonable
MAX_PAGES = 400

#: html -> (product code, specifications), or None when the page is no printer
ReadPage = Callable[[str, str], tuple[str, dict[str, Any]] | None]


def locs(sitemap: str) -> list[str]:
    return [url.replace("&amp;", "&") for url in LOC.findall(sitemap)]


def discover(
    fetcher: Fetcher,
    *,
    name: str,
    brand: str,
    market: str,
    reference: bool,
    sitemap: str,
    printer_pages: Callable[[str], dict[str, str]],
    product_id: re.Pattern[str],
    read_page: ReadPage,
    cache: dict[str, Any],
) -> list[Candidate]:
    """Candidates of one market; ``reference`` reads and caches new pages."""
    if not reference:
        return known(sitemap, name, brand, market, product_id, cache)
    found: dict[str, Candidate] = {}
    budget = MAX_PAGES
    for page_id, url in printer_pages(sitemap).items():
        entry: Any = cache.get(page_id)
        if not isinstance(entry, dict):
            # an older cache kept the code alone: read the page again
            if budget == 0:
                continue
            budget -= 1
            try:
                read = read_page(fetcher.text(url), url)
            except FetchError:
                continue
            fresh: dict[str, Any] = {"code": read[0], "record": read[1]} if read else {}
            entry = cache[page_id] = fresh | {"code": fresh.get("code", "")}
        code: str = entry["code"]
        record: dict[str, Any] | None = entry.get("record")
        if code:
            found.setdefault(
                code,
                Candidate(name, brand, code, url=url, markets=(market,), record=record),
            )
    return list(found.values())


def known(
    sitemap: str,
    name: str,
    brand: str,
    market: str,
    product_id: re.Pattern[str],
    cache: dict[str, Any],
) -> list[Candidate]:
    """Printers of another market, matched by product id to the reference one."""
    found: dict[str, Candidate] = {}
    for url in locs(sitemap):
        match = product_id.search(url)
        entry = cache.get(match["id"]) if match else None
        if isinstance(entry, dict) and entry["code"]:
            found.setdefault(
                entry["code"],
                Candidate(
                    name,
                    brand,
                    entry["code"],
                    url=url,
                    markets=(market,),
                    record=entry.get("record"),
                ),
            )
    return list(found.values())


def clean(text: str) -> str:
    """Visible text of an html fragment, on one line."""
    text = re.sub(r"<[^>]+>", " ", text)
    for entity, char in (("&amp;", "&"), ("&#43;", "+"), ("&lt;", "<"), ("&lrm;", "")):
        text = text.replace(entity, char)
    return re.sub(r"\s+", " ", text).strip()


def compact(record: dict[str, Any]) -> dict[str, Any]:
    """Drop what the page did not say: an unknown is not a "no"."""
    return {key: value for key, value in record.items() if value is not None}
