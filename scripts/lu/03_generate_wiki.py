"""Generate one wiki/<slug>.md per LU record + extend wiki/_index.json.

Pipeline stage 03 (lu). Sibling of scripts/sk/03_generate_wiki.py.
Reads raw/lu/cahier-extracted/*.json (1 parent + 11 per-commune
sub-denominations), emits per-record markdown pages with French
section headings, and merges LU entries into wiki/_index.json
(preserving entries from other countries).
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
from _lib.lu.region import derive_region  # noqa: E402

EXTRACTED = ROOT / "raw" / "lu" / "cahier-extracted"
WIKI = ROOT / "wiki"
WIKI_INDEX = WIKI / "_index.json"
TERROIR_FACTS = ROOT / "raw" / "terroir-facts"
APPELLATION_NOTES = ROOT / "scripts" / "_lib" / "appellation_notes.json"

_FACTS_SLUGS: frozenset[str] | None = None
_NOTES: dict[str, dict] | None = None


def _terroir_facts_slugs() -> frozenset[str]:
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


def _appellation_notes() -> dict[str, dict]:
    global _NOTES
    if _NOTES is None:
        _NOTES = {}
        if APPELLATION_NOTES.exists():
            try:
                raw = json.loads(APPELLATION_NOTES.read_text(encoding="utf-8"))
                _NOTES = {k: v for k, v in raw.items() if not k.startswith("__")}
            except (ValueError, OSError):
                _NOTES = {}
    return _NOTES


# French headings — LU's source language is fr.
SECTION_LABELS = {
    "summary": "Résumé",
    "geo": "Aire géographique",
    "grapes": "Cépages",
    "yields": "Rendements maximaux",
    "link": "Lien au terroir",
    "controle": "Autorité de contrôle",
    "note": "Note",
    "sources": "Sources",
}


def _truncate(text: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(". ", 1)[0]
    return cut + ("." if not cut.endswith(".") else "")


def _render_note_section(slug: str) -> list[str]:
    note = _appellation_notes().get(slug)
    if not note:
        return []
    text = ((note.get("note") or {}).get("fr") or
            (note.get("note") or {}).get("en") or "").strip()
    if not text:
        return []
    body = [f"## {SECTION_LABELS['note']}", "", text, ""]
    sources = note.get("sources") or []
    if sources:
        for s in sources:
            label = (s.get("label") or "").strip()
            url = (s.get("url") or "").strip()
            if label and url:
                body.append(f"- [{label}]({url})")
        body.append("")
    return body


def render_record(record: dict) -> str:
    name = record["name"]
    slug = record["slug"]
    kind = record.get("kind", "DOP")
    region = record.get("region") or derive_region(record)

    src = record.get("source") or {}
    summary = (record.get("summary") or "").strip()
    geo = (record.get("geo_area_brief") or "").strip()
    yields_text = (record.get("yields_text") or "").strip()
    link = (record.get("link_to_terroir") or "").strip()
    controle = (record.get("autorite_controle") or "").strip()
    grape_details = (record.get("grapes") or {}).get("details") or []

    fm = [
        "---",
        f"title: {name}",
        f"type: {kind.lower()}",
        f"slug: {slug}",
        "country: lu",
        f"region: {region}",
        f"kind: {kind}",
        f"file_number: {record.get('file_number') or ''}",
        f"id_eambrosia: {record.get('id_eambrosia') or ''}",
    ]
    if record.get("is_sub_denomination"):
        fm += [
            "is_sub_denomination: true",
            f"parent_slug: {record.get('parent_slug') or ''}",
            f"parent_name: {record.get('parent_name') or ''}",
            f"commune: {record.get('commune') or ''}",
        ]
    fm += [
        "sources:",
        f"  cahier: {src.get('source_url') or ''}",
        f"  cahier_filename: {src.get('filename') or ''}",
        f"  publisher: {src.get('publisher') or ''}",
        "---",
        "",
        f"# {name}",
        "",
    ]

    body: list[str] = []

    if record.get("is_sub_denomination"):
        body += [
            f"> Sous-dénomination communale de [{record.get('parent_name')}]"
            f"({record.get('parent_slug')}.md) — les vins issus de la commune "
            f"de **{record.get('commune')}** peuvent porter cette indication "
            f"sur l'étiquette (Art. 8 / Art. 9 du règlement grand-ducal du "
            f"17 décembre 2015). Cépages, terroir et règles d'élaboration "
            f"sont ceux de l'AOP-Moselle Luxembourgeoise.",
            "",
        ]
        historic = record.get("historic_communes") or []
        if historic:
            body += [
                f"_Communes historiques fusionnées dans **{record.get('commune')}**: "
                f"{', '.join(historic)}._",
                "",
            ]

    _facts = _terroir_facts_slugs()
    if summary and slug not in _facts:
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

    if grape_details and not record.get("is_sub_denomination"):
        body += [
            f"## {SECTION_LABELS['grapes']}",
            "",
            ", ".join(d.get("name") or d.get("slug") for d in grape_details),
            "",
        ]

    if yields_text and not record.get("is_sub_denomination"):
        body += [
            f"## {SECTION_LABELS['yields']}",
            "",
            _truncate(yields_text, max_chars=600),
            "",
        ]

    if link and not record.get("is_sub_denomination"):
        body += [
            f"## {SECTION_LABELS['link']}",
            "",
            _truncate(link, max_chars=2400),
            "",
        ]

    if controle and not record.get("is_sub_denomination"):
        body += [
            f"## {SECTION_LABELS['controle']}",
            "",
            _truncate(controle, max_chars=600),
            "",
        ]

    body += _render_note_section(slug)

    body += [
        f"## {SECTION_LABELS['sources']}",
        "",
        f"- Cahier des charges (IVV): <{src.get('source_url') or ''}>",
        f"- Éditeur: {src.get('publisher') or 'Institut Viti-Vinicole'}",
        f"- eAmbrosia GI-Register: "
        f"<https://ec.europa.eu/agriculture/eambrosia/geographical-indications-register/details/"
        f"{record.get('id_eambrosia') or ''}>",
        f"- File number: `{record.get('file_number') or ''}`",
        "",
        "_Cahier des charges: © Institut Viti-Vinicole / Ministère de "
        "l'Agriculture (Luxembourg). Document public, réutilisation avec "
        "attribution._",
        "",
    ]
    return "\n".join(fm + body)


def index_entry(record: dict) -> dict:
    return {
        "country": "lu",
        "id_eambrosia": record.get("id_eambrosia") or "",
        "file_number": record.get("file_number") or "",
        "name": record["name"],
        "kind": record.get("kind", "DOP"),
        "region": record.get("region") or derive_region(record),
        "is_sub_denomination": bool(record.get("is_sub_denomination")),
        "parent_slug": record.get("parent_slug") or "",
        "parent_name": record.get("parent_name") or "",
        "commune": record.get("commune") or "",
        "categories": list(record.get("categories") or [record.get("kind", "DOP")]),
        "stub": bool(record.get("stub")),
        "page": f"{record['slug']}.md",
    }


def main() -> int:
    if not EXTRACTED.exists():
        print(f"error: {EXTRACTED} missing — run scripts/lu/02_extract_cahier.py first",
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
    lu_index: dict[str, dict] = {}
    for f in tqdm(files, desc="lu-wiki", leave=False):
        rec = json.loads(f.read_text(encoding="utf-8"))
        out_path = WIKI / f"{rec['slug']}.md"
        out_path.write_text(render_record(rec), encoding="utf-8")
        lu_index[rec["slug"]] = index_entry(rec)
        written += 1

    existing: dict[str, dict] = {}
    if WIKI_INDEX.exists():
        try:
            existing = json.loads(WIKI_INDEX.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            existing = {}
    other_kept = {k: v for k, v in existing.items() if v.get("country") != "lu"}
    merged = {**other_kept, **lu_index}
    WIKI_INDEX.write_text(json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(
        f"[lu/03] wrote {written} LU wiki pages, merged index "
        f"({len(other_kept)} non-LU + {len(lu_index)} LU = {len(merged)} entries) "
        f"@ {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
