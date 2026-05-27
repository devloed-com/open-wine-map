"""Pre-flight audit: inventory canonical grape slugs in the current
FR/ES/PT extraction that lack VIVC coverage AND lack a GRAPE_ALIAS
entry. These slugs are at risk under the vocab-anchored matcher —
they survive only if the cross-corpus union of slugs catches them.

Writes raw/es/no-vivc-grapes.json (sorted freq desc, alpha) and a
stderr summary. Read-only, safe to run repeatedly.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.grape_lexicon import GRAPE_ALIAS  # noqa: E402

EXTRACTED_DIRS = [
    ROOT / "raw" / "inao" / "cahier-extracted",
    ROOT / "raw" / "es" / "pliegos-extracted",
    ROOT / "raw" / "pt" / "cadernos-extracted",
]
VIVC_DIR = ROOT / "raw" / "vivc" / "by-slug"
OUT_PATH = ROOT / "raw" / "es" / "no-vivc-grapes.json"

GRAPE_CATEGORIES = ("principal", "accessory", "observation")


def collect_slugs() -> dict[str, dict[str, set[str]]]:
    """Return {slug: {corpus: {pliego_slug, ...}}} across all corpora."""
    found: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for dir_ in EXTRACTED_DIRS:
        if not dir_.exists():
            continue
        corpus = dir_.parent.name
        for path in sorted(dir_.glob("*.json")):
            if path.name.startswith("_"):
                continue
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            pliego_slug = record.get("slug") or path.stem
            grapes = record.get("grapes") or {}
            for cat in GRAPE_CATEGORIES:
                for slug in grapes.get(cat) or []:
                    if isinstance(slug, str) and slug:
                        found[slug][corpus].add(pliego_slug)
    return found


def vivc_status(slug: str) -> str:
    path = VIVC_DIR / f"{slug}.json"
    if not path.exists():
        return "absent"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "absent"
    return "resolved" if data.get("vivc_id") else "absent"


def in_grape_alias(slug: str) -> bool:
    return slug in GRAPE_ALIAS or slug in set(GRAPE_ALIAS.values())


def main() -> None:
    slugs = collect_slugs()
    print(f"[no-vivc] scanned {len(slugs)} distinct canonical slugs", file=sys.stderr)

    candidates = []
    for slug, by_corpus in slugs.items():
        all_pliegos = sorted({p for ps in by_corpus.values() for p in ps})
        frequency = len(all_pliegos)
        status = vivc_status(slug)
        alias = in_grape_alias(slug)
        if status == "resolved" or alias:
            continue
        candidates.append(
            {
                "slug": slug,
                "frequency": frequency,
                "pliegos": all_pliegos,
                "in_grape_alias": alias,
                "vivc_status": status,
                "corpora": sorted(by_corpus.keys()),
            }
        )

    candidates.sort(key=lambda c: (-c["frequency"], c["slug"]))

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_slugs_scanned": len(slugs),
        "at_risk_count": len(candidates),
        "candidates": candidates,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(
        f"[no-vivc] {len(candidates)} slugs lack VIVC + GRAPE_ALIAS coverage "
        f"(out of {len(slugs)} total)",
        file=sys.stderr,
    )
    for c in candidates[:30]:
        sample_pliegos = ", ".join(c["pliegos"][:3])
        more = f", +{len(c['pliegos']) - 3} more" if len(c["pliegos"]) > 3 else ""
        print(
            f"  freq={c['frequency']:>3}  {c['slug']:<40}  {sample_pliegos}{more}",
            file=sys.stderr,
        )
    if len(candidates) > 30:
        print(f"  ... and {len(candidates) - 30} more in {OUT_PATH}", file=sys.stderr)
    print(f"[no-vivc] full report → {OUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
