"""Per-AOC commune-list carving for multi-AOC cantons + VS Grand Cru.

Stage 02's universal règlement parser extracts commune candidates at
the **canton** level (the règlement applies to the whole canton). For
the multi-AOC cantons (VD, BE, FR), this is too coarse — each AOC
inside the canton has its own production area defined in a specific
article.

This module returns `{slug: text_block}` mapping each sub-AOC slug to
the règlement passage that defines its area; stage 02 then feeds that
text to the shared `CHCommuneIndex.scan_text()` to resolve commune
names against the swissBOUNDARIES3D index (BFS-keyed). This keeps the
commune-name resolution centralised and consistent.

Coverage:
  - VD: Art. 7 (Chablais), Art. 8 (Lavaux), Art. 9 (La Côte). The
    smaller régionale AOCs (Côtes-de-l'Orbe, Bonvillars, Vully,
    Dézaley, Calamin) declare themselves as "single lieu de production"
    without commune enumeration — geometry falls back to parent
    inheritance or cantonal cadastre (handled in stage 04).
  - BE: Art. 2 has Bielersee + Thunersee production regions with explicit
    commune lists (hardcoded — the article is short and stable).
  - FR: Art. 16 names the two AOC areas — hardcoded.
  - GE: deferred — the 22 premier crus already resolve via SITG
    VIT_VIGNOBLE_AO geoportal (parcel-precise).
  - TI: deferred — the 3 colour-tier sub-DOCs share the canton-wide
    production area; no per-AOC carving needed.

Also exports `VS_GRAND_CRU` — the 12 Valais Grand Cru communes
homologated under Art. 86 OVV, sourced from Vinum Montis +
grandcrusion.ch + Thomas Vino historical reportage (researched
2026-05; full source URLs in `verification` field).
"""

from __future__ import annotations

import re
from typing import Callable

# ─────────────────────────────────────────────────────────────── VD ──

# Map VD règlement region names to OFAG slugs.
_VD_REGION_TO_SLUG: dict[str, str] = {
    "chablais": "chablais",
    "lavaux": "lavaux",
    "la côte": "la-cote",
    "la cote": "la-cote",
    "côtes-de-l'orbe": "cotes-de-l-orbe",
    "côtes de l'orbe": "cotes-de-l-orbe",
    "bonvillars": "bonvillars",
    "vully": "vully",
    "dézaley": "dezaley",
    "dezaley": "dezaley",
    "calamin": "calamin",
    "dézaley-marsens": "dezaley-marsens",
    "dezaley-marsens": "dezaley-marsens",
}

_VD_ARTICLE_HEADER_RE = re.compile(
    r"^Art\.\s+(\d+[a-z]?)\s+Lieux de production de la région (?:du|de|des|de la|de l['’])\s*(.+?)\s*(?:\d+(?:\s*,\s*\d+)*)?\s*$",
    re.MULTILINE,
)


def _resolve_vd_region_slug(region_raw: str) -> str | None:
    region = region_raw.strip().lower()
    if region in _VD_REGION_TO_SLUG:
        return _VD_REGION_TO_SLUG[region]
    for k, v in _VD_REGION_TO_SLUG.items():
        if region.startswith(k):
            return v
    return None


_VD_ANY_ARTICLE_RE = re.compile(r"^Art\.\s+\d+[a-z]?\b", re.MULTILINE)


def carve_vd_text_blocks(text: str) -> dict[str, str]:
    """Return {slug: article_body_text} for VD's per-region articles.

    pdftotext emits `\\f` page breaks; we normalise to `\\n` so the
    MULTILINE `^` anchor catches headers that sit at the top of a new
    page (Art. 8 Lavaux is the canonical case). The body of each
    per-region article is bounded by the next ANY-article header
    (Art. 12c whose title is literally "..." would otherwise let Art.
    12b Calamin bleed past it into Title II + the rest of the doc)."""
    text = text.replace("\f", "\n")
    any_article_starts = [m.start() for m in _VD_ANY_ARTICLE_RE.finditer(text)]
    out: dict[str, str] = {}
    for m in _VD_ARTICLE_HEADER_RE.finditer(text):
        slug = _resolve_vd_region_slug(m.group(2))
        if slug is None:
            continue
        body_start = m.end()
        next_starts = [s for s in any_article_starts if s > body_start]
        body_end = next_starts[0] if next_starts else len(text)
        body = text[body_start:body_end].strip()
        if body:
            out[slug] = body
    return out


# ─────────────────────────────────────────────────────────────── BE ──

# BE Art. 2 explicitly enumerates communes per Produktionsregion. The
# article is short and stable; embedding it here is more robust than
# parsing the surrounding German legalese.
BE_PER_AOC_COMMUNES: dict[str, list[str]] = {
    "bielersee-lac-de-bienne": [
        # Twann + Tüscherz-Alfermée merged 2010 → "Twann-Tüscherz".
        # Biel is "Biel/Bienne" in BFS. Other communes match directly.
        "La Neuveville", "Ligerz", "Twann-Tüscherz", "Biel/Bienne",
        "Erlach", "Tschugg", "Gampelen", "Ins",
    ],
    "thunersee": ["Spiez", "Oberhofen am Thunersee", "Sigriswil"],
}


# ─────────────────────────────────────────────────────────────── FR ──

FR_PER_AOC_COMMUNES: dict[str, list[str]] = {
    # FR/VD intercantonal: wine on both the FR (Mont-Vully) and VD
    # (Vully-les-Lacs) sides.
    "vully": ["Mont-Vully", "Vully-les-Lacs"],
    # Cheyres + Font merged into "Cheyres-Châbles" in 2017; the
    # règlement still uses the historic names. swissBOUNDARIES3D 2026
    # has "Cheyres-Châbles" as the current commune.
    "cheyres": ["Cheyres-Châbles"],
}


# ──────────────────────────────────────────────── VS Grand Cru ──

# Valais Grand Cru per-commune sub-denomination roster, homologated
# under OVV Art. 86 — researched 2026-05 from Vinum Montis +
# grandcrusion.ch + Thomas Vino historical reportage. Each entry
# becomes a sub-denomination record of `valais-wallis`.
#
# year=None for entries whose Conseil d'État decree date wasn't
# located in the public record but whose Grand Cru status is
# corroborated by Vinum Montis (tourism office) or membership in the
# Association des Grands Crus du Valais (founded 2015). Promote
# `confidence` to "confirmed" once the per-commune homologation decree
# is found in the Bulletin officiel.
VS_GRAND_CRU: list[dict] = [
    {"commune": "Salquenen", "alias": "Salgesch",
     "grand_cru_name": "Salquenen Grand Cru", "year": 1988,
     "confidence": "confirmed",
     "sources": ["https://thomasvino.ch/?p=15303",
                 "https://www.vinum-montis.ch/fr/grands-crus-204.html"]},
    {"commune": "Vétroz", "alias": None,
     "grand_cru_name": "Vétroz Grand Cru", "year": 1993,
     "confidence": "confirmed",
     "sources": ["https://thomasvino.ch/?p=12907"]},
    {"commune": "Saint-Léonard", "alias": None,
     "grand_cru_name": "Saint-Léonard Grand Cru", "year": 1994,
     "confidence": "confirmed",
     "sources": ["https://thomasvino.ch/?p=12907"]},
    {"commune": "Fully", "alias": None,
     "grand_cru_name": "Fully Grand Cru", "year": 1996,
     "confidence": "confirmed",
     "sources": ["https://thomasvino.ch/?p=12907"]},
    {"commune": "Conthey", "alias": None,
     "grand_cru_name": "Conthey Grand Cru", "year": 1999,
     "confidence": "confirmed",
     "sources": ["https://thomasvino.ch/?p=12907"]},
    {"commune": "Chamoson", "alias": None,
     "grand_cru_name": "Chamoson Grand Cru", "year": 2011,
     "confidence": "confirmed",
     "sources": ["https://www.chamoson.ch/fr/decouvrir-chamoson/le-vignoble-de-chamoson/chamoson-grand-cru/les-grands-crus-en-valais-17817/"]},
    {"commune": "Sion", "alias": None,
     "grand_cru_name": "Grand Cru Ville de Sion", "year": 2012,
     "confidence": "confirmed",
     "sources": ["https://grandcrusion.ch/legislation.html"]},
    {"commune": "Saillon", "alias": None,
     "grand_cru_name": "Saillon Grand Cru", "year": None,
     "confidence": "association-member",
     "sources": ["https://thomasvino.ch/?p=12907"]},
    {"commune": "Leytron", "alias": None,
     "grand_cru_name": "Leytron Grand Cru", "year": None,
     "confidence": "association-member",
     "sources": ["https://thomasvino.ch/?p=12907"]},
    {"commune": "Sierre", "alias": None,
     "grand_cru_name": "Sierre Grand Cru", "year": 2015,
     "confidence": "confirmed",
     "sources": ["https://thomasvino.ch/?p=12907",
                 "https://www.vinum-montis.ch/fr/grands-crus-204.html"]},
    {"commune": "Savièse", "alias": None,
     "grand_cru_name": "Savièse Grand Cru", "year": None,
     "confidence": "to-verify",
     "sources": ["https://www.vinum-montis.ch/fr/grands-crus-204.html"]},
    {"commune": "Visperterminen", "alias": None,
     "grand_cru_name": "Visperterminen Grand Cru", "year": None,
     "confidence": "to-verify",
     "sources": ["https://www.vinum-montis.ch/fr/grands-crus-204.html"]},
]


# ────────────────────────────────────────────────── canton dispatch ──

# Carve functions that take règlement text → {slug: text_block}.
CARVE_TEXT_BLOCKS: dict[str, Callable[[str], dict[str, str]]] = {
    "vd": carve_vd_text_blocks,
}

# Direct {slug: [commune_name, ...]} for cantons whose Art. is short
# enough to hardcode reliably.
PER_AOC_COMMUNE_LISTS: dict[str, dict[str, list[str]]] = {
    "be": BE_PER_AOC_COMMUNES,
    "fr": FR_PER_AOC_COMMUNES,
}
