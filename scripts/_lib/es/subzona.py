"""Extract subzonas from a Spanish DOP/IGP pliego's brief geographical area.

Subzonas are the Spanish analog of French DGCs (dénominations géographiques
complémentaires): named sub-regions of a parent DOP that carry their own
identity but live under the parent's regulatory umbrella. Examples:

  - Rioja (DOCa) → Rioja Alta / Rioja Alavesa / Rioja Oriental
  - Rías Baixas → Val do Salnés / Condado do Tea / O Rosal / Soutomaior /
    Ribeira do Ulla
  - Ribeira Sacra → Amandi / Chantada / Quiroga-Bibei / Ribeiras do Miño /
    Ribeiras do Sil
  - Costers del Segre → 7 "unidades geográficas menores"

Pliegos vary in how subzonas are written. Three patterns cover the bulk
of cases observed across the ES corpus (10 explicit-subzona wines plus
Rioja-style ALL-CAPS):

  Pattern A — `Subzona <name>: comma1, comma2, …`
              (or with leading `—` dash separator).
              Wines: alicante, monterrei, ribeira-sacra, vinos-de-madrid,
                     valencia (with `a) Subzona NAME:` letter-marking).

  Pattern B — `Unidad geográfica menor <name>: Compuesta por las siguientes
              localidades: — commune1 — commune2 — …`
              Wines: costers-del-segre.

  Pattern C — Rioja-style ALL-CAPS header lines:
              ```
              RIOJA ALTA
              Comunidad Autónoma de La Rioja
              <commune list, one per line>
              RIOJA ALAVESA
              Comunidad Autónoma del País Vasco
              <commune list>
              ```

Wines that mention "subzona" in narrative but don't match any pattern are
flagged by `audit_subzonas.py` for curator review.

Returns a list of `{name, slug, communes, source_pattern}` dicts. Caller
(stage 02) wraps each into a child record with `is_sub_denomination=True`,
`parent_id_eambrosia`, `parent_slug`, `parent_name`.
"""

from __future__ import annotations

import re
import unicodedata


def slugify(s: str) -> str:
    """Same shape as scripts/02_extract_cahiers.py:slug — for parity with
    the FR DGC slug derivation."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()


# Pattern A: "Subzona NAME: communes" — most common.
# Matches both "Subzona X: …" and "Subzona de X: …" and the letter-marked
# "a) Subzona X: …" form (we just skip the prefix).
# Name is non-greedy up to the first colon; communes capture everything up
# to the next "Subzona" / "Unidad" / end-of-block delimiter.
PATTERN_A_RE = re.compile(
    r"(?:^|\n)\s*(?:[—\-]\s*|[a-z]\)\s*)?"
    r"Subzona\s+(?:de\s+)?"
    r"(?P<name>[^:\n]{2,80}?)\s*:\s*"
    r"(?P<communes>[^\n]+(?:\n(?!\s*(?:[—\-]\s*|[a-z]\)\s*)?(?:Subzona|Unidad geográfica menor)\b)[^\n]+)*)",
    re.MULTILINE,
)

# Pattern D: "El territorio se divide en N subzonas …\n— NAME: communes\n
# — NAME: communes" — same as A but the per-subzona lines drop the
# "Subzona" prefix (they're implied by the preamble). Rías Baixas uses
# this. We require the preamble to fire so we don't false-positive on
# stray "X: list" colon lines.
PATTERN_D_PREAMBLE_RE = re.compile(
    r"(?:divide|formada|dividida|compone|consta).{0,80}?\bsubzonas?\b",
    re.IGNORECASE,
)
# Inside the post-preamble block: dashed `Name: communes` lines.
PATTERN_D_ITEM_RE = re.compile(
    r"(?:^|\n)\s*[—\-]\s*"
    r"(?P<name>[^:\n]{2,80}?)\s*:\s*"
    r"(?P<communes>[^\n]+(?:\n(?!\s*[—\-]\s*[A-ZÁÉÍÓÚÑÜ])[^\n]+)*)",
    re.MULTILINE,
)

# Pattern B: "Unidad geográfica menor NAME: Compuesta por las siguientes
# localidades: — c1 — c2 — …"
PATTERN_B_RE = re.compile(
    r"Unidad\s+geográfica\s+menor\s+"
    r"(?P<name>[^:\n]{2,80}?)\s*:\s*"
    r"(?:Compuesta por las siguientes localidades\s*:\s*)?"
    r"(?P<dash_block>(?:\n\s*—\s*[^\n]+){2,200})",
    re.MULTILINE,
)

# Pattern C: Rioja-style — ALL-CAPS header line that contains the parent
# wine name as a prefix (e.g. "RIOJA ALTA"), followed by "Comunidad
# Autónoma de …" line, followed by commune list (one per line) until the
# next ALL-CAPS header or end-of-text. We require the wine-name prefix to
# avoid mis-firing on "PROVINCIA DE …" / "COMUNIDAD AUTÓNOMA …" headers.
def _all_caps_header_re(parent_wine_name: str) -> re.Pattern:
    # Strip diacritics + lowercase the prefix for the regex; case-insensitive
    # match handles the actual data (which is all-caps).
    prefix = (
        unicodedata.normalize("NFKD", parent_wine_name)
        .encode("ascii", "ignore").decode()
        .strip()
    )
    if not prefix:
        return re.compile(r"$^")  # never matches
    # Word-boundary on the wine name; the rest of the header is a single
    # uppercase word/phrase up to ~30 chars.
    return re.compile(
        rf"(?:^|\n)\s*({re.escape(prefix.upper())}\s+[A-ZÁÉÍÓÚÑÜ][A-ZÁÉÍÓÚÑÜ\s]{{2,40}}?)\s*\n",
        re.IGNORECASE,
    )


# Word-tokens that should never be parsed as a commune name. Stage 02's
# parse_communes split is intentionally permissive; this filter trims the
# obvious junk.
_COMMUNE_DROP_TOKENS = frozenset({
    "y", "e", "del", "de", "la", "el", "los", "las",
    "según", "segun", "etc", "etcétera", "etcetera",
})


# Narrative-end markers — the commune list of a subzona ends right before
# any of these phrases. Pliegos commonly transition from a commune-name
# list into a paragraph describing additional polygons / SIGPAC parcels /
# bodega rules / etc., and the comma-split logic below would otherwise
# treat each clause of that paragraph as a "commune". Cutting at the
# first marker keeps the commune list clean.
_COMMUNE_LIST_END_MARKERS = (
    "Así como", "Asi como", "Dichos polígonos", "Dichos poligonos",
    "Del término municipal", "Del termino municipal",
    "El término municipal", "El termino municipal",
    "Y ciertos polígonos", "Y ciertos poligonos",
    "según la cartografía", "segun la cartografia",
    "siempre y cuando", "y los polígonos", "y los poligonos",
    "Y las parcelas", "y las parcelas",
)


def _split_inline_communes(s: str) -> list[str]:
    """Parse a 'Subzona X: c1, c2 y c3.' commune list into [c1, c2, c3].

    Truncates at any narrative-end marker (see _COMMUNE_LIST_END_MARKERS).
    Splits on commas and " y "; preserves parenthetical context attached
    to a commune (e.g. "Tui*", "Caudete (Albacete)"). Filters tokens
    that look like prose fragments (lowercase prefixes, numbers, etc.)."""
    s = re.sub(r"\s+", " ", s).strip().rstrip(".;")
    # Truncate at the first end-of-commune-list marker.
    cut = len(s)
    for marker in _COMMUNE_LIST_END_MARKERS:
        i = s.find(marker)
        if i >= 0 and i < cut:
            cut = i
    s = s[:cut].rstrip(" ,;.")

    out: list[str] = []
    depth = 0
    cur: list[str] = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth -= 1
            cur.append(ch)
        elif depth == 0 and ch == ",":
            tok = "".join(cur).strip()
            if tok:
                out.append(tok)
            cur = []
        elif depth == 0 and s[i : i + 3] == " y ":
            tok = "".join(cur).strip()
            if tok:
                out.append(tok)
            cur = []
            i += 2
        else:
            cur.append(ch)
        i += 1
    tok = "".join(cur).strip()
    if tok:
        out.append(tok)

    return [t for t in out if _is_commune_token(t)]


def _is_commune_token(t: str) -> bool:
    """A real Spanish commune name: not too short, no digits, doesn't start
    with a lowercase function-word (`su `, `del `, `la `, `que `…), not
    in the _COMMUNE_DROP_TOKENS list. Defensive — pliegos with
    parenthetical descriptions or partida-by-partida lists slip past the
    comma split and end up here."""
    if len(t) < 2 or any(c.isdigit() for c in t):
        return False
    if t.lower() in _COMMUNE_DROP_TOKENS:
        return False
    # Lowercase first character → almost certainly a fragment of prose,
    # not a commune name (Spanish proper nouns are title-cased).
    if t[0].islower():
        return False
    # Spanish function words that may appear at the start of a captured
    # fragment when the comma-split doesn't align with sentence structure.
    for prefix in ("su ", "sus ", "del ", "de la ", "de los ", "de las "):
        if t.lower().startswith(prefix):
            return False
    return True


def _split_dash_block(s: str) -> list[str]:
    """Parse a `\n— c1\n— c2\n— c3\n` block into [c1, c2, c3]."""
    out: list[str] = []
    for line in re.split(r"\n\s*[—\-]\s*", s):
        line = line.strip()
        if not line:
            continue
        # A dash-block entry sometimes spans multiple commas (e.g.
        # "Cubells, Os de Balaguer, Vilanova de Meià") — split inline.
        out.extend(_split_inline_communes(line))
    return out


def _emit_subzona(name: str, communes: list[str], source_pattern: str) -> dict:
    return {
        "name": name.strip().strip("«»\"'"),
        "slug": slugify(name),
        "communes": communes,
        "source_pattern": source_pattern,
    }


def extract_subzonas(geo_area_brief: str, parent_wine_name: str) -> list[dict]:
    """Return a list of subzona records extracted from `geo_area_brief`.
    Empty list when the wine has no detectable subzonas. The caller can
    tell "no subzonas" from "extraction failed" by checking whether the
    text contains the literal word "subzona" / "unidad geográfica menor"
    or matches the Rioja-style ALL-CAPS rule."""
    out: list[dict] = []
    seen_slugs: set[str] = set()

    # Pattern A — Subzona NAME: communes
    for m in PATTERN_A_RE.finditer(geo_area_brief):
        name = m.group("name").strip()
        communes_raw = m.group("communes").strip()
        # Drop "Subzona:" definitional sentences (sierras-de-malaga has one
        # before the actual subzona enumeration).
        if "Unidad geográfica menor" in name or len(name) < 2:
            continue
        communes = _split_inline_communes(communes_raw)
        if not communes or len(communes) > 200:
            continue
        rec = _emit_subzona(name, communes, "subzona-prefix")
        if rec["slug"] not in seen_slugs:
            seen_slugs.add(rec["slug"])
            out.append(rec)

    # Pattern D — preamble + dashed `Name: communes`. Only fires when
    # pattern A produced nothing AND the preamble phrase ("se divide en …
    # subzonas") is present. Avoids false-positives on every colon-bearing
    # line in a flat-list pliego.
    if not out and PATTERN_D_PREAMBLE_RE.search(geo_area_brief):
        preamble = PATTERN_D_PREAMBLE_RE.search(geo_area_brief)
        block = geo_area_brief[preamble.end():]
        for m in PATTERN_D_ITEM_RE.finditer(block):
            name = m.group("name").strip()
            communes_raw = m.group("communes").strip()
            # Filter out section headers that happen to fit the regex
            # ("Comunidad Autónoma de Galicia" is descriptive, not a name).
            if name.lower().startswith(("comunidad", "provincia")):
                continue
            communes = _split_inline_communes(communes_raw)
            if not communes:
                continue
            rec = _emit_subzona(name, communes, "preamble-dashed-name")
            if rec["slug"] not in seen_slugs:
                seen_slugs.add(rec["slug"])
                out.append(rec)

    # Pattern B — Unidad geográfica menor
    for m in PATTERN_B_RE.finditer(geo_area_brief):
        name = m.group("name").strip()
        communes = _split_dash_block(m.group("dash_block"))
        if not communes:
            continue
        rec = _emit_subzona(name, communes, "unidad-geografica-menor")
        if rec["slug"] not in seen_slugs:
            seen_slugs.add(rec["slug"])
            out.append(rec)

    # Pattern C — Rioja-style ALL-CAPS headers. Only fires when no
    # pattern-A matches were found (the explicit "Subzona" prefix is more
    # reliable than ALL-CAPS heuristics).
    if not out:
        header_re = _all_caps_header_re(parent_wine_name)
        headers = list(header_re.finditer(geo_area_brief))
        for i, hm in enumerate(headers):
            name = hm.group(1).strip()
            start = hm.end()
            end = headers[i + 1].start() if i + 1 < len(headers) else len(geo_area_brief)
            block = geo_area_brief[start:end]
            # Drop the "Comunidad Autónoma de …" lead-in lines, then take
            # the rest as one-commune-per-line.
            commune_lines = []
            for line in block.split("\n"):
                line = line.strip().rstrip(".,")
                if not line:
                    continue
                if line.lower().startswith("comunidad autónoma"):
                    continue
                if line.lower().startswith("provincia de"):
                    continue
                commune_lines.append(line)
            if not commune_lines or len(commune_lines) > 500:
                continue
            rec = _emit_subzona(name, commune_lines, "all-caps-rioja-style")
            if rec["slug"] not in seen_slugs:
                seen_slugs.add(rec["slug"])
                out.append(rec)

    return out
