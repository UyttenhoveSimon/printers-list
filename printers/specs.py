"""The fields a printer record has, whatever source filled them.

Icecat, Lexmark's and Epson's spec tables all end up in these keys, so the
page filters them alike and the catalogue can compare two sources field by
field. Readers here turn the sources' text ("250 sheets", "4.2 kg",
"Up to: Black: 36 ppm") into numbers.
"""

import re
from datetime import date

#: bumped when a source's mapping changes; older records are read again
SCHEMA = 2

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
