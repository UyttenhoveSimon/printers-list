import gzip
import io
from types import SimpleNamespace

import pytest
from conftest import FIXTURES, FakeFetcher, fixture_text

from printers.fetch import FetchError
from printers.sources import (
    Candidate,
    all_sources,
    brother,
    brother_support,
    canon_uk,
    epson,
    hp,
    hp_shop,
    icecat_index,
    kyocera,
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


def test_hp_shop_reads_the_spec_sheet_embedded_in_the_page():
    sheet = hp_shop.spec_sheet(fixture_text("hp_shop_m776dn.html"))
    assert sheet["Weight"] == "70.9 kg"  # its footnote mark dropped
    assert hp_shop.specifications(sheet) == {
        "weight_kg": 70.9,
        "paper_input": 650,  # the trays it comes with, not the first one
        "paper_output": 500,
        "adf_capacity": 200,
        "duty_cycle": 200000,
        "monthly_volume": 40000,
        "ppm_iso": 46,
        "first_page_s": 6.5,
        "print_dpi": 1200,
        "scan_dpi": 600,
        "power_w": 900.0,
        "tec_kwh": 2.47,
        "max_paper": "A3",
    }


def test_hp_shop_finds_a_printer_by_its_sku_in_the_shop_list():
    url = "https://www.hp.com/gb-en/shop/products/printers/hp-color-laserjet-enterprise-mfp-m776dn-t3u55a-b19"
    fetcher = FakeFetcher(
        {
            hp_shop.list_url("gb-en"): fixture_text("hp_products_url_gb_en.txt"),
            **{
                hp_shop.list_url(locale): FetchError("refused")
                for locale in hp_shop.LOCALES[1:]
            },
            hp_shop.STORE_INDEX: FetchError("refused"),
            url: fixture_text("hp_shop_m776dn.html"),
        }
    )
    record = hp_shop.enrich(fetcher, {"code": "T3U55A#B19"})
    assert record is not None
    assert record["weight_kg"] == 70.9
    assert hp_shop.enrich(fetcher, {"code": "XXXXXX"}) is None
    # each list is read once a run
    assert fetcher.calls.count(hp_shop.list_url("gb-en")) == 1


def test_hp_power_is_the_printing_figure_or_nothing():
    assert hp_shop.watts("Active Printing: 282 W; Ready: 27 W; Sleep: 1.0 W") == 282
    assert hp_shop.watts("900 watts (printing), 100 watts (ready)") == 900
    assert hp_shop.watts("0.109 watts (manual-Off), 3.023 watts (ready)") is None


def test_canon_uk_reads_an_inkjet_and_a_laser_spec_page():
    inkjet = canon_uk.spec_list(fixture_text("canon_uk_pixma_g3510.html"))
    assert canon_uk.specifications(inkjet) == {
        "ppm_iso": 9,
        "print_dpi": 4800,
        "paper_input": 100,
        "weight_kg": 6.3,
        "noise_db": 53.5,
        "power_w": 11.0,
        "scan_dpi": 600,
        "max_paper": "A4",
        "width_mm": 445.0,
        "depth_mm": 330.0,
        "height_mm": 163.0,
    }
    laser = canon_uk.specifications(
        canon_uk.spec_list(fixture_text("canon_uk_lbp361dw.html"))
    )
    assert laser["paper_input"] == 650  # cassette and multi-purpose tray
    assert laser["noise_db"] == 55.0  # sound pressure, not power
    assert (laser["monthly_volume"], laser["duty_cycle"]) == (16000, 275000)
    assert laser["width_mm"] == 430.0


def test_canon_uk_matches_models_and_series():
    sitemap = (
        "<loc>https://www.canon.co.uk/printers/pixma-g3510/specifications/</loc>"
        "<loc>https://www.canon.co.uk/printers/pixma-ts6050-series/specifications/</loc>"
        "<loc>https://www.canon.co.uk/printers/inkjet/pixma/photo-paper/pp-201/specifications/</loc>"
    )
    pages = canon_uk.spec_pages(FakeFetcher({canon_uk.SITEMAP: sitemap}))
    assert canon_uk.key({"name": "Canon PIXMA G3510"}) == "pixmag3510"
    assert (canon_uk.page_for("pixmag3510", pages) or "").endswith(
        "pixma-g3510/specifications/"
    )
    assert (canon_uk.page_for("pixmats6051", pages) or "").endswith(
        "series/specifications/"
    )
    assert canon_uk.page_for("pixmapp201", pages) is None
    assert canon_uk.key({"name": "Canon 7063C013 laser printer"}) == ""


def test_kyocera_reads_its_icon_row_and_tabs():
    page = fixture_text("kyocera_ecosys_pa2100cwx.html")
    assert kyocera.specifications(kyocera.spec_list(page)) == {
        "ppm_black": 21,
        "print_dpi": 1200,
        "weight_kg": 21.0,
        "power_w": 345.0,
        "paper_input": 300,  # 50-sheet tray and 250-sheet cassette
        "paper_output": 150,
        "max_paper": "A4",
        "width_mm": 410.0,
        "depth_mm": 410.0,
        "height_mm": 329.0,
    }


def test_kyocera_matches_names_with_or_without_the_range():
    sitemap = (
        "<loc>https://www.kyoceradocumentsolutions.eu/en/products/printers/"
        "ECOSYSPA2100CWX.html</loc>"
    )
    pages = kyocera.product_pages(FakeFetcher({kyocera.SITEMAP: sitemap}))
    for name in ("KYOCERA ECOSYS PA2100cwx", "KYOCERA PA2100CWX laser printer"):
        assert pages.get(kyocera.key({"name": name}), "").endswith("CWX.html")


def test_canon_uk_reads_a_number_after_a_stray_dot():
    """Synthetic value, the shape of the one that broke a run: "Approx. .13.0"."""
    assert canon_uk.specifications({"Mono Print Speed": "Approx .13.0 ipm"}) == {
        "ppm_iso": 13
    }


def test_a_cut_short_icecat_index_is_a_fetch_error(monkeypatch):
    """Synthetic: the real index, compressed, then cut in the middle."""
    monkeypatch.setenv("ICECAT_USER", "u")
    monkeypatch.setenv("ICECAT_PASSWORD", "p")
    data = gzip.compress((FIXTURES / "icecat_daily_index.xml").read_bytes())

    class Response:
        raw = io.BytesIO(data[: len(data) // 2])

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    fetcher = SimpleNamespace(stream=lambda url, auth: Response())
    with pytest.raises(FetchError, match="cut short"):
        icecat_index.discover(fetcher, "ALL", {})


def test_hp_shop_reads_a_german_sheet_under_the_english_labels():
    page = fixture_text("hp_shop_de_4002dw.html")
    record = hp_shop.specifications(hp_shop.spec_sheet(page, english=False))
    assert record["weight_kg"] == 8.56  # "8,56 kg"
    assert record["duty_cycle"] == 80000  # "Bis zu 80.000 Seiten"
    assert record["monthly_volume"] == 4000  # "750 bis 4.000"
    assert record["tec_kwh"] == 0.36
    assert (record["width_mm"], record["paper_input"]) == (381.0, 350)


def test_hp_figures_written_the_local_way():
    assert hp_shop.english_figures("1.140 x 570 mm") == "1140 x 570 mm"
    assert hp_shop.english_figures("0,109 Watt") == "0.109 Watt"
    assert hp_shop.english_figures("Up to 3,000 pages") == "Up to 3,000 pages"


def test_epson_model_codes_in_page_urls():
    url = (
        "https://www.epson.co.uk/en_GB/products/printers/inkjet/microbusiness/"
        "workforce-pro-wf-3920-a4-multifunction-wireless-inkjet-printer/p/56721"
    )
    assert epson.models_in(url) == {"WF-3920"}
    assert epson.models_in("https://x/inkjet/consumer/ecotank-l3351/p/2") == {"L3351"}


def test_hp_store_reads_a_latin_american_sheet():
    """Argentina's page for the LaserJet M111w: Spanish labels, mixed figures."""
    sheet = hp_shop.store_sheet(fixture_text("hp_store_ar_4ry23a.html"))
    assert hp_shop.specifications(sheet) == {
        "weight_kg": 6.95,  # "6,95 kg"
        "paper_input": 150,
        "paper_output": 100,
        "duty_cycle": 25000,  # the A4 figure, not the letter one ("20,000")
        "monthly_volume": 2500,
        "first_page_s": 7.6,  # "Apenas 7,6 segundos"
        "print_dpi": 600,
        "power_w": 365.0,  # "365vatios (impresión activa)"
        "max_paper": "A4",
        "width_mm": 380.5,
        "depth_mm": 293.4,
        "height_mm": 211.0,
    }


def test_hp_store_reads_an_asian_sheet():
    sheet = hp_shop.store_sheet(fixture_text("hp_store_sg_m501dn.html"))
    record = hp_shop.specifications(sheet)
    assert record["power_w"] == 660.0  # "660 watts (active printing)"
    assert record["tec_kwh"] == 1.623
    assert (record["paper_input"], record["duty_cycle"]) == (650, 100000)


def test_hp_figures_with_english_thousands_in_a_local_sheet():
    assert hp_shop.english_figures("Hasta 1,200 x 1,200 dpi") == "Hasta 1200 x 1200 dpi"
    assert hp_shop.english_figures("1,144 kWh/semana") == "1.144 kWh/semana"
    assert hp_shop.english_figures("18,9 kg") == "18.9 kg"


def test_hp_input_adds_the_standard_trays():
    assert hp_shop.input_sheets("Up to 650 sheets (MP Tray: Up to 100 sheets)") == 650
    text = "1 hoja en la Bandeja 1; hasta 250 hojas (altura de pila) en la Bandeja 2"
    assert hp_shop.input_sheets(text) == 251
    text = "100-sheet multipurpose tray and 550-sheet main cassette"
    assert hp_shop.input_sheets(text) == 650


def test_hp_store_pages_are_tried_until_one_has_a_sheet():
    """Synthetic sitemaps, shaped like HP's global one; the pages are real."""
    stale = "https://www.hp.com/th-en/shop/hp-laserjet-m111w-4ry23a.html"
    live = "https://www.hp.com/ar-es/shop/impresora-hp-laserjet-m111w-4ry23a.html"
    sitemap = (
        f'<url><xhtml:link rel="alternate" hreflang="en-th" href="{stale}"/>'
        f'<xhtml:link rel="alternate" hreflang="es-ar" href="{live}"/>'
        '<xhtml:link rel="alternate" hreflang="en-gb" href="https://www.hp.com/'
        'gb-en/shop/product.aspx?id=4RY23A&amp;opt=B19&amp;sel=DEF"/></url>'
    )
    fetcher = FakeFetcher(
        {
            **{hp_shop.list_url(locale): "" for locale in hp_shop.LOCALES},
            hp_shop.STORE_INDEX: "<loc>https://www.hp.com/sitemap-hreflang-pdp-ar-es.xml</loc>",
            "https://www.hp.com/sitemap-hreflang-pdp-ar-es.xml": sitemap,
            stale: "<html><title>Printers - Shop HP.com Thailand</title></html>",
            live: fixture_text("hp_store_ar_4ry23a.html"),
        }
    )
    product = {"code": "4RY23A#BGJ"}
    assert hp_shop.covers(fetcher, product)
    assert not hp_shop.listed(fetcher, product)  # no European shop sells it
    record = hp_shop.enrich(fetcher, product)
    assert record is not None
    assert record["weight_kg"] == 6.95
    assert fetcher.calls[-2:] == [stale, live]

