"""Which rows of the EU GI register the drinks pipeline holds, who owns a
multi-country one, and what a record is called.

Pure functions over the register listing (`eambrosia_register.load_gi_rows`),
so the selection is testable without the network.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from unidecode import unidecode

from _lib.product_class import classify_register_row

HERE = Path(__file__).resolve().parent
CIDER_GIS_PATH = HERE / "cider_gis.json"

# The countries whose records the map holds through the EU register. The
# United Kingdom (GOV.UK) and Switzerland (OFAG) have registers of their own.
CORPUS_COUNTRIES: tuple[str, ...] = (
    "fr", "es", "pt", "it", "at", "de", "si", "hr", "hu", "ro", "bg", "gr", "cy",
    "sk", "cz", "lu", "be", "nl", "mt",
)

# The register's `countryId` tokens that are the United Kingdom's: the GB rows
# and the island-of-Ireland GIs ("ie,uk(ni)") are read from GOV.UK.
_UK_TOKENS = frozenset({"gb", "uk", "uk(ni)"})

_NON_LATIN_RE = re.compile(r"[Ͱ-ϿЀ-ӿἀ-῿]")
_ALIAS_SPLIT_RE = re.compile(r"\s+/\s+")
_FILE_COUNTRIES_RE = re.compile(r"^(?:PDO|PGI)-([A-Z]{2}(?:\+[A-Z]{2})*)-")


def load_cider_gis(path: Path = CIDER_GIS_PATH) -> dict[str, dict]:
    """The cider / perry GIs of the register, by file number. They are
    Food-class GIs in the catch-all class 1.8 ("Other products of Annex I of
    the Treaty"), which also holds spices and salt, so nothing in the listing
    tells them apart: the list is curated, each entry with the register name
    it was read from."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def countries_of(row: dict) -> list[str]:
    return [c.strip().lower() for c in (row.get("countryId") or "").split(",") if c.strip()]


def file_number_countries(file_number: str) -> list[str]:
    """The country codes a file number spells, in its own order
    ("PGI-BE+NL+FR+DE-01962" → be, nl, fr, de)."""
    m = _FILE_COUNTRIES_RE.match(file_number or "")
    return [c.lower() for c in m.group(1).split("+")] if m else []


def owner_and_aliases(row: dict) -> tuple[str, list[str]]:
    """The corpus country that owns a register row and the other countries it
    is listed under. The owner is the first corpus country of the file number
    (the Maasvallei rule: PDO-BE+NL-02172 is the Belgian record), else of
    `countryId`; the aliases are the remaining corpus countries, in the
    register's order."""
    listed = countries_of(row)
    ordered = [c for c in file_number_countries(row.get("fileName") or "") if c in listed]
    ordered += [c for c in listed if c not in ordered]
    corpus = [c for c in ordered if c in CORPUS_COUNTRIES]
    if not corpus:
        return "", []
    return corpus[0], corpus[1:]


def aliases_of(protected_name: str) -> list[str]:
    """The names a register `protectedName` lists ("Korn / Kornbrand")."""
    return [a.strip() for a in _ALIAS_SPLIT_RE.split(protected_name or "") if a.strip()]


def is_latin(text: str) -> bool:
    return not _NON_LATIN_RE.search(text or "")


def naming(protected_name: str) -> dict:
    """`name` (the first alias, the regulator's own string), `name_latin`
    (the first Latin-script alias when the name is Greek or Cyrillic — the
    register's own transcription), `name_aliases` (the other aliases, search
    keys) and `registered_name` (the whole string)."""
    aliases = aliases_of(protected_name)
    if not aliases:
        return {"name": "", "name_latin": "", "name_aliases": [], "registered_name": ""}
    name = aliases[0]
    name_latin = ""
    if not is_latin(name):
        name_latin = next((a for a in aliases[1:] if is_latin(a)), "")
    return {
        "name": name,
        "name_latin": name_latin,
        "name_aliases": [a for a in aliases[1:] if a != name_latin],
        "registered_name": (protected_name or "").strip(),
    }


def slugify(text: str) -> str:
    s = unidecode(text or "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()


def record_slug(names: dict) -> str:
    """The slug of a drinks record: the Latin form of its name."""
    return slugify(names.get("name_latin") or names.get("name") or "")


def kind_for(product_class: str, gi_type: str) -> str:
    """The stored `kind` token: EDV for every spirit drink (the token the FR
    spirits already carry); DOP / IGP for an aromatised wine or a cider, which
    are PDO / PGI agricultural-product GIs."""
    if product_class == "spirit":
        return "EDV"
    return "DOP" if (gi_type or "").upper() == "PDO" else "IGP"


def select(
    rows: list[dict],
    *,
    cider_file_numbers: set[str] | frozenset[str],
    fr_owned_file_numbers: set[str] | frozenset[str] = frozenset(),
) -> tuple[list[dict], list[dict]]:
    """(entries, skipped): the Registered drink rows of the corpus countries
    as index entries, and the drink rows left to another pipeline with the
    reason. `fr_owned_file_numbers` are the GIs INAO's referentiel carries
    (stage 01d's bindings): they stay with the French stages when France is
    the first country of the file number (Génépi des Alpes, FR+IT)."""
    entries: list[dict] = []
    skipped: list[dict] = []
    for row in rows:
        if (row.get("status") or "") != "Registered":
            continue
        pclass, dcat = classify_register_row(row, cider_file_numbers)
        if not pclass:
            continue
        file_number = row.get("fileName") or ""
        listed = countries_of(row)
        if set(listed) & _UK_TOKENS:
            skipped.append({"file_number": file_number, "name": row.get("protectedName"),
                            "reason": "uk-register"})
            continue
        owner, aliases = owner_and_aliases(row)
        if not owner:
            continue
        # the French stages hold a French GI, and a shared one France filed
        # (PGI-FR+IT-01909 Génépi des Alpes); a shared one another state
        # filed is this pipeline's even when INAO's referentiel lists it
        # (PGI-BE+NL+FR+DE-01962 Genièvre)
        first = (file_number_countries(file_number) or [owner])[0]
        if listed == ["fr"] or (file_number in fr_owned_file_numbers and first == "fr"):
            skipped.append({"file_number": file_number, "name": row.get("protectedName"),
                            "reason": "fr-siqo"})
            continue
        names = naming(row.get("protectedName") or "")
        entries.append({
            "slug": record_slug(names),
            **names,
            "file_number": file_number,
            "id_register": row.get("id"),
            "country": owner,
            "country_aliases": aliases,
            "product_class": pclass,
            "drink_category": dcat,
            "register_category": (row.get("productCategory") or "").strip(),
            "kind": kind_for(pclass, row.get("geographicalIndicatorTypeCode") or ""),
            "gi_type": (row.get("geographicalIndicatorTypeCode") or "").strip(),
            "registration_date": row.get("registrationDate") or "",
            "status": row.get("status") or "",
        })
    entries.sort(key=lambda e: (e["country"], e["slug"]))
    return entries, skipped
