"""Generate one wiki/<slug>.md per CH wine record + extend wiki/_index.json
with CH entries.

Pipeline stage 03 (ch). Mirrors `scripts/de/03_generate_wiki.py` but with
trilingual section headings per record's source_lang (fr / de / it):
Switzerland is the first country where source-language is per-record
(per canton) rather than per-country.

For each AOC:
  - frontmatter: country=ch, region (Swiss wine region), canton, tier,
    is_sub_denomination, parent_slug (if applicable)
  - body: summary + grape list + cantonal-règlement source + OFAG source
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
from _lib.ch.canton import canton_name  # noqa: E402
from _lib.ch.region import derive_region  # noqa: E402

EXTRACTED = ROOT / "raw" / "ch" / "dokumente-extracted"
WIKI = ROOT / "wiki"
WIKI_INDEX = WIKI / "_index.json"

SECTION_LABELS: dict[str, dict[str, str]] = {
    "fr": {
        "summary": "Résumé",
        "grapes": "Cépages",
        "sources": "Sources",
    },
    "de": {
        "summary": "Zusammenfassung",
        "grapes": "Keltertraubensorten",
        "sources": "Quellen",
    },
    "it": {
        "summary": "Sintesi",
        "grapes": "Vitigni",
        "sources": "Fonti",
    },
}


def _labels(record: dict) -> dict[str, str]:
    lang = record.get("source_lang") or "fr"
    return SECTION_LABELS.get(lang, SECTION_LABELS["fr"])


def _truncate(text: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(". ", 1)[0]
    return cut + ("." if not cut.endswith(".") else "")


def _resolve_source(record: dict, kind: str) -> dict:
    return next((s for s in (record.get("sources") or [])
                 if s.get("kind") == kind), {})


def render_record(record: dict) -> str:
    name = record["name"]
    slug = record["slug"]
    region = derive_region(record)
    canton = record.get("canton") or ""
    canton_label = canton_name(canton) if canton else ""
    tier = record.get("tier", "cantonale")
    is_sub = bool(record.get("is_sub_denomination"))
    labels = _labels(record)

    summary = (record.get("section_roles", {}).get("summary") or "").strip()
    grape_details = (record.get("grapes") or {}).get("details") or []

    ofag = _resolve_source(record, "ofag-repertoire")
    reglement = _resolve_source(record, "cantonal-reglement")

    fm = [
        "---",
        f"title: {name}",
        "country: ch",
        f"slug: {slug}",
        f"region: {region}",
        f"canton: {canton}",
        f"canton_name: {canton_label}",
        f"tier: {tier}",
        f"kind: {record.get('kind', 'AOC')}",
        f"source_lang: {record.get('source_lang') or ''}",
    ]
    if record.get("cantons") and len(record["cantons"]) > 1:
        fm += [f"cantons: {','.join(record['cantons'])}"]
    if is_sub:
        fm += [
            "is_sub_denomination: true",
            f"parent_slug: {record.get('parent_slug') or ''}",
            f"parent_name: {record.get('parent_name') or ''}",
            f"parent_canton: {record.get('parent_canton') or ''}",
        ]
    if record.get("stub_reason"):
        fm += [f"stub_reason: {record['stub_reason']}"]
    fm += [
        "sources:",
        f"  ofag_repertoire: {ofag.get('url', '')}",
        f"  cantonal_reglement: {reglement.get('url', '')}",
        f"  cantonal_reglement_shelf: {reglement.get('shelf', '')}",
        "---",
        "",
        f"# {name}",
        "",
    ]

    body: list[str] = []
    if summary:
        body += [
            f"## {labels['summary']}",
            "",
            _truncate(summary, max_chars=1200),
            "",
        ]
    if grape_details:
        body += [
            f"## {labels['grapes']}",
            "",
            ", ".join(d.get("name") or d.get("slug") for d in grape_details),
            "",
        ]
    body += [
        f"## {labels['sources']}",
        "",
        f"- OFAG/BLW Répertoire suisse des AOC: <{ofag.get('url', '')}>",
    ]
    if reglement.get("url"):
        body += [
            f"- {reglement.get('label', 'Cantonal règlement')}: "
            f"<{reglement.get('url', '')}> "
            f"({reglement.get('shelf', '')})",
        ]
    body += ["", ]
    return "\n".join(fm + body)


def index_entry(record: dict) -> dict:
    is_sub = bool(record.get("is_sub_denomination"))
    return {
        "country": "ch",
        "name": record["name"],
        "kind": record.get("kind", "AOC"),
        "tier": record.get("tier", "cantonale"),
        "region": derive_region(record),
        "canton": record.get("canton") or "",
        "source_lang": record.get("source_lang") or "",
        "is_sub_denomination": is_sub,
        "parent_slug": record.get("parent_slug") or "" if is_sub else "",
        "parent_name": record.get("parent_name") or "" if is_sub else "",
        "categories": [record.get("kind", "AOC")],
        "page": f"{record['slug']}.md",
    }


def main() -> int:
    if not EXTRACTED.exists():
        print(f"error: {EXTRACTED} missing — run scripts/ch/02_extract_reglements.py first",
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
    ch_index: dict[str, dict] = {}
    for f in tqdm(files, desc="ch-wiki", leave=False):
        rec = json.loads(f.read_text(encoding="utf-8"))
        out_path = WIKI / f"{rec['slug']}.md"
        out_path.write_text(render_record(rec), encoding="utf-8")
        ch_index[rec["slug"]] = index_entry(rec)
        written += 1

    existing: dict[str, dict] = {}
    if WIKI_INDEX.exists():
        try:
            existing = json.loads(WIKI_INDEX.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            existing = {}
    other_kept = {k: v for k, v in existing.items() if v.get("country") != "ch"}
    merged = {**other_kept, **ch_index}
    WIKI_INDEX.write_text(json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(
        f"[ch/03] wrote {written} CH wiki pages, merged index "
        f"({len(other_kept)} non-CH + {len(ch_index)} CH = {len(merged)} entries) "
        f"@ {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
