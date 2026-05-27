"""Audit cadastre-lieu-dit matches for cluster DGCs.

For every DGC that lacks a parcellaire row, no village-INSEE override,
and falls into a parent appellation whose climat geometry is published
on cadastre.data.gouv.fr (the CADASTRE_PARENTS list in stage 00),
report the best-scoring lieu-dit match per DGC. Scores are bucketed:

  accept (≥ 0.85) — geometry is published in stage 04 as
                    geom_source=cadastre-lieu-dit-dgc.
  review (0.6 - 0.85) — surfaced for curator inspection; would be
                        rejected by the default threshold; consider
                        pinning via cadastre_lieu_dit_overrides.json.
  reject (< 0.6) — no usable cadastre match; falls through to
                   aires-csv-dgc / sibling / parent.

Run: .venv/bin/python scripts/audit_climats.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.aires import load_aires, lookup as lookup_aire  # noqa: E402
from _lib.dgc_village_overrides import DGC_VILLAGE_INSEE  # noqa: E402
from _lib.lieu_dit import LieuDitIndex, _score, derive_climat_name  # noqa: E402
from _lib.parcellaire import build_aoc_polygons  # noqa: E402

EXTRACTED = ROOT / "raw" / "inao" / "cahier-extracted"

ACCEPT = 0.85
REVIEW = 0.6


def best_unfiltered(idx: LieuDitIndex, climat: str, insees) -> tuple[float, str, str]:
    """Highest-scoring (score, lieu_dit_name, insee) — no threshold gate.

    Used so the audit can show a rejected near-miss instead of just
    blanking the row when it's below the resolver's accept bar.
    """
    best = (0.0, "", "")
    for insee in insees or set():
        for nom, _geom in idx._by_commune.get(insee, []):  # noqa: SLF001
            s = _score(climat, nom)
            if s > best[0]:
                best = (s, nom, insee)
    return best


def main() -> int:
    aires = load_aires()
    parcels_by_app, parcels_by_denom = build_aoc_polygons()
    idx = LieuDitIndex()

    if idx.total_lieux_dits == 0:
        print(
            "no cadastre data on disk — run scripts/00_fetch_data.py first",
            file=sys.stderr,
        )
        return 1

    # Build umbrella index (sibling DGCs whose name strictly prefixes a
    # later DGC's name). Mirrors _find_sibling_umbrella in stage 04 but
    # only needs names — we don't care about geometry here.
    siblings_by_app: dict[str, list[str]] = defaultdict(list)
    for path in sorted(EXTRACTED.glob("*.json")):
        if path.name == "_index.json":
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        if d.get("is_sub_denomination"):
            siblings_by_app[d.get("id_appellation") or ""].append(d["name"])

    rows: list[dict] = []
    for path in sorted(EXTRACTED.glob("*.json")):
        if path.name == "_index.json":
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        if not d.get("is_sub_denomination"):
            continue
        id_denom = d.get("id_denomination_geo") or ""
        if id_denom in parcels_by_denom:
            continue
        if id_denom in DGC_VILLAGE_INSEE:
            continue
        parent_name = d.get("parent_name") or ""
        parent_aires = lookup_aire(aires, parent_name) if parent_name else None
        if not parent_aires or not (parent_aires & idx.communes):
            # Parent's communes aren't in the cadastre cache → out of
            # scope (different parent cluster). Skip silently.
            continue
        siblings = siblings_by_app.get(d.get("id_appellation") or "", [])
        umbrella = ""
        for sib in siblings:
            if d["name"].startswith(sib + " ") and len(sib) > len(umbrella):
                umbrella = sib
        climat = derive_climat_name(d["name"], parent_name=parent_name, umbrella_name=umbrella)
        score, lieu_dit, insee = best_unfiltered(idx, climat, parent_aires & idx.communes)
        if score >= ACCEPT:
            bucket = "accept"
        elif score >= REVIEW:
            bucket = "review"
        else:
            bucket = "reject"
        rows.append({
            "slug": path.stem,
            "name": d["name"],
            "parent": parent_name,
            "climat": climat,
            "score": score,
            "lieu_dit": lieu_dit,
            "insee": insee,
            "bucket": bucket,
        })

    rows.sort(key=lambda r: (r["parent"], -r["score"], r["climat"]))

    by_bucket: dict[str, int] = defaultdict(int)
    by_parent: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        by_bucket[r["bucket"]] += 1
        by_parent[r["parent"]][r["bucket"]] += 1

    print(f"{'slug':45} {'climat':28} {'best lieu-dit':36} {'commune':6} {'score':>5}  bucket")
    print("-" * 130)
    for r in rows:
        print(
            f"{r['slug'][:44]:45} "
            f"{r['climat'][:27]:28} "
            f"{(r['lieu_dit'] or '—')[:35]:36} "
            f"{r['insee'] or '—':6} "
            f"{r['score']:5.2f}  "
            f"{r['bucket']}"
        )

    print()
    print(f"Totals: {sum(by_bucket.values())} cluster DGCs evaluated.")
    for b in ("accept", "review", "reject"):
        print(f"  {b:7} {by_bucket.get(b, 0)}")
    print()
    print("By parent:")
    for parent, buckets in sorted(by_parent.items()):
        accept = buckets.get("accept", 0)
        review = buckets.get("review", 0)
        reject = buckets.get("reject", 0)
        total = accept + review + reject
        print(f"  {parent:30} accept={accept}/{total}  review={review}  reject={reject}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
