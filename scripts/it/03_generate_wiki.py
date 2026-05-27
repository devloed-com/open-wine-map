"""Generate one wiki/<slug>.md per IT wine record + extend
wiki/_index.json with IT entries.

Pipeline stage 03 (it). Mirrors `scripts/es/03_generate_wiki.py` for the
IT corpus. Reads `raw/it/disciplinari-extracted/*.json`, emits per-record
markdown pages with Italian section headings, and merges IT entries
into `wiki/_index.json` (preserving any pre-existing FR / ES / PT
entries).

Section order:
  Riepilogo / Zona geografica / Varietà di uve / Descrizione del
  legame / Menzioni geografiche aggiuntive / Fonti
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
from _lib.it.region import derive_regione  # noqa: E402

EXTRACTED = ROOT / "raw" / "it" / "disciplinari-extracted"
MASAF_EXTRACTED = ROOT / "raw" / "it" / "masaf-disciplinari-extracted"
WIKI = ROOT / "wiki"
WIKI_INDEX = WIKI / "_index.json"
TERROIR_FACTS = ROOT / "raw" / "terroir-facts"

_FACTS_SLUGS: frozenset[str] | None = None
_MASAF_REGIONI: dict[str, str] | None = None


def _masaf_regione(slug: str) -> str:
    """Regione from the stage-02f MASAF sidecar. A MASAF-augmented stub's
    regione lives in the sidecar, not the (immutable) on-disk stub
    record — stage 04 merges it in; stage 03 reads it directly so the
    wiki frontmatter carries the regione too."""
    global _MASAF_REGIONI
    if _MASAF_REGIONI is None:
        out: dict[str, str] = {}
        if MASAF_EXTRACTED.exists():
            for p in MASAF_EXTRACTED.glob("*.json"):
                if p.name.startswith("_"):
                    continue
                try:
                    rec = json.loads(p.read_text(encoding="utf-8"))
                except (ValueError, OSError):
                    continue
                if rec.get("regione"):
                    out[rec.get("slug") or p.stem] = rec["regione"]
        _MASAF_REGIONI = out
    return _MASAF_REGIONI.get(slug, "")


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
                    if json.loads(p.read_text(encoding="utf-8")).get("facts"):
                        slugs.add(p.stem)
                except (ValueError, OSError):
                    continue
        _FACTS_SLUGS = frozenset(slugs)
    return _FACTS_SLUGS


SECTION_LABELS = {
    "summary": "Riepilogo",
    "geo": "Zona geografica delimitata",
    "grapes": "Varietà di uve",
    "menzioni": "Menzioni geografiche aggiuntive",
    "link": "Descrizione del legame con la zona geografica",
    "sources": "Fonti",
}


def _resolve_regione(record: dict) -> str:
    if record.get("regione"):
        return record["regione"]
    if record.get("is_sub_denomination"):
        return ""
    sidecar = _masaf_regione(record.get("slug") or "")
    if sidecar:
        return sidecar
    # Fallback only — stage 02 / 02f persist `regione` on every real
    # record. Terroir text is deliberately not passed (it names
    # neighbouring regioni); a commune index is not available here.
    return derive_regione(
        {"file_number": record.get("file_number") or ""},
        (record.get("section_roles") or {}).get("geo_area", ""),
        record.get("name", ""),
    )


def render_record(record: dict) -> str:
    name = record["name"]
    slug = record["slug"]
    kind = record.get("kind", "DOP")
    region = _resolve_regione(record)
    is_sub_denomination = bool(record.get("is_sub_denomination"))
    parent_slug = record.get("parent_slug") or ""
    parent_name = record.get("parent_name") or ""

    src = record.get("source") or {}
    summary = (record.get("summary") or "").strip()
    geo = (record.get("geo_area_brief") or "").strip()
    link = (record.get("link_to_terroir") or "").strip()
    grape_details = (record.get("grapes") or {}).get("details") or []
    menzioni = record.get("menzioni") or []

    fm = [
        "---",
        f"title: {name}",
        f"type: {kind.lower()}",
        f"slug: {slug}",
        "country: it",
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
        fm.append(f"_Sottozona di [[{parent_slug}|{parent_name}]]._")
        fm.append("")

    body: list[str] = []

    if record.get("stub"):
        body += [
            "> ⚠️ **Documento unico non disponibile.** "
            f"Motivo: `{record.get('stub_reason') or 'unknown'}`. "
            "Il nome rimane nell'indice; il contenuto sarà completato "
            "quando una URL pubblica del disciplinare sarà disponibile "
            "(curatore) o quando eAmbrosia pubblicherà un nuovo "
            "riferimento.",
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
        body += [
            f"## {SECTION_LABELS['grapes']}",
            "",
            ", ".join(d.get("name") or d.get("slug") for d in grape_details),
            "",
        ]

    if link:
        body += [
            f"## {SECTION_LABELS['link']}",
            "",
            _truncate(link, max_chars=2000),
            "",
        ]

    if menzioni:
        body += [
            f"## {SECTION_LABELS['menzioni']}",
            "",
            ", ".join(m.get("name") for m in menzioni),
            "",
        ]

    body += [
        f"## {SECTION_LABELS['sources']}",
        "",
        f"- EUR-Lex (DOCUMENTO UNICO): <{src.get('final_url') or src.get('source_url') or ''}>",
        f"- eAmbrosia GI register: <https://ec.europa.eu/agriculture/eambrosia/geographical-indications-register/details/{record.get('id_eambrosia') or ''}>",
        f"- File number: `{record.get('file_number') or ''}`",
        "",
        "_Testo del documento unico: © Unione Europea / EUR-Lex. Riutilizzo con attribuzione._",
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
        "country": "it",
        "id_eambrosia": record.get("id_eambrosia") or "",
        "file_number": record.get("file_number") or "",
        "name": record["name"],
        "kind": record.get("kind", "DOP"),
        "region": _resolve_regione(record),
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
        print(f"error: {EXTRACTED} missing — run scripts/it/02_extract_pliegos.py first",
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
    it_index: dict[str, dict] = {}
    for f in tqdm(files, desc="it-wiki", leave=False):
        rec = json.loads(f.read_text(encoding="utf-8"))
        out_path = WIKI / f"{rec['slug']}.md"
        out_path.write_text(render_record(rec), encoding="utf-8")
        it_index[rec["slug"]] = index_entry(rec)
        written += 1

    existing: dict[str, dict] = {}
    if WIKI_INDEX.exists():
        try:
            existing = json.loads(WIKI_INDEX.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            existing = {}
    other_kept = {k: v for k, v in existing.items() if v.get("country") != "it"}
    merged = {**other_kept, **it_index}
    WIKI_INDEX.write_text(json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(
        f"[it/03] wrote {written} IT wiki pages, merged index "
        f"({len(other_kept)} non-IT + {len(it_index)} IT = {len(merged)} entries) "
        f"@ {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
