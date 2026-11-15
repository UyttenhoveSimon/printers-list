import pytest

from printers import specs


@pytest.mark.parametrize(
    ("value", "expected"),
    [("01-04-2024", "2024-04-01"), ("", None), ("2024", None)],
)
def test_dmy_date(value, expected):
    assert specs.dmy_date(value) == expected


def test_numbers():
    assert specs.number("50,000 pages per month") == 50000
    assert specs.number(None) is None
    assert specs.decimal("4.2 kg") == 4.2
    assert specs.decimal("0,13 kWh") == 0.13
    assert specs.whole("Black: 24.7 ppm") == 25
    assert specs.whole("") is None
    assert specs.upper_bound("150 - 2,500 pages per month") == 2500
    assert specs.upper_bound("none") is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Laser", "laser"),
        ("LED", "laser"),
        ("Colour Laser", "laser"),
        ("Inkjet", "inkjet"),
        ("", "unknown"),
        ("Thermal", "thermal"),
    ],
)
def test_technology(value, expected):
    assert specs.technology(value) == expected


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("TN-423BK toner", "toner"),
        ("DR-421CL drum unit", "drum"),
        ("103 EcoTank Black ink bottle", "ink"),
        ("Waste box", "supply"),
    ],
)
def test_consumable_kind(name, kind):
    assert specs.consumable_kind(name) == kind


def test_disagreements_allow_rounding_and_skip_unknowns():
    icecat = {"duplex_print": True, "ppm_iso": 20, "fax": False, "technology": "laser"}
    site = {"duplex_print": False, "ppm_iso": 21, "wifi": True, "technology": "laser"}
    assert specs.disagreements(icecat, site) == {"duplex_print": [True, False]}
    assert specs.disagreements(icecat, {"ppm_iso": 23}) == {"ppm_iso": [20, 23]}


def test_present():
    assert specs.present("Colour scanning")
    assert not specs.present("No")
    assert not specs.present("Not Available")
    assert not specs.present(None)


def test_out_of_scope():
    assert specs.out_of_scope({"workgroup": "Large Workgroup"})
    assert not specs.out_of_scope({"workgroup": "Small Workgroup"})
    assert not specs.out_of_scope({})
