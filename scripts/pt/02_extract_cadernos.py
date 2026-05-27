"""Extract structured records from PT IVV cadernos de especificações.

Pipeline stage 02 (pt).

For each wine in `raw/pt/eambrosia/index.json` whose caderno PDF was
cached by stage 01:
  - run pdftotext + the keyword-anchored section finder
  - extract sub-regiões (when the area / grapes section enumerates them)
  - parse a flat principal grape-slug list
  - emit one JSON per (parent, sub-região) pair

For wines without a cached caderno (no IVV match + no override), emit a
stub record with `stub: true, stub_reason: "no-caderno"`. Stage 04 will
still place it in the sidebar (with no polygon) so the corpus is
visible and a curator can fill in the override.

Outputs:
  raw/pt/cadernos-extracted/<slug>.json   — one per record
  raw/pt/cadernos-extracted/_index.json   — slug → metadata

Re-runnable: stages 01 → 02 are deterministic given the cached PDFs and
the manifest. Pass --refresh to force re-extraction.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.grape_entity import (  # noqa: E402
    flush_unknowns_queue, match_variety, set_pliego_context,
)
from _lib.grape_lexicon import GRAPE_ALIAS, GRAPE_BLOCKLIST  # noqa: E402
from _lib.pt.caderno_sections import (  # noqa: E402
    collapse_whitespace,
    extract_sections,
    first_paragraph,
    pdftotext_layout,
)
from _lib.pt.subregiao import extract_subregioes  # noqa: E402

INDEX_PATH = ROOT / "raw" / "pt" / "eambrosia" / "index.json"
CADERNOS_DIR = ROOT / "raw" / "pt" / "ivv" / "cadernos"
CADERNOS_MANIFEST = CADERNOS_DIR / "manifest.json"
OUT_DIR = ROOT / "raw" / "pt" / "cadernos-extracted"
INDEX_OUT_PATH = OUT_DIR / "_index.json"


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()


# Lines we skip when reading grape candidates from the grapes section.
# Anchored at both ends so a header keyword that happens to PREFIX a real
# variety name (`Tinto Cão N`, `Branco Especial B`) doesn't drop the row.
_GRAPE_HEADER_KEYWORDS = re.compile(
    r"^\s*(?:castas?\s+(?:tintas?|brancas?|principais?|secund[áa]rias?|"
    r"utilizadas?|de\s+(?:uva|vitis\s+vin[íi]fera)|menores?)"
    r"|invent[áa]rio\s+das?\s+principais?.*"
    r"|principal\(is\)?\s+casta\(s\)?"
    r"|lista\s+das?\s+castas?"
    r"|quadro\s+\d.*"
    r"|c[óo]digo\s+nome.*"
    r"|de\s+uva"
    r"|cor"
    r"|tinta|branca|tinto|branco|tintas|brancas)\s*[:\-]?\s*$",
    re.IGNORECASE,
)
# Tokens that look like prose words, not variety names. Used to filter
# out lines that survived header stripping (`As castas utilizadas …`).
_PROSE_RE = re.compile(
    r"\b(?:são|deve(?:rão|m)?|podem|pode|com|para|todas?|também|conforme|"
    r"ainda|seguintes?|legisla|consider(?:a|am|ad)|presente|"
    r"adotad|aplicáve|estabelec|regulamento|portaria|"
    r"vinho|vinhos|produto|produtos|indicação|obtidos|obtida|"
    r"replantac|plantac|efectuad|efetuad|ultrapass|elabora|"
    r"vinificaç|cento|conjunto|partir)",
    re.IGNORECASE,
)


_GRAPE_SPLIT_INNER_RE = re.compile(r"\s*,\s*|\s+e\s+")
_CODE_LIKE_RE = re.compile(r"^(?:PRT|PT|ES|FR)?\s*\d{2,}", re.IGNORECASE)
_COLOUR_ONLY = {"branco", "tinto", "rosado", "rose", "rosa", "tinta", "branca"}
_LINE_TAIL_TRIM_RE = re.compile(r"\s+e\s*$", re.IGNORECASE)

# IVV tabular row: trailing single-letter colour code (B/N/R/G/T/Rs/Rg).
# Anchored on a whitespace boundary so we don't eat the final letter of a
# real variety name. Matches at end-of-line only.
_COLOUR_CODE_TAIL_RE = re.compile(r"\s+(?:Rs|Rg|[BNRGT])\s*$")

# Bairrada-style PRT tabular row prefix: `PRT52003 ...`.
_PRT_PREFIX_RE = re.compile(r"^\s*PRT\d{4,6}\s+", re.IGNORECASE)

# PT-IVV tabular name + synonym split. Each side is `<Cap-word>
# [(de|do|da|dos|das) <Cap-word>]` (handles Pico's `Arinto dos Açores
# Terrantez da Terceira` → group(1) = "Arinto dos Açores").
_PT_TABULAR_NAME_RE = re.compile(
    r"^([A-ZÁÂÃÉÊÍÓÔÚÇ][\wÀ-ÿ-]*"
    r"(?:\s+(?:de|do|da|dos|das)\s+[A-ZÁÂÃÉÊÍÓÔÚÇ][\wÀ-ÿ-]+)?)"
    r"(?:\s+(.+))?$",
)

# Sub-região block start — everything after this line belongs to a sub-
# denomination, not the parent grape list. We `break` at the first match.
_SUBREGIAO_LINE_RE = re.compile(r"^\s*sub-?regi[ãa]o\b", re.IGNORECASE)

# IVV section letter-prefix headers — `a. Inventário das…`, `b. Castas
# de uvas…`, `c. Outras castas`. Drop entirely (the keyword regex above
# only handles `a) `/`b) `; this catches the dot-form `a. `).
_LETTER_DOT_HEADER_RE = re.compile(r"^[a-c]\.\s+", re.IGNORECASE)

# Caderno page-footer repetition (every page repeats title + file no.).
_CADERNO_HEADER_RE = re.compile(
    r"caderno\s+de\s+especifica[cç][õo]es", re.IGNORECASE
)

# eAmbrosia file number (printed as page footer; sometimes followed by
# the appellation name on the same line: `PDO-PT-A1470 - Encostas d'Aire`).
_PDO_FILE_NUMBER_RE = re.compile(r"^\s*p?do[-\s]?pt[-\s]?a\d+\b", re.IGNORECASE)

# Slug-level noise filter. After slugification, drop any slug that
# matches one of these — catches residual fragments that survive the
# line-level filters above.
_NOISE_SLUGS = {
    "os-vinhos", "outras-castas", "outras", "uvas-de-vinho",
    "castas-utilizadas", "castas-de-uva",
    "ivv", "ip", "ip-pagina-2",
    "seguinte", "uva",
    # Section-heading boilerplate from the documento-único / caderno templates
    "secundarias", "outros-documentos", "material-de-apoio",
    "estatuto-em-anexo", "decisao-nacional-de-aprovacao",
    "nome-do-processo", "descricao", "documentos-de-apoio",
    "alterada-pela", "mapas-da-area-delimitada",
    "mapa-da-area-delimitada", "referencia-juridica",
    # Bare Portuguese month names — never grape names
    "janeiro", "fevereiro", "marco", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
}
_NOISE_SLUG_RES = [
    re.compile(r"^pdo-?pt-?a\d+$"),
    re.compile(r"^pgi-?pt-?a\d+$"),
    re.compile(r"^prt\d+$"),
    # Plant-passport accession codes — "B PRT52316 Antão Vaz" → b-prt52316-…
    re.compile(r"^b-?prt\d+"),
    re.compile(r"^caderno-de-especificacoes"),
    re.compile(r"^ip-pagina"),
    re.compile(r"^sub-regiao"),
    re.compile(r"^as?-castas-indicadas-em"),
    re.compile(r"^castas?-indicadas-em"),
    # Page footers — `página 11`, `pagina 12 de 18`, `pagina10-de-18`,
    # and the two-number `Página 10/11` form (slugifies to `pagina-10-11`)
    re.compile(r"^pagina-?\d+(-(?:de-)?\d+)?$"),
    # Date strings — "de 13 de janeiro", "de 22 de", "de 9 de dezembro"
    re.compile(r"^de-\d+-de(-[a-z]+)?$"),
    # EU / Portuguese regulation citations — "nº 255/2014", "nº 322/2015"
    re.compile(r"^no?-\d+-\d+$"),
    # `Descrição: «xxx»` field labels — descricao-palmela, descricao-setubal, …
    re.compile(r"^descricao-"),
    # `Nome do processo: DO X` headers
    re.compile(r"^nome-do-processo"),
    # Roman-numeral-prefixed section headings —
    # "ii. Decisão nacional", "iii- nome do processo", etc.
    re.compile(
        r"^(?:i{1,3}v?|iv|v|vi{0,3})-"
        r"(?:decisao|nome|estatuto|material|outros|mapas?|"
        r"referencia|descricao|documentos|secundarias)"
    ),
]


def _strip_colour_code(line: str) -> str:
    """Strip trailing single-letter IVV colour code (B/N/R/G/T/Rs/Rg).

    `Boal Branco B` → `Boal Branco`.  `Petit Verdot N` → `Petit Verdot`.
    """
    return _COLOUR_CODE_TAIL_RE.sub("", line).strip()


def _is_noise_slug(slug: str) -> bool:
    if slug in _NOISE_SLUGS or slug in GRAPE_BLOCKLIST:
        return True
    return any(rx.match(slug) for rx in _NOISE_SLUG_RES)


def _prt_canonical_name(rest: str) -> str:
    """From a PRT-row tail (after stripping `PRT<code>` and colour),
    extract the canonical variety name.

    - `Arinto Pedernã` → `Arinto` (synonym in second slot)
    - `Cabernet-Sauvignon` → `Cabernet-Sauvignon` (no synonym)
    - `Arinto dos Açores Terrantez da Terceira` → `Arinto dos Açores`
      (article-pattern `<Cap> de/do/... <Cap>` is part of the name)
    - `Petit -Verdot` → `Petit-Verdot` (re-glue stray hyphen)
    """
    rest = rest.split(",", 1)[0].strip()
    rest = re.sub(r"\s*-\s*", "-", rest)
    m = _PT_TABULAR_NAME_RE.match(rest)
    if m:
        return m.group(1).strip()
    tokens = rest.split()
    return tokens[0] if tokens else ""


_PAREN_SYNONYM_RE = re.compile(r"\s*\(([^)]*)\)?\s*")


def _split_line_into_candidates(line: str) -> list[str]:
    """One grapes-section line → candidate variety names.

    - `Aragonez; Tinta-Roriz; Tempranillo` (synonyms): take first.
    - `Alfrocheiro, Alvarelhão, … e Trincadeira` (enumeration): split.
    - `Arinto (Pedernã)` (parenthesised synonym): emit both as separate
      candidates so the matcher sees `Arinto` and `Pedernã`
      independently. The matcher's vocab folds them to the same slug;
      dedupe drops the duplicate. Tolerates an unbalanced opening paren
      from a column-split fragment.
    """
    paren_raw = _PAREN_SYNONYM_RE.findall(line)
    paren_synonyms: list[str] = []
    for content in paren_raw:
        for piece in re.split(r"\s*[,;]\s*", content):
            piece = piece.strip()
            if piece:
                paren_synonyms.append(piece)
    bare = _PAREN_SYNONYM_RE.sub(" ", line).strip()
    if ";" in bare:
        bare = bare.split(";")[0].strip()
        return [bare, *paren_synonyms] if bare else paren_synonyms
    if "," in bare or re.search(r"\be\b", bare):
        parts = _GRAPE_SPLIT_INNER_RE.split(bare)
        primary = [p.strip() for p in parts if p.strip()]
    else:
        primary = [bare.strip()] if bare.strip() else []
    return [*primary, *paren_synonyms]


def _candidate_to_slug(candidate: str) -> tuple[str, str] | None:
    """Normalise one candidate name into (display-name, canonical-slug).

    Pre-cleans the candidate (strip leading numeric/code prefix, drop
    prose-looking tokens, drop over-long tokens), then hands off to the
    vocab matcher. Returns None on miss; unmatched tokens land in the
    curator queue via `match_variety`. Note: trailing "Branco"/"Branca"/
    "Tinto"/"Tinta" words are NOT stripped — in PT cadernos these are
    part of the canonical variety name (`Pinheira Branca` is distinct
    from `Pinheira`). The PRT-tabular path strips its own colour-column.
    """
    cand = candidate.strip().rstrip(",.;:").strip()
    if not cand or len(cand) < 3:
        return None
    if _PROSE_RE.search(cand):
        return None
    tokens = cand.split()
    if tokens and _CODE_LIKE_RE.match(tokens[0]):
        tokens = tokens[1:]
    if not tokens:
        return None
    name = " ".join(tokens).strip()
    if len(name) < 3 or len(name.split()) > 5:
        return None
    # Quick noise pre-filter: a token that slugifies to a known noise
    # pattern (PRT-codes, page-footer fragments, regulation citations,
    # …) is rejected before the matcher so the curator queue stays
    # focused on real grape-vs-prose ambiguities.
    pre_slug = GRAPE_ALIAS.get(slugify(name), slugify(name))
    if pre_slug and _is_noise_slug(pre_slug):
        return None
    result = match_variety(name)
    if result is None or result.slug in GRAPE_BLOCKLIST:
        return None
    if _is_noise_slug(result.slug):
        return None
    return result.name, result.slug


def _normalize_line(line: str) -> str:
    """Strip leading enumerators / bullet prefixes / trailing connector."""
    line = re.sub(r"^[a-z]\)\s*", "", line, flags=re.IGNORECASE)
    line = re.sub(r"^\s*\d+\s*[-–.]\s+", "", line)
    return _LINE_TAIL_TRIM_RE.sub("", line).strip()


def _skip_line(line: str) -> bool:
    """True for letter-headers, page-footer repeats, file numbers, and
    `_GRAPE_HEADER_KEYWORDS` matches — none contribute candidates."""
    if _LETTER_DOT_HEADER_RE.match(line):
        return True
    if _CADERNO_HEADER_RE.search(line):
        return True
    if _PDO_FILE_NUMBER_RE.match(line):
        return True
    return bool(_GRAPE_HEADER_KEYWORDS.match(line))


def _prt_row_candidate(line: str) -> str | None:
    """If `line` is a PRT-tabular row, return its canonical name.
    Otherwise return None."""
    if not _PRT_PREFIX_RE.match(line):
        return None
    tail = _PRT_PREFIX_RE.sub("", line).strip()
    tail = _strip_colour_code(tail)
    # Also strip a trailing full-word colour (Pico's "Verdelho Branco").
    tail_tokens = tail.split()
    if tail_tokens and tail_tokens[-1].lower() in _COLOUR_ONLY:
        tail = " ".join(tail_tokens[:-1]).strip()
    if not tail:
        return None
    return _prt_canonical_name(tail)


def _line_candidates(line: str) -> list[str]:
    """One pre-cleaned grapes-section line → list of candidate names.

    Empty list = the caller should skip this line entirely.
    """
    if not line or len(line) < 3:
        return []
    if _SUBREGIAO_LINE_RE.match(line):
        return ["__STOP__"]
    line = _normalize_line(line)
    if not line or _skip_line(line):
        return []
    prt_name = _prt_row_candidate(line)
    if prt_name:
        return [prt_name]
    line = _strip_colour_code(line)
    return _split_line_into_candidates(line) if line else []


def parse_grape_list(grapes_text: str) -> dict:
    """Best-effort flat slug list from a PT grapes section.

    PT cadernos enumerate varieties in three formats:
      Vinho Verde — one variety per line, synonyms joined with `;`.
      Dão — comma-and-`e` enumerations on a single line.
      Bairrada / Pico — tabular `PRT-code  Name  Synonym  Colour`.

    Non-tabular rows from Trás-os-Montes/Douro/Porto/Alentejo/Madeira
    are `Name [Modifier] <ColourCode>` (B/N/R/G/T/Rs/Rg); the colour
    code is stripped before slugification.

    Anything from a `Sub-região …` line onwards is sub-denomination
    grape data and is skipped (it will be inherited at the rendering
    layer rather than mixed into the parent list).
    """
    if not grapes_text:
        return {"principal": [], "accessory": [], "details": []}
    seen: set[str] = set()
    details: list[dict] = []
    for raw in grapes_text.split("\n"):
        candidates = _line_candidates(raw.strip())
        if candidates == ["__STOP__"]:
            break
        for candidate in candidates:
            result = _candidate_to_slug(candidate)
            if not result:
                continue
            name, slug = result
            if slug in seen:
                continue
            seen.add(slug)
            details.append({"slug": slug, "name": name, "role": "principal"})
    return {
        "principal": [d["slug"] for d in details],
        "accessory": [],
        "details": details,
    }


def make_parent_record(
    wine: dict,
    sections: dict[str, str],
    subregioes_count: int,
    caderno_manifest: dict,
) -> dict:
    """Build a parent (non-sub-denomination) record."""
    sections_clean = {
        role: collapse_whitespace(body) for role, body in sections.items()
    }
    area = sections_clean.get("area", "")
    description = sections_clean.get("description", "")
    link_to_terroir = sections_clean.get("link", "")
    grapes_text = sections_clean.get("grapes", "")
    grapes = parse_grape_list(grapes_text)
    # Summary = first paragraph of description, used by stage 02c.
    summary = first_paragraph(description) or first_paragraph(area)

    return {
        "country": "pt",
        "slug": wine["slug"],
        "name": wine["name"],
        "kind": wine["kind"],
        "file_number": wine.get("fileNumber") or "",
        "id_eambrosia": wine.get("giIdentifier") or "",
        "producer_group": wine.get("producer_group") or {},
        "publications": wine.get("publications") or [],
        "eu_protection_date": wine.get("eu_protection_date") or "",
        "modification_date": wine.get("modification_date") or "",
        "is_sub_denomination": False,
        "parent_slug": "",
        "parent_id_eambrosia": "",
        "parent_name": "",
        "sections": sections_clean,
        "summary": summary,
        "geo_area_brief": area[:1200],
        "link_to_terroir": link_to_terroir,
        "grapes": grapes,
        "subregioes_count": subregioes_count,
        "source": {
            "filename": f"{wine['slug']}.pdf",
            "source_url": caderno_manifest.get("source_url") or "",
            "final_url": caderno_manifest.get("final_url") or "",
            "sha256": caderno_manifest.get("sha256") or "",
            "bytes": caderno_manifest.get("bytes") or 0,
            "fetched_at": caderno_manifest.get("fetched_at") or "",
            "from_override": bool(caderno_manifest.get("from_override")),
        },
        "stub": False,
        "stub_reason": "",
    }


def make_subregion_record(
    parent: dict,
    subregiao: dict,
) -> dict:
    """Build a sub-denomination record. Inherits most fields from
    the parent at the rendering layer (same idiom as FR DGCs and ES
    subzonas); we carry only the per-sub-region identity + the body
    paragraph as `geo_area_brief`."""
    sub_slug = subregiao["slug"]
    parent_slug = parent["slug"]
    full_slug = f"{parent_slug}-{sub_slug}"
    return {
        "country": "pt",
        "slug": full_slug,
        "name": subregiao["name"],
        "kind": parent["kind"],
        "file_number": parent["file_number"],
        "id_eambrosia": parent["id_eambrosia"],
        "producer_group": parent["producer_group"],
        "publications": parent["publications"],
        "eu_protection_date": parent["eu_protection_date"],
        "modification_date": parent["modification_date"],
        "is_sub_denomination": True,
        "parent_slug": parent_slug,
        "parent_id_eambrosia": parent["id_eambrosia"],
        "parent_name": parent["name"],
        # Inherit cahier-level sections from the parent so stage 04 can
        # render a non-empty detail panel without re-running extraction.
        "sections": parent["sections"],
        "summary": parent["summary"],
        "geo_area_brief": (subregiao.get("body") or "")[:1200],
        "link_to_terroir": parent["link_to_terroir"],
        "grapes": parent["grapes"],
        "subregioes_count": 0,
        "source_pattern": subregiao.get("source_pattern", ""),
        "source": parent["source"],
        "stub": False,
        "stub_reason": "",
    }


def make_stub_record(wine: dict, reason: str) -> dict:
    """Sidebar-visible stub for wines without a usable caderno."""
    return {
        "country": "pt",
        "slug": wine["slug"],
        "name": wine["name"],
        "kind": wine["kind"],
        "file_number": wine.get("fileNumber") or "",
        "id_eambrosia": wine.get("giIdentifier") or "",
        "producer_group": wine.get("producer_group") or {},
        "publications": wine.get("publications") or [],
        "eu_protection_date": wine.get("eu_protection_date") or "",
        "modification_date": wine.get("modification_date") or "",
        "is_sub_denomination": False,
        "parent_slug": "",
        "parent_id_eambrosia": "",
        "parent_name": "",
        "sections": {},
        "summary": "",
        "geo_area_brief": "",
        "link_to_terroir": "",
        "grapes": {"principal": [], "accessory": [], "details": []},
        "subregioes_count": 0,
        "source": {},
        "stub": True,
        "stub_reason": reason,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--refresh",
        action="store_true",
        help="re-extract even if output JSON already exists",
    )
    ap.add_argument(
        "--only",
        action="append",
        default=[],
        help="slug substring (repeatable)",
    )
    args = ap.parse_args()

    if not INDEX_PATH.exists():
        print(
            f"error: {INDEX_PATH} missing — run scripts/pt/00_fetch_data.py first",
            file=sys.stderr,
        )
        return 1
    if not CADERNOS_MANIFEST.exists():
        print(
            f"error: {CADERNOS_MANIFEST} missing — run scripts/pt/01_fetch_cadernos.py first",
            file=sys.stderr,
        )
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    wines = json.loads(INDEX_PATH.read_text(encoding="utf-8"))["wines"]
    manifest = json.loads(CADERNOS_MANIFEST.read_text(encoding="utf-8")).get("by_slug", {})

    if args.only:
        needles = [s.lower() for s in args.only]
        wines = [w for w in wines if any(n in w["slug"].lower() for n in needles)]

    index: dict[str, dict] = {}
    n_parents = n_subregioes = n_stubs = 0

    for w in tqdm(wines, desc="extract", leave=False):
        slug = w["slug"]
        set_pliego_context(slug)
        info = manifest.get(slug, {})
        status = info.get("status", "unknown")
        if status != "ok":
            stub = make_stub_record(w, reason=f"no-caderno:{status}")
            (OUT_DIR / f"{slug}.json").write_text(
                json.dumps(stub, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            index[slug] = {
                "country": "pt",
                "name": w["name"],
                "kind": w["kind"],
                "is_sub_denomination": False,
                "parent_slug": "",
                "stub": True,
                "stub_reason": stub["stub_reason"],
            }
            n_stubs += 1
            continue

        pdf_path = CADERNOS_DIR / f"{slug}.pdf"
        if not pdf_path.exists():
            stub = make_stub_record(w, reason="no-caderno:missing-pdf")
            (OUT_DIR / f"{slug}.json").write_text(
                json.dumps(stub, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            index[slug] = {
                "country": "pt",
                "name": w["name"],
                "kind": w["kind"],
                "is_sub_denomination": False,
                "parent_slug": "",
                "stub": True,
                "stub_reason": stub["stub_reason"],
            }
            n_stubs += 1
            continue

        try:
            text = pdftotext_layout(pdf_path)
        except Exception as exc:  # noqa: BLE001
            stub = make_stub_record(w, reason=f"pdftotext-error:{exc!r}")
            (OUT_DIR / f"{slug}.json").write_text(
                json.dumps(stub, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            index[slug] = {
                "country": "pt",
                "name": w["name"],
                "kind": w["kind"],
                "is_sub_denomination": False,
                "parent_slug": "",
                "stub": True,
                "stub_reason": stub["stub_reason"],
            }
            n_stubs += 1
            continue

        sections = extract_sections(text)
        sub_records = extract_subregioes(
            sections.get("area", ""), sections.get("grapes", "")
        )
        parent = make_parent_record(w, sections, len(sub_records), info)
        (OUT_DIR / f"{slug}.json").write_text(
            json.dumps(parent, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        index[slug] = {
            "country": "pt",
            "name": parent["name"],
            "kind": parent["kind"],
            "is_sub_denomination": False,
            "parent_slug": "",
            "subregioes_count": parent["subregioes_count"],
            "stub": False,
            "stub_reason": "",
        }
        n_parents += 1

        for sr in sub_records:
            sub = make_subregion_record(parent, sr)
            (OUT_DIR / f"{sub['slug']}.json").write_text(
                json.dumps(sub, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            index[sub["slug"]] = {
                "country": "pt",
                "name": sub["name"],
                "kind": sub["kind"],
                "is_sub_denomination": True,
                "parent_slug": sub["parent_slug"],
                "stub": False,
                "stub_reason": "",
            }
            n_subregioes += 1

    set_pliego_context(None)
    INDEX_OUT_PATH.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "counts": {
                    "parents": n_parents,
                    "subregioes": n_subregioes,
                    "stubs": n_stubs,
                    "total": n_parents + n_subregioes + n_stubs,
                },
                "by_slug": index,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    unknowns_path = ROOT / "raw" / "pt" / "extraction-unknowns.json"
    n_unknowns = flush_unknowns_queue(unknowns_path)
    if n_unknowns:
        print(
            f"[entity] {n_unknowns} unknown variety candidates → "
            f"review at {unknowns_path.relative_to(ROOT)}",
            file=sys.stderr,
        )
    print(
        f"[done] parents={n_parents} subregioes={n_subregioes} "
        f"stubs={n_stubs} → {OUT_DIR.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
