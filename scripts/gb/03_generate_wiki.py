"""Generate one wiki/<slug>.md per GB wine record + extend
wiki/_index.json with GB entries.

Pipeline stage 03 (gb). Mirrors `scripts/mt/03_generate_wiki.py` — the
other English-source corpus — for the United Kingdom. Reads
`raw/gb/specs-extracted/*.json`, emits per-record markdown pages with
English section headings, and merges GB entries into `wiki/_index.json`
(preserving entries from the other countries).

Sources cited per page are the UK ones: the DEFRA product specification
and the GOV.UK register entry. No EUR-Lex or eAmbrosia link is emitted —
the UK register is the authority for these names.
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
from _lib.gb.region import derive_region  # noqa: E402

EXTRACTED = ROOT / "raw" / "gb" / "specs-extracted"
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


SECTION_LABELS = {
    "summary": "Summary",
    "geo": "Demarcated area",
    "grapes": "Grape varieties",
    "link": "Link with the geographical area",
    "note": "Note",
    "sources": "Sources",
}


def _resolve_region(record: dict) -> str:
    return record.get("region") or derive_region({
        "file_number": record.get("file_number") or "",
        "demarcation": record.get("demarcation") or "",
    })


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
    text = ((note.get("note") or {}).get("en") or "").strip()
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
    region = _resolve_region(record)

    src = record.get("source") or {}
    summary = (record.get("summary") or "").strip()
    geo = (record.get("geo_area_brief") or "").strip()
    link = (record.get("link_to_terroir") or "").strip()
    grape_details = (record.get("grapes") or {}).get("details") or []

    fm = [
        "---",
        f"title: {name}",
        f"type: {kind.lower()}",
        f"slug: {slug}",
        "country: gb",
        f"region: {region}",
        f"kind: {kind}",
        f"file_number: {record.get('file_number') or ''}",
        f"parser_template: {record.get('parser_template') or ''}",
    ]
    if record.get("stub"):
        fm += [
            "stub: true",
            f"stub_reason: {record.get('stub_reason') or ''}",
        ]
    fm += [
        "sources:",
        f"  product_specification: {src.get('source_url') or ''}",
        f"  register_entry: {src.get('register_url') or ''}",
        f"  specification_filename: {src.get('filename') or ''}",
        "---",
        "",
        f"# {name}",
        "",
    ]

    body: list[str] = []

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

    body += _render_note_section(slug)

    body += [
        f"## {SECTION_LABELS['sources']}",
        "",
        f"- Product specification (DEFRA): <{src.get('source_url') or ''}>",
        f"- UK GI register entry: <{src.get('register_url') or ''}>",
        f"- File number: `{record.get('file_number') or ''}`",
        "",
        "_Product-specification text: © Crown copyright, DEFRA / GOV.UK. "
        "Licensed under the Open Government Licence v3.0._",
        "",
    ]
    return "\n".join(fm + body)


def index_entry(record: dict) -> dict:
    return {
        "country": "gb",
        "file_number": record.get("file_number") or "",
        "name": record["name"],
        "kind": record.get("kind", "DOP"),
        "region": _resolve_region(record),
        "is_sub_denomination": False,
        "parent_slug": "",
        "parent_name": "",
        "categories": [record.get("kind", "DOP")],
        "stub": False,
        "page": f"{record['slug']}.md",
    }


def main() -> int:
    if not EXTRACTED.exists():
        print(f"error: {EXTRACTED} missing — run scripts/gb/02_extract_specs.py first",
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
    gb_index: dict[str, dict] = {}
    for f in tqdm(files, desc="gb-wiki", leave=False):
        rec = json.loads(f.read_text(encoding="utf-8"))
        out_path = WIKI / f"{rec['slug']}.md"
        out_path.write_text(render_record(rec), encoding="utf-8")
        gb_index[rec["slug"]] = index_entry(rec)
        written += 1

    existing: dict[str, dict] = {}
    if WIKI_INDEX.exists():
        try:
            existing = json.loads(WIKI_INDEX.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            existing = {}
    other_kept = {k: v for k, v in existing.items() if v.get("country") != "gb"}
    merged = {**other_kept, **gb_index}
    WIKI_INDEX.write_text(json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True),
                          encoding="utf-8")
    print(
        f"[gb/03] wrote {written} GB wiki pages, merged index "
        f"({len(other_kept)} non-GB + {len(gb_index)} GB = {len(merged)} entries) "
        f"@ {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
