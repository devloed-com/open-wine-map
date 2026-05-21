"""Generate one wiki/<slug>.md per PT wine record + extend
wiki/_index.json with PT entries.

Pipeline stage 03 (pt). Mirrors `scripts/es/03_generate_wiki.py` for
the PT corpus. Reads `raw/pt/cadernos-extracted/*.json`, emits per-
record markdown pages with Portuguese section headings, and merges
PT entries into `wiki/_index.json` (preserving any pre-existing FR
and ES entries).

Frontmatter mirrors the ES shape with PT-specific fields:
  country, slug, kind, file_number, region, is_sub_denomination,
  parent_slug, parent_name, sources (IVV caderno PDF URL).

Section order:
  Resumo / Área geográfica / Castas / Relação com a área
  geográfica / Fontes
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
from _lib.pt.region import derive_region  # noqa: E402

EXTRACTED = ROOT / "raw" / "pt" / "cadernos-extracted"
WIKI = ROOT / "wiki"
WIKI_INDEX = WIKI / "_index.json"
TERROIR_FACTS = ROOT / "raw" / "terroir-facts"

_FACTS_SLUGS: frozenset[str] | None = None


def _terroir_facts_slugs() -> frozenset[str]:
    """Slugs whose terroir-facts cache holds at least one fact. The fallback
    summary is suppressed only for these — a record that 02d extracted to
    zero facts still shows its summary."""
    global _FACTS_SLUGS
    if _FACTS_SLUGS is None:
        slugs: set[str] = set()
        if TERROIR_FACTS.exists():
            for p in TERROIR_FACTS.glob("*.json"):
                if p.stem.startswith("manifest"):
                    continue
                try:
                    if json.loads(p.read_text()).get("facts"):
                        slugs.add(p.stem)
                except (ValueError, OSError):
                    continue
        _FACTS_SLUGS = frozenset(slugs)
    return _FACTS_SLUGS


SECTION_LABELS = {
    "summary": "Resumo",
    "geo": "Área geográfica",
    "grapes": "Castas",
    "link": "Relação com a área geográfica",
    "sources": "Fontes",
}


def _truncate(text: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(". ", 1)[0]
    return cut + ("." if not cut.endswith(".") else "")


def render_record(record: dict) -> str:
    name = record["name"]
    slug = record["slug"]
    kind = record.get("kind", "DOP")
    region = derive_region(record)
    is_sub = bool(record.get("is_sub_denomination"))
    parent_slug = record.get("parent_slug") or ""
    parent_name = record.get("parent_name") or ""

    src = record.get("source") or {}
    summary = (record.get("summary") or "").strip()
    geo = (record.get("geo_area_brief") or "").strip()
    link = (record.get("link_to_terroir") or "").strip()
    grape_details = (record.get("grapes") or {}).get("details") or []

    fm: list[str] = [
        "---",
        f"title: {name}",
        f"type: {kind.lower()}",
        f"slug: {slug}",
        "country: pt",
        f"region: {region}",
        f"kind: {kind}",
        f"file_number: {record.get('file_number') or ''}",
        f"id_eambrosia: {record.get('id_eambrosia') or ''}",
    ]
    if is_sub:
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
        f"  ivv_caderno: {src.get('source_url') or ''}",
        f"  ivv_filename: {src.get('filename') or ''}",
        "---",
        "",
        f"# {name}",
        "",
    ]
    if is_sub and parent_slug:
        fm.append(f"_Sub-região de [[{parent_slug}|{parent_name}]]._")
        fm.append("")

    body: list[str] = []

    if record.get("stub"):
        body += [
            "> ⚠️ **Caderno de especificações indisponível.** "
            f"Motivo: `{record.get('stub_reason') or 'unknown'}`. "
            "O nome mantém-se no índice; o conteúdo será preenchido "
            "quando uma URL pública for incorporada (curador) ou "
            "quando o IVV publicar uma nova referência.",
            "",
            f"## {SECTION_LABELS['sources']}",
            "",
            f"- eAmbrosia: <https://ec.europa.eu/agriculture/eambrosia/geographical-indications-register/details/{record.get('id_eambrosia') or ''}>",
            f"- File number: `{record.get('file_number') or ''}`",
            "",
        ]
        return "\n".join(fm + body)

    _psl = record.get("parent_slug") or ""
    _facts = _terroir_facts_slugs()
    if summary and slug not in _facts and _psl not in _facts:
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
    if grape_details:
        names = [d.get("name") or d.get("slug") for d in grape_details]
        body += [
            f"## {SECTION_LABELS['grapes']}",
            "",
            ", ".join(names),
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
        f"- IVV — caderno de especificações: <{src.get('source_url') or ''}>",
        f"- eAmbrosia GI register: <https://ec.europa.eu/agriculture/eambrosia/geographical-indications-register/details/{record.get('id_eambrosia') or ''}>",
        f"- File number: `{record.get('file_number') or ''}`",
        "",
        "_Texto do caderno: © Instituto da Vinha e do Vinho, I.P. — "
        "reutilização com atribuição._",
        "",
    ]
    return "\n".join(fm + body)


def index_entry(record: dict) -> dict:
    is_sub = bool(record.get("is_sub_denomination"))
    return {
        "country": "pt",
        "id_eambrosia": record.get("id_eambrosia") or "",
        "file_number": record.get("file_number") or "",
        "name": record["name"],
        "kind": record.get("kind", "DOP"),
        "region": derive_region(record),
        "is_sub_denomination": is_sub,
        "parent_slug": record.get("parent_slug") or "",
        "parent_name": record.get("parent_name") or "",
        "categories": [record.get("kind", "DOP")] if not is_sub else [],
        "stub": bool(record.get("stub")),
        "stub_reason": record.get("stub_reason", ""),
        "page": f"{record['slug']}.md",
    }


def main() -> int:
    if not EXTRACTED.exists():
        print(
            f"error: {EXTRACTED} missing — run scripts/pt/02_extract_cadernos.py first",
            file=sys.stderr,
        )
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
    pt_index: dict[str, dict] = {}
    for f in tqdm(files, desc="pt-wiki", leave=False):
        rec = json.loads(f.read_text())
        out_path = WIKI / f"{rec['slug']}.md"
        out_path.write_text(render_record(rec))
        pt_index[rec["slug"]] = index_entry(rec)
        written += 1

    existing: dict[str, dict] = {}
    if WIKI_INDEX.exists():
        try:
            existing = json.loads(WIKI_INDEX.read_text())
        except (ValueError, OSError):
            existing = {}
    kept = {k: v for k, v in existing.items() if v.get("country") != "pt"}
    merged = {**kept, **pt_index}
    WIKI_INDEX.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True)
    )
    by_country: dict[str, int] = {}
    for v in merged.values():
        c = v.get("country") or "fr"
        by_country[c] = by_country.get(c, 0) + 1
    print(
        f"[pt/03] wrote {written} PT wiki pages, merged index "
        f"({by_country}) @ "
        f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
