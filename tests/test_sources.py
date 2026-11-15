import gzip
import io

import pytest
from conftest import FIXTURES, FakeFetcher, fixture_text

from printers.fetch import FetchError
from printers.sources import Candidate, all_sources, brother, epson, hp, icecat_index


def test_hp_reads_the_sku_from_the_url():
    found = hp.parse(fixture_text("hp_products_url_gb_en.txt"), "GB")
    codes = [c.code for c in found]
    assert codes[0] == "4ZB95A"
    assert "499R0F" in codes
    # care packs are not printers; a DesignJet accessory is, until Icecat says not
    assert all(c.markets == ("GB",) for c in found)
    assert len(codes) == 7


def test_brother_codes_get_their_series_dash():
    found = brother.parse(fixture_text("brother_support_gb.xml"), "GB")
    assert [c.code for c in found] == [
        "DCP-L3527CDW",
        "DCP-7025",
        "HL-L9310CDWT",
        "MFC-J5945DW",
    ]


def test_epson_skips_professional_ranges():
    pages = epson.printer_pages(fixture_text("epson_products_gb.xml"))
    assert set(pages) == {"60087", "161"}


def test_epson_reads_the_sku_once_then_reuses_it_in_other_markets():
    gb = "https://www.epson.co.uk"
    product_map = f"{gb}/medias/Product-en_GB.xml"
    fetcher = FakeFetcher(
        {
            f"{gb}/sitemap.xml": f"<loc>{product_map}</loc>",
            product_map: fixture_text("epson_products_gb.xml"),
        }
    )
    l3360, epl = epson.printer_pages(fixture_text("epson_products_gb.xml")).values()
    fetcher.pages[l3360] = fixture_text("epson_page_l3360.html")
    fetcher.pages[epl] = FetchError("gone")
    cache: dict[str, str] = {}
    found = epson.discover(fetcher, "GB", cache)
    assert [c.code for c in found] == ["C11CL63409"]
    assert cache == {"60087": "C11CL63409"}

    be = "https://www.epson.be"
    fetcher.pages |= {
        f"{be}/sitemap.xml": f"<loc>{be}/medias/Product-nl_BE.xml</loc>",
        f"{be}/medias/Product-nl_BE.xml": (
            f"<loc>{be}/nl_BE/producten/printers/inkjet/ecotank-l3360/p/60087</loc>"
            f"<loc>{be}/nl_BE/producten/scanners/x/p/291</loc>"
        ),
    }
    found = epson.discover(fetcher, "BE", cache)
    assert [(c.code, c.markets) for c in found] == [("C11CL63409", ("BE",))]


def test_epson_without_product_sitemap_is_an_error():
    fetcher = FakeFetcher({"https://www.epson.de/sitemap.xml": "<loc>x</loc>"})
    with pytest.raises(FetchError):
        epson.discover(fetcher, "DE", {})


def test_icecat_index_keeps_printers_on_the_market():
    data = (FIXTURES / "icecat_daily_index.xml").read_bytes()
    found = list(
        icecat_index.parse(gzip.GzipFile(fileobj=io.BytesIO(gzip.compress(data))))
    )
    assert len(found) == 1
    printer = found[0]
    assert printer.icecat_id == 129039974
    assert printer.key == "icecat:129039974"
    assert "GB" in printer.markets
    assert "WW" not in printer.markets


def test_icecat_index_needs_the_password(no_icecat_account):
    with pytest.raises(FetchError, match="ICECAT_PASSWORD"):
        icecat_index.credentials()


def test_candidate_keys():
    assert Candidate("x", gtin="4977766790185").key == "gtin:4977766790185"
    assert Candidate("x", "HP", "499R0F").key == "hp:499r0f"


def test_every_source_is_registered():
    assert [s.NAME for s in all_sources()] == ["icecat", "hp.com", "brother", "epson"]
