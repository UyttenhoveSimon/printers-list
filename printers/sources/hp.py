"""HP: the online shop publishes a plain list of its product URLs.

A printer URL ends in its SKU, then a locale option the SKU is sold with:
``.../hp-color-laserjet-pro-3202dw-499r0f-b19``. Icecat files HP printers
under the bare SKU (``499R0F``). Markets without an HP online shop, Belgium
among them, answer with an image instead of the list.

hp.com leaves plain HTTP clients without an answer, so the list is read
through `browser.Browser`, like HP's shop pages.
"""

import re

from ..fetch import Reader
from . import Candidate

NAME = "hp.com"
LOCALES = {"GB": "gb-en", "FR": "fr-fr", "DE": "de-de"}
MARKETS = tuple(LOCALES)
#: hp.com answers only clients that behave like a browser
BROWSER = True
LIST_URL = "https://www.hp.com/{locale}/shop/media/facets_url/products_url_{suffix}.txt"
PRINTER_URL = re.compile(
    r"^https://www\.hp\.com/[a-z-]+/shop/products/printers/"
    r"[a-z0-9-]+?-(?P<sku>[a-z0-9]{6})(?:-[a-z0-9]{3})?/?$"
)


def discover(fetcher: Reader, market: str, cache: dict[str, str]) -> list[Candidate]:
    locale = LOCALES[market]
    body = fetcher.text(LIST_URL.format(locale=locale, suffix=locale.replace("-", "_")))
    return parse(body, market)


def parse(body: str, market: str) -> list[Candidate]:
    found: dict[str, Candidate] = {}
    for line in body.splitlines():
        url = line.strip()
        match = PRINTER_URL.match(url)
        if match:
            sku = match["sku"].upper()
            found.setdefault(
                sku, Candidate(NAME, "HP", sku, url=url, markets=(market,))
            )
    return list(found.values())
