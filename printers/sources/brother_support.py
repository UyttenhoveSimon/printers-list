"""Brother's support portal: the spec pages that brother.* will not serve us.

support.brother.com allows crawlers (its robots.txt shuts out only a few
named bots) and publishes each model family's user-guide specifications. It
fills the fields Icecat leaves empty for a Brother printer: weight, noise,
paper trays, ADF capacity.

One page covers a family; a cell lists values per model group:
"DCP-L3555CDW/MFC-L3740CDW 20.0 kg MFC-L3740CDWE 20.2 kg". The value kept is
the one whose group names the model; a cell without groups applies to all.
"""

import re
from typing import Any

from ..fetch import Fetcher
from ..specs import decimal, number
from .pages import clean, compact

NAME = "brother-support"
#: the fields this portal can fill
FIELDS = ("weight_kg", "noise_db", "paper_input", "paper_output", "adf_capacity")
SPEC_URL = "https://support.brother.com/g/b/spec.aspx?c=gb&lang=en&prod={slug}_eu"
MODEL = re.compile(r"\b(?:DCP|MFC|HL)-[A-Z0-9]+\b")
#: a run of model codes joined by slashes, then the value that applies to them
GROUP = re.compile(r"((?:(?:DCP|MFC|HL)-[A-Z0-9]+/?)+)\s+")
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL)
CELL = re.compile(r"<t[hd][^>]*>(.*?)</t[hd]>", re.DOTALL)


def model_of(name: str) -> str:
    """The model code in a printer's name: "Brother MFC-L3740CDW printer"."""
    match = MODEL.search(name or "")
    return match.group() if match else ""


def spec_url(model: str) -> str:
    return SPEC_URL.format(slug=model.replace("-", "").lower())


def rows(html: str) -> list[list[str]]:
    out = []
    for row in ROW.findall(html):
        cells = [clean(cell) for cell in CELL.findall(row)]
        if any(cells):
            out.append([cell for cell in cells if cell])
    return out


def value_for(text: str, model: str) -> str:
    """The part of a multi-model cell that applies to ``model``."""
    groups = list(GROUP.finditer(text))
    if not groups:
        return text
    for here, after in zip(groups, [*groups[1:], None], strict=True):
        if model in here.group(1).split("/"):
            end = after.start() if after else len(text)
            return text[here.end() : end].strip()
    return ""


def applies(label: str, model: str) -> bool:
    """A row whose label names its models, "ADF ( DCP-L3555CDW/... )", may skip ours."""
    named = re.search(r"\(\s*((?:(?:DCP|MFC|HL)-[A-Z0-9]+/?)+)\s*\)", label)
    return not named or model in named.group(1).split("/")


def specifications(html: str, model: str) -> dict[str, Any]:
    """The fields the page states for ``model``; silence stays unknown."""
    found: dict[str, Any] = {}
    in_tray = False
    for cells in rows(html):
        label, rest = cells[0], " ".join(cells[1:])
        line = " ".join(cells)
        if not applies(label, model):
            continue
        if label.startswith("Weight"):
            found.setdefault("weight_kg", decimal(value_for(rest, model)))
        elif "Sound Pressure" in line and "Printing" in line and "Quiet" not in line:
            pressure = re.search(r"(\d+(?:\.\d+)?)\s*dB", value_for(line, model))
            if pressure:
                found.setdefault("noise_db", float(pressure.group(1)))
        elif label.startswith("Automatic Document Feeder"):
            found.setdefault("adf_capacity", number(value_for(rest, model)))
        elif "Face Down Output Tray" in line:
            found.setdefault("paper_output", number(value_for(rest, model)))
        if "Paper Tray (Standard)" in line:
            in_tray = True
        if in_tray and "Maximum Paper Capacity" in line:
            found.setdefault("paper_input", number(value_for(line, model)))
            in_tray = False
    return compact(found)


def enrich(fetcher: Fetcher, product: dict[str, Any]) -> dict[str, Any] | None:
    """Specs for a Brother printer from the support portal, or None if no page."""
    model = model_of(product.get("name", ""))
    if not model:
        return None
    return specifications(fetcher.text(spec_url(model)), model) or None
