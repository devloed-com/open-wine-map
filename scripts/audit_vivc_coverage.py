"""Summarise VIVC resolution coverage produced by scripts/02g_fetch_vivc.py.

Reads `raw/vivc/by-slug/*.json` + the FR/ES/PT extracted corpora (for
per-slug usage counts) and reports:

- Bucket counts (override / exact-cultivar / exact-prime / ambiguous-* / miss).
- Cross-country synonym wins — slugs whose VIVC prime name differs from
  the corpus name (Mourvèdre → MONASTRELL, Tinta Roriz → TEMPRANILLO TINTO).
- **Not found / uncertain queue** — slugs the curator should pin manually,
  weighted by appellation-usage count so high-impact items surface first.

`--curator-todo PATH` mode appends the queue to `CURATOR_TODO.md` as
a dated section. No network. No writes (other than the optional
`--curator-todo`).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BY_SLUG = ROOT / "raw" / "vivc" / "by-slug"

sys.path.insert(0, str(ROOT / "scripts"))
from _lib.grape_corpus import collect_grape_slugs  # noqa: E402


def _norm(s: str) -> str:
    return s.casefold().replace(" ", "").replace("-", "")


def _load_records() -> list[dict]:
    if not BY_SLUG.exists():
        print(
            f"error: {BY_SLUG.relative_to(ROOT)} missing — run scripts/02g_fetch_vivc.py first",
            file=sys.stderr,
        )
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(BY_SLUG.glob("*.json"))]


def _usage_index() -> dict[str, dict]:
    """`{slug: {total_uses, by_lang, sample_appellations}}` from the corpus."""
    corpus = collect_grape_slugs()
    return {
        slug: {
            "total": sum(entry["by_lang"].values()),
            "by_lang": entry["by_lang"],
        }
        for slug, entry in corpus.items()
    }


def _bucket_summary(records: list[dict]) -> None:
    buckets = Counter(r.get("resolved_via", "?") for r in records)
    print("## Buckets")
    for b, n in buckets.most_common():
        print(f"  {b:25s} {n:>5d}")
    resolved = sum(
        buckets[b] for b in buckets if b in {"override", "exact-cultivar", "exact-prime"}
    )
    pct = 100 * resolved / max(1, len(records))
    print(f"\n  resolved: {resolved}/{len(records)} ({pct:.1f}%)\n")


def _print_wins(records: list[dict], usage: dict[str, dict]) -> None:
    wins = [
        r for r in records
        if r.get("vivc_id") and r.get("prime_name")
        and _norm(r["query"]) != _norm(r["prime_name"].split()[0] if r["prime_name"] else "")
        and _norm(r["query"]) not in _norm(r["prime_name"])
    ]
    wins.sort(key=lambda r: -(usage.get(r["slug"], {}).get("total", 0)))
    print(f"## Cross-country synonym wins (slug → VIVC prime, when names differ) — {len(wins)} slugs")
    for r in wins[:40]:
        synonyms = len(r.get("synonyms") or [])
        u = usage.get(r["slug"], {}).get("total", 0)
        print(
            f"  {r['slug']:30s} → {r['prime_name']:30s} "
            f"({r['color']:5s} {r['country']:10s} uses={u:>4d} syn={synonyms})"
        )
    if len(wins) > 40:
        print(f"  ... ({len(wins) - 40} more)")
    print()


def _print_uncertain(records: list[dict], usage: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    """Print + return (`ambiguous`, `misses`), both sorted by usage descending."""
    ambig = [r for r in records if r.get("resolved_via", "").startswith("ambiguous")]
    ambig.sort(key=lambda r: -(usage.get(r["slug"], {}).get("total", 0)))
    if ambig:
        print(f"## Ambiguity queue — {len(ambig)} slug(s) need curator pin")
        for r in ambig:
            u = usage.get(r["slug"], {})
            uses = u.get("total", 0)
            by_lang = u.get("by_lang", {})
            print(f"  {r['slug']:30s} query={r['query']!r:20s} uses={uses} ({by_lang})")
            for c in (r.get("candidates") or [])[:6]:
                print(
                    f"    - id={c['vivc_id']} cultivar={c['cultivar_name']!r} "
                    f"→ prime={c['prime_name']!r} ({c['color']}, {c['country']})"
                )
        print()

    misses = [r for r in records if r.get("resolved_via") == "miss"]
    misses.sort(key=lambda r: -(usage.get(r["slug"], {}).get("total", 0)))
    if misses:
        print(f"## Misses — {len(misses)} slug(s) not found in VIVC at all")
        for r in misses:
            u = usage.get(r["slug"], {})
            uses = u.get("total", 0)
            by_lang = u.get("by_lang", {})
            print(f"  {r['slug']:30s} query={r['query']!r:20s} uses={uses} ({by_lang})")
        print()
    return ambig, misses


def _write_curator_section(
    todo_path: Path, ambig: list[dict], misses: list[dict], usage: dict[str, dict]
) -> None:
    today = date.today().isoformat()
    lines: list[str] = []
    lines.append(f"\n## VIVC grape resolution — open queue ({today})\n")
    lines.append(
        "Curator action: for each row below, open the VIVC search URL, pick "
        "the variety number that best matches the slug's actual identity, "
        "and add `{\"vivc_id\": <id>}` to "
        "[raw/vivc/slug_overrides.json](raw/vivc/slug_overrides.json). "
        "Then `./.venv/bin/python scripts/02g_fetch_vivc.py` re-runs the "
        "passport fetch for the pinned slugs. Sorted by "
        "appellation-usage count (high impact first).\n"
    )
    if ambig:
        lines.append(f"\n### Ambiguous — {len(ambig)} slugs (multiple VIVC candidates)\n")
        lines.append("| slug | uses | query | top candidates (VIVC #id → prime) |")
        lines.append("|---|---:|---|---|")
        for r in ambig:
            uses = usage.get(r["slug"], {}).get("total", 0)
            cands = r.get("candidates") or []
            preview = "; ".join(
                f"[{c['vivc_id']}](https://www.vivc.de/index.php?r=passport%2Fview&id={c['vivc_id']}) → {c['prime_name']} ({c['country']})"
                for c in cands[:4]
            )
            lines.append(f"| `{r['slug']}` | {uses} | `{r['query']}` | {preview} |")
    if misses:
        lines.append(f"\n### Not found in VIVC — {len(misses)} slugs\n")
        lines.append("Likely a typo in the source cahier, a very obscure local cultivar, or a non-grape token leaking from `02_extract_cahiers.py`. If genuine, look for the grape on [VIVC](https://www.vivc.de/) under any alternative spelling and pin its variety number.\n")
        lines.append("| slug | uses | query |")
        lines.append("|---|---:|---|")
        for r in misses:
            uses = usage.get(r["slug"], {}).get("total", 0)
            lines.append(f"| `{r['slug']}` | {uses} | `{r['query']}` |")
    existing = todo_path.read_text(encoding="utf-8") if todo_path.exists() else ""
    todo_path.write_text(existing.rstrip() + "\n" + "\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"[audit-vivc] appended VIVC queue to {todo_path.relative_to(ROOT)} "
        f"({len(ambig)} ambiguous + {len(misses)} misses)",
        file=sys.stderr,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--curator-todo",
        type=Path,
        nargs="?",
        const=ROOT / "CURATOR_TODO.md",
        default=None,
        help="append the not-found/ambiguous queue to a CURATOR_TODO.md section "
        "(default path: CURATOR_TODO.md at repo root)",
    )
    args = ap.parse_args()

    records = _load_records()
    if not records:
        return 1
    usage = _usage_index()
    print(f"# VIVC coverage audit — {len(records)} resolved slugs over a {len(usage)}-slug corpus\n")

    _bucket_summary(records)
    _print_wins(records, usage)
    ambig, misses = _print_uncertain(records, usage)

    if args.curator_todo:
        _write_curator_section(args.curator_todo, ambig, misses, usage)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
