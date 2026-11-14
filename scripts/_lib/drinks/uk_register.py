"""The United Kingdom's spirit drinks, ciders and perries.

The UK left the EU GI scheme: its names are protected under the UK schemes
and listed in the GOV.UK "protected food and drink names" register, the
finder the UK wine pipeline already reads (scripts/gb/00_fetch_data.py). Two
of its registers hold drinks other than wine:

- `spirit-drinks` — Scotch Whisky, Somerset Cider Brandy, the Welsh and
  English whiskies registered under the UK scheme since 2021, and the three
  all-island Irish names (Irish Whiskey, Irish Cream, Irish Poteen), which
  the register lists under the United Kingdom and Ireland;
- `foods-designated-origin-and-geographical-indication`, class 1.8, where
  the ciders and perries sit among spices and salts: told apart by the word
  the English name carries (cider, cyder, perry).

Each entry's content-API document carries the product specification as an
attachment. The register publishes no file number; where the EU register
lists the same name (the pre-2021 registrations) its file number is taken
from there, else the entry has none.

Open Government Licence v3.0 — © Crown copyright, DEFRA.
"""
from __future__ import annotations

import re

import requests
from unidecode import unidecode

from _lib.drinks import index as ix

SEARCH_URL = "https://www.gov.uk/api/search.json"
CONTENT_URL = "https://www.gov.uk/api/content"
SITE = "https://www.gov.uk"
USER_AGENT = "open-wine-map/1.0 (+https://www.openwinemap.com; winemap@devloed.com)"

_FIELDS = ("title,link,protection_type,status,country_of_origin,register,class_category,"
           "date_registration,date_registration_eu")
_CIDER_RE = re.compile(r"\b(cider|cyder|perry)\b", re.I)
_ALIAS_RE = re.compile(r"\s*/\s*")

# The register's category slug ("2-whisky-or-whiskey") → drink category. The
# UK keeps the numbering of Reg. (EC) No 110/2008 Annex II, which differs
# from the EU's 2019/787 list, so the words decide, not the number.
_CATEGORY_WORDS: tuple[tuple[str, str], ...] = (
    ("whisk", "whisky"), ("cider-spirit", "cider-spirit"), ("perry-spirit", "cider-spirit"),
    ("grape-marc", "grape-marc"), ("wine-spirit", "wine-spirit"), ("brandy", "brandy"),
    ("fruit-spirit", "fruit-spirit"), ("rum", "rum"), ("grain-spirit", "grain-spirit"),
    ("gin", "juniper"), ("juniper", "juniper"), ("anis", "aniseed"), ("bitter", "bitter"),
    ("liqueur", "liqueur"),
)


def category_of(class_category: list[str] | None) -> str:
    slug = " ".join(class_category or []).lower()
    for word, category in _CATEGORY_WORDS:
        if word in slug:
            return category
    return "other-spirit"


def naming(title: str) -> dict:
    """`index.naming` over a GOV.UK title, whose aliases are slash-separated
    with or without spaces ("English Whisky/ English Whiskey")."""
    aliases = [re.sub(r"\s+", " ", a).strip() for a in _ALIAS_RE.split(title or "") if a.strip()]
    return ix.naming(" / ".join(aliases))


def _search(session: requests.Session, register: str) -> list[dict]:
    r = session.get(
        SEARCH_URL,
        params={"filter_format": "protected_food_drink_name", "filter_register": register,
                "filter_country_of_origin": "united-kingdom", "count": 1000, "fields": _FIELDS},
        headers={"User-Agent": USER_AGENT}, timeout=60,
    )
    r.raise_for_status()
    return r.json().get("results") or []


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", unidecode(text or "").lower()).strip()


def eu_file_numbers(eu_rows: list[dict]) -> dict[str, str]:
    """normalised alias → EU file number, over the EU register's rows of the
    United Kingdom."""
    out: dict[str, str] = {}
    for row in eu_rows:
        if not set(ix.countries_of(row)) & {"gb", "uk", "uk(ni)"}:
            continue
        for alias in _ALIAS_RE.split(row.get("protectedName") or ""):
            if _norm(alias):
                out.setdefault(_norm(alias), row.get("fileName") or "")
    return out


def entries(session: requests.Session, eu_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """(index entries of the registered UK drinks, the names left out with
    the reason — an application still in assessment)."""
    file_numbers = eu_file_numbers(eu_rows)
    out: list[dict] = []
    pending: list[dict] = []
    hits = [("spirit", h) for h in _search(session, "spirit-drinks")]
    hits += [
        ("cider", h) for h in _search(session, "foods-designated-origin-and-geographical-indication")
        if _CIDER_RE.search(h.get("title") or "")
    ]
    for pclass, hit in hits:
        title = re.sub(r"\s+", " ", hit.get("title") or "").strip()
        if (hit.get("status") or "") != "registered":
            pending.append({"name": title, "status": hit.get("status") or "", "reason": "uk-not-registered"})
            continue
        names = naming(title)
        protection = hit.get("protection_type") or ""
        origin = hit.get("country_of_origin") or []
        file_number = next(
            (file_numbers[_norm(a)] for a in [names["name"], *names["name_aliases"]] if _norm(a) in file_numbers),
            "",
        )
        category = category_of(hit.get("class_category")) if pclass == "spirit" else "cider"
        out.append({
            "slug": ix.record_slug(names),
            **names,
            "file_number": file_number,
            "id_register": None,
            "register": "gov-uk",
            "register_url": SITE + (hit.get("link") or ""),
            "gov_uk_path": hit.get("link") or "",
            "country": "gb",
            "country_aliases": ["ie"] if "ireland" in origin else [],
            "product_class": pclass,
            "drink_category": category,
            "register_category": ", ".join(hit.get("class_category") or []),
            "kind": "EDV" if pclass == "spirit" else ("DOP" if "pdo" in protection else "IGP"),
            "gi_type": "PDO" if "pdo" in protection else ("PGI" if "pgi" in protection else "GI"),
            "registration_date": hit.get("date_registration") or "",
            "eu_registration_date": hit.get("date_registration_eu") or "",
            "status": "Registered",
        })
    out.sort(key=lambda e: e["slug"])
    return out, pending


# an attachment that is the specification itself: not its Welsh translation,
# a decision notice or an amendment notice
_NOT_SPEC_RE = re.compile(
    r"welsh[ _-]+translation|[-_ ]welsh\.pdf$|cymraeg|decision|amendment|notice|\bmap\b", re.I
)
_SPEC_RE = re.compile(r"spec|technical[ _-]?file|pfn-|protected-food-name", re.I)


def spec_attachment(content: dict) -> dict | None:
    """The product-specification PDF among a register entry's attachments."""
    attachments = (content.get("details") or {}).get("attachments") or []
    pdfs = [a for a in attachments if (a.get("content_type") or "") == "application/pdf" and a.get("url")]
    good = [a for a in pdfs if not _NOT_SPEC_RE.search(a.get("url") or "") and not _NOT_SPEC_RE.search(a.get("title") or "")]
    best = [a for a in good if _SPEC_RE.search(a.get("url") or "") or _SPEC_RE.search(a.get("title") or "")]
    pick = (best or good or [None])[0]
    if pick is None:
        return None
    return {"url": pick["url"], "title": (pick.get("title") or "").strip()}


def content(session: requests.Session, path: str) -> dict:
    r = session.get(CONTENT_URL + path, headers={"User-Agent": USER_AGENT}, timeout=60)
    r.raise_for_status()
    return r.json()


# --- boundaries -----------------------------------------------------------------

ONS_FS = "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services"
ONS_LICENSE = (
    "Open Government Licence v3.0 — Source: Office for National Statistics licensed under the "
    "Open Government Licence. Contains OS data © Crown copyright and database right 2025."
)
ONS_LAYERS = {
    "countries.geojson": ("Countries_December_2025_Boundaries_UK_BGC", "CTRY25NM", "CTRY25CD"),
    "counties.geojson": ("Counties_and_Unitary_Authorities_December_2025_Boundaries_UK_BGC",
                         "CTYUA25NM", "CTYUA25CD"),
}


def fetch_boundaries(session: requests.Session, filename: str, names: list[str]) -> dict:
    """The ONS features (generalised, clipped to the coastline, EPSG:4326)
    named `names` of one layer, as a GeoJSON FeatureCollection."""
    service, name_field, code_field = ONS_LAYERS[filename]
    quoted = ",".join("'" + n.replace("'", "''") + "'" for n in names)
    r = session.get(
        f"{ONS_FS}/{service}/FeatureServer/0/query",
        params={"where": f"{name_field} IN ({quoted})", "outFields": f"{code_field},{name_field}",
                "outSR": 4326, "f": "geojson"},
        headers={"User-Agent": USER_AGENT}, timeout=180,
    )
    r.raise_for_status()
    return r.json()
