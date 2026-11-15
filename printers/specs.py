"""The fields a printer record has, whatever source filled them.

Icecat, Lexmark's and Epson's spec tables all end up in these keys, so the
page filters them alike and the catalogue can compare two sources field by
field. Readers here turn the sources' text ("250 sheets", "4.2 kg",
"Up to: Black: 36 ppm") into numbers.
"""

import re
from datetime import date

#: bumped when a source's mapping changes; older records are read again
SCHEMA = 3

#: fields a manufacturer's site and Icecat can disagree on, and how near is equal
CHECKED_FIELDS: dict[str, float] = {
    "technology": 0,
    "color": 0,
    "duplex_print": 0,
    "duplex_scan": 0,
    "scan": 0,
    "fax": 0,
    "adf": 0,
    "wifi": 0,
    "ethernet": 0,
    # the ISO/IEC 24734 speed, the one makers quote alike; sheets round it
    "ppm_iso": 1,
}

#: fields a maker's page may fill when Icecat leaves them empty
FILLABLE = (
    "weight_kg",
    "width_mm",
    "depth_mm",
    "height_mm",
    "paper_input",
    "paper_output",
    "adf_capacity",
    "duty_cycle",
    "monthly_volume",
    "noise_db",
    "ppm_black",
    "ppm_color",
    "ppm_iso",
    "first_page_s",
    "print_dpi",
    "scan_dpi",
    "power_w",
    "max_paper",
)

NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def yes(value: str | None) -> bool:
    return value == "Yes"


def present(value: str | None) -> bool:
    """A function the machine has: sources say "No" or leave it out otherwise."""
    return value not in {None, "", "No", "Not supported", "Not Available"}


def number(value: str | None) -> int | None:
    """The first whole number in a text, thousands separators allowed."""
    match = re.search(r"\d[\d,]*", value or "")
    return int(match.group().replace(",", "")) if match else None


def whole(value: str | None) -> int | None:
    """A number such as "24.7 ppm", rounded."""
    found = decimal(value)
    return round(found) if found is not None else None


def decimal(value: str | None) -> float | None:
    match = NUMBER.search(value or "")
    return float(match.group().replace(",", ".")) if match else None


def upper_bound(value: str | None) -> int | None:
    """The top of a range such as "150 - 2500 pages per month"."""
    numbers = [int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", value or "")]
    return max(numbers) if numbers else None


def dmy_date(value: str) -> str | None:
    """Icecat writes dates as dd-mm-yyyy; the catalogue keeps ISO dates."""
    match = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", value or "")
    if not match:
        return None
    day, month, year = (int(part) for part in match.groups())
    return date(year, month, day).isoformat()


def technology(value: str | None) -> str:
    """LED printers are laser printers with an LED array; they are filed together."""
    lowered = (value or "").lower()
    if "laser" in lowered or lowered == "led":
        return "laser"
    if "inkjet" in lowered or "ink" in lowered:
        return "inkjet"
    return lowered or "unknown"


def consumable_kind(name: str) -> str:
    """Toner, drum or ink, from the supply's own name."""
    lowered = name.lower()
    for kind, words in (
        ("drum", ("drum", "imaging unit", "photoconductor")),
        ("toner", ("toner",)),
        ("ink", ("ink", "bottle", "cartridge", "tank")),
    ):
        if any(word in lowered for word in words):
            return kind
    return "supply"


def disagreements(reference: dict, other: dict) -> dict[str, list]:
    """Fields both records fill with values further apart than allowed."""
    differ = {}
    for field, tolerance in CHECKED_FIELDS.items():
        mine, theirs = reference.get(field), other.get(field)
        if mine is None or theirs is None:
            continue
        if isinstance(mine, (bool, str)):
            same = mine == theirs
        else:
            same = abs(mine - theirs) <= tolerance
        if not same:
            differ[field] = [mine, theirs]
    return differ


def out_of_scope(record: dict) -> str:
    """Why a maker-described printer is not for a home or small office, or ``""``.

    Lexmark sizes its machines by workgroup; a large-workgroup one is an
    office fleet's, like Icecat's enterprise ranges.
    """
    if "Large" in (record.get("workgroup") or ""):
        return "large workgroup range"
    return ""


#: ranges built as office copiers: floor-standing, leased, serviced by contract
COPIER_RANGES = re.compile(
    r"imageRUNNER|imagePRESS|TASKalfa|AltaLink|WorkCentre|VersaLink C7|bizhub|"
    r"e-STUDIO|Apeos|ApeosPort|DocuCentre|\bIM C?\d{3,4}|\bMX-[A-Z]?\d{4}|"
    r"\bMP C?\d{4}|Aficio MP|LaserJet Managed|PageWide Managed",
    re.IGNORECASE,
)
#: kilograms from which a printer is not carried to a desk
COPIER_WEIGHT_KG = 50


def office_copier(record: dict) -> bool:
    """Whether a printer is an office copier rather than a home or small-office one.

    Any one sign is enough: a copier range by name, Icecat positioning it for
    enterprises or workgroups, an A3 laser (no home printer is one: they are
    department machines, 20 kg and more), or a weight no one puts on a desk.
    """
    name = f"{record.get('name') or ''} {record.get('title') or ''}"
    a3 = (record.get("max_paper") or "").replace("SR", "").startswith("A3")
    return bool(
        COPIER_RANGES.search(name)
        or record.get("market_positioning") in {"Enterprise", "Workgroup"}
        or (a3 and record.get("technology") == "laser")
        or (record.get("weight_kg") or 0) >= COPIER_WEIGHT_KG
    )
