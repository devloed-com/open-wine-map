"""Extract sottozone from an Italian DOP/IGP documento unico.

Sottozone are the Italian analogue of FR DGCs and ES subzonas: named
sub-regions of a parent DOP that carry their own identity but live
under the parent's regulatory umbrella. Examples:

  - Chianti DOP → Colli Aretini, Colli Fiorentini, Colli Senesi,
    Colline Pisane, Montalbano, Rufina, Montespertoli, Montespertoli
  - Valpolicella DOP → Classico, Valpantena
  - Soave DOP → Classico, Colli Scaligeri
  - Bardolino DOP → Classico

Two patterns cover the bulk of observed cases:

  Pattern A — `Sottozona NAME` (header / inline) followed by a commune
              or area description.
  Pattern B — preamble + comma list, e.g.
              `Le sottozone Colli Aretini, Colli Fiorentini, Colli
              Senesi, Colline Pisane, Montalbano, Rufina, Montespertoli`.
              Pattern B is the common case for Italian disciplinari —
              the documento unico lists sottozone in one breath without
              per-sottozona commune detail (that lives in the national
              allegato).

Wines that mention "sottozona" in narrative but don't match either
pattern emit no sottozona records — they get flagged by stage 02f
when the national disciplinare is parsed.

Returns a list of `{name, slug, communes, source_pattern}` dicts. The
caller (stage 02) wraps each into a child record with
`is_sub_denomination=True`, `parent_slug`, `parent_id_eambrosia`,
`parent_name`. `communes` may be empty when the documento unico only
gives sottozona names (Pattern B preamble); stage 02f or the curator
queue can fill them in later.
"""

from __future__ import annotations

import re
import unicodedata


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()


# Pattern A — explicit "Sottozona NAME:" header followed by a description.
# Italian docs use both "sottozona" and "sotto-zona" spellings.
PATTERN_A_RE = re.compile(
    r"(?:^|\n)\s*(?:[—\-]\s*|[a-z]\)\s*)?"
    r"[Ss]otto[\s\-]?zona\s+"
    r"(?P<name>[A-ZÀ-ÖØ-Þ][^:\n]{1,80}?)\s*:\s*"
    r"(?P<body>[^\n]+(?:\n(?!\s*(?:[—\-]\s*|[a-z]\)\s*)?[Ss]otto[\s\-]?zona\b)[^\n]+)*)",
    re.MULTILINE,
)

# Pattern B — preamble phrase that announces a sottozona enumeration,
# followed by a comma-and-`e`-separated list of names. We deliberately
# allow the list to be open-ended (some preambles run on for a
# sentence) and stop at the next `.` or `;` or section header.
PATTERN_B_PREAMBLE_RE = re.compile(
    r"(?:le|delle|seguenti|comprende|prevede|individua)\s+"
    r"sotto[\s\-]?zone[^.;:]*?:?\s+"
    r"(?P<list>[A-Z][^.;]+)",
    re.IGNORECASE,
)


# Tokens that should never be parsed as a sottozona name. Filters out
# captures where the regex accidentally swallowed prose ("e i comuni di").
_NAME_DROP_TOKENS = frozenset({
    "e", "ed", "del", "della", "dei", "delle", "il", "la", "lo", "gli", "le",
    "di", "con", "per", "in", "tra", "fra", "comuni", "comune",
})


def _split_pattern_b_list(s: str) -> list[str]:
    """Parse a 'NAME1, NAME2, NAME3 e NAME4' enumeration into a list of
    names. Italian uses ` e ` as the final conjunction (no Oxford comma)."""
    s = re.sub(r"\s+", " ", s).strip().rstrip(".;:")
    # Drop a trailing "rispettivamente" / "tipologie" tail that some
    # preambles bolt on after the name list.
    s = re.split(
        r"\s+(?:rispettivamente|come\s+segue|tipologie?|sono|che|i\s+cui)\b",
        s, maxsplit=1,
    )[0].strip().rstrip(",.;")

    out: list[str] = []
    for token in re.split(r",|\be\s+", s):
        tok = token.strip().strip("«»\"'").rstrip(".,;:")
        if not tok:
            continue
        if tok.lower() in _NAME_DROP_TOKENS:
            continue
        if tok[0].islower():
            continue
        if any(c.isdigit() for c in tok):
            continue
        if len(tok) < 2 or len(tok) > 50:
            continue
        out.append(tok)
    return out


def _emit(name: str, communes: list[str], source_pattern: str) -> dict:
    return {
        "name": name.strip().strip("«»\"'"),
        "slug": slugify(name),
        "communes": communes,
        "source_pattern": source_pattern,
    }


def extract_sottozone(geo_area_brief: str, parent_wine_name: str) -> list[dict]:
    """Return a list of sottozona records extracted from `geo_area_brief`."""
    out: list[dict] = []
    seen_slugs: set[str] = set()
    seen_slugs.add(slugify(parent_wine_name))

    for m in PATTERN_A_RE.finditer(geo_area_brief):
        name = m.group("name").strip()
        body = m.group("body").strip()
        rec = _emit(name, [body] if body else [], "sottozona-prefix")
        if rec["slug"] not in seen_slugs and rec["name"]:
            seen_slugs.add(rec["slug"])
            out.append(rec)

    if not out:
        pre = PATTERN_B_PREAMBLE_RE.search(geo_area_brief)
        if pre:
            names = _split_pattern_b_list(pre.group("list"))
            for name in names:
                rec = _emit(name, [], "sottozona-preamble-list")
                if rec["slug"] not in seen_slugs:
                    seen_slugs.add(rec["slug"])
                    out.append(rec)
    return out
