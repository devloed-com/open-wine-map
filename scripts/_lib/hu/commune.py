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
    # "kivéve a termékleírás térképi mellékletén jelölt területek" (Debrői
    # hárslevelű) — an exclusion by map, reached once every group is read
    "területek", "kivéve", "termékleírás", "térképi", "mellékletén",
    "mellékletében", "melléklet", "jelölt", "határrészeibe", "határrészei",
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


# "Települések:", "1. CLASSICUS BOROK:", "Pest megye:" — a heading ends at
# its colon and names no settlement; what precedes it since the last comma
# or full stop is dropped.
_HEADING_RE = re.compile(r"(?:^|(?<=[,;.:\n]))[^,;.:\n]*:")
_MARKER_RE = re.compile(r"\btelepül[eé]s\w*\b", re.IGNORECASE)


def _chunks(body: str) -> list[str]:
    out: list[str] = []
    for raw in _SPLIT_RE.split(body):
        chunk = _TIER_PREFIX_RE.sub("", (raw or "").strip(_EDGE_STRIP))
        chunk = chunk.strip(_EDGE_STRIP)
        key = _normalise_commune(chunk)
        if not key or any(tok in _PROSE_TOKENS for tok in key.split()):
            continue
        # Hungarian settlement names are rarely > 3 whitespace tokens;
        # longer chunks are prose.
        if len(key.split()) > 3 or len(key) < 3 or not key[0].isalpha():
            continue
        out.append(chunk)
    return out


def parse_commune_list(text: str) -> list[str]:
    """Extract settlement names from a Hungarian Egységes Dokumentum
    area body. Returns a deduped list of candidate names (original form,
    order preserved) that `HUPolygonIndex.commune_union` resolves.

    A name list ends at "… település(ek)(nek)" and the cadastre qualifier
    follows. A text can carry several such groups — one per wine tier
    (Eger's Classicus and Superior lists) or one per hill, "Monor
    településen a Strázsa-hegy, Monor, Monorierdő és Bénye településen a
    Száraz-hegy, Gomba településen Harc-völgy dőlőknek …" — so every group
    is read, a later group from after the earlier one's qualifier or hill
    (its first comma); until 2026-10-24 the first marker ended the list
    (Monor read Monor alone, Tolna's "Települések: Aba, …" nothing)."""
    if not text:
        return []
    body = _HEADING_RE.sub(",", text)
    parts = _MARKER_RE.split(body)
    groups = parts[:-1] if len(parts) > 1 else parts
    seen: set[str] = set()
    out: list[str] = []
    for k, part in enumerate(groups):
        if k:
            # the previous group's qualifier or hill runs to the first comma
            part = part.split(",", 1)[1] if "," in part else ""
        for chunk in _chunks(part):
            key = _normalise_commune(chunk)
            if key not in seen:
                seen.add(key)
                out.append(chunk)
    return out
