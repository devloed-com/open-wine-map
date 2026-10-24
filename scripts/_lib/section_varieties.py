"""Varieties an EU single document names outside its §7 roster (2026-10-24).

§7 ("main wine grape varieties") is the roster every reader takes, but a
document names varieties elsewhere too: §4 describes a varietal type
("Piemonte bianco, con specificazione di vitigno Cortese, Chardonnay,
Sauvignon" — and §7 of C 91/2020 has no Sauvignon), §5 states a production
rule for a variety ("a bort legalább 6 hónapig fahordóban kell érlelni,
kivéve: Blauburger, Kadarka, Kékoportó, Turán fajták borait" — Eger's §7
has no Turán; Prosecco's §5 allows Chardonnay and the three Pinots up to
15 %). A variety the regulator names as a type or in a rule is a permitted
variety, so it joins the roster as an *accessory*, tagged by the section
that names it (`section-4-type` / `section-5-rule`) — the RO yield-table
precedent (`add_yield_table_varieties`).

Only an exact, curated lexicon surface counts (`is_curated_surface`: a
corpus slug, a GRAPE_ALIAS key, a VIVC prime or a country's official
synonym — never an unflagged VIVC synonym, which include place names), and
never a bare family word: the corpus sweep of 2026-10-24 found "Lambrusco"
(five Emilian documents), "Albillo" (eight Castilian ones, for Albillo
Mayor / Real) and "Moscato" named this way, each a family of cultivars the
bare word does not settle. A surface that is part of the appellation's own
name is skipped. Sibling readers call `add_section_varieties(grapes,
routed, wine_name)` right after `parse_grapes`; the sweep found hits in
the ES, IT, HU and BE corpora (38 records) and none in the other twelve.
"""
from __future__ import annotations

import re
import sys
from functools import lru_cache
from pathlib import Path

_LIB_ROOT = Path(__file__).resolve().parent
if str(_LIB_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_LIB_ROOT.parent))
from _lib.grape_entity import (  # noqa: E402
    _BANNED_SURFACES,
    _load_vocabulary,
    _normalise,
    exact_match,
    is_curated_surface,
)

SOURCE_BY_ROLE = {
    "description": "section-4-type",
    "viticultural_practices": "section-5-rule",
}

# A bare word that names a family of cultivars, not one: the IT Article 1
# reader's list (`masaf._ART1_FAMILY_TAILS`) without "sauvignon" — a bare
# "Sauvignon" in a wine document is Sauvignon blanc (Cabernet Sauvignon is
# always written in full; the Italian register's entry is "Sauvignon B.") —
# plus the Iberian and Hungarian family words the sweep met.
FAMILY_WORDS = frozenset({
    "pinot", "moscato", "moscatel", "muscat", "muskotaly", "malvasia", "trebbiano",
    "lambrusco", "vernaccia", "greco", "bonarda", "cabernet", "riesling", "rizling",
    "traminer", "albillo", "incrocio manzoni", "listan", "groppello", "raboso",
    # the family words the lexicon folds onto one member — the TRUNCATED class
    # of audit_grape_surfaces (2026-10-24: Maremma Toscana's "Canaiolo", Val
    # d'Arno di Sopra's "Malvasia nera")
    "canaiolo", "malvasia nera", "refosco", "magliocco", "nerello", "verduzzo",
    "budai", "couderc", "cesanese",
})

# Variety names that are everyday words of a corpus language: the first run
# over the four corpora (2026-10-24) read "óptima maduración" as Optima, "sol y
# serena" as Serena, "frutti di bosco" as Bosco, "vitigni a bacca bianca" as
# Bianca, "halvány rubin" as Rubin, "lilás árnyalatokkal" as Lilas, "melón",
# "duras condiciones", "columna de burbujas", "sensación grasa", "primavera",
# "equi-valente". Capitalisation settles most of them (below); these are
# excluded whatever their case.
PROSE_WORDS = frozenset({
    "bianca", "bosco", "rubin", "lilas", "optima", "serena", "primavera", "melon",
    "duras", "columna", "grasa", "valente", "molar",
})

# A variety is a proper noun: the written form must be capitalised, unless a
# variety word stands within 30 characters before it ("las variedades
# garnacha blanca y macabeo", "la variedad forastera") — the ES reader's own
# rule, lowercase names accepted only in roster context.
_VARIETY_WORD_RE = re.compile(
    r"\b(?:variedad(?:es)?|vitign[oi]|variet[àa]|uv[ae]|cep[aá]s?|casta|fajt[aá]k?|"
    r"c[ée]pages?|druif|druiven|rassen|sort[ae]n?|odr[uů]d[ay]?|ποικιλ\w*)\b",
    re.IGNORECASE,
)
# "El Molar", "La Serena": a capitalised article or geographic word right before
# the surface marks a toponym, not a variety.
_TOPONYM_LEAD_RE = re.compile(
    r"(?:\b(?:El|La|Los|Las|Il|Lo|Le|Les|San|Santa|Sant|Sankt|Monte|Mont|R[ií]o|Val|Valle|"
    r"Colli|Colle|Serra|Sierra|Costa|Isla|Punta|Cap|Puerto|Puig|Torre|Terra|Terre)\s+)$",
)

_ACCENTS = {
    "a": "aàáâäãåăą", "c": "cçčć", "d": "dď", "e": "eèéêëěę", "g": "gğ", "i": "iìíîïı",
    "l": "lł", "n": "nñňń", "o": "oòóôöõőø", "r": "rř", "s": "sšşś", "t": "tţțť",
    "u": "uùúûüű", "y": "yýÿ", "z": "zžżź",
}


@lru_cache(maxsize=1)
def _surface_pattern() -> re.Pattern:
    vocab = _load_vocabulary()
    surfaces = [
        s for s in vocab.curated
        if (len(s) >= 5 or " " in s) and s not in _BANNED_SURFACES
        and s not in FAMILY_WORDS and s not in PROSE_WORDS
    ]
    alternation = "|".join(sorted(map(re.escape, surfaces), key=len, reverse=True))
    return re.compile(r"(?<![a-z0-9])(" + alternation + r")(?![a-z0-9])")


def _find_written(text: str, surface: str) -> re.Match | None:
    """The surface as the document writes it (case, accents, an apostrophe
    the normaliser dropped — "Nero d'Avola")."""
    parts = []
    for ch in surface:
        if ch == " ":
            parts.append(r"[\s\-'’.]*")
        elif ch in _ACCENTS:
            parts.append("[" + _ACCENTS[ch] + _ACCENTS[ch].upper() + "]")
        else:
            parts.append(re.escape(ch))
    return re.search(r"(?<![A-Za-zÀ-ž])" + "".join(parts) + r"(?![A-Za-zÀ-ž])", text, re.IGNORECASE)


def _written_form(text: str, surface: str) -> str:
    m = _find_written(text, surface)
    return re.sub(r"\s+", " ", m.group(0)) if m else surface


def _reads_as_a_name(text: str, surface: str) -> bool:
    """Capitalised in the document, or introduced by a variety word; never a
    toponym fragment ("El Molar")."""
    m = _find_written(text, surface)
    if m is None:
        return False
    before = text[max(0, m.start() - 30):m.start()]
    if _TOPONYM_LEAD_RE.search(before):
        return False
    return m.group(0)[:1].isupper() or bool(_VARIETY_WORD_RE.search(before))


def section_varieties(roles: dict, have: set[str], wine_name: str = "") -> list[dict]:
    """The accessory details §4 / §5 add to a roster of `have` slugs."""
    out: list[dict] = []
    seen = set(have)
    name_norm = _normalise(wine_name or "")
    pattern = _surface_pattern()
    for role, source in SOURCE_BY_ROLE.items():
        text = roles.get(role) or ""
        if not text:
            continue
        for m in pattern.finditer(_normalise(text)):
            surface = m.group(1)
            if name_norm and surface in name_norm:
                continue
            if not is_curated_surface(surface):
                continue
            hit = exact_match(surface)
            if hit is None or hit.slug in seen:
                continue
            if _normalise(hit.slug.replace("-", " ")) in FAMILY_WORDS | PROSE_WORDS:
                continue
            if not _reads_as_a_name(text, surface):
                continue
            seen.add(hit.slug)
            out.append({
                "slug": hit.slug, "name": _written_form(text, surface), "role": "accessory",
                "colour": hit.colour, "source": source,
            })
    return out


def add_section_varieties(grapes: dict, roles: dict, wine_name: str = "") -> list[str]:
    """Append the §4 / §5 varieties to `grapes` in place (accessory + details).
    Returns the added slugs."""
    have = set(grapes.get("principal") or []) | set(grapes.get("accessory") or [])
    added = section_varieties(roles, have, wine_name)
    if added:
        grapes.setdefault("accessory", []).extend(d["slug"] for d in added)
        grapes.setdefault("details", []).extend(added)
    return [d["slug"] for d in added]
