"""Specifications from Open Icecat.

Open Icecat is free for the brands that sponsor it (HP, Brother, Epson, Canon,
Kyocera, Xerox...). The JSON API reads one product at a time; it takes the
account named in ``ICECAT_USER`` (plus ``ICECAT_KEY``, the API access token,
when set) and falls back to the public demo account ``openIcecat-live``.
"""

import os
import re
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

from .fetch import Fetcher
from .specs import (
    SCHEMA,
    consumable_kind,
    decimal,
    dmy_date,
    number,
    present,
    technology,
    upper_bound,
    yes,
)

API = "https://live.icecat.biz/api/"
DEMO_USER = "openIcecat-live"

#: Icecat category ids of inkjet, laser and multifunction printers
PRINTER_CATIDS = frozenset({"234", "235", "304"})
#: Icecat categories that hold home and office printers
PRINTER_CATEGORIES = frozenset(
    {
        "Laser Printers",
        "Inkjet Printers",
        "LED Printers",
        "Multifunction Printers",
    }
)
#: titles of machines sold to corporate fleets or print shops, not homes
OUT_OF_SCOPE = re.compile(
    r"\b(Enterprise|Managed|DesignJet|PageWide XL|Production|Large format|"
    r"SureColor|Label|Photo Lab)\b",
    re.IGNORECASE,
)
#: categories of related products that are paper, not ink or toner
PAPER_CATIDS = frozenset({714, 847})


@dataclass(frozen=True)
class Lookup:
    """What Icecat said about one product code."""

    record: dict[str, Any] | None
    reason: str = ""


def features(data: dict[str, Any]) -> dict[str, str]:
    """Flatten the feature groups into name -> presentation value."""
    return {
        feature["Feature"]["Name"]["Value"]: feature["PresentationValue"]
        for group in data.get("FeaturesGroups", [])
        for feature in group.get("Features", [])
    }


def first(spec: dict[str, str], *names: str) -> str | None:
    for name in names:
        if name in spec:
            return spec[name]
    return None


def consumables(data: dict[str, Any]) -> list[dict[str, Any]]:
    """The ink, toner and drums Icecat relates to the printer; paper left out.

    Icecat relates compatible supplies from other brands too (Xerox toner for
    a Brother): each carries its brand, and the printer's own brand comes
    first.
    """
    maker = (data.get("GeneralInfo") or {}).get("Brand", "")
    found: dict[str, dict[str, Any]] = {}
    for related in data.get("ProductRelated") or []:
        if related.get("RelationTypeCode") != "consumable":
            continue
        if related.get("CategoryID") in PAPER_CATIDS:
            continue
        code = related.get("ProductCode") or ""
        name = related.get("ProductName") or code
        brand = related.get("Brand") or ""
        if code and code not in found:
            found[code] = {
                "code": code,
                "name": name,
                "kind": consumable_kind(name),
                "brand": brand,
                "own": brand.lower() == maker.lower(),
            }
    return sorted(found.values(), key=lambda c: (not c["own"], c["kind"], c["code"]))


def parse(data: dict[str, Any]) -> dict[str, Any]:
    """Turn an Icecat data sheet into a catalogue record."""
    info = data["GeneralInfo"]
    spec = features(data)
    title = info.get("Title") or ""
    mobile = spec.get("Mobile printing technologies", "")
    duplex_mode = spec.get("Duplex printing mode", "")
    image = data.get("Image") or {}
    return {
        "schema": SCHEMA,
        "icecat_id": info["IcecatId"],
        "brand": info["Brand"],
        # "HP Color LaserJet Pro 3202dw Printer", where ProductName drops the brand
        "name": info.get("TitleInfo", {}).get("GeneratedIntTitle") or title,
        "title": title,
        "code": info.get("BrandPartCode") or None,
        "gtin": next(iter(info.get("GTIN") or []), None),
        "category": info["Category"]["Name"]["Value"],
        "image": image.get("Pic500x500") or image.get("ThumbPic"),
        "technology": technology(spec.get("Print technology")),
        "led": spec.get("Print technology") == "LED",
        "ink_tank": yes(spec.get("Ink tank system"))
        or bool(re.search(r"EcoTank|Smart Tank|MegaTank|InkBenefit", title)),
        "color": yes(spec.get("Colour")) or "Cyan" in spec.get("Printing colours", ""),
        # a manual duplex asks you to turn the stack over: not what is wanted
        "duplex_print": yes(spec.get("Duplex printing")) and duplex_mode != "Manual",
        "duplex_scan": yes(spec.get("Duplex scanning")),
        "scan": present(spec.get("Scanning")),
        "copy": present(spec.get("Copying")),
        "fax": present(spec.get("Faxing")),
        "adf": yes(spec.get("Auto document feeder (ADF)")),
        "adf_capacity": number(spec.get("Auto document feeder (ADF) input capacity")),
        "borderless": yes(spec.get("Borderless printing")),
        "wifi": yes(spec.get("Wi-Fi")),
        "wifi_direct": yes(spec.get("Wi-Fi Direct")),
        "ethernet": yes(spec.get("Ethernet LAN")),
        "usb": yes(spec.get("USB port")),
        "bluetooth": yes(spec.get("Bluetooth")),
        "nfc": yes(spec.get("Near Field Communication (NFC)")),
        "airprint": "AirPrint" in mobile,
        "mopria": "Mopria" in mobile,
        "display": yes(spec.get("Built-in display")) or present(spec.get("Display")),
        "touchscreen": yes(spec.get("Touchscreen")),
        "ppm_black": number(
            first(
                spec,
                "Print speed (black, normal quality, A4/US Letter)",
                "Print speed (ISO/IEC 24734) black",
            )
        ),
        "ppm_color": number(
            first(
                spec,
                "Print speed (colour, normal quality, A4/US Letter)",
                "Print speed (ISO/IEC 24734) colour",
            )
        ),
        "ppm_iso": number(spec.get("Print speed (ISO/IEC 24734) black")),
        "first_page_s": decimal(spec.get("Time to first page (black, normal)")),
        "print_dpi": number(spec.get("Maximum resolution")),
        "scan_dpi": number(spec.get("Optical scanning resolution")),
        "max_paper": spec.get("Maximum ISO A-series paper size"),
        "paper_input": number(
            first(spec, "Total input capacity", "Maximum input capacity")
        ),
        "paper_output": number(
            first(spec, "Total output capacity", "Maximum output capacity")
        ),
        "trays": number(spec.get("Total number of input trays")),
        "duty_cycle": number(spec.get("Maximum duty cycle")),
        "monthly_volume": upper_bound(spec.get("Recommended duty cycle")),
        "noise_db": decimal(spec.get("Sound pressure level (printing)")),
        "power_w": decimal(spec.get("Power consumption (printing)")),
        "tec_kwh": decimal(
            spec.get("Energy Star Typical Electricity Consumption (TEC)")
        ),
        "weight_kg": decimal(spec.get("Weight")),
        "width_mm": decimal(spec.get("Width")),
        "depth_mm": decimal(spec.get("Depth")),
        "height_mm": decimal(spec.get("Height")),
        "cartridges": number(spec.get("Number of print cartridges")),
        "starter_yield": number(spec.get("Included cartridge capacity (black)")),
        "consumables": consumables(data),
        "market_positioning": spec.get("Market positioning"),
        "release_date": dmy_date(info.get("ReleaseDate", "")),
        "end_of_life": dmy_date(info.get("EndOfLifeDate", "")),
    }


def in_scope(record: dict[str, Any]) -> str:
    """Return why a record is not a home or small-office printer, or ``""``."""
    if record["category"] not in PRINTER_CATEGORIES:
        return f"category {record['category']}"
    match = OUT_OF_SCOPE.search(record["title"])
    if match:
        return f"{match.group()} range"
    return ""


def product_url(icecat_id: int) -> str:
    """Icecat's data sheet page; it redirects to the canonical slug."""
    return f"https://icecat.biz/p/vendorName/mpn/desc-{icecat_id}.html"


def lookup(
    fetcher: Fetcher,
    *,
    icecat_id: int | None = None,
    brand: str = "",
    code: str = "",
    gtin: str = "",
) -> Lookup:
    """Fetch one product by Icecat id, GTIN (EAN), or brand and product code."""
    params = {"UserName": os.environ.get("ICECAT_USER") or DEMO_USER, "Language": "en"}
    if icecat_id is not None:
        params["icecat_id"] = str(icecat_id)
    elif gtin:
        params["GTIN"] = gtin
    else:
        params |= {"Brand": brand, "ProductCode": code}
    token = os.environ.get("ICECAT_KEY")
    headers = {"api-token": token} if token and os.environ.get("ICECAT_USER") else None
    status, body = fetcher.json(API, params, headers)
    if status == HTTPStatus.OK and "data" in body:
        record = parse(body["data"])
        return Lookup(record, in_scope(record))
    if status == HTTPStatus.FORBIDDEN:
        # the brand does not sponsor Open Icecat: only Full Icecat has it
        return Lookup(None, "not in Open Icecat")
    if status == HTTPStatus.NOT_FOUND:
        return Lookup(None, "not in Icecat")
    return Lookup(None, f"Icecat answered {status}")
