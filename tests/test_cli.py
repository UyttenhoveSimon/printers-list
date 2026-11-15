import json

import pytest

from printers import cli
from printers.catalog import save


def test_build_writes_the_site_with_compact_records(tmp_path):
    data = tmp_path / "data"
    save(
        data / "products.json",
        {
            "7": {
                "icecat_id": 7,
                "brand": "HP",
                "name": "HP Color LaserJet Pro 3202dw Printer",
                "title": "HP Color LaserJet Pro 3202dw",
                "category": "Laser Printers",
                "gtin": None,
                "duplex_print": True,
                "fax": False,
                "ppm_black": 25,
                "first_seen": "2026-11-15",
                "sightings": {
                    "icecat:ALL": {"date": "2026-11-15", "markets": ["BE"], "url": ""}
                },
            }
        },
    )
    save(
        data / "state.json",
        {
            "lookups": {},
            "caches": {},
            "runs": {"icecat:ALL": "2026-11-15"},
            "started": "2026-11-15",
            "report": {"date": "2026-11-15"},
        },
    )
    out = tmp_path / "site"
    cli.main(["--data", str(data), "build", "--out", str(out)])
    assert (out / "index.html").exists()
    site = json.loads((out / "printers.json").read_text())
    (printer,) = site["printers"]
    assert printer["available"] is True
    assert printer["markets"] == ["BE"]
    assert "fax" not in printer  # false flags are left out
    assert printer["url"].endswith("desc-7.html")
    assert site["updated"] == "2026-11-15"


def test_update_with_no_source_selected(tmp_path, capsys):
    cli.main(["--data", str(tmp_path), "update", "--source", "none"])
    assert "0 Icecat lookups" in capsys.readouterr().out
    assert (tmp_path / "state.json").exists()


def state_with(tmp_path, sources):
    save(
        tmp_path / "state.json",
        {
            "lookups": {},
            "caches": {},
            "runs": {},
            "started": None,
            "report": {"sources": sources},
        },
    )


def test_check_passes_with_known_walls(tmp_path, capsys):
    state_with(
        tmp_path,
        {
            "icecat:ALL": {"status": "ok", "found": 10990},
            "brother:GB": {"status": "walled", "detail": "403"},
        },
    )
    cli.main(["--data", str(tmp_path), "check"])
    assert "walled" in capsys.readouterr().out


def test_check_fails_when_a_working_source_breaks(tmp_path):
    state_with(tmp_path, {"epson:GB": {"status": "empty", "detail": ""}})
    with pytest.raises(SystemExit, match="epson:GB"):
        cli.main(["--data", str(tmp_path), "check"])
