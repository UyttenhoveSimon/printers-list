import gzip
import io

import pytest
from conftest import FIXTURES, FakeFetcher, fixture_text

from printers.fetch import FetchError
from printers.sources import (
    Candidate,
    all_sources,
    brother,
    brother_support,
    epson,
    hp,
    icecat_index,
    lexmark,
    pages,
)


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


def test_epson_sku_without_its_country_suffix():
    assert epson.page_sku('content="C11CL63409B2"') == "C11CL63409"
    assert epson.page_sku("no sku here") == ""
    assert epson.read_page("no sku here", "https://x/p/1") is None


def test_epson_skips_professional_ranges():
    pages = epson.printer_pages(fixture_text("epson_products_gb.xml"))
    assert set(pages) == {"60087", "161"}


def test_epson_reads_the_page_once_then_reuses_it_in_other_markets():
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
    cache: dict = {}
    (found,) = epson.discover(fetcher, "GB", cache)
    assert found.code == "C11CL63409"
    assert found.record == {
        "technology": "inkjet",
        "color": True,
        "duplex_print": False,
        "scan": True,
        "fax": False,
        "wifi": True,
        "ethernet": False,
        "ppm_iso": 11,
        "ppm_black": 33,
        "ppm_color": 15,
        "first_page_s": 10.0,
        "paper_input": 100,
        "paper_output": 30,
        "weight_kg": 4.2,
        "noise_db": 38.0,
        "print_dpi": 5760,
        "scan_dpi": 1200,
        "power_w": 12.0,
        "max_paper": "A4",
        "width_mm": 361.0,
        "depth_mm": 317.0,
        "height_mm": 162.0,
    }
    assert cache["60087"]["code"] == "C11CL63409"
    assert "161" not in cache  # its page failed: read again next run

    be = "https://www.epson.be"
    fetcher.pages |= {
        f"{be}/sitemap.xml": f"<loc>{be}/medias/Product-nl_BE.xml</loc>",
        f"{be}/medias/Product-nl_BE.xml": (
            f"<loc>{be}/nl_BE/producten/printers/inkjet/ecotank-l3360/p/60087</loc>"
            f"<loc>{be}/nl_BE/producten/scanners/x/p/291</loc>"
        ),
    }
    calls = len(fetcher.calls)
    (found,) = epson.discover(fetcher, "BE", cache)
    assert (found.code, found.markets) == ("C11CL63409", ("BE",))
    assert len(fetcher.calls) == calls + 2  # the two sitemaps, no product page


def test_an_old_cache_entry_is_read_again(monkeypatch):
    gb = "https://www.epson.co.uk"
    product_map = f"{gb}/medias/Product-en_GB.xml"
    l3360 = next(
        iter(epson.printer_pages(fixture_text("epson_products_gb.xml")).values())
    )
    fetcher = FakeFetcher(
        {
            f"{gb}/sitemap.xml": f"<loc>{product_map}</loc>",
            product_map: fixture_text("epson_products_gb.xml"),
            l3360: fixture_text("epson_page_l3360.html"),
        }
    )
    monkeypatch.setattr(pages, "MAX_PAGES", 1)
    cache = {"60087": "C11CL63409", "161": "C11C000000"}
    epson.discover(fetcher, "GB", cache)
    assert cache["60087"]["code"] == "C11CL63409"
    assert cache["161"] == "C11C000000"  # past this run's page budget


def test_lexmark_reads_its_spec_tables():
    read = lexmark.read_page(
        fixture_text("lexmark_mc3326adwe.html"),
        "https://www.lexmark.com/en_gb/printers/printer/14450/Lexmark-MC3326adwe",
    )
    assert read is not None
    code, record = read
    assert code == "40N9163"
    assert record["name"] == "Lexmark MC3326adwe"
    assert record["technology"] == "laser"
    assert record["color"] is True
    assert (record["duplex_print"], record["duplex_scan"]) == (True, False)
    assert (record["scan"], record["copy"], record["fax"]) == (True, True, True)
    assert (record["adf"], record["adf_capacity"]) == (True, 50)
    assert (record["wifi"], record["ethernet"], record["usb"]) == (True, True, True)
    assert (record["airprint"], record["mopria"]) == (True, True)
    assert (record["ppm_black"], record["ppm_color"]) == (25, 25)
    assert record["paper_input"] == 250
    assert record["duty_cycle"] == 50000
    assert record["monthly_volume"] == 2500
    assert record["noise_db"] == 50
    assert record["weight_kg"] == 19.4
    assert (record["height_mm"], record["width_mm"]) == (344.4, 411.2)
    assert "High Yield" in record["supplies"]


def test_lexmark_mono_printer():
    read = lexmark.read_page(
        fixture_text("lexmark_b2338dw.html"),
        "https://www.lexmark.com/en_gb/printers/printer/11831/Lexmark-B2338dw",
    )
    assert read is not None
    code, record = read
    assert code == "36SC128"
    assert record["color"] is False
    assert record["category"] == "Laser Printers"
    assert record["ppm_black"] == 36
    assert "ppm_color" not in record


def test_lexmark_discovers_printers_from_its_sitemap():
    gb = lexmark.SITEMAP.format(locale="en_gb")
    pages_found = lexmark.printer_pages(fixture_text("lexmark_sitemap_gb.xml"))
    assert list(pages_found) == ["14450", "11831"]
    mc, b = pages_found.values()
    fetcher = FakeFetcher(
        {
            gb: fixture_text("lexmark_sitemap_gb.xml"),
            mc: fixture_text("lexmark_mc3326adwe.html"),
            b: "<html>no spec table</html>",
        }
    )
    cache: dict = {}
    (found,) = lexmark.discover(fetcher, "GB", cache)
    assert found.code == "40N9163"
    assert found.record is not None
    assert found.record["name"] == "Lexmark MC3326adwe"
    assert cache["11831"] == {"code": "", "v": pages.PAGE_VERSION}  # remembered


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
    assert printer.added == "2025-03-04"


def test_index_dates():
    assert icecat_index.iso_date("20050715000000") == "2005-07-15"
    assert icecat_index.iso_date("") == ""
    assert icecat_index.iso_date("2005") == ""


def test_icecat_index_needs_the_password(no_icecat_account):
    with pytest.raises(FetchError, match="ICECAT_PASSWORD"):
        icecat_index.credentials()


def test_candidate_keys():
    assert Candidate("x", gtin="4977766790185").key == "gtin:4977766790185"
    assert Candidate("x", "HP", "499R0F").key == "hp:499r0f"


def test_every_source_is_registered():
    assert [s.NAME for s in all_sources()] == [
        "icecat",
        "hp.com",
        "brother",
        "epson",
        "lexmark",
    ]


def test_a_page_read_by_an_older_reader_is_read_again():
    gb = lexmark.SITEMAP.format(locale="en_gb")
    mc = next(
        iter(lexmark.printer_pages(fixture_text("lexmark_sitemap_gb.xml")).values())
    )
    fetcher = FakeFetcher(
        {
            gb: fixture_text("lexmark_sitemap_gb.xml"),
            mc: fixture_text("lexmark_mc3326adwe.html"),
        }
    )
    cache = {
        "14450": {"code": "40N9163", "record": {"name": "old"}},
        "11831": {"code": "", "v": pages.PAGE_VERSION},
    }
    (found,) = lexmark.discover(fetcher, "GB", cache)
    assert found.record is not None
    assert found.record["name"] == "Lexmark MC3326adwe"
    assert cache["14450"]["v"] == pages.PAGE_VERSION


def test_brother_support_values_per_model():
    """Brother's spec pages list values per model group within one cell."""
    html = fixture_text("brother_support_spec_mfcl3740cdw.html")
    mfc = brother_support.specifications(html, "MFC-L3740CDW")
    assert mfc == {
        "weight_kg": 20.0,
        "noise_db": 46.0,
        "adf_capacity": 50,
        "paper_input": 250,
        "paper_output": 150,
    }
    dcp = brother_support.specifications(html, "DCP-L3520CDW")
    assert dcp["weight_kg"] == 18.6
    assert "adf_capacity" not in dcp  # the ADF row names the models that have one


def test_brother_support_finds_the_model_and_its_page():
    assert (
        brother_support.model_of("Brother MFC-L3740CDW multifunction printer")
        == "MFC-L3740CDW"
    )
    assert brother_support.model_of("Brother printer") == ""
    assert brother_support.spec_url("MFC-L3740CDW").endswith("prod=mfcl3740cdw_eu")
    fetcher = FakeFetcher(
        {
            brother_support.spec_url("MFC-L3740CDW"): fixture_text(
                "brother_support_spec_mfcl3740cdw.html"
            )
        }
    )
    record = brother_support.enrich(fetcher, {"name": "Brother MFC-L3740CDW"})
    assert record is not None
    assert record["weight_kg"] == 20.0
    assert brother_support.enrich(fetcher, {"name": "no model here"}) is None
