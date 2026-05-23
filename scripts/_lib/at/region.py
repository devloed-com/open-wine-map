"""Derive the Austrian Bundesland (federal state) for a wine GI.

Austria has 9 Bundesländer; all 9 of the wine-growing ones appear in the
corpus as generic regional PDOs (Burgenland, Niederösterreich,
Steiermark, Wien, …). The 29 PDOs each sit inside exactly one
Bundesland; the 3 PGIs (Bergland, Weinland, Steirerland) span several
Bundesländer and are tagged "Österreich" except Steirerland, which is
coextensive with Steiermark.

The Bundesland drives stage 03 (wiki frontmatter) and stage 04 (panel
header + region facet filter). It is also a translation surface in
gettext (`build_labels`), so the names here are canonical German forms.

Resolution order: explicit `record['bundesland']` → scan the supplied
text candidates (section 6 geo area, section 8 link, name) → curated
`_BUNDESLAND_BY_FILE_NUMBER` fallback.
"""

from __future__ import annotations

import re
import unicodedata

# The 9 Austrian Bundesländer (canonical German spelling) + the
# "Österreich" catch-all for the multi-state Landwein PGIs.
BUNDESLAENDER = (
    "Burgenland",
    "Kärnten",
    "Niederösterreich",
    "Oberösterreich",
    "Salzburg",
    "Steiermark",
    "Tirol",
    "Vorarlberg",
    "Wien",
    "Österreich",
)

# Diacritic-free / common variants → canonical name. Keys are normalised.
_VARIANTS: dict[str, str] = {
    "karnten": "Kärnten",
    "niederosterreich": "Niederösterreich",
    "nieder osterreich": "Niederösterreich",
    "oberosterreich": "Oberösterreich",
    "ober osterreich": "Oberösterreich",
    "osterreich": "Österreich",
    "wein": "Wien",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


_CANON_BY_NORM = {_norm(b): b for b in BUNDESLAENDER}
_CANON_BY_NORM.update({k: v for k, v in _VARIANTS.items()})
# "wein" would shadow the Wien variant; drop it — Wien is matched by its
# own normalised form "wien" and the variant is only useful as a typo
# guard, which causes more harm than good in free text.
_CANON_BY_NORM.pop("wein", None)


# Curated file_number → Bundesland, hand-verified against eAmbrosia +
# the Einziges Dokument geo section. The 3 PGIs span several states:
# Bergland (Oberösterreich/Salzburg/Tirol/Vorarlberg/Kärnten) and
# Weinland (Niederösterreich/Burgenland/Wien) are tagged "Österreich";
# Steirerland is coextensive with Steiermark.
_BUNDESLAND_BY_FILE_NUMBER: dict[str, str] = {
    "PDO-AT-A0207": "Burgenland",          # Burgenland
    "PDO-AT-A0217": "Niederösterreich",    # Carnuntum
    "PDO-AT-A0215": "Burgenland",          # Eisenberg
    "PDO-AT-A0209": "Niederösterreich",    # Kamptal
    "PDO-AT-A0208": "Niederösterreich",    # Kremstal
    "PDO-AT-A0218": "Kärnten",             # Kärnten
    "PDO-AT-A0216": "Burgenland",          # Leithaberg
    "PDO-AT-A0214": "Burgenland",          # Mittelburgenland
    "PDO-AT-A0219": "Burgenland",          # Neusiedlersee
    "PDO-AT-A0220": "Burgenland",          # Neusiedlersee-Hügelland
    "PDO-AT-A0221": "Niederösterreich",    # Niederösterreich
    "PDO-AT-A0223": "Oberösterreich",      # Oberösterreich
    "PDO-AT-02594": "Burgenland",          # Rosalia
    "PDO-AT-02769": "Burgenland",          # Ruster Ausbruch
    "PDO-AT-A0224": "Salzburg",            # Salzburg
    "PDO-AT-A0225": "Steiermark",          # Steiermark
    "PDO-AT-A0227": "Burgenland",          # Südburgenland
    "PDO-AT-A0228": "Steiermark",          # Südsteiermark
    "PDO-AT-A0229": "Niederösterreich",    # Thermenregion
    "PDO-AT-A0230": "Tirol",               # Tirol
    "PDO-AT-A0210": "Niederösterreich",    # Traisental
    "PDO-AT-A0231": "Vorarlberg",          # Vorarlberg
    "PDO-AT-A0226": "Steiermark",          # Vulkanland Steiermark
    "PDO-AT-A0205": "Niederösterreich",    # Wachau
    "PDO-AT-A0233": "Niederösterreich",    # Wagram
    "PDO-AT-A0206": "Niederösterreich",    # Weinviertel
    "PDO-AT-A0234": "Steiermark",          # Weststeiermark
    "PDO-AT-A0235": "Wien",                # Wien
    "PDO-AT-02593": "Wien",                # Wiener Gemischter Satz
    "PGI-AT-A0211": "Österreich",          # Bergland
    "PGI-AT-A0212": "Österreich",          # Weinland
    "PGI-AT-A0213": "Steiermark",          # Steirerland
}


def bundesland_for_file_number(file_number: str) -> str:
    """Curated fallback Bundesland for a wine GI file_number, or '' if
    unknown."""
    return _BUNDESLAND_BY_FILE_NUMBER.get(file_number or "", "")


def find_bundesland_in_text(text: str) -> str | None:
    """Scan text for a Bundesland name. Returns the canonical form or
    None. Earliest match wins; longer needle breaks ties."""
    if not text:
        return None
    low = " " + _norm(text) + " "
    best: tuple[int, str] | None = None
    for needle, canon in _CANON_BY_NORM.items():
        if not needle:
            continue
        pos = low.find(" " + needle + " ")
        if pos < 0:
            continue
        if best is None or pos < best[0] or (
            pos == best[0] and len(needle) > len(_norm(best[1]))
        ):
            best = (pos, canon)
    return best[1] if best else None


def derive_bundesland(record: dict, *text_candidates: str) -> str:
    """Resolve the Bundesland for one record. The curated file_number
    map is authoritative (hand-verified); the text scan only runs when
    the file_number is unknown."""
    if record.get("bundesland"):
        return record["bundesland"]
    curated = bundesland_for_file_number(record.get("file_number", ""))
    if curated:
        return curated
    for text in text_candidates:
        hit = find_bundesland_in_text(text or "")
        if hit:
            return hit
    return ""
