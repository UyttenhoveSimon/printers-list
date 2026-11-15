"""HP's shops: the spec sheets of the printers they sell, read through a browser.

hp.com answers only clients that behave like a browser, so these pages go
through `browser.Browser`. Each shop lists its product URLs in a plain text
file; a printer's URL ends in its SKU (``...-4zb95a-b19``). The page embeds
HP's spec sheet as JSON (``technical_specifications``: groups of name and
value), which fills the fields Icecat leaves empty for an HP printer.

Each shop sells its own range, so the English shops come first, then the
German, French and Spanish ones, whose labels are mapped to the English ones
(paired by their values on SKUs two shops share) and whose figures are
written the local way ("80.000 Seiten", "8,56 kg").
"""

import json
import re
from functools import cache
from typing import Any

from ..fetch import FetchError, Reader
from ..specs import decimal, number, upper_bound
from .epson import dimensions, largest_paper
from .pages import compact

NAME = "hp-shop"
#: hp.com refuses plain HTTP clients
BROWSER = True
#: what the page states; a printer missing any of them is read
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
    "max_paper",
)
LIST_URL = "https://www.hp.com/{locale}/shop/media/facets_url/products_url_{suffix}.txt"
#: the shops read, English ones first: a SKU takes its first shop's page
LOCALES = ("gb-en", "ca-en", "in-en", "de-de", "ch-de", "fr-fr", "es-es")
#: HP's German, French and Spanish labels, as the English ones (HP writes
#: some with an en dash, kept as \u2013)
LABELS = {
    "Gewicht": "Weight",
    "Poids": "Weight",
    "Peso": "Weight",
    "Mindestabmessungen (B x T x H)": "Dimensions (W x D x H)",
    "Dimensions minimales (L x P x H)": "Dimensions (W x D x H)",
    "Dimensiones mínimas (ancho x fondo x alto)": "Dimensions (W x D x H)",
    "Papierzuführungskapazität": "Input capacity",
    "Capacité d'entrée papier": "Input capacity",
    "Capacidad de entrada": "Input capacity",
    "Papierhandhabung \u2013 Papiereingabe, Standard": "Paper handling input, standard",
    "Gestion d'introduction du papier, standard": "Paper handling input, standard",
    "Manipulación del papel de entrada, estándar": "Paper handling input, standard",
    "Papierhandhabung \u2013 Papierausgabe, Standard": (
        "Paper handling output, standard"
    ),
    "Gestion de sortie du papier, standard": "Paper handling output, standard",
    "Manipulación del papel de salida, estándar": "Paper handling output, standard",
    "Capacité du bac d'alimentation automatique": "Automatic document feeder capacity",
    "Capacidad del alimentador automático de documentos": (
        "Automatic document feeder capacity"
    ),
    "Druckleistung (monatlich, A4)": "Duty cycle (monthly, A4)",
    "Cycle d'utilisation (mensuel, lettre)": "Duty cycle (monthly, A4)",
    "Ciclo de trabajo (mensual, carta)": "Duty cycle (monthly, A4)",
    "Empfohlenes monatliches Druckvolumen": "Recommended monthly page volume",
    "Volume de pages mensuel recommandé": "Recommended monthly page volume",
    "Volumen de páginas mensuales recomendado": "Recommended monthly page volume",
    "Druckgeschwindigkeit Schwarzweiß (ISO, A4)": "Print speed black (ISO, A4)",
    "Velocidad de impresión en blanco y negro (ISO, A4)": (
        "Print speed black (ISO, A4)"
    ),
    "Ausgabe der ersten Seite schwarzweiß (A4, betriebsbereit)": (
        "First page out black (A4, ready)"
    ),
    "Délai d'impression de la première page noire (A4, prêt)": (
        "First page out black (A4, ready)"
    ),
    "Primera página en blanco y negro (A4, listo)": "First page out black (A4, ready)",
    "Druckqualität schwarzweiß (optimal)": "Print quality black (best)",
    "Resolución de escaneo, óptica": "Scan resolution, optical",
    "Energieverbrauch": "Power consumption",
    "Consommation électrique": "Power consumption",
    "Consumo energético": "Power consumption",
    "Typischer Stromverbrauch (TEC) \u2013 Nummer": (
        "Typical electricity consumption (TEC) number"
    ),
    "Numéro de consommation d'électricité typique": (
        "Typical electricity consumption (TEC) number"
    ),
    "Número de consumo eléctrico típico (TEC)": (
        "Typical electricity consumption (TEC) number"
    ),
    "Unterstützte Medienformate": "Media sizes supported",
    "Formats de supports pris en charge": "Media sizes supported",
    "Tamaños de soportes compatibles": "Media sizes supported",
}
#: HP's local sheets keep some values in English ("Up to 3,000 pages")
ENGLISH_VALUE = re.compile(r"\b(?:up to|pages|sheets|watts)\b", re.IGNORECASE)
PRINTER_URL = re.compile(
    r"^https://www\.hp\.com/[a-z-]+/shop/products/printers/"
    r"[a-z0-9-]+?-(?P<sku>[a-z0-9]{6})(?:-[a-z0-9]{3})?/?$"
)
#: the spec sheet sits in a JavaScript string, its quotes escaped
SPECS_KEY = 'technical_specifications\\":'


def key(product: dict[str, Any]) -> str:
    """HP's SKU without its localisation: ``58D77A#B19`` is ``58D77A``."""
    return (product.get("code") or "").split("#")[0].upper()


def list_url(locale: str) -> str:
    return LIST_URL.format(locale=locale, suffix=locale.replace("-", "_"))


@cache
def product_urls(fetcher: Reader) -> dict[str, str]:
    """SKU -> page URL, from every shop's list that answers, read once per run.

    A shop that refuses or fails is skipped; only when none answers is it an
    error.
    """
    found: dict[str, str] = {}
    errors = []
    for locale in LOCALES:
        try:
            body = fetcher.text(list_url(locale))
        except FetchError as error:
            errors.append(error)
            continue
        for line in body.split():
            match = PRINTER_URL.match(line.strip())
            if match:
                found.setdefault(match["sku"].upper(), line.strip())
    if len(errors) == len(LOCALES):
        raise errors[0]
    return found


def english_figures(value: str) -> str:
    """Write "80.000 Seiten" as "80000 Seiten" and "8,56 kg" as "8.56 kg"."""
    if ENGLISH_VALUE.search(value):
        return value
    value = re.sub(r"\b([1-9]\d{0,2})[.\u202f\u00a0 ](\d{3})(?!\d)", r"\1\2", value)
    return re.sub(r"(?<=\d),(?=\d)", ".", value)


def spec_sheet(html: str, *, english: bool = True) -> dict[str, str]:
    """HP's spec names and values, flattened; empty when the page has none.

    A sheet from a German, French or Spanish shop (``english=False``) comes
    back under the English labels, its figures written the English way.
    """
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
            if isinstance(spec.get("value"), str) and isinstance(spec.get("name"), str):
                # footnote marks ("70.9 kg [9]") are not figures
                value = re.sub(r"\s*\[\d+\]", "", spec["value"])
                name = spec["name"].strip()
                if not english:
                    name, value = LABELS.get(name, name), english_figures(value)
                sheet.setdefault(name, value)
    return sheet


def watts(text: str | None) -> float | None:
    """Power while printing, "Active Printing: 282 W" or "900 watts (printing)".

    A sheet that gives only ready, sleep and off figures says nothing of it.
    """
    match = re.search(
        r"(?:Printing|Drucken|Druckbetrieb|Impression|Impresión):\s*(\d+(?:\.\d+)?)\s*W"
        r"|(\d+(?:\.\d+)?)\s*(?:watts?|vatios)\s*\((?:printing|impression|impresión)",
        text or "",
        re.IGNORECASE,
    )
    return float(match.group(1) or match.group(2)) if match else None


def specifications(sheet: dict[str, str]) -> dict[str, Any]:
    """The fields HP's sheet states, in catalogue terms; silence is unknown."""
    tec = re.search(
        r"(\d+(?:\.\d+)?)\s*kWh",
        sheet.get("Typical electricity consumption (TEC) number", ""),
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
    english = re.search(r"/[a-z]{2}-en/", url) is not None
    return specifications(spec_sheet(fetcher.text(url), english=english)) or None
