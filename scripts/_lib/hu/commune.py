"""Hungarian commune-list parser for the Egységes Dokumentum area section.

The Hungarian EU single document delimits the appellation area as prose
naming the constituent **települések** (settlements) followed by a
vineyard-cadastre qualifier, e.g.

    "Bozsok, Cák, Kőszeg és Kőszegdoroszló településeknek a szőlő
     termőhelyi kataszter szerint I. és II. osztályú területei."
    "Etyek település szőlő termőhelyi kataszter I. és II. osztályába
     tartozó területei."

`parse_commune_list` extracts the deduped settlement-name list from one
such body; the names are resolved by `HUPolygonIndex.commune_union`
against the GISCO LAU 2024 `HU_*` polygons. Same architecture as
`scripts/_lib/ro/commune.py` and `scripts/_lib/at/gemeinde.py`, but
Hungarian commune names are matched in their native diacritic form
(GISCO LAU_NAME uses native Hungarian spelling — Kőszeg, Aszófő, …) so
the normaliser only casefolds, it does not strip diacritics.

Used by the 3 newer PDOs that post-date the Bétard 2022 snapshot
(Etyeki Pezsgő, Kőszeg, Füred) and available to any HU record whose
geometry must fall back to a commune union.
"""

from __future__ import annotations

import re

# The cadastre-qualifier tail that follows the settlement list. Everything
# from the first "település…" token onward describes WHICH parcels of the
# named settlements belong to the area (the vineyard-cadastre class), not
# further commune names — so we cut the body there.
_DESCRIPTOR_TAIL_RE = re.compile(
    r"\s*\btelepül[eé]s\w*\b.*$",
    re.IGNORECASE | re.DOTALL,
)

# Leading settlement-tier words occasionally prefix a name in older docs.
_TIER_PREFIX_RE = re.compile(
    r"^\s*(?:k[öo]zs[eé]g|v[aá]ros|telep[üu]l[eé]s)\w*\s+",
    re.IGNORECASE,
)

# Commas, semicolons, newlines and the conjunction "és" / "valamint"
# separate settlement names.
_SPLIT_RE = re.compile(r"\s*[,;\n]\s*|\s+(?:és|valamint|illetve)\s+", re.IGNORECASE)

_EDGE_STRIP = " .,;:\t-–—•·()"

# Chunks containing any of these tokens are prose lead-in, not a name.
_PROSE_TOKENS = frozenset({
    "terület", "területei", "területe", "kataszter", "termőhelyi",
    "osztályú", "osztályba", "osztálya", "szerint", "tartozó", "szőlő",
    "borvidék", "borvidéki", "következő", "alábbi", "alábbiak",
    "lehatárolt", "körülhatárolt", "földrajzi", "valamint", "egész",
    "közigazgatási", "külterülete", "belterülete",
})


def _normalise_commune(name: str) -> str:
    """Casefold + collapse whitespace. Hungarian diacritics are KEPT —
    GISCO LAU_NAME stores native Hungarian spelling, so an ASCII fold
    would lose the ő/ű/á distinctions that disambiguate names."""
    if not name:
        return ""
    s = _TIER_PREFIX_RE.sub("", name.strip())
    s = re.sub(r"\s+", " ", s).strip(_EDGE_STRIP)
    return s.casefold()


def parse_commune_list(text: str) -> list[str]:
    """Extract settlement names from a Hungarian Egységes Dokumentum
    area body. Returns a deduped list of candidate names (original form,
    order preserved) that `HUPolygonIndex.commune_union` resolves."""
    if not text:
        return []
    # Cut the cadastre-qualifier tail ("… településeknek a szőlő
    # termőhelyi kataszter szerint …") so only the name list survives.
    body = _DESCRIPTOR_TAIL_RE.sub("", text).strip(_EDGE_STRIP)
    if not body:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in _SPLIT_RE.split(body):
        chunk = _TIER_PREFIX_RE.sub("", (raw or "").strip(_EDGE_STRIP))
        chunk = chunk.strip(_EDGE_STRIP)
        if not chunk:
            continue
        key = _normalise_commune(chunk)
        if not key or key in seen:
            continue
        if any(tok in _PROSE_TOKENS for tok in key.split()):
            continue
        # Hungarian settlement names are rarely > 3 whitespace tokens;
        # longer chunks are prose.
        if len(key.split()) > 3 or len(key) < 3 or not key[0].isalpha():
            continue
        seen.add(key)
        out.append(chunk)
    return out
