"""Shared fakes: no test reaches the network.

The fixtures under ``fixtures/`` are real captures from Icecat and the
manufacturers' sites (November 2026), trimmed to a few entries. The two
Brother and Epson sitemaps keep the captured ``<loc>`` URLs verbatim in a
minimal ``<urlset>``; the Icecat data sheets keep only the features read.
"""

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixture_json(name: str):
    return json.loads(fixture_text(name))


class FakeFetcher:
    """Answers from a dict: URL -> body, or an exception to raise."""

    def __init__(self, pages=None, api=None):
        self.pages = pages or {}
        self.api = api or (lambda params: (404, {}))
        self.calls = []

    def text(self, url):
        self.calls.append(url)
        page = self.pages[url]
        if isinstance(page, Exception):
            raise page
        return page

    def json(self, url, params, headers=None):
        self.calls.append(params)
        return self.api(params)


@pytest.fixture
def no_icecat_account(monkeypatch):
    for name in ("ICECAT_USER", "ICECAT_KEY", "ICECAT_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
