"""Epson Australia's spec pages: power, noise and duty cycle Epson Europe leaves out.

epson.com.au still runs its older site, which answers plain HTTP. Its printer
sitemaps list a ``..._Specs.asp`` page per model, named after it
(``ecotank/ET-2850_Specs.asp``, ``WorkForcePro_WF-M5899_Specs.asp``), and
keep models Europe has dropped. A page is a table of label and value rows,
under headings that changed over the years: labels are matched loosely.
"""

import html
import re
from functools import cache
from typing import Any

from ..fetch import Reader
from ..specs import decimal, number, whole
from .canon_uk import dimensions, first
from .epson import largest_paper
from .pages import compact

NAME = "epson-au"
#: what the page states; a printer missing any of them is read
FIELDS = (
    "power_w",
    "tec_kwh",
    "noise_db",
    "duty_cycle",
    "ppm_iso",
    "paper_input",
    "paper_output",
    "scan_dpi",
    "weight_kg",
    "width_mm",
    "max_paper",
)
#: no sign of sale: the old site keeps models long gone, and Epson's own
#: listing comes from its European sites (``catalog.MAKER_SOURCES``)
listed = None
SITEMAPS = tuple(
    f"https://www.epson.com.au/sitemap_output/sitemap_{name}.xml"
    for name in ("PrintersForHome", "PrintersForBusiness")
)
SPEC_PAGE = re.compile(r"/([A-Za-z0-9_-]+)_Specs\.asp(?:\?|$)")
#: a model in a printer's name: "ET-2850", "WF-M5899", "XP-2200"
MODEL = re.compile(r"(?<![A-Z])([A-Z]{1,3}-[A-Z]?\d{2,5}[A-Z]*)")
#: the same in a page's name, its range run in: "ExpressionHomeXP-2200"
RUN_IN = re.compile(r"([A-Z]{1,3})-([A-Z]?\d{2,5}[A-Z]*)")
#: sound pressure, in dB(A); sound power, in B(A), is a single figure
QUIETEST, LOUDEST = 20, 90
ROW = re.compile(
    r"<tr[^>]*>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*</tr>", re.DOTALL
)
#: longer cells are a whole old-style table in one cell, not a label
LONGEST_LABEL = 60


def models(text: str) -> list[str]:
    return MODEL.findall(re.sub(r"[\u2010-\u2015]", "-", text.upper()))


def key(product: dict[str, Any]) -> str:
    """The first model code in a printer's name: "Epson EcoTank ET-2850" is ET-2850."""
    found = models(product.get("name") or "")
    return found[0] if found else ""


@cache
def spec_pages(reader: Reader) -> dict[str, str]:
    """Model -> spec page URL, read once per run."""
    found: dict[str, str] = {}
    for sitemap in SITEMAPS:
        for url in re.findall(r"<loc>([^<]+)</loc>", reader.text(sitemap)):
            match = SPEC_PAGE.search(url)
            if match:
                for model in page_models(match.group(1)):
                    found.setdefault(model, html.unescape(url))
    return found


def page_models(name: str) -> list[str]:
    """Every reading of the codes in a page's name, as its range runs into them.

    "ExpressionHomeXP-2200" is read XP-2200, but also P-2200 and EXP-2200:
    only the reading a printer's name holds is ever looked up.
    """
    return [
        f"{letters[start:]}-{figures}"
        for letters, figures in RUN_IN.findall(name.upper())
        for start in range(len(letters))
    ]


def page_for(product: dict[str, Any], pages: dict[str, str]) -> str | None:
    return next(
        (pages[m] for m in models(product.get("name") or "") if m in pages), None
    )


def clean(fragment: str) -> str:
    fragment = re.sub(r"<sup>.*?</sup>", "", fragment, flags=re.DOTALL)
    text = html.unescape(re.sub(r"<[^>]+>", " ", fragment))
    return re.sub(r"\s+", " ", text).strip()


def spec_list(page: str) -> dict[str, str]:
    """Upper-cased label -> value; the page repeats its table for phones."""
    found: dict[str, str] = {}
    for raw_label, raw_value in ROW.findall(page):
        label = clean(raw_label).upper()
        if label and len(label) <= LONGEST_LABEL:
            found.setdefault(label, clean(raw_value))
    return found


def find(spec: dict[str, str], *wanted: str, avoid: str = "") -> str:
    """The value of the first label holding one of ``wanted``."""
    for word in wanted:
        for label, value in spec.items():
            if word in label and not (avoid and re.search(avoid, label)):
                return value
    return ""


def input_sheets(text: str) -> int | None:
    """Standard input of plain paper, the trays added up.

    "2 x 250 sheet cassette, ..., Multipurpose Tray: 50 sheets 20 sheets-PGPP"
    is 550: photo paper and envelope counts, what is in brackets (a
    breakdown, an option) and the output tray are left out.
    """
    text = re.sub(r"\([^)]*\)?", "", re.split(r"Output", text, maxsplit=1)[0])
    trays = [int(n) * int(m) for n, m in re.findall(r"(\d+)\s*x\s*(\d+)", text)]
    text = re.sub(r"\d+\s*x\s*\d+", "", text)
    trays += [
        int(n)
        for n in re.findall(r"(\d+)\s*(?:sheets?|pages?)\b(?!-)", text, re.IGNORECASE)
    ]
    return sum(trays) if trays else number(text)


def loudness(text: str) -> float | None:
    """Sound pressure: "Power: 6.6 dB(A) Pressure: 51 dB(A)" is 51."""
    for figure in re.findall(r"\d+(?:\.\d+)?", text):
        if QUIETEST <= float(figure) < LOUDEST:
            return float(figure)
    return None


def specifications(spec: dict[str, str]) -> dict[str, Any]:
    """The fields Epson Australia's page states; silence is unknown."""
    duty = find(spec, "DUTY CYCLE")
    power = find(spec, "POWER CONSUMPTION")
    size = find(spec, "DIMENSIONS", avoid="PACK|CARTON")
    # a printer closed, as Icecat measures it, rather than printing
    size = size.split("Storage", 1)[-1]
    return compact(
        {
            "ppm_iso": whole(
                find(spec, "ISO PRINT SPEED", "PRINTING SPEED ISO", avoid="2-SIDED")
            ),
            "print_dpi": number(find(spec, "PRINT RESOLUTION", "PRINTING RESOLUTION")),
            "weight_kg": decimal(
                first(r"(\d+(?:\.\d+)?)\s*kg", find(spec, "WEIGHT", avoid="PAPER"))
            ),
            "paper_input": input_sheets(
                find(
                    spec,
                    "INPUT PAPER CAPACITY",
                    "PAPER TRAY CAPACITY",
                    "PAPER HOLD CAPACITY",
                    "INPUT",
                )
            ),
            "paper_output": number(find(spec, "OUTPUT TRAY", "OUTPUT PAPER")),
            "adf_capacity": number(find(spec, "ADF") or None),
            # "Up to 500 pages recommended / max 3,000 pages per month"
            "monthly_volume": number(first(r"(\d[\d,]*)\s*pages recommended", duty)),
            "duty_cycle": number(first(r"max\.?\s*(\d[\d,]*)", duty) or duty),
            "power_w": decimal(first(r"(\d+(?:\.\d+)?)\s*W\b", power)),
            "tec_kwh": decimal(first(r"TEC[^0-9]*(\d+(?:\.\d+)?)\s*kWh", power)),
            "noise_db": loudness(find(spec, "NOISE")),
            "scan_dpi": number(find(spec, "OPTICAL RESOLUTION", "SCANNING RESOLUTION")),
            "max_paper": largest_paper(find(spec, "PAPER SIZES", avoid="MAXIMUM")),
            **dimensions(size),
        }
    )


def covers(reader: Reader, product: dict[str, Any]) -> bool:
    """Whether Epson Australia has a spec page for one of the printer's models."""
    return page_for(product, spec_pages(reader)) is not None


def enrich(fetcher: Reader, product: dict[str, Any]) -> dict[str, Any] | None:
    """Specs for an Epson printer from Epson Australia, or None without a page."""
    url = page_for(product, spec_pages(fetcher))
    if not url:
        return None
    return specifications(spec_list(fetcher.text(url))) or None
