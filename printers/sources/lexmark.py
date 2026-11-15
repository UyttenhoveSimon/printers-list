"""Lexmark: not in Open Icecat, so its own spec pages make the record.

Each locale has a sitemap listing ``/printers/printer/<id>/Lexmark-<model>``
pages; the id is shared across locales. The UK page is read once per id for
its part number and its spec table (rows of ``<th>`` / ``<td>`` under section
headings), the other markets reuse them (see ``pages``). Machines Lexmark
sizes for large workgroups are out of scope, like Icecat's enterprise ranges.
"""

import re
from typing import Any

from ..fetch import Fetcher
from ..specs import SCHEMA, decimal, number, upper_bound, whole
from . import Candidate, pages
from .pages import clean, compact

NAME = "lexmark"
LOCALES = {
    "GB": "en_gb",
    "BE": "nl_be",
    "NL": "nl_nl",
    "FR": "fr_fr",
    "DE": "de_de",
    "CH": "de_ch",
    "IT": "it_it",
    "ES": "es_es",
    "US": "en_us",
}
REFERENCE = "GB"
MARKETS = tuple(LOCALES)
SITEMAP = "https://www.lexmark.com/{locale}/sitemap.xml"
PRINTER_PAGE = re.compile(r"/printers/printer/(?P<id>\d+)/(?P<slug>Lexmark-[^/?#]+)$")
PRODUCT_ID = re.compile(r"/printers/printer/(?P<id>\d+)/")
ROW = re.compile(
    r'<th scope="row">\s*(.*?)\s*</th>\s*<td>(.*?)</td>', re.DOTALL | re.IGNORECASE
)
PART_NUMBER = re.compile(r"^\w{5,8}$")
#: height, width and depth
DIMENSIONS = 3


def discover(fetcher: Fetcher, market: str, cache: dict[str, Any]) -> list[Candidate]:
    sitemap = fetcher.text(SITEMAP.format(locale=LOCALES[market]))
    return pages.discover(
        fetcher,
        name=NAME,
        brand="Lexmark",
        market=market,
        reference=market == REFERENCE,
        sitemap=sitemap,
        printer_pages=printer_pages,
        product_id=PRODUCT_ID,
        read_page=read_page,
        cache=cache,
    )


def printer_pages(sitemap: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for url in pages.locs(sitemap):
        match = PRINTER_PAGE.search(url)
        if match:
            found.setdefault(match["id"], url)
    return found


def spec_table(html: str) -> dict[str, str]:
    return {clean(head): clean(value) for head, value in ROW.findall(html)}


def after(label: str, text: str) -> str:
    """The part of "Black: 36 ppm Colour: 30 ppm" that follows ``label``."""
    match = re.search(rf"{label}\s*:?\s*(.*?)(?=\b[A-Z][a-z]+:|$)", text or "")
    return match.group(1) if match else ""


def read_page(html: str, url: str) -> tuple[str, dict[str, Any]] | None:
    spec = spec_table(html)
    code = spec.get("Part no.", "").split(",")[0].strip()
    if not PART_NUMBER.match(code):
        return None
    slug = PRINTER_PAGE.search(url)
    name = slug["slug"].replace("-", " ") if slug else f"Lexmark {code}"
    return code, specifications(spec, name, code)


def flag(value: str | None, yes: tuple[str, ...], no: tuple[str, ...]) -> bool | None:
    if not value:
        return None
    lowered = value.lower()
    if any(word in lowered for word in no):
        return False
    if any(word in lowered for word in yes):
        return True
    return None


def specifications(spec: dict[str, str], name: str, code: str) -> dict[str, Any]:
    technology = spec.get("Print Technology", "")
    function = spec.get("Function", "")
    ports = spec.get("Standard Ports", "")
    scanner = spec.get("Scanner Type / ADF Scan", "")
    speed = spec.get("Print Speed", "")
    size = re.findall(r"\d+(?:\.\d+)?", spec.get("Size (mm - H x W x D)", ""))
    workgroup = spec.get("Workgroup Size", "")
    media = spec.get("Media Sizes Supported", "")
    systems = " ".join(spec.get(k, "") for k in spec if "Operating System" in k)
    return compact(
        {
            "schema": SCHEMA,
            "brand": "Lexmark",
            "name": name,
            "title": f"{name} {technology}".strip(),
            "code": code,
            "category": "Multifunction Printers"
            if "Scan" in function
            else "Laser Printers",
            "workgroup": workgroup or None,
            "technology": "laser"
            if "Laser" in technology
            else technology.lower() or None,
            "color": ("Colour" in technology or "Color" in technology)
            if technology
            else None,
            "duplex_print": flag(
                spec.get("Duplex"),
                ("integrated", "standard", "automatic"),
                ("not", "manual"),
            ),
            "duplex_scan": flag(scanner, ("duplex", "dual", "reversing"), ("simplex",)),
            "scan": "Scanning" in function if function else None,
            "copy": "Copying" in function if function else None,
            "fax": "Faxing" in function if function else None,
            "adf": flag(spec.get("ADF"), ("feeder", "adf"), ("not available",)),
            "adf_capacity": number(spec.get("ADF")),
            "wifi": spec.get("Wireless") == "Yes" or "802.11" in ports or None,
            "ethernet": spec.get("Ethernet Network") == "Yes"
            or "Ethernet" in ports
            or None,
            "usb": spec.get("Direct USB") == "Yes" or "USB" in ports or None,
            "airprint": "AirPrint" in systems or None,
            "mopria": "Mopria" in systems or None,
            "display": bool(spec.get("Display")) or None,
            "touchscreen": spec.get("Touch Screen Display") == "Yes" or None,
            "ppm_black": whole(after("Black", speed)),
            "ppm_color": whole(after("Colour", speed)) or whole(after("Color", speed)),
            "first_page_s": decimal(after("Black", spec.get("Time to First Page", ""))),
            "max_paper": "A3"
            if re.search(r"\bA3\b", media)
            else ("A4" if media else None),
            "paper_input": number(
                after("Standard", spec.get("Paper Input Capacity", ""))
            ),
            "paper_output": number(
                after("Standard", spec.get("Paper Output Capacity", ""))
            ),
            "duty_cycle": number(spec.get("Maximum Monthly Duty Cycle")),
            "monthly_volume": upper_bound(spec.get("Recommended Monthly Page Volume")),
            "noise_db": decimal(
                (
                    re.findall(r"(\d+)\s*dBA\s*\(Print\)", spec.get("Noise Level", ""))
                    or [None]
                )[0]
            ),
            "weight_kg": decimal(spec.get("Weight")),
            "height_mm": float(size[0]) if len(size) == DIMENSIONS else None,
            "width_mm": float(size[1]) if len(size) == DIMENSIONS else None,
            "depth_mm": float(size[2]) if len(size) == DIMENSIONS else None,
            "supplies": spec.get("Laser Cartridge Yields") or None,
        }
    )
