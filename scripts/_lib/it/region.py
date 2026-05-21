"""Derive the Italian regione (administrative region) for a DOP/IGP.

Italy has 20 regioni. Most documenti unici embed the regione name
inside section 6 ("Zona geografica delimitata") as either a province
list ("Provincia di …") or a regione header ("Regione TOSCANA",
"nella regione Veneto"). When the documento unico is silent or the
wine is a stub, we fall back to a curated map keyed on the wine's
file_number (PDO-IT-A* / PGI-IT-A* → regione).

The regione is used by stage 03 (wiki frontmatter) and stage 04 (panel
header + regione facet filter). It is also a translation surface in
gettext (`build_labels`) so the regione names here are canonical
Italian forms.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

# Canonical Italian regione names (UN/LOCODE / ISTAT spelling).
REGIONI = (
    "Abruzzo",
    "Basilicata",
    "Calabria",
    "Campania",
    "Emilia-Romagna",
    "Friuli-Venezia Giulia",
    "Lazio",
    "Liguria",
    "Lombardia",
    "Marche",
    "Molise",
    "Piemonte",
    "Puglia",
    "Sardegna",
    "Sicilia",
    "Toscana",
    "Trentino-Alto Adige",
    "Umbria",
    "Valle d'Aosta",
    "Veneto",
)

# Alternate spellings / common variants → canonical name. The keys are
# already normalised (lowercase, no diacritics) so the lookup function
# can match against either form.
_VARIANTS: dict[str, str] = {
    # diacritic-free + common variants
    "emilia romagna": "Emilia-Romagna",
    "emilia-romagna": "Emilia-Romagna",
    "friuli venezia giulia": "Friuli-Venezia Giulia",
    "friuli-venezia giulia": "Friuli-Venezia Giulia",
    "friuli": "Friuli-Venezia Giulia",
    "trentino alto adige": "Trentino-Alto Adige",
    "trentino-alto adige": "Trentino-Alto Adige",
    "trentino": "Trentino-Alto Adige",
    "alto adige": "Trentino-Alto Adige",
    "sudtirol": "Trentino-Alto Adige",
    "sud tirol": "Trentino-Alto Adige",
    "valle d aosta": "Valle d'Aosta",
    "vallee d aoste": "Valle d'Aosta",
    "valle daosta": "Valle d'Aosta",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


_CANON_BY_NORM = {_norm(r): r for r in REGIONI}
_CANON_BY_NORM.update({_norm(k): v for k, v in _VARIANTS.items()})

# Curated file_number → regione fallback, hand-verified against
# it.wikipedia.org / eAmbrosia / the disciplinare for DOPs whose
# documento unico (or MASAF disciplinare) never names the regione in
# machine-parseable form. Interregional DOPs are stored as an ordered
# list (bulk regione first) and collapsed to the primary regione here.
_REGIONE_BY_FILE_NUMBER_PATH = Path(__file__).with_name("regione_by_file_number.json")


def _load_file_number_map() -> dict[str, str]:
    try:
        raw = json.loads(_REGIONE_BY_FILE_NUMBER_PATH.read_text())
    except (OSError, ValueError):
        return {}
    out: dict[str, str] = {}
    for fn, value in raw.items():
        primary = value[0] if isinstance(value, list) else value
        out[fn] = _CANON_BY_NORM.get(_norm(primary), primary)
    return out


_REGIONE_BY_FILE_NUMBER = _load_file_number_map()


def regione_for_file_number(file_number: str) -> str:
    """Curated fallback regione for a DOP/IGP file_number, or '' if unknown."""
    return _REGIONE_BY_FILE_NUMBER.get(file_number or "", "")


def find_regione_in_text(text: str) -> str | None:
    """Scan text for an Italian regione name. Returns the canonical form
    or None. First match wins."""
    if not text:
        return None
    low = " " + _norm(text) + " "
    best: tuple[int, str] | None = None
    for needle, canon in _CANON_BY_NORM.items():
        pos = low.find(" " + needle + " ")
        if pos < 0:
            continue
        # Prefer earliest match (proxy for "introduced first in the
        # section body"). Tie-breaks: longer needle wins (more specific).
        if best is None or pos < best[0] or (pos == best[0] and len(needle) > len(_norm(best[1]))):
            best = (pos, canon)
    return best[1] if best else None


def derive_regione(record: dict, *text_candidates: str) -> str:
    """Resolve the regione for one record. Order of precedence:
    (1) explicit `record['regione']` from prior stage,
    (2) scan provided text candidates in order (section 6 body,
        section 9 body, name),
    (3) curated `regione_by_file_number.json` fallback keyed on
        `record['file_number']`."""
    if record.get("regione"):
        return record["regione"]
    for text in text_candidates:
        hit = find_regione_in_text(text or "")
        if hit:
            return hit
    return regione_for_file_number(record.get("file_number", ""))
