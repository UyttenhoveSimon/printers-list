import pytest
from conftest import FakeFetcher, fixture_json

from printers import icecat


@pytest.fixture
def brother():
    return icecat.parse(fixture_json("icecat_brother_dcp-l3550cdw.json")["data"])


def test_brother_dcp_l3550cdw(brother):
    assert brother["name"] == "Brother DCP-L3550CDW multifunction printer"
    assert brother["technology"] == "laser"
    assert brother["led"] is True
    assert brother["color"] is True
    assert brother["duplex_print"] is True
    assert brother["duplex_scan"] is False
    assert (brother["scan"], brother["copy"], brother["fax"]) == (True, True, False)
    assert brother["adf"] is True
    assert (brother["wifi"], brother["ethernet"], brother["airprint"]) == (
        True,
        True,
        True,
    )
    assert brother["ppm_black"] == 18
    assert brother["max_paper"] == "A4"
    assert icecat.in_scope(brother) == ""
    assert brother["schema"] == 3
    assert brother["code"] == "DCP-L3550CDW"
    assert brother["paper_input"] == 250
    assert brother["paper_output"] == 150
    assert brother["adf_capacity"] == 50
    assert brother["touchscreen"] is True
    assert brother["weight_kg"] == pytest.approx(21.9, abs=10)
    assert brother["noise_db"] is not None


def test_consumables_keep_ink_and_toner_not_paper_or_service():
    data = fixture_json("icecat_epson_c11cl63409.json")["data"]
    supplies = icecat.consumables(data)
    names = [s["name"] for s in supplies]
    assert "103 EcoTank Black ink bottle" in names
    assert not any("Paper" in n for n in names)
    assert {s["kind"] for s in supplies} <= {"ink", "supply"}
    assert all(s["own"] and s["brand"] == "Epson" for s in supplies)
    record = icecat.parse(data)
    assert record["consumables"] == supplies
    assert record["starter_yield"] == 8300
    assert record["cartridges"] == 4
    assert record["borderless"] is True


def test_other_brands_supplies_come_after_the_makers():
    """Synthetic: a Brother printer with a Xerox compatible toner related."""
    related = [
        {
            "RelationTypeCode": "consumable",
            "CategoryID": 375,
            "ProductCode": "006R04206",
            "ProductName": "Mono Toner compatible with Brother TN3380",
            "Brand": "Xerox",
        },
        {
            "RelationTypeCode": "consumable",
            "CategoryID": 375,
            "ProductCode": "TN-3380",
            "ProductName": "TN-3380 toner",
            "Brand": "Brother",
        },
    ]
    supplies = icecat.consumables(
        {"GeneralInfo": {"Brand": "Brother"}, "ProductRelated": related}
    )
    assert [(s["code"], s["own"]) for s in supplies] == [
        ("TN-3380", True),
        ("006R04206", False),
    ]


def test_epson_ecotank_is_an_ink_tank_without_duplex():
    epson = icecat.parse(fixture_json("icecat_epson_c11cl63409.json")["data"])
    assert epson["technology"] == "inkjet"
    assert epson["ink_tank"] is True
    assert epson["duplex_print"] is False
    assert epson["ethernet"] is False


def test_manual_duplex_does_not_count():
    hp = icecat.parse(fixture_json("icecat_hp_4zb95a.json")["data"])
    assert hp["release_date"] == "2019-07-01"
    assert hp["end_of_life"] == "2030-06-01"
    # the Color Laser 150nw "duplex" asks you to turn the stack over
    assert hp["duplex_print"] is False


def test_enterprise_ranges_are_out_of_scope(brother):
    enterprise = brother | {"title": "HP Color LaserJet Enterprise M455dn"}
    assert icecat.in_scope(enterprise) == "Enterprise range"
    scanner = brother | {"category": "Scanners"}
    assert icecat.in_scope(scanner) == "category Scanners"


def test_lookup_by_icecat_id_uses_the_account(monkeypatch):
    monkeypatch.setenv("ICECAT_USER", "someone")
    monkeypatch.setenv("ICECAT_KEY", "token")
    body = fixture_json("icecat_brother_dcp-l3550cdw.json")
    fetcher = FakeFetcher(api=lambda params: (200, body))
    result = icecat.lookup(fetcher, icecat_id=59243891)
    assert result.record is not None
    assert result.reason == ""
    assert fetcher.calls == [
        {"UserName": "someone", "Language": "en", "icecat_id": "59243891"}
    ]


@pytest.mark.usefixtures("no_icecat_account")
@pytest.mark.parametrize(
    ("status", "reason"),
    [(403, "not in Open Icecat"), (404, "not in Icecat"), (500, "Icecat answered 500")],
)
def test_lookup_failures(status, reason):
    fetcher = FakeFetcher(api=lambda params: (status, {}))
    result = icecat.lookup(fetcher, brand="Lexmark", code="36S0300")
    assert result.record is None
    assert result.reason == reason
    assert fetcher.calls[0]["UserName"] == icecat.DEMO_USER
