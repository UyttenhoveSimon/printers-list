"""Canon Asia's product pages (Singapore, then India): they fill what Canon UK leaves.

Canon's Asian sites share one platform, read through `browser.Browser` like
canon.co.uk. Each lists a page per current model in its product sitemaps
(``.../business/imageclass-lbp246dw-ii/main/product``), the spec sheet a
table on the page itself. Asia sells some models under the European code
(LBP246dw II, MF275dw) and others under its own (PIXMA G3010, GX7170), which
Icecat also carries for printers sold there.

A table row is a bold label and its value, or a bold heading over rows of
sub-labels ("Power Consumption" over "Operation: 21 W"), kept as one value.
"""

import re
from functools import cache
from typing import Any

from ..fetch import Reader
from ..specs import decimal, number, upper_bound
from .canon_uk import clean, dimensions, find, first
from .epson import largest_paper
from .pages import compact

NAME = "canon-asia"
#: Canon's sites refuse plain HTTP clients
BROWSER = True
#: what the page states; a printer missing any of them is read
FIELDS = (
    "ppm_iso",
    "ppm_black",
    "print_dpi",
    "first_page_s",
    "paper_input",
    "paper_output",
    "duty_cycle",
    "weight_kg",
    "noise_db",
    "power_w",
    "max_paper",
    "width_mm",
)
#: Singapore first: India's pages are the same, for fewer models
SITEMAPS = tuple(
    f"https://{site}/en/{kind}/sitemap-product.xml"
    for site in ("sg.canon", "in.canon")
    for kind in ("consumer", "business")
)
PRODUCT_PAGE = re.compile(r"/en/(?:consumer|business)/([a-z0-9-]+)/main/product$")
#: words of a page's name that are a range, not a model
RANGE_WORDS = frozenset(
    {"pixma", "maxify", "imageclass", "i", "sensys", "x", "imagerunner", "advance"}
    | {"dx", "selphy", "megatank", "series"}
)
#: a model code: "LBP246dw", "G3010", "C359i"
CODE = r"[a-z]{0,4}\d{3,5}[a-z]*"
#: a code in a printer's name, with the generation that follows it ("MF275dw II")
NAMED_CODE = re.compile(rf"\b({CODE})(?:\s+(II|III|IV))?\b", re.IGNORECASE)
GENERATIONS = frozenset({"ii", "iii", "iv"})
#: the first word of a printer's page name
PRINTER_RANGES = frozenset({"pixma", "maxify", "imageclass", "i", "imagerunner"})
ROW = re.compile(r"<tr>(.*?)</tr>", re.DOTALL)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL)


def codes_in_name(name: str) -> list[str]:
    """The model codes a printer's name holds: "i-SENSYS MF275dw II" is mf275dwii."""
    return [
        (code + (generation or "")).lower()
        for code, generation in NAMED_CODE.findall(name)
    ]


def codes_in_slug(slug: str) -> list[str]:
    """The models a page covers: "imagerunner-advance-dx-4945i-4935i-4925i" is three.

    Only a printer range's pages count: scanners, cameras and imageFORCE
    copiers carry codes too ("imageforce-1440", "as-2600").
    """
    codes: list[str] = []
    if slug.split("-", maxsplit=1)[0] not in PRINTER_RANGES:
        return codes
    for word in slug.split("-"):
        if word in GENERATIONS and codes:
            codes[-1] += word
        elif word not in RANGE_WORDS and re.fullmatch(CODE, word):
            codes.append(word)
    return codes


def key(product: dict[str, Any]) -> str:
    """The first model code in a printer's name."""
    codes = codes_in_name(product.get("name") or "")
    return codes[0] if codes else ""


@cache
def product_pages(reader: Reader) -> dict[str, str]:
    """Model code -> page URL, from every sitemap, read once per run."""
    found: dict[str, str] = {}
    for sitemap in SITEMAPS:
        for url in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", reader.text(sitemap)):
            match = PRODUCT_PAGE.search(url)
            if match:
                for code in codes_in_slug(match.group(1)):
                    found.setdefault(code, url)
    return found


def page_for(product: dict[str, Any], pages: dict[str, str]) -> str | None:
    return next(
        (pages[c] for c in codes_in_name(product.get("name") or "") if c in pages),
        None,
    )


def spec_list(page: str) -> dict[str, str]:
    """Label -> value; a heading's sub-rows are joined under it."""
    found: dict[str, str] = {}
    heading = None
    for row in ROW.findall(page):
        cells = CELL.findall(row)
        if not cells:
            continue
        # labels carry links to the test conditions: "Print Speed ; Click here"
        label = re.split(r"\s*(?:;|Click here)", clean(cells[0]))[0]
        if "<strong>" in cells[0]:
            heading = None if len(cells) > 1 else label
            if len(cells) > 1:
                found.setdefault(label, clean(cells[1]))
        elif heading and len(cells) > 1:
            value = f"{label}: {clean(cells[1])}"
            found[heading] = (
                f"{found[heading]} ; {value}" if heading in found else value
            )
    return found


def tray_sheets(text: str) -> int | None:
    """Standard paper input, whichever way the page writes it.

    "Standard: 650 Sheets" (copiers); "Cassette: 250 sheets ; Multi-Purpose
    Tray: 100 sheets ; Paper Feeder: 550 sheets" (lasers: the optional feeder
    and the maximum left out); "Rear Tray: Plain Paper (A4, 64 g/m²): 100"
    (inkjets: plain paper per tray).
    """
    standard = first(r"Standard:\s*(\d[\d,]*)\s*sheets", text)
    if standard:
        return number(standard)
    plain = re.findall(r"Plain Paper[^:;]*:\s*(\d[\d,]*)(?!\s*-)", text)
    if plain:
        return sum(int(n.replace(",", "")) for n in plain)
    trays = [
        int(count.replace(",", ""))
        for tray, count in re.findall(r"([A-Za-z -]+):\s*(\d[\d,]*)\s*sheets", text)
        if not re.search(r"feeder|maximum|optional", tray, re.IGNORECASE)
    ]
    return sum(trays) if trays else None


def specifications(spec: dict[str, str]) -> dict[str, Any]:
    """The fields Canon Asia's page states, in catalogue terms; silence is unknown."""
    speed = find(spec, "Print Speed")
    # inkjets: "Document (ESAT/Simplex): 24 / 15.5 ipm (Mono/Colour)", ISO's measure
    iso = first(r"ESAT/Simplex\):\s*(\d+(?:\.\d+)?)", speed)
    power = find(spec, "Power Consumption")
    output = find(spec, "Output Tray Capacity", "Paper Output")
    return compact(
        {
            "ppm_iso": round(float(iso)) if iso else None,
            "ppm_black": number(first(r"(\d+)\s*ppm", speed)),
            "print_dpi": number(
                find(spec, "Maximum Print Resolution", "Print Resolution")
            ),
            "first_page_s": decimal(
                first(
                    r"(\d+(?:\.\d+)?)\s*sec",
                    find(spec, "First Print Out", "First-Print-Out"),
                )
            ),
            "paper_input": tray_sheets(
                find(
                    spec,
                    "Input Tray Capacity",
                    "Paper Supply Capacity",
                    "Maximum Capacity",
                )
            ),
            "paper_output": number(first(r"Standard:\s*(\d[\d,]*)", output) or output),
            "monthly_volume": upper_bound(
                find(spec, "Recommended Monthly Print Volume")
            ),
            "duty_cycle": number(find(spec, "Monthly Duty Cycle", "Duty Cycle")),
            "weight_kg": decimal(first(r"(\d+(?:\.\d+)?)\s*kg", find(spec, "Weight"))),
            "noise_db": decimal(
                first(r"(\d+(?:\.\d+)?)\s*dB", find(spec, "Acoustic Noise"))
            ),
            "power_w": decimal(
                first(
                    r"(?:Operation|Operating|Printing|Active)[^;:]*:\s*"
                    r"(?:Approx\.\s*)?(\d+(?:\.\d+)?)\s*W\b",
                    power,
                )
            ),
            "scan_dpi": number(find(spec, "Optical Resolution", "Scan Resolution")),
            "max_paper": largest_paper(
                find(spec, "Paper Size", "Media Size", "Supported Media Sizes")
            ),
            **dimensions(find(spec, "Dimensions")),
        }
    )


def covers(reader: Reader, product: dict[str, Any]) -> bool:
    """Whether Canon Asia has a page for one of the printer's model codes."""
    return page_for(product, product_pages(reader)) is not None


def enrich(fetcher: Reader, product: dict[str, Any]) -> dict[str, Any] | None:
    """Specs for a Canon printer from Canon Asia, or None when it has no page."""
    url = page_for(product, product_pages(fetcher))
    if not url:
        return None
    return specifications(spec_list(fetcher.text(url))) or None
