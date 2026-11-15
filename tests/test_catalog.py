"""The merge of a run into the catalogue.

The sources and Icecat are fakes here: synthetic candidates and records, so
each test states exactly the situation it checks.
"""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from printers import catalog as catalog_module
from printers.catalog import Catalog
from printers.fetch import BotWallError, FetchError
from printers.icecat import Lookup
from printers.sources import Candidate
from printers.specs import SCHEMA

DAY = date(2026, 11, 16)


def record(icecat_id, name="Brother DCP-T430W", markets=()):
    return {
        "schema": SCHEMA,
        "icecat_id": icecat_id,
        "brand": "Brother",
        "name": name,
        "title": name,
        "category": "Multifunction Printers",
        "gtin": None,
        "duplex_print": True,
    }


def source(name, markets, found):
    """A fake source: ``found`` maps market -> candidates or an exception."""

    def discover(fetcher, market, cache):
        outcome = found[market]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    return SimpleNamespace(NAME=name, MARKETS=markets, discover=discover)


@pytest.fixture(autouse=True)
def no_enrichers(monkeypatch):
    """The makers' gap-filling sites are faked in their own tests below."""
    monkeypatch.setattr(catalog_module, "ENRICHERS", {})


@pytest.fixture
def icecat(monkeypatch):
    """Icecat knows ids 1 and 2 (two regional SKUs of one model) and 3."""
    calls = []
    known = {1: record(1), 2: record(2), 3: record(3, name="Brother HL-L2445DW")}

    def lookup(fetcher, *, icecat_id=None, brand="", code="", gtin=""):
        calls.append(icecat_id or code)
        if icecat_id in known:
            return Lookup(known[icecat_id])
        return Lookup(None, "not in Icecat")

    monkeypatch.setattr(catalog_module.icecat, "lookup", lookup)
    return calls


def run(tmp_path, today, sources, max_lookups=100):
    catalog = Catalog(tmp_path, today=today)
    report = catalog.update(None, sources, max_lookups)
    catalog.save()
    return catalog, report


def index(*candidates):
    return source("icecat", ("ALL",), {"ALL": list(candidates)})


def test_first_run_adds_everything_found(tmp_path, icecat):
    catalog, report = run(
        tmp_path,
        DAY,
        [index(Candidate("icecat", icecat_id=1, markets=("BE", "NL")))],
    )
    assert report.new == ["1"]
    product = catalog.products["1"]
    assert product["first_seen"] == DAY.isoformat()
    assert product["sightings"]["icecat:ALL"]["markets"] == ["BE", "NL"]


def test_known_products_are_not_looked_up_again(tmp_path, icecat):
    first = [index(Candidate("icecat", icecat_id=1))]
    run(tmp_path, DAY, first)
    catalog, report = run(tmp_path, DAY + timedelta(days=7), first)
    assert icecat == [1]
    assert report.lookups == 0
    assert catalog.products["1"]["first_seen"] == DAY.isoformat()


def test_misses_are_retried_after_a_month(tmp_path, icecat):
    missing = [index(Candidate("icecat", icecat_id=9))]
    run(tmp_path, DAY, missing)
    run(tmp_path, DAY + timedelta(days=7), missing)
    assert icecat == [9]
    run(tmp_path, DAY + timedelta(days=31), missing)
    assert icecat == [9, 9]


def test_lookup_budget_leaves_the_rest_for_next_run(tmp_path, icecat):
    candidates = [Candidate("icecat", icecat_id=i) for i in (1, 2, 3)]
    _, report = run(tmp_path, DAY, [index(*candidates)], max_lookups=2)
    assert report.lookups == 2
    assert report.pending == 1
    catalog, report = run(tmp_path, DAY, [index(*candidates)], max_lookups=2)
    assert report.lookups == 1
    assert set(catalog.products) == {"1", "2", "3"}


def test_a_failing_source_does_not_retire_its_printers(tmp_path, icecat):
    seen = source("brother", ("GB",), {"GB": [Candidate("brother", "Brother", "X")]})
    seen_index = index(Candidate("icecat", icecat_id=3))
    run(tmp_path, DAY, [seen_index])
    catalog, report = run(
        tmp_path,
        DAY + timedelta(days=7),
        [
            source("icecat", ("ALL",), {"ALL": BotWallError("walled")}),
            source("epson", ("BE",), {"BE": FetchError("down")}),
            seen,
        ],
    )
    assert report.sources["icecat:ALL"]["status"] == "walled"
    assert report.sources["epson:BE"]["status"] == "error"
    (printer,) = catalog.site()["printers"]
    assert printer["available"] is True


def test_a_printer_dropped_by_its_source_is_no_longer_on_sale(tmp_path, icecat):
    run(tmp_path, DAY, [index(Candidate("icecat", icecat_id=3))])
    catalog, _ = run(
        tmp_path, DAY + timedelta(days=7), [index(Candidate("icecat", icecat_id=1))]
    )
    printers = {p["name"]: p for p in catalog.site()["printers"]}
    assert printers["Brother HL-L2445DW"]["available"] is False
    assert printers["Brother DCP-T430W"]["available"] is True


def test_an_empty_list_is_reported_not_trusted(tmp_path, icecat):
    run(tmp_path, DAY, [index(Candidate("icecat", icecat_id=3))])
    catalog, report = run(tmp_path, DAY + timedelta(days=7), [index()])
    assert report.sources["icecat:ALL"]["status"] == "empty"
    assert catalog.site()["printers"][0]["available"] is True


def test_regional_skus_fold_into_one_row(tmp_path, icecat):
    catalog, _ = run(
        tmp_path,
        DAY,
        [
            index(
                Candidate("icecat", icecat_id=1, markets=("BE",)),
                Candidate("icecat", icecat_id=2, markets=("MX",)),
            )
        ],
    )
    (printer,) = catalog.site()["printers"]
    assert printer["markets"] == ["BE", "MX"]
    assert printer["variants"] == 2
    assert "sightings" not in printer


def test_a_folded_row_takes_the_fields_its_variants_have(tmp_path, icecat):
    catalog, _ = run(
        tmp_path,
        DAY,
        [
            index(
                Candidate("icecat", icecat_id=1, markets=("BE", "NL")),
                Candidate("icecat", icecat_id=2, markets=("MX",)),
            )
        ],
    )
    catalog.products["2"]["weight_kg"] = 6.1
    (printer,) = catalog.site()["printers"]
    assert printer["id"] == "1"
    assert printer["weight_kg"] == 6.1


def test_hp_skus_of_one_model_fold_whatever_their_names(tmp_path, icecat):
    """Synthetic HP records: one named after its code, one localised (#B19)."""
    catalog = Catalog(tmp_path, today=DAY)
    for product_id, code, name, weight in (
        ("7", "58D77A", "HP 58D77A multifunction printer", 43.2),
        ("8", "58D77A#B19", "HP LJ Ent MFP X728dn Printer:EUR", None),
        ("9", "58D78A", "HP LaserJet X729dn", None),
    ):
        catalog.store(
            product_id,
            record(int(product_id), name)
            | {
                "brand": "HP",
                "code": code,
                "weight_kg": weight,
            },
        )
    printers = {p["name"]: p for p in catalog.site()["printers"]}
    assert set(printers) == {"HP LJ Ent MFP X728dn Printer:EUR", "HP LaserJet X729dn"}
    assert printers["HP LJ Ent MFP X728dn Printer:EUR"]["weight_kg"] == 43.2
    assert printers["HP LJ Ent MFP X728dn Printer:EUR"]["variants"] == 2


def test_records_under_an_older_mapping_are_read_again(tmp_path, icecat):
    found = [index(Candidate("icecat", icecat_id=1))]
    catalog, _ = run(tmp_path, DAY, found)
    catalog.products["1"]["schema"] = SCHEMA - 1
    catalog.save()
    catalog, report = run(tmp_path, DAY + timedelta(days=7), found)
    assert icecat == [1, 1]
    assert report.lookups == 1
    assert catalog.products["1"]["schema"] == SCHEMA
    assert catalog.products["1"]["first_seen"] == DAY.isoformat()


def lexmark_page(code="40N9163", workgroup="Small-Medium Workgroup"):
    return {
        "schema": SCHEMA,
        "brand": "Lexmark",
        "name": "Lexmark MC3326adwe",
        "title": "Lexmark MC3326adwe Colour Laser",
        "code": code,
        "category": "Multifunction Printers",
        "workgroup": workgroup,
        "duplex_print": True,
    }


def test_a_brand_icecat_lacks_is_described_by_its_maker(tmp_path, icecat):
    lexmark = source(
        "lexmark",
        ("GB", "BE"),
        {
            "GB": [
                Candidate(
                    "lexmark",
                    "Lexmark",
                    "40N9163",
                    record=lexmark_page(),
                    markets=("GB",),
                )
            ],
            "BE": [
                Candidate(
                    "lexmark",
                    "Lexmark",
                    "40N9163",
                    record=lexmark_page(),
                    markets=("BE",),
                )
            ],
        },
    )
    catalog, report = run(tmp_path, DAY, [lexmark])
    assert icecat == []  # Lexmark is not in Open Icecat: no lookup is wasted
    assert report.new == ["lexmark:40N9163"]
    (printer,) = catalog.site()["printers"]
    assert printer["markets"] == ["BE", "GB"]
    assert printer["id"] == "lexmark:40N9163"
    assert printer["duplex_print"] is True


def test_large_workgroup_machines_are_left_out(tmp_path, icecat):
    big = lexmark_page(workgroup="Large Workgroup")
    lexmark = source(
        "lexmark", ("GB",), {"GB": [Candidate("lexmark", "Lexmark", "X1", record=big)]}
    )
    catalog, _ = run(tmp_path, DAY, [lexmark])
    assert catalog.products == {}


def test_a_maker_page_confirms_or_contradicts_icecat(tmp_path, icecat):
    agrees = Candidate("epson", icecat_id=1, record={"duplex_print": True})
    disagrees = Candidate("epson", icecat_id=3, record={"duplex_print": False})
    catalog, _ = run(
        tmp_path, DAY, [source("epson", ("GB",), {"GB": [agrees, disagrees]})]
    )
    printers = {p["id"]: p for p in catalog.site()["printers"]}
    assert printers["1"]["confirmed"] == ["epson"]
    assert printers["1"]["differs"] == {}
    assert printers["3"]["confirmed"] == []
    assert printers["3"]["differs"] == {"epson": {"duplex_print": [True, False]}}


def test_the_earliest_added_date_is_kept(tmp_path, icecat):
    first = [index(Candidate("icecat", icecat_id=1, added="2021-06-01"))]
    run(tmp_path, DAY, first)
    later = [
        index(
            Candidate("icecat", icecat_id=1, added="2023-01-01"),
            Candidate("icecat", icecat_id=1, added="2020-02-02"),
        )
    ]
    catalog, _ = run(tmp_path, DAY + timedelta(days=7), later)
    assert catalog.products["1"]["added"] == "2020-02-02"
    catalog.products["1"]["schema"] = SCHEMA - 1
    catalog.save()
    catalog, _ = run(
        tmp_path, DAY + timedelta(days=14), [index(Candidate("icecat", icecat_id=1))]
    )
    assert catalog.products["1"]["added"] == "2020-02-02"  # kept across a fresh read


def test_a_maker_page_fills_what_icecat_left_empty(tmp_path, icecat):
    page = Candidate(
        "epson", icecat_id=1, record={"weight_kg": 9.5, "duplex_print": True}
    )
    catalog, _ = run(tmp_path, DAY, [source("epson", ("GB",), {"GB": [page]})])
    product = catalog.products["1"]
    assert product["weight_kg"] == 9.5
    assert product["filled"] == {"weight_kg": "epson"}
    (printer,) = catalog.site()["printers"]
    assert printer["filled"] == {"weight_kg": "epson"}


def test_icecat_values_are_never_overwritten_by_a_fill(tmp_path, icecat):
    catalog, _ = run(tmp_path, DAY, [index(Candidate("icecat", icecat_id=1))])
    catalog.products["1"]["weight_kg"] = 12.0
    catalog.save()
    page = Candidate("epson", icecat_id=1, record={"weight_kg": 9.5})
    catalog, _ = run(tmp_path, DAY, [source("epson", ("GB",), {"GB": [page]})])
    assert catalog.products["1"]["weight_kg"] == 12.0
    assert "filled" not in catalog.products["1"]


class FakeEnricher:
    NAME = "fake-support"
    FIELDS = ("weight_kg", "noise_db")

    def __init__(self, record=None, error=None):
        self.record, self.error, self.calls = record, error, []

    def key(self, product):
        return product["name"].split()[-1]

    def enrich(self, fetcher, product):
        self.calls.append(product["name"])
        if self.error:
            raise self.error
        return self.record


def test_gaps_are_filled_from_the_support_site_and_cached(
    tmp_path, icecat, monkeypatch
):
    enricher = FakeEnricher({"weight_kg": 21.5, "noise_db": 47.0})
    monkeypatch.setattr(catalog_module, "ENRICHERS", {"Brother": enricher})
    found = [index(Candidate("icecat", icecat_id=3))]
    catalog, report = run(tmp_path, DAY, found)
    assert catalog.products["3"]["weight_kg"] == 21.5
    assert catalog.products["3"]["filled"] == {
        "weight_kg": "fake-support",
        "noise_db": "fake-support",
    }
    assert report.sources["fake-support:ALL"] == {"status": "ok", "found": 1}
    # the next run fills again from the cache, without reading the page
    catalog.products["3"]["schema"] = SCHEMA - 1
    catalog.save()
    catalog, _ = run(tmp_path, DAY + timedelta(days=7), found)
    assert enricher.calls == ["Brother HL-L2445DW"]  # one page read, two runs
    assert catalog.products["3"]["weight_kg"] == 21.5


def test_a_support_site_that_fails_is_reported(tmp_path, icecat, monkeypatch):
    enricher = FakeEnricher(error=FetchError("down"))
    monkeypatch.setattr(catalog_module, "ENRICHERS", {"Brother": enricher})
    catalog, report = run(tmp_path, DAY, [index(Candidate("icecat", icecat_id=3))])
    assert report.sources["fake-support:ALL"]["status"] == "error"
    assert "weight_kg" not in catalog.products["3"]


def test_records_with_gaps_are_read_again_after_a_month(tmp_path, icecat):
    printer = [index(Candidate("icecat", icecat_id=1))]
    run(tmp_path, DAY, printer)
    run(tmp_path, DAY + timedelta(days=7), printer)
    assert icecat == [1]
    run(tmp_path, DAY + timedelta(days=31), printer)
    assert icecat == [1, 1]
    run(tmp_path, DAY + timedelta(days=38), printer)
    assert icecat == [1, 1]


def test_new_models_go_before_refreshes(tmp_path, icecat):
    run(tmp_path, DAY, [index(Candidate("icecat", icecat_id=1))])
    later = [index(*(Candidate("icecat", icecat_id=i) for i in (1, 2, 3)))]
    run(tmp_path, DAY + timedelta(days=31), later, max_lookups=2)
    assert icecat == [1, 2, 3]


class BrowserEnricher(FakeEnricher):
    BROWSER = True

    def enrich(self, fetcher, product):
        self.readers = [*getattr(self, "readers", []), fetcher]
        return super().enrich(fetcher, product)


def test_a_maker_that_needs_a_browser_is_read_only_through_it(
    tmp_path, icecat, monkeypatch
):
    enricher = BrowserEnricher({"weight_kg": 21.5})
    monkeypatch.setattr(catalog_module, "ENRICHERS", {"Brother": enricher})
    found = [index(Candidate("icecat", icecat_id=3))]
    run(tmp_path, DAY, found)
    assert enricher.calls == []  # no browser in this run: skipped
    catalog = Catalog(tmp_path, today=DAY)
    browser = SimpleNamespace(text=lambda url: "")
    catalog.update(None, found, 100, browser)
    assert enricher.readers == [browser]
    assert catalog.products["3"]["weight_kg"] == 21.5
