#!/usr/bin/env python3
"""Stage 03 of the drinks pipeline: one wiki/<slug>.md per spirit drink,
aromatised wine and cider of the EU register, and their entries in
wiki/_index.json.

Reads raw/drinks/extracted/*.json. The index entries carry `pipeline:
"drinks"` beside their country, so a full run replaces the drinks entries
and leaves every country's wine entries alone (`wiki_index_kept`), and a
country's own stage 03 leaves the drinks alone. `--only SLUG` (repeatable
substring) rewrites the selected pages and merges their entries.

    .venv/bin/python scripts/drinks/03_generate_wiki.py [--only SLUG …]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.extract_index import wiki_index_kept  # noqa: E402

EXTRACTED = ROOT / "raw" / "drinks" / "extracted"
WIKI = ROOT / "wiki"
WIKI_INDEX = WIKI / "_index.json"
TERROIR_FACTS = ROOT / "raw" / "terroir-facts"

CLASS_LABEL = {"spirit": "spirit drink", "aromatised-wine": "aromatised wine", "cider": "cider or perry"}


def _facts_slugs() -> frozenset[str]:
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
    return frozenset(slugs)


def _truncate(text: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(". ", 1)[0]
    return cut + ("." if not cut.endswith(".") else "")


def render_record(record: dict, facts: frozenset[str]) -> str:
    src = record.get("source") or {}
    roles = record.get("section_roles") or {}
    name = record["name"]
    title = f"{name} ({record['name_latin']})" if record.get("name_latin") else name
    document = src.get("attachment_url") or src.get("source_url") or src.get("url") or ""
    fm = [
        "---",
        f"title: {title}",
        f"type: {(record.get('kind') or '').lower()}",
        f"slug: {record['slug']}",
        f"country: {record.get('country') or ''}",
        *([f"country_aliases: {', '.join(record['country_aliases'])}"] if record.get("country_aliases") else []),
        f"product_class: {record.get('product_class') or ''}",
        f"drink_category: {record.get('drink_category') or ''}",
        f"file_number: {record.get('file_number') or ''}",
        f"source_lang: {record.get('source_lang') or ''}",
        *(["stub: true", f"stub_reason: {record.get('stub_reason') or ''}"] if record.get("stub") else []),
        "sources:",
        f"  kind: {src.get('kind') or ''}",
        f"  document: {document}",
        f"  register_entry: {src.get('register_url') or ''}",
        "---",
        "",
        f"# {title}",
        "",
    ]
    body: list[str] = []
    category = record.get("register_category") or CLASS_LABEL.get(record.get("product_class") or "", "")
    if category:
        body += ["## Category", "", category, ""]
    summary = (record.get("summary") or "").strip()
    if summary and record["slug"] not in facts:
        body += ["## Summary", "", _truncate(summary, 1200), ""]
    geo = (record.get("geo_area_brief") or "").strip()
    if geo:
        body += ["## Geographical area", "", _truncate(geo, 2000), ""]
    nuts = [f"{r.get('code')} {r.get('name') or ''}".strip() for r in record.get("geo_nuts") or []]
    if nuts:
        body += ["NUTS: " + "; ".join(nuts), ""]
    method = (roles.get("method") or "").strip()
    if method:
        body += ["## Method", "", _truncate(method, 2000), ""]
    link = (record.get("link_to_terroir") or "").strip()
    if link:
        body += ["## Link with the geographical area", "", _truncate(link, 2000), ""]
    body += ["## Sources", ""]
    if document:
        label = {
            "eambrosia-register-technical-file": "Technical file (EU GI register)",
            "eur-lex-single-document": "Single document (Official Journal of the EU)",
            "national-specification": "National product specification",
        }.get(src.get("kind") or "", "Document")
        body.append(f"- {label}: <{document}>")
    if src.get("register_url"):
        body.append(f"- EU GI register entry: <{src['register_url']}>")
    body += [f"- File number: `{record.get('file_number') or ''}`", ""]
    return "\n".join(fm + body)


def index_entry(record: dict) -> dict:
    return {
        "country": record.get("country") or "",
        "pipeline": "drinks",
        "file_number": record.get("file_number") or "",
        "name": record["name"],
        "kind": record.get("kind") or "",
        "product_class": record.get("product_class") or "",
        "drink_category": record.get("drink_category") or "",
        "region": "",
        "is_sub_denomination": False,
        "parent_slug": "",
        "parent_name": "",
        "categories": [record.get("drink_category") or ""],
        "stub": bool(record.get("stub")),
        "page": f"{record['slug']}.md",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", default=[], help="slug substring (repeatable)")
    args = ap.parse_args()
    if not EXTRACTED.exists():
        print(f"error: {EXTRACTED} missing — run scripts/drinks/02_extract_technical_files.py first",
              file=sys.stderr)
        return 1
    files = sorted(p for p in EXTRACTED.glob("*.json") if not p.name.startswith("_"))
    if args.only:
        needles = [s.lower() for s in args.only]
        files = [p for p in files if any(n in p.stem.lower() for n in needles)]
    WIKI.mkdir(parents=True, exist_ok=True)
    facts = _facts_slugs()
    index: dict[str, dict] = {}
    for path in files:
        record = json.loads(path.read_text(encoding="utf-8"))
        (WIKI / f"{record['slug']}.md").write_text(render_record(record, facts), encoding="utf-8")
        index[record["slug"]] = index_entry(record)
    existing: dict[str, dict] = {}
    if WIKI_INDEX.exists():
        try:
            existing = json.loads(WIKI_INDEX.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            existing = {}
    kept = wiki_index_kept(existing, "", partial=bool(args.only), pipeline="drinks")
    merged = {**kept, **index}
    WIKI_INDEX.write_text(json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(
        f"[drinks/03] wrote {len(index)} pages, merged index ({len(kept)} kept + {len(index)} drinks = "
        f"{len(merged)} entries) @ {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
