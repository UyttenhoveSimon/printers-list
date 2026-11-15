"""Kyocera Europe's product pages: power, size and paper capacity Icecat lacks.

The English site answers plain HTTP. Its sitemap lists a page per printer and
multifunction model, named after it (``.../printers/ECOSYSPA2100CWX.html``).
A page states a few figures in an icon row (speed, resolution, size,
weight) and the rest in tabs, both as a title over a value.
"""

import html
import re
from functools import cache
from typing import Any

from ..fetch import Reader
from ..specs import decimal, number
from .canon_uk import dimensions, find, first, sheets
from .pages import compact

NAME = "kyocera"
#: what the page states; a printer missing any of them is read
FIELDS = (
    "ppm_black",
    "print_dpi",
    "weight_kg",
    "width_mm",
    "power_w",
    "paper_input",
    "paper_output",
    "max_paper",
)
SITEMAP = "https://www.kyoceradocumentsolutions.eu/sitemap.xml"
PRODUCT_PAGE = re.compile(r"/en/products/(?:printers|mfp)/([A-Za-z0-9-]+)\.html$")
#: the ranges in front of a model code, dropped to match names with or without
RANGES = re.compile(r"^(ecosys|taskalfa)")
#: a model code: "PA2100cwx", "M5526cdw", "2554ci"
MODEL = re.compile(
    r"\b(?:ECOSYS\s+|TASKalfa\s+)?([A-Z]{0,3}\d{3,5}[A-Z]*)\b", re.IGNORECASE
)
ICON = re.compile(
    r'l-icon-row__title[^>]*>(.*?)</h5>.*?l-icon-row__text">(.*?)</p>', re.DOTALL
)
TAB = re.compile(
    r'c-title--h5 c-text--spacer-half-xxs">\s*(.*?)\s*</div>\s*'
    r'<div class="c-text c-text--minor">(.*?)</div>',
    re.DOTALL,
)


def normal(text: str) -> str:
    return RANGES.sub("", re.sub(r"[^a-z0-9]", "", text.lower()))


def key(product: dict[str, Any]) -> str:
    """The model code in a printer's name: "KYOCERA ECOSYS PA2100cwx" is pa2100cwx."""
    match = MODEL.search(product.get("name") or "")
    return normal(match.group(1)) if match else ""


@cache
def product_pages(reader: Reader) -> dict[str, str]:
    """Model code -> page URL, read once per run."""
    found: dict[str, str] = {}
    for url in re.findall(r"<loc>([^<]+)</loc>", reader.text(SITEMAP)):
        match = PRODUCT_PAGE.search(url)
        if match:
            found.setdefault(normal(match.group(1)), url)
    return found


def clean(fragment: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", fragment))
    return re.sub(r"\s+", " ", text).strip()


def spec_list(page: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for label, value in [*ICON.findall(page), *TAB.findall(page)]:
        found.setdefault(clean(label), clean(value))
    return found


def specifications(spec: dict[str, str]) -> dict[str, Any]:
    """The fields Kyocera's page states, in catalogue terms; silence is unknown."""
    power = first(r"Printing:\s*(\d+(?:[.,]\d+)?)\s*W", find(spec, "Power consumption"))
    paper = first(r"\bA(\d)\b", find(spec, "General type"))
    return compact(
        {
            "ppm_black": number(find(spec, "Engine speed")),
            "print_dpi": number(find(spec, "Resolution")),
            "weight_kg": decimal(
                first(r"(\d+(?:[.,]\d+)?)\s*kg", find(spec, "Weight"))
            ),
            "power_w": decimal(power.replace(",", ".") if power else None),
            "paper_input": sheets(find(spec, "Input capacity")),
            "paper_output": number(
                find(spec, "Max. output capacity", "Output capacity")
            ),
            "max_paper": f"A{paper}" if paper else None,
            **dimensions(find(spec, "Dimensions")),
        }
    )


def covers(reader: Reader, product: dict[str, Any]) -> bool:
    """Whether Kyocera Europe has a page for the printer's model."""
    return key(product) in product_pages(reader)


def enrich(fetcher: Reader, product: dict[str, Any]) -> dict[str, Any] | None:
    """Specs for a Kyocera printer from Kyocera Europe, or None without a page."""
    url = product_pages(fetcher).get(key(product))
    if not url:
        return None
    return specifications(spec_list(fetcher.text(url))) or None
