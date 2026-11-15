"""HP's UK shop: the spec sheets of the printers it sells, read through a browser.

hp.com answers only clients that behave like a browser, so these pages go
through `browser.Browser`. The shop lists its product URLs in a plain text
file; a printer's URL ends in its SKU (``...-4zb95a-b19``). The page embeds
HP's spec sheet as JSON (``technical_specifications``: groups of name and
value), which fills the fields Icecat leaves empty for an HP printer. Only
the English shop is read: the labels below are HP's English ones.
"""

import json
import re
from functools import cache
from typing import Any

from ..fetch import Reader
from ..specs import decimal, number, upper_bound
from .epson import dimensions, largest_paper
from .pages import compact

NAME = "hp-shop"
#: hp.com refuses plain HTTP clients
BROWSER = True
FIELDS = (
    "weight_kg",
    "width_mm",
    "paper_input",
    "paper_output",
    "duty_cycle",
    "monthly_volume",
    "ppm_iso",
    "first_page_s",
    "print_dpi",
    "power_w",
    "tec_kwh",
)
LIST_URL = "https://www.hp.com/gb-en/shop/media/facets_url/products_url_gb_en.txt"
PRINTER_URL = re.compile(
    r"^https://www\.hp\.com/[a-z-]+/shop/products/printers/"
    r"[a-z0-9-]+?-(?P<sku>[a-z0-9]{6})(?:-[a-z0-9]{3})?/?$"
)
#: the spec sheet sits in a JavaScript string, its quotes escaped
SPECS_KEY = 'technical_specifications\\":'


def key(product: dict[str, Any]) -> str:
    """HP's SKU without its localisation: ``58D77A#B19`` is ``58D77A``."""
    return (product.get("code") or "").split("#")[0].upper()


@cache
def product_urls(fetcher: Reader) -> dict[str, str]:
    """SKU -> page URL, from the shop's list, read once per run."""
    found: dict[str, str] = {}
    for line in fetcher.text(LIST_URL).split():
        match = PRINTER_URL.match(line.strip())
        if match:
            found.setdefault(match["sku"].upper(), line.strip())
    return found


def spec_sheet(html: str) -> dict[str, str]:
    """HP's spec names and values, flattened; empty when the page has none."""
    start = html.find(SPECS_KEY)
    if start < 0:
        return {}
    start += len(SPECS_KEY)
    depth = 0
    for end in range(start, len(html)):
        if html[end] == "[":
            depth += 1
        elif html[end] == "]":
            depth -= 1
            if depth == 0:
                break
    groups = json.loads(json.loads(f'"{html[start : end + 1]}"'))
    sheet: dict[str, str] = {}
    for group in groups:
        for spec in group.get("technical_specifications", []):
            if isinstance(spec.get("value"), str):
                # footnote marks ("70.9 kg [9]") are not figures
                value = re.sub(r"\s*\[\d+\]", "", spec["value"])
                sheet.setdefault(spec["name"], value)
    return sheet


def watts(text: str | None) -> float | None:
    """Power while printing, "Active Printing: 282 W" or "900 watts (printing)".

    A sheet that gives only ready, sleep and off figures says nothing of it.
    """
    match = re.search(
        r"Printing:\s*(\d+(?:\.\d+)?)\s*W|(\d+(?:\.\d+)?)\s*watts?\s*\(printing",
        text or "",
        re.IGNORECASE,
    )
    return float(match.group(1) or match.group(2)) if match else None


def specifications(sheet: dict[str, str]) -> dict[str, Any]:
    """The fields HP's sheet states, in catalogue terms; silence is unknown."""
    tec = re.search(
        r"([\d.]+)\s*kWh", sheet.get("Typical electricity consumption (TEC) number", "")
    )
    return compact(
        {
            "weight_kg": decimal(sheet.get("Weight")),
            # "Up to 650 sheets": all standard trays; the other label names each
            "paper_input": number(
                sheet.get("Input capacity")
                or sheet.get("Paper handling input, standard")
            ),
            "paper_output": number(sheet.get("Paper handling output, standard")),
            "adf_capacity": number(sheet.get("Automatic document feeder capacity")),
            "duty_cycle": number(sheet.get("Duty cycle (monthly, A4)")),
            "monthly_volume": upper_bound(sheet.get("Recommended monthly page volume")),
            "ppm_iso": number(sheet.get("Print speed black (ISO, A4)")),
            "first_page_s": decimal(sheet.get("First page out black (A4, ready)")),
            "print_dpi": number(sheet.get("Print quality black (best)")),
            "scan_dpi": number(sheet.get("Scan resolution, optical")),
            "power_w": watts(sheet.get("Power consumption")),
            "tec_kwh": float(tec.group(1)) if tec else None,
            "max_paper": largest_paper(sheet.get("Media sizes supported")),
            **dimensions(sheet.get("Dimensions (W x D x H)", "")),
        }
    )


def covers(reader: Reader, product: dict[str, Any]) -> bool:
    """Whether the shop sells the printer: only those have a page to read."""
    return key(product) in product_urls(reader)


def enrich(fetcher: Reader, product: dict[str, Any]) -> dict[str, Any] | None:
    """Specs for an HP printer from the UK shop, or None if it does not sell it."""
    url = product_urls(fetcher).get(key(product))
    if not url:
        return None
    return specifications(spec_sheet(fetcher.text(url))) or None
