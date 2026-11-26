"""Against the real sites, on demand: `uv run pytest -m live`.

The weekly update is the canary (``printers check``); these tests are for
checking a source by hand while working on it.

A source that answers with a wall is an expected failure, not a broken
reader; a source that answers but yields no printer means its markup moved.
"""

import os

import pytest

from printers import icecat
from printers.browser import Browser
from printers.fetch import BotWallError, Fetcher, FetchError
from printers.sources import KNOWN_WALLS, all_sources, epson, lexmark, pages

pytestmark = pytest.mark.live


@pytest.mark.parametrize(
    ("source", "market"),
    [
        (source, market)
        for source in all_sources()
        # their other markets depend on the UK cache, tested below
        if source.NAME not in {"epson", "lexmark"}
        for market in source.MARKETS
    ],
    ids=lambda value: getattr(value, "NAME", value),
)
def test_source_lists_printers(source, market):
    if source.NAME == "icecat" and not os.environ.get("ICECAT_PASSWORD"):
        pytest.skip("needs an Icecat account")
    try:
        if getattr(source, "BROWSER", False):
            with Browser() as browser:
                found = source.discover(browser, market, {})
        else:
            found = source.discover(Fetcher(), market, {})
    except (BotWallError, FetchError) as error:
        if source.NAME in KNOWN_WALLS:
            pytest.xfail(str(error))
        raise
    assert found


@pytest.mark.parametrize("source", [epson, lexmark], ids=["epson", "lexmark"])
def test_maker_site_lists_printers_with_specs(source, monkeypatch):
    monkeypatch.setattr(pages, "MAX_PAGES", 3)
    found = source.discover(Fetcher(), "GB", {})
    assert found
    assert all(candidate.record for candidate in found)


def test_icecat_reads_a_known_printer():
    result = icecat.lookup(Fetcher(), brand="Brother", code="DCP-L3550CDW")
    assert result.record is not None
    assert result.record["duplex_print"] is True
