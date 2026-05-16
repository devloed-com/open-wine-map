"""Generate one wiki/<slug>.md per ES wine record + extend
wiki/_index.json with ES entries.

Pipeline stage 03 (es). Mirrors `scripts/03_generate_wiki.py` for the
ES corpus. Reads `raw/es/pliegos-extracted/*.json` and the
`raw/translations/summaries/<lang>/<slug>.json` cache for per-locale
summary text, emits per-record markdown pages with Spanish section
headings, and merges ES entries into `wiki/_index.json` (preserving
any pre-existing FR entries).

Frontmatter mirrors the FR shape with ES-specific fields:
  country, slug, kind, file_number, region (CCAA), is_sub_denomination,
  parent_slug, parent_name, sources (eAmbrosia URL, EUR-Lex URL).

Section order:
  Resumen / Zona geográfica / Variedades / Vínculo con la zona
  geográfica / Fuentes
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.es.region import derive_ccaa  # noqa: E402

EXTRACTED = ROOT / "raw" / "es" / "pliegos-extracted"
WIKI = ROOT / "wiki"
WIKI_INDEX = WIKI / "_index.json"

SECTION_LABELS = {
    "summary": "Resumen",
    "geo": "Zona geográfica",
    "grapes": "Variedades de uva",
    "link": "Vínculo con la zona geográfica",
    "sources": "Fuentes",
}


def render_record(record: dict) -> str:
    """Render one ES record as a markdown page."""
    name = record["name"]
    slug = record["slug"]
    kind = record.get("kind", "DOP")
    region = derive_ccaa(record) if not record.get("is_sub_denomination") else ""
    is_sub_denomination = bool(record.get("is_sub_denomination"))
    parent_slug = record.get("parent_slug") or ""
    parent_name = record.get("parent_name") or ""

    src = record.get("source") or {}
    summary = (record.get("summary") or "").strip()
    geo = (record.get("geo_area_brief") or "").strip()
    link = (record.get("link_to_terroir") or "").strip()
    grapes_raw = (record.get("grapes") or {}).get("raw_tokens") or []

    fm = [
        "---",
        f"title: {name}",
        f"type: {kind.lower()}",
        f"slug: {slug}",
        "country: es",
        f"region: {region}",
        f"kind: {kind}",
        f"file_number: {record.get('file_number') or ''}",
        f"id_eambrosia: {record.get('id_eambrosia') or ''}",
    ]
    if is_sub_denomination:
        fm += [
            "is_sub_denomination: true",
            f"parent_slug: {parent_slug}",
            f"parent_name: {parent_name}",
        ]
    if record.get("stub"):
        fm += [
            "stub: true",
            f"stub_reason: {record.get('stub_reason') or ''}",
        ]
    fm += [
        "sources:",
        f"  eu_oj: {src.get('final_url') or src.get('source_url') or ''}",
        f"  eu_oj_filename: {src.get('filename') or ''}",
        "---",
        "",
        f"# {name}",
        "",
    ]
    if is_sub_denomination and parent_slug:
        fm.append(f"_Subzona de [[{parent_slug}|{parent_name}]]._")
        fm.append("")

    body: list[str] = []

    if record.get("stub"):
        body += [
            "> ⚠️ **Pliego no disponible.** "
            f"Razón: `{record.get('stub_reason') or 'unknown'}`. "
            "El nombre se mantiene en el índice; el contenido se completará "
            "cuando se incorpore una URL pública (curador) o cuando "
            "eAmbrosia publique una nueva referencia.",
            "",
            f"## {SECTION_LABELS['sources']}",
            "",
            f"- eAmbrosia: <https://ec.europa.eu/agriculture/eambrosia/geographical-indications-register/details/{record.get('id_eambrosia') or ''}>",
            f"- File number: `{record.get('file_number') or ''}`",
            "",
        ]
        return "\n".join(fm + body)

    if summary:
        body += [
            f"## {SECTION_LABELS['summary']}",
            "",
            _truncate(summary, max_chars=1200),
            "",
        ]

    if geo:
        body += [
            f"## {SECTION_LABELS['geo']}",
            "",
            _truncate(geo, max_chars=2000),
            "",
        ]

    if grapes_raw:
        body += [
            f"## {SECTION_LABELS['grapes']}",
            "",
            ", ".join(grapes_raw),
            "",
        ]

    if link:
        body += [
            f"## {SECTION_LABELS['link']}",
            "",
            _truncate(link, max_chars=2000),
            "",
        ]

    body += [
        f"## {SECTION_LABELS['sources']}",
        "",
        f"- EUR-Lex (DOCUMENTO ÚNICO): <{src.get('final_url') or src.get('source_url') or ''}>",
        f"- eAmbrosia GI register: <https://ec.europa.eu/agriculture/eambrosia/geographical-indications-register/details/{record.get('id_eambrosia') or ''}>",
        f"- File number: `{record.get('file_number') or ''}`",
        "",
        f"_Texto del pliego: © Unión Europea / EUR-Lex. Reutilización con atribución._",
        "",
    ]
    return "\n".join(fm + body)


def _truncate(text: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(". ", 1)[0]
    return cut + ("." if not cut.endswith(".") else "")


def index_entry(record: dict) -> dict:
    return {
        "country": "es",
        "id_eambrosia": record.get("id_eambrosia") or "",
        "file_number": record.get("file_number") or "",
        "name": record["name"],
        "kind": record.get("kind", "DOP"),
        "region": derive_ccaa(record) if not record.get("is_sub_denomination") else "",
        "is_sub_denomination": bool(record.get("is_sub_denomination")),
        "parent_slug": record.get("parent_slug") or "",
        "parent_name": record.get("parent_name") or "",
        "categories": [record.get("kind", "DOP")] if not record.get("is_sub_denomination") else [],
        "stub": bool(record.get("stub")),
        "stub_reason": record.get("stub_reason", ""),
        "page": f"{record['slug']}.md",
    }


def main() -> int:
    if not EXTRACTED.exists():
        print(f"error: {EXTRACTED} missing — run scripts/es/02_extract_pliegos.py first",
              file=sys.stderr)
        return 1

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", default=[])
    args = ap.parse_args()

    files = sorted(p for p in EXTRACTED.glob("*.json") if not p.name.startswith("_"))
    if args.only:
        needles = [s.lower() for s in args.only]
        files = [p for p in files if any(n in p.stem.lower() for n in needles)]

    WIKI.mkdir(parents=True, exist_ok=True)
    written = 0
    es_index: dict[str, dict] = {}
    for f in tqdm(files, desc="es-wiki", leave=False):
        rec = json.loads(f.read_text())
        out_path = WIKI / f"{rec['slug']}.md"
        out_path.write_text(render_record(rec))
        es_index[rec["slug"]] = index_entry(rec)
        written += 1

    # Merge into wiki/_index.json: keep FR entries, replace any prior ES
    # entries with the fresh ones.
    existing: dict[str, dict] = {}
    if WIKI_INDEX.exists():
        try:
            existing = json.loads(WIKI_INDEX.read_text())
        except (ValueError, OSError):
            existing = {}
    fr_kept = {k: v for k, v in existing.items() if v.get("country") != "es"}
    merged = {**fr_kept, **es_index}
    WIKI_INDEX.write_text(json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True))
    print(
        f"[es/03] wrote {written} ES wiki pages, merged index "
        f"({len(fr_kept)} FR + {len(es_index)} ES = {len(merged)} entries) "
        f"@ {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
