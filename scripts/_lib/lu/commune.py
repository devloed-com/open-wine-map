"""Luxembourg commune name resolution.

The 2020 IVV cahier des charges enumerates 15 historic communal
administrations as the holders of the cadastral viticultural-perimeter
maps (Bous, Burmerange, Flaxweiler, Grevenmacher, Lenningen, Mertert,
Mompach, Mondorf-les-Bains, Schengen, Remich, Rosport, Stadtbredimus,
Waldbredimus, Wellenstein, Wormeldange). Luxembourg has aggressively
merged communes since: the 15 historic wine-communes consolidate into
**11 modern administrative communes** as carried by Eurostat GISCO LAU
2024 (and by the LU national geoportal):

  Burmerange + Schengen + Wellenstein   → Schengen                (2011 fusion)
  Bous + Waldbredimus                   → Bous-Waldbredimus       (2023 fusion)
  Mompach + Rosport                     → Rosport - Mompach       (2018 fusion)
  Flaxweiler                            → Flaxweiler              (independent)
  Grevenmacher                          → Grevenmacher            (independent)
  Lenningen                             → Lenningen               (independent)
  Mertert                               → Mertert                 (independent)
  Mondorf-les-Bains                     → Mondorf-les-Bains       (independent)
  Remich                                → Remich                  (independent)
  Stadtbredimus                         → Stadtbredimus           (independent)
  Wormeldange                           → Wormeldange             (independent)

11 modern wine communes total. Stage 02 emits one sub-denomination
record per modern commune; the historic spellings live in the alias
table so future cahier amendments or curator queries that hit a
pre-fusion name still resolve.
"""

from __future__ import annotations

import re
import unicodedata


# Historic-cahier commune name → modern GISCO LAU 2024 commune name.
# Identity entries are kept explicit so the parser can validate every
# extracted name against this table without ambiguity.
HISTORIC_TO_MODERN: dict[str, str] = {
    # 2011 fusion: 3 historic communes → Schengen
    "Burmerange": "Schengen",
    "Schengen": "Schengen",
    "Wellenstein": "Schengen",
    # 2023 fusion: 2 historic communes → Bous-Waldbredimus
    "Bous": "Bous-Waldbredimus",
    "Waldbredimus": "Bous-Waldbredimus",
    # 2018 fusion: 2 historic communes → Rosport - Mompach
    "Mompach": "Rosport - Mompach",
    "Rosport": "Rosport - Mompach",
    # Independent (no fusion)
    "Flaxweiler": "Flaxweiler",
    "Grevenmacher": "Grevenmacher",
    "Lenningen": "Lenningen",
    "Mertert": "Mertert",
    "Mondorf-les-Bains": "Mondorf-les-Bains",
    "Remich": "Remich",
    "Stadtbredimus": "Stadtbredimus",
    "Wormeldange": "Wormeldange",
}

# Modern wine communes (the 11 deduped successors), sorted for
# deterministic output.
MODERN_WINE_COMMUNES: tuple[str, ...] = tuple(sorted(set(HISTORIC_TO_MODERN.values())))

# Modern → historic-cahier names for search/alias display.
MODERN_TO_HISTORIC: dict[str, tuple[str, ...]] = {}
for historic, modern in HISTORIC_TO_MODERN.items():
    MODERN_TO_HISTORIC.setdefault(modern, ())
    if historic != modern:
        MODERN_TO_HISTORIC[modern] = MODERN_TO_HISTORIC[modern] + (historic,)


def _normalise(s: str) -> str:
    """Casefold + diacritic-strip + punctuation-collapse for matching."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
    return s


_HISTORIC_BY_NORM: dict[str, str] = {_normalise(h): h for h in HISTORIC_TO_MODERN}
_MODERN_BY_NORM: dict[str, str] = {_normalise(m): m for m in MODERN_WINE_COMMUNES}


def slugify_commune(name: str) -> str:
    """Stable slug for a modern commune (sub-denomination slug helper)."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s


def historic_to_modern(name: str) -> str:
    """Resolve a historic or modern commune name to the modern GISCO LAU
    canonical form. Returns '' if not a recognised wine commune."""
    key = _normalise(name)
    if key in _HISTORIC_BY_NORM:
        return HISTORIC_TO_MODERN[_HISTORIC_BY_NORM[key]]
    if key in _MODERN_BY_NORM:
        return _MODERN_BY_NORM[key]
    return ""


def extract_communes_from_perimetre(text: str) -> list[str]:
    """Parse the cahier section d "périmètre viticole" sentence for the
    enumerated commune list. Returns the cahier-order modern-canonical
    names (deduped, fusion-collapsed).

    The cahier wording is:
      "...peuvent être consultées auprès de l'Institut viti-vinicole à
       Remich, ainsi qu'auprès des administrations communales de Bous,
       de Burmerange, de Flaxweiler, ... et de Wormeldange."
    """
    if not text:
        return []
    # Slice from "administrations communales de" onward; the sentence
    # ends at the next paragraph break (we already concatenated cahier
    # lines into paragraphs upstream).
    anchor = "administrations communales de"
    idx = text.find(anchor)
    if idx < 0:
        return []
    tail = text[idx + len(anchor):]
    # Cut at the next paragraph-ending punctuation (full stop followed
    # by capital, or two newlines). The historic-commune list itself
    # uses ", de " separators and ends with " et de Wormeldange.".
    cut = re.search(r"\.\s*[A-ZÉÀÈÊÎÔÛÄËÏÖÜÇ]", tail)
    sentence = tail[: cut.start() + 1] if cut else tail
    # Split on ", de " / ", d'" / " et de " / " et d'" and strip "de "/"d'"
    # from the first token; entries may also be split on commas alone.
    parts = re.split(r"\s*(?:,|\bet)\s+", sentence)
    out: list[str] = []
    seen: set[str] = set()
    for raw in parts:
        token = raw.strip().lstrip(".").strip()
        token = re.sub(r"^d(?:e|')\s*", "", token, flags=re.I).strip()
        token = re.sub(r"\s*\.\s*$", "", token).strip()
        if not token:
            continue
        modern = historic_to_modern(token)
        if not modern:
            continue
        if modern in seen:
            continue
        seen.add(modern)
        out.append(modern)
    return out


def normalise_name(s: str) -> str:
    """Public alias for downstream packages that need the same
    name-folding rule as the commune table."""
    return _normalise(s)


MODERN_BY_NORM: dict[str, str] = _MODERN_BY_NORM
