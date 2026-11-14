"""The region a drink record is filed under in the sidebar.

Wines carry a region each country derives its own way (comunidad autónoma,
regione, Anbaugebiet, borrégió …). A drink takes, in this order:

1. the `region` a curator pin of `areas.json` states;
2. the region of the wine record whose area it shares (a `ref:` unit —
   Aguardente de Vinho Douro is filed where Douro is);
3. the administrative region its drawn NUTS units all lie in, for the
   countries whose facet is an administrative tier (`nuts_regions.json`);
4. the country's own name — the label the wine pipelines already use for a
   record of no single region ("Italia" for Grappa, "Österreich" for
   Inländerrum), which the titles drop (`_COUNTRY_AS_REGION`).
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
NUTS_REGIONS_PATH = HERE / "nuts_regions.json"

COUNTRY_LABEL: dict[str, str] = {
    "fr": "France", "es": "España", "pt": "Portugal", "it": "Italia", "at": "Österreich",
    "de": "Deutschland", "si": "Slovenija", "hr": "Hrvatska", "hu": "Magyarország",
    "ro": "România", "bg": "България", "gr": "Ελλάδα", "cy": "Κύπρος", "sk": "Slovensko",
    "cz": "Česko", "lu": "Luxembourg", "be": "België", "nl": "Nederland", "mt": "Malta",
    "gb": "United Kingdom",
}

# the UK wine records' region is the home nation; a county is filed under its
UK_COUNTY_NATION = "England"

_TABLE: dict[str, str] | None = None


def nuts_regions() -> dict[str, str]:
    global _TABLE
    if _TABLE is None:
        data = json.loads(NUTS_REGIONS_PATH.read_text(encoding="utf-8"))
        _TABLE = {k: v for k, v in data.items() if not k.startswith("_")}
    return _TABLE


def region_of_nuts(code: str) -> str:
    """The table region a NUTS unit lies in ("" for a unit above the table's
    tier — a whole country — or of a country without a table)."""
    table = nuts_regions()
    for n in (4, 3):
        if len(code) >= n and code[:n] in table:
            return table[code[:n]]
    return ""


def derive_region(record: dict, units: list[dict], pin: dict | None,
                  region_by_slug: dict[str, str]) -> str:
    country = record.get("country") or ""
    if pin and pin.get("region"):
        return pin["region"]
    labels: set[str] = set()
    for unit in units or []:
        if unit.get("kind") == "country" and unit.get("code") != country:
            # the part of a shared GI that lies in another state (the island
            # of Ireland for a UK record) does not decide the record's region
            continue
        if unit.get("kind") == "uk":
            labels.add(unit["name"] if unit.get("level") == "country" else UK_COUNTY_NATION)
        elif unit.get("kind") == "ref":
            labels.add(region_by_slug.get(unit.get("slug") or "", ""))
        elif unit.get("kind") == "nuts":
            labels.add(region_of_nuts(unit.get("code") or ""))
        elif unit.get("kind") in ("lau", "lauid") and unit.get("nuts"):
            labels.add(region_of_nuts(unit["nuts"]))
        else:
            labels.add("")
    if len(labels) == 1:
        label = next(iter(labels))
        if label:
            return label
    return COUNTRY_LABEL.get(country, "")
