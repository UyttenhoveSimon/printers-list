"""Brother: the support sitemap has a page per model, current and past.

``/support/dcpl3550cdw`` is the DCP-L3550CDW: Icecat writes the series
prefix (HL, DCP, MFC) with a dash, the site without. Brother France files
the same pages under ``/services-et-supports/``. Support pages outlive the
machines, so old models come through too; their Icecat end-of-life date and
release date let the page hide them.
"""

import re

from ..fetch import Fetcher
from . import Candidate

NAME = "brother"
SITEMAPS = {
    "GB": "https://www.brother.co.uk/sitemaps/sitemap_main-uk_en_Support.xml",
    "BE": "https://www.brother.be/sitemaps/sitemap_main-be_nl-be_Support.xml",
    "FR": "https://www.brother.fr/sitemaps/sitemap_main-fr_fr-FR_Support.xml",
    "DE": "https://www.brother.de/sitemaps/sitemap_main-de_de-DE_Support.xml",
}
MARKETS = tuple(SITEMAPS)
LOC = re.compile(r"<loc>([^<]+)</loc>")
MODEL = re.compile(
    r"/(?:support|services-et-supports)/(?P<series>hl|dcp|mfc)(?P<model>[a-z0-9]+)(?:/|$)"
)


def discover(fetcher: Fetcher, market: str, cache: dict[str, str]) -> list[Candidate]:
    return parse(fetcher.text(SITEMAPS[market]), market)


def model_code(series: str, model: str) -> str:
    return f"{series}-{model}".upper()


def parse(body: str, market: str) -> list[Candidate]:
    found: dict[str, Candidate] = {}
    for url in LOC.findall(body):
        match = MODEL.search(url)
        if match:
            code = model_code(match["series"], match["model"])
            found.setdefault(
                code, Candidate(NAME, "Brother", code, url=url, markets=(market,))
            )
    return list(found.values())
