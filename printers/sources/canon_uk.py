"""Canon UK's spec pages, read through a browser: they fill Canon's gaps.

Canon's sites refuse plain HTTP clients, so these pages go through
`browser.Browser`. The UK sitemap lists a ``.../<model>/specifications/``
page per model or series (``pixma-g3510``, ``i-sensys-lbp361dw``,
``pixma-ts6050-series``); each is a list of label and value pairs. A page
named after a series also covers its siblings: the TS6050 series is the
TS6050, TS6051 and TS6052.
"""

import html
import re
from functools import cache
from typing import Any

from ..fetch import Reader
from ..specs import decimal, number, upper_bound
from .epson import largest_paper
from .pages import compact

NAME = "canon-uk"
#: canon.co.uk refuses plain HTTP clients
BROWSER = True
#: what the page states; a printer missing any of them is read
FIELDS = (
    "ppm_iso",
    "ppm_black",
    "print_dpi",
    "first_page_s",
    "paper_input",
    "paper_output",
    "monthly_volume",
    "duty_cycle",
    "weight_kg",
    "noise_db",
    "power_w",
    "tec_kwh",
    "max_paper",
    "width_mm",
)
SITEMAP = "https://www.canon.co.uk/sitemap/sitemap-default-uk-en.xml"
SPEC_PAGE = re.compile(r"/([a-z0-9_-]+)/specifications/$", re.IGNORECASE)
#: the ranges Canon names its printers by, then the model: "PIXMA G3570"
MODEL = re.compile(
    r"\b(pixma|maxify|i-sensys x|i-sensys|imageclass|selphy)\s+"
    r"(?:pro-)?([a-z]{0,4}-?\d{2,5}[a-z]*)\b",
    re.IGNORECASE,
)
PAIR = re.compile(
    r'list-key[^"]*">(.*?)</div><div class="product-specification-detail__'
    r'value-wrapper"><div[^>]*list-value[^"]*">(.*?)</div></div>',
    re.DOTALL,
)
SERIES = "series"


def normal(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def key(product: dict[str, Any]) -> str:
    """The range and model in a printer's name: "pixmag3570"."""
    match = MODEL.search(product.get("name") or "")
    return normal(match.group(1) + match.group(2)) if match else ""


@cache
def spec_pages(reader: Reader) -> dict[str, str]:
    """Model (or series stem, with ``*``) -> spec page URL, read once per run."""
    found: dict[str, str] = {}
    for url in re.findall(r"<loc>([^<]+)</loc>", reader.text(SITEMAP)):
        match = SPEC_PAGE.search(url)
        if not match or "photo-paper" in url:
            continue
        slug = match.group(1).lower()
        if slug.endswith(SERIES):
            # the TS6050 series: any TS605x
            found.setdefault(normal(slug.removesuffix(SERIES))[:-1] + "*", url)
        else:
            found.setdefault(normal(slug), url)
    return found


def page_for(model: str, pages: dict[str, str]) -> str | None:
    return pages.get(model) or pages.get(model[:-1] + "*")


def clean(fragment: str) -> str:
    fragment = re.sub(r"<sup>.*?</sup>", "", fragment, flags=re.DOTALL)
    fragment = re.sub(r"<br\s*/?>", "; ", fragment)
    text = html.unescape(re.sub(r"<[^>]+>", " ", fragment))
    return re.sub(r"\s+", " ", text).strip()


def spec_list(page: str) -> dict[str, str]:
    """Label -> value; a label met twice keeps both values, joined."""
    found: dict[str, str] = {}
    for raw_label, raw_value in PAIR.findall(page):
        label, value = clean(raw_label), clean(raw_value)
        found[label] = f"{found[label]} ; {value}" if label in found else value
    return found


def find(spec: dict[str, str], *labels: str) -> str:
    """The value of the first label that starts with one of ``labels``."""
    for wanted in labels:
        for label, value in spec.items():
            if label.lower().startswith(wanted.lower()):
                return value
    return ""


def sheets(text: str) -> int | None:
    """Standard trays: "550-sheet cassette ; 100-sheet multi-purpose tray" is 650."""
    trays = [int(n.replace(",", "")) for n in re.findall(r"(\d[\d,]*)-sheet", text)]
    return sum(trays) if trays else number(text)


def dimensions(text: str) -> dict[str, float]:
    """Read "430 mm x 464 mm x 370 mm" or "approx. 445 x 330 x 163 mm"."""
    figures = re.findall(r"\d+(?:\.\d+)?", text.replace("mm", ""))
    if "mm" not in text or len(figures) < 3:  # noqa: PLR2004 width, depth, height
        return {}
    width, depth, height = (float(n) for n in figures[:3])
    return {"width_mm": width, "depth_mm": depth, "height_mm": height}


def first(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1) if match else None


def specifications(spec: dict[str, str]) -> dict[str, Any]:
    """The fields Canon's page states, in catalogue terms; silence is unknown."""
    speed = find(spec, "Mono Print Speed", "Print Speed")
    weight = first(r"(\d+(?:\.\d+)?)\s*kg", find(spec, "Weight") + " ; ")
    noise = find(spec, "Noise Levels", "Acoustic Noise")
    # sound pressure, as Icecat gives it; Canon lists sound power first
    pressure = noise.lower().split("pressure", 1)[-1]
    scan = find(spec, "Scanner Resolution", "Scan Resolution")
    return compact(
        {
            "ppm_iso": round(float(n))
            if (n := first(r"(\d+(?:\.\d+)?)\s*ipm", speed))
            else None,
            "ppm_black": number(first(r"(\d+)\s*ppm", speed)),
            "print_dpi": number(find(spec, "Print Resolution")),
            "first_page_s": decimal(
                first(
                    r"(\d+(?:\.\d+)?)\s*sec",
                    find(spec, "First-Print-Out", "First Print Out"),
                )
            ),
            "paper_input": sheets(
                find(
                    spec, "Paper Input (Standard)", "Maximum Paper Input", "Paper Input"
                )
            ),
            "paper_output": number(find(spec, "Paper Output")),
            "monthly_volume": upper_bound(
                find(spec, "Recommended Monthly Print Volume")
            ),
            "duty_cycle": number(find(spec, "Duty Cycle")),
            "weight_kg": decimal(weight),
            "noise_db": decimal(first(r"(\d+(?:\.\d+)?)\s*dB", pressure)),
            "power_w": decimal(
                first(
                    r"(?:Active|Printing|Copying|Operating)[^;:]*:\s*(?:Approx\.\s*)?(\d+(?:\.\d+)?)\s*W",
                    find(spec, "Power Consumption"),
                )
            ),
            "tec_kwh": decimal(
                first(
                    r"(\d+(?:\.\d+)?)\s*kWh", find(spec, "Typical Electricity", "TEC")
                )
            ),
            "scan_dpi": number(first(r"Optical[^0-9]*(\d[\d,]*)", scan) or scan),
            "max_paper": largest_paper(find(spec, "Media Sizes", "Paper Sizes")),
            **dimensions(
                find(
                    spec,
                    "Dimensions with Trays",
                    "Dimensions (W x D x H)",
                    "Dimensions",
                )
            ),
        }
    )


def covers(reader: Reader, product: dict[str, Any]) -> bool:
    """Whether Canon UK has a spec page for the printer's model or series."""
    return page_for(key(product), spec_pages(reader)) is not None


def enrich(fetcher: Reader, product: dict[str, Any]) -> dict[str, Any] | None:
    """Specs for a Canon printer from Canon UK, or None when it has no page."""
    url = page_for(key(product), spec_pages(fetcher))
    if not url:
        return None
    return specifications(spec_list(fetcher.text(url))) or None
