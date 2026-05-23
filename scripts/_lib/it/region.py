"""Derive the Italian regione (administrative region) for a DOP/IGP.

Italy has 20 regioni. The robust signal is the wine's **provinces and
communes**, enumerated in the documento unico's section 6 ("Zona
geografica delimitata") / the MASAF disciplinare's Article 3 — province
→ regione is unambiguous. A bare regione-name scan is fragile: an area
or terroir description routinely names a *neighbouring* regione before
(or instead of) the wine's own, and the earliest-match-wins heuristic
then latches onto the wrong one (e.g. "case Toscana", a Piedmontese
hamlet, inside Dogliani's delimitation prose).

`derive_regione` therefore resolves in this order:
  1. an explicit `record['regione']` carried from a prior stage;
  2. a **province + commune tally** of the geo-area text (sigle,
     "provincia di NAME", and every commune named — see
     `scripts/_lib/it/province.py`). The curated file-number map breaks
     ties for genuinely interregional DOPs;
  3. the curated `regione_by_file_number.json` fallback, hand-verified
     for DOPs whose documento unico never names a province in
     machine-parseable form;
  4. a bare regione-name scan as a last resort — keyword-anchored
     ("regione X") first, then unanchored.

The regione feeds stage 03 (wiki frontmatter) and stage 04 (panel
header + regione facet filter + gettext label), so the names here are
canonical Italian forms. `scripts/audit_it_regions.py` independently
cross-checks every resolved regione against the wine's polygon.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from _lib.it.province import (  # noqa: F401 — REGIONI re-exported for callers
    REGIONI, _norm, dominant_regione, scan_commune_mentions,
    scan_province_mentions, truncate_at_delimitation,
)

# Alternate regione spellings / common variants → canonical name. Keys
# are already normalised (lowercase, no diacritics).
_VARIANTS: dict[str, str] = {
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

_CANON_BY_NORM = {_norm(r): r for r in REGIONI}
_CANON_BY_NORM.update({_norm(k): v for k, v in _VARIANTS.items()})

# Canonical names sorted longest-first so "Trentino-Alto Adige" matches
# before the bare "Trentino" variant.
_NEEDLES_BY_LEN: tuple[str, ...] = tuple(sorted(_CANON_BY_NORM, key=lambda n: -len(n)))

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
    or None. First match wins (longest needle breaks position ties).

    Fragile by design — kept only as the last-resort fallback in
    `derive_regione` and for callers that have nothing better."""
    if not text:
        return None
    low = " " + _norm(text) + " "
    best: tuple[int, str] | None = None
    for needle in _NEEDLES_BY_LEN:
        pos = low.find(" " + needle + " ")
        if pos < 0:
            continue
        if best is None or pos < best[0]:
            best = (pos, _CANON_BY_NORM[needle])
    return best[1] if best else None


_REGIONE_KEYWORD_RE = re.compile(r"\bregion[ei]\b\s+(?:di\s+|del\s+)?([^.;:\n]{0,40})", re.I)


def find_regione_after_keyword(text: str) -> str | None:
    """Find a regione named right after the word 'regione' — e.g.
    'nella regione Veneto'. Safer than a bare scan: it will not trip on
    a same-named hamlet or farm ('case Toscana')."""
    if not text:
        return None
    for m in _REGIONE_KEYWORD_RE.finditer(text):
        window = " " + _norm(m.group(1)) + " "
        for needle in _NEEDLES_BY_LEN:
            if f" {needle} " in window:
                return _CANON_BY_NORM[needle]
    return None


def derive_regione(
    record: dict,
    geo_area_text: str = "",
    name_text: str = "",
    *,
    comune_map: dict | None = None,
) -> str:
    """Resolve the regione for one IT record.

    `geo_area_text` is the area-definition text (documento unico
    section 6 / MASAF Article 3). `comune_map` is the optional
    GISCO-derived commune→regione index (see
    `province.load_comune_regione_map`) — when supplied, every commune
    named in the text votes, which resolves wines that never write a
    province or regione name. The terroir / legame text is deliberately
    NOT consulted: it names neighbouring regioni and is the source of
    the misattribution bug this function exists to avoid."""
    if record.get("regione"):
        return record["regione"]

    file_number = record.get("file_number", "")
    curated = regione_for_file_number(file_number)

    # Keep only the commune-enumeration half of the area text — the
    # boundary-tracing prose that follows is noise (and may name a
    # neighbouring province / regione at a border).
    geo = truncate_at_delimitation(geo_area_text)

    def _resolve(tally: Counter) -> str:
        # A genuinely interregional DOP tallies several regioni; defer to
        # the curated primary when the document confirms it is in play.
        if curated and curated in tally:
            return curated
        return dominant_regione(tally)

    # (1) Province sigle / "provincia di NAME" with a clear winner — the
    #     most reliable signal: explicit, anchored, unambiguous province
    #     → regione. A bare tie (own province vs a border province named
    #     once) is left to the commune tally below.
    prov = scan_province_mentions(geo)
    ranked = prov.most_common()
    if ranked and (len(ranked) == 1 or ranked[0][1] > ranked[1][1]):
        return _resolve(prov)

    # (2) An explicit "Regione X" statement — carries the region-wide
    #     DOCs that enumerate no province (e.g. the "Piemonte" DOC).
    kw = find_regione_after_keyword(geo)
    if kw:
        return kw

    # (3) Province + commune tally — every commune named in the
    #     enumeration votes; province mentions corroborate.
    tally = Counter(prov)
    if comune_map:
        tally += scan_commune_mentions(geo, comune_map)
    if tally:
        return _resolve(tally)

    # (4) Curated, hand-verified file-number fallback.
    if curated:
        return curated

    # (5) Last resort — bare regione-name scan of the geo-area / name.
    return find_regione_in_text(geo) or find_regione_in_text(name_text) or ""
