"""Icecat's index of the products on the market, filtered to printers.

``on_market.index.xml.gz`` (about 200 MB) lists every Open Icecat product
still sold, with the countries it is sold in and its EANs. It is streamed and
parsed as it arrives, so it never sits on disk or in memory whole. It needs
an Icecat account: ``ICECAT_USER`` and ``ICECAT_PASSWORD`` (the API token in
``ICECAT_KEY`` is refused here).
"""

import gzip
import os
from collections.abc import Iterable
from typing import IO

from defusedxml.ElementTree import iterparse

from ..fetch import Fetcher, FetchError
from ..icecat import PRINTER_CATIDS
from . import Candidate

NAME = "icecat"
#: the index is world-wide; the countries come with each product
MARKETS = ("ALL",)
INDEX_URL = "https://data.icecat.biz/export/freexml/EN/on_market.index.xml.gz"
#: Icecat's code for "sold everywhere", not a country
WORLDWIDE = "WW"
#: yyyymmdd at the start of the index's timestamps
DATE_DIGITS = 8


def credentials() -> tuple[str, str]:
    user = os.environ.get("ICECAT_USER", "")
    password = os.environ.get("ICECAT_PASSWORD", "")
    if not (user and password):
        raise FetchError("the Icecat index needs ICECAT_USER and ICECAT_PASSWORD")
    return user, password


def discover(fetcher: Fetcher, market: str, cache: dict[str, str]) -> list[Candidate]:
    response = fetcher.stream(INDEX_URL, credentials())
    with response, gzip.GzipFile(fileobj=response.raw) as index:
        return list(parse(index))


def iso_date(stamp: str) -> str:
    """``20250304000000`` -> ``2025-03-04``; anything else -> ``""``."""
    if len(stamp) < DATE_DIGITS or not stamp[:DATE_DIGITS].isdigit():
        return ""
    return f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}"


def parse(index: IO[bytes] | gzip.GzipFile) -> Iterable[Candidate]:
    for _, element in iterparse(index):
        if element.tag != "file":
            continue
        if element.get("Catid") in PRINTER_CATIDS and element.get("On_Market") == "1":
            markets = tuple(
                sorted(
                    {
                        market.get("Value", "")
                        for market in element.iter("Country_Market")
                    }
                    - {"", WORLDWIDE}
                )
            )
            yield Candidate(
                NAME,
                code=element.get("Prod_ID", ""),
                icecat_id=int(element.get("Product_ID", "0")),
                markets=markets,
                added=iso_date(element.get("Date_Added", "")),
            )
        # the index holds millions of products: keep only the one being read
        element.clear()
