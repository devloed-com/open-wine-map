"""Audit: which ES DOPs have grape varieties added by amendment but missing
from the canonical `grapes` field?

Mines the amendment-description text inside `raw/es/pliegos-extracted/*.json`
for sentences that announce new varieties ("Incorporación de las variedades
...", "Se incorpora la variedad ...", "Las N nuevas variedades ... son ...",
"Se introduce la variedad «X»", etc.), extracts candidate grape names,
slug/alias-folds them through the same helpers stage 02 uses, and diffs
against the record's current `grapes.principal ∪ grapes.accessory`.

Prototype to size the gap before deciding whether to wire it into stage 02
or build a national-pliego-PDF parser. Not a pipeline stage — run
ad-hoc and read the report on stderr/stdout.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.grape_lexicon import DEFAULT_COLOUR, GRAPE_ALIAS, slugify as _grape_slug  # noqa: E402

PLIEGOS_DIR = ROOT / "raw" / "es" / "pliegos-extracted"

# Trigger phrases: a sentence (or short span) that *both* announces an
# addition AND mentions varieties. Each pattern captures the trailing
# enumeration up to the next sentence boundary.
TRIGGERS = [
    # "Incorporación de las variedades tintas: X, Y y Z, y blancas: W."
    re.compile(
        r"[Ii]ncorporaci[oó]n\s+de\s+(?:las\s+)?(?:nuevas\s+)?variedades?\b[^.]*?:\s*([^.]+)\.",
        re.S,
    ),
    # "Las 4 nuevas variedades de uva incluidas son el Picapoll Blanco, la Malvasía, la Pirene y el Marselan."
    re.compile(
        r"(?:[Ll]as\s+\d+\s+)?nuevas\s+variedades\s+de\s+uva\s+(?:incluidas|incorporadas|aprobadas)?\s*son\s+([^.]+)\.",
        re.S,
    ),
    # "Se incorpora la variedad Tempranillo" / "Se incorporan las variedades X y Y"
    re.compile(
        r"[Ss]e\s+(?:incorpora|incluy[ae]|introduc[ae]|a[ñn]ad[ei])n?\s+(?:la|las|el|los)\s+variedad(?:es)?\s+([^.]+)\.",
        re.S,
    ),
    # "Se introduce la variedad «Petit Verdot»"
    re.compile(
        r"[Ss]e\s+(?:introduce|incorpora|incluye|a[ñn]ade)\s+la\s+variedad\s+[«\"']([^»\"']+)[»\"']",
        re.S,
    ),
    # "Inclusión de la(s) variedad(es) X y Y"
    re.compile(
        r"[Ii]nclusi[oó]n\s+de\s+(?:la|las)\s+variedad(?:es)?\s+([^.]+)\.",
        re.S,
    ),
]

# A few clearly-non-grape proper nouns that show up in this corpus.
_DROP_TOKENS = {
    "documento", "documento único", "pliego", "pliego de condiciones",
    "reglamento", "comisión", "unión europea", "comunidad", "comunidades",
    "regulador", "consejo regulador", "ministerio", "modificación",
    "modificaciones", "denominación", "denominación de origen", "dop", "igp",
    "real decreto", "uvas", "uva", "vino", "vinos", "tinto", "tintos",
    "blanco", "blancos", "rosado", "rosados", "secundaria", "secundarias",
    "principal", "principales", "preferente", "preferentes", "autorizada",
    "autorizadas", "accesoria", "accesorias", "complementaria", "complementarias",
    "tinta", "tintas", "blanca", "blancas", "negra", "negras",
    "península", "ibérica", "españa", "españolas", "españolas", "francia",
    "cataluña", "andalucía", "rioja", "navarra", "aragón", "castilla",
    "mancha", "comunidad valenciana", "galicia", "castilla y león",
    "principado de asturias", "país vasco", "extremadura",
    "directiva", "anexo", "tabla", "apartado", "punto",
    "el real de san vicente", "santa ana de pusa",
    "color", "aroma", "gusto", "boca",
    "petit", "verdot",  # split anomaly handled below
}

# Tokens that *look* like a grape but are actually region/sub-region prose.
# Kept tight so we don't lose anything.
_REGION_HINTS = {
    "rioja", "navarra", "cataluña", "andalucía", "valencia", "murcia",
    "galicia", "aragón", "asturias", "castilla", "léon", "mancha",
    "extremadura", "país", "vasco", "canarias", "baleares", "alicante",
    "albacete", "toledo", "ciudad real", "cuenca", "guadalajara",
}

_CONNECTOR_RE = re.compile(r"\s+(?:y/o|y|o|u|e|i)\s+", re.IGNORECASE)
_COLOUR_HINT_RE = re.compile(
    r"\b(tinta|tintas|blanca|blancas|negra|negras|rosada|rosadas|tinto|tintos|blanco|blancos)\b",
    re.IGNORECASE,
)


def _split_enumeration(span: str) -> list[str]:
    """Break "Garnacha Peluda, Garnacha Tintorera y Moravia Agria, y blancas: Garnacha Blanca"
    into individual variety candidate strings."""
    # Drop trailing "as secondary" / "como secundarias" framing.
    span = re.sub(r",?\s+(?:como|se incorporan? como).+$", "", span, flags=re.I)
    # "tintas: X, Y y Z, y blancas: W" → keep the W. Split on colons that
    # follow a colour hint and pull the right-hand items in too.
    parts: list[str] = []
    for chunk in re.split(r"[:;]", span):
        chunk = chunk.strip(" ,.;")
        if not chunk:
            continue
        # Skip pure colour-header chunks ("tintas", "y blancas").
        if _COLOUR_HINT_RE.fullmatch(chunk):
            continue
        # Split on commas + Spanish 'y'/'o' connectors.
        pieces = re.split(r",|\s+y\s+|\s+o\s+|\s+e\s+", chunk)
        for p in pieces:
            p = p.strip(" .,;«»\"'")
            # Strip leading article ("el ", "la ", "los ", "las ").
            p = re.sub(r"^(?:el|la|los|las)\s+", "", p, flags=re.IGNORECASE)
            if p:
                parts.append(p)
    return parts


def _looks_like_grape(name: str) -> tuple[str, str] | None:
    """Return (slug, name) if the token plausibly names a grape variety,
    else None. Mirrors the strict-but-permissive checks in stage 02."""
    name = name.strip().strip(" .,;«»\"'·")
    if not name or len(name) < 3 or len(name) > 60:
        return None
    if any(c.isdigit() for c in name):
        return None
    if name.lower() in _DROP_TOKENS:
        return None
    words = name.split()
    if not words or len(words) > 4:
        return None
    first = words[0]
    if not first[0].isalpha() or not first[0].isupper():
        return None
    if any(w.lower() in _REGION_HINTS for w in words):
        return None
    raw_slug = _grape_slug(name)
    if not raw_slug:
        return None
    slug = GRAPE_ALIAS.get(raw_slug, raw_slug)
    # Strip colour suffix collapse like stage 02 does.
    for suf in ("-blanc", "-blanca", "-noir", "-negra", "-tinta", "-gris", "-rosada"):
        if slug.endswith(suf):
            stem = slug[: -len(suf)]
            stem_canon = GRAPE_ALIAS.get(stem, stem)
            if stem_canon in DEFAULT_COLOUR:
                slug = stem_canon
                break
    return slug, name


def mine_record(record: dict) -> list[tuple[str, str, str]]:
    """Return a list of (slug, name, source_section) candidates for this
    record. Source section is the section key the trigger fired in, so the
    audit report can point a curator at the right paragraph."""
    sections = record.get("sections") or {}
    found: dict[str, tuple[str, str]] = {}  # slug → (name, section)
    for sec_key, text in sections.items():
        if not text:
            continue
        for trig in TRIGGERS:
            for m in trig.finditer(text):
                span = m.group(1)
                for cand in _split_enumeration(span):
                    hit = _looks_like_grape(cand)
                    if hit is None:
                        continue
                    slug, name = hit
                    found.setdefault(slug, (name, sec_key))
    return [(slug, name, sec) for slug, (name, sec) in found.items()]


def main() -> int:
    files = sorted(PLIEGOS_DIR.glob("*.json"))
    files = [p for p in files if p.name != "_index.json"]
    affected: list[dict] = []
    distinct_added_slugs: dict[str, int] = defaultdict(int)
    total_records = 0

    for path in files:
        rec = json.loads(path.read_text(encoding="utf-8"))
        if rec.get("stub"):
            continue
        if rec.get("is_sub_denomination"):
            continue
        total_records += 1
        current = set(rec.get("grapes", {}).get("principal", [])) | set(
            rec.get("grapes", {}).get("accessory", [])
        )
        candidates = mine_record(rec)
        new = [(s, n, sec) for (s, n, sec) in candidates if s not in current]
        if not new:
            continue
        affected.append(
            {
                "slug": rec["slug"],
                "name": rec["name"],
                "current": sorted(current),
                "additions": new,
            }
        )
        for slug, _, _ in new:
            distinct_added_slugs[slug] += 1

    print("# ES secondary-variety audit\n")
    print(f"Non-stub, non-DGC records scanned: {total_records}")
    print(f"Records with candidate additions : {len(affected)}")
    print(f"Distinct candidate variety slugs : {len(distinct_added_slugs)}")
    print(f"Total candidate additions        : {sum(len(a['additions']) for a in affected)}")
    print()
    print("## Per-DOP candidate additions\n")
    for a in sorted(affected, key=lambda x: x["slug"]):
        print(f"### {a['name']}  ({a['slug']})")
        print(f"  current: {', '.join(a['current']) or '(empty)'}")
        for slug, name, sec in a["additions"]:
            marker = "  +" if slug in DEFAULT_COLOUR else "  ?"
            print(f"{marker} [{sec:>4}] {name!r:30s} → slug={slug}")
        print()
    print("\n## Most-frequent candidate variety slugs\n")
    for slug, count in sorted(distinct_added_slugs.items(), key=lambda x: -x[1])[:30]:
        flag = "" if slug in DEFAULT_COLOUR else "  (unknown in lexicon)"
        print(f"  {count:3d}× {slug}{flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
