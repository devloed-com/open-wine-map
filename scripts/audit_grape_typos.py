"""One-shot audit: cluster grape-name spellings observed in the cahier
corpus against the canonical lexicon (`raw/wikipedia/grapes/fr/`).

Anchors on every colour code (B|N|G|Rs|Rg) in the section bodies, walks
back to recover the candidate grape name, slugifies it, and groups it
under the closest lexicon slug (Levenshtein ≤ 2, capped by length).
Variants that differ from the canonical slug are reported as typo
candidates with frequency and example AOCs.

Run: uv run python scripts/audit_grape_typos.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from difflib import get_close_matches
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.grape_lexicon import (  # noqa: E402
    DEFAULT_COLOUR,
    GRAPE_ALIAS,
    GRAPE_BLOCKLIST,
    _HARD_STOP,
    _SOFT_STOP,
    _WORD_RE,
    slugify,
)

_COLOUR_QUALIFIERS = {"blanc", "noir", "gris", "rose", "rouge"}


def _strip_default_colour(slug: str) -> str:
    """Fold "X-<default-colour>" → "X" so the audit sees the same slug
    stage 02 emits (the cahier-verbose form "Grenache Noir N" is just a
    notational variant of the bare canonical, not a typo)."""
    for suf in ("-blanc", "-noir", "-gris", "-rose", "-rouge"):
        if slug.endswith(suf):
            stem = slug[: -len(suf)]
            if DEFAULT_COLOUR.get(stem) == suf[1:]:
                return stem
    return slug

LEXICON_DIR = ROOT / "raw" / "wikipedia" / "grapes" / "fr"
EXTRACTED = ROOT / "raw" / "inao" / "cahier-extracted"

_COLOUR_RE = re.compile(r"\b(B|N|G|Rs|Rg)\b")


def collect_text(obj) -> str:
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return " \n ".join(collect_text(v) for v in obj.values())
    if isinstance(obj, list):
        return " \n ".join(collect_text(v) for v in obj)
    return ""


def candidate_names(text: str):
    """Yield the raw multi-word name preceding each colour code."""
    text = re.sub(r"\s+", " ", text)
    cursor = 0
    for m in _COLOUR_RE.finditer(text):
        head = text[cursor : m.start()]
        head = re.split(r"[,;:()]|\s+et\s+|\s+ou\s+", head)[-1]
        words = _WORD_RE.findall(head)
        cursor = m.end()
        picked: list[str] = []
        for w in reversed(words):
            wl = w.lower()
            if wl in _HARD_STOP:
                break
            picked.append(wl)
            if len(picked) >= 5:
                break
        picked.reverse()
        while picked and picked[0] in _SOFT_STOP:
            picked.pop(0)
        if not picked:
            continue
        name = " ".join(picked).strip(" -'’")
        if len(name) >= 3:
            yield name


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            curr[j] = min(
                curr[j - 1] + 1,
                prev[j] + 1,
                prev[j - 1] + (ca != cb),
            )
        prev = curr
    return prev[-1]


def edit_threshold(canonical: str) -> int:
    n = len(canonical)
    if n <= 6:
        return 1
    if n <= 12:
        return 2
    return 3


def main() -> None:
    canonical = sorted(p.stem for p in LEXICON_DIR.glob("*.json"))
    canonical_set = set(canonical)

    # token slug -> {name: count, aocs: set}. Note: we deliberately do NOT
    # fold via GRAPE_ALIAS here — that would hide the very typos already
    # listed there (e.g. gewurtztraminer → gewurztraminer).
    observed: dict[str, dict] = defaultdict(lambda: {"count": 0, "aocs": set(), "raw": set()})
    for path in sorted(EXTRACTED.glob("*.json")):
        if path.name == "_index.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        text = collect_text(data)
        seen_in_doc: set[str] = set()
        for raw in candidate_names(text):
            slug = _strip_default_colour(slugify(raw))
            if not slug or slug in GRAPE_BLOCKLIST:
                continue
            entry = observed[slug]
            entry["count"] += 1
            entry["raw"].add(raw)
            if slug not in seen_in_doc:
                entry["aocs"].add(path.stem)
                seen_in_doc.add(slug)

    # Cluster: for each canonical slug, gather observed slugs that are
    # close-matches (edit distance ≤ threshold) and NOT identical.
    # Drop noisy variants that are clearly extraction-leak (a 1-2 char
    # prefix in front of the canonical name, e.g. "e-semillon").
    clusters: dict[str, list[dict]] = {}
    matched_observed: set[str] = set()
    for canon in canonical:
        thr = edit_threshold(canon)
        variants = []
        for obs_slug, entry in observed.items():
            if obs_slug == canon:
                continue
            if obs_slug in canonical_set:
                continue  # belongs to a different canonical entry
            d = levenshtein(canon, obs_slug)
            if d == 0 or d > thr:
                continue
            if len(obs_slug) <= 6 and obs_slug[0] != canon[0]:
                continue
            # Pure prefix-leak: the observed slug equals "<junk>-<canon>"
            # or "<canon>-<junk>" with junk length ≤ 3. Treat as parser
            # noise, not a typo.
            if obs_slug.endswith("-" + canon) or obs_slug.startswith(canon + "-"):
                tail = obs_slug.replace(canon, "", 1).strip("-")
                if len(tail) <= 3:
                    continue
            obs_head, _, obs_tail = obs_slug.partition("-")
            can_head, _, can_tail = canon.partition("-")
            # Distinct cultivars sharing a colour-qualified naming pattern:
            # if the variant's leading stem is itself a canonical lexicon
            # entry and differs from canon's leading stem, they're different
            # grapes, not typos (savagnin-blanc vs sauvignon-blanc).
            if obs_head != can_head and obs_head in canonical_set:
                continue
            # Sibling colour mutations of the same stem (grolleau-noir vs
            # grolleau-gris): same stem, both trailing tokens are colour
            # qualifiers — not a typo, the colour is the distinguisher.
            if (
                obs_head == can_head
                and obs_tail in _COLOUR_QUALIFIERS
                and can_tail in _COLOUR_QUALIFIERS
            ):
                continue
            variants.append({
                "slug": obs_slug,
                "distance": d,
                "count": entry["count"],
                "raw_forms": sorted(entry["raw"]),
                "aocs": sorted(entry["aocs"])[:5],
                "aoc_count": len(entry["aocs"]),
                "in_alias": obs_slug in GRAPE_ALIAS,
            })
            matched_observed.add(obs_slug)
        if variants:
            variants.sort(key=lambda v: (-v["count"], v["slug"]))
            clusters[canon] = variants

    # Unresolved observed slugs that didn't match any canonical: surface
    # the ones with high frequency that have no close lexicon entry, in
    # case they're a missing canonical or a typo too far from its mate.
    unresolved = []
    for obs_slug, entry in observed.items():
        if obs_slug in canonical_set or obs_slug in matched_observed:
            continue
        # Try a looser difflib match for reporting only.
        nearest = get_close_matches(obs_slug, canonical, n=1, cutoff=0.7)
        unresolved.append({
            "slug": obs_slug,
            "count": entry["count"],
            "raw_forms": sorted(entry["raw"])[:3],
            "aocs": sorted(entry["aocs"])[:3],
            "nearest_canonical": nearest[0] if nearest else None,
        })
    unresolved.sort(key=lambda v: -v["count"])

    # ---- print report ----
    print("=" * 78)
    print(f"Canonical lexicon slugs : {len(canonical)}")
    print(f"Distinct observed slugs : {len(observed)}")
    print(f"Clusters with variants  : {len(clusters)}")
    print(f"Unresolved observed     : {len(unresolved)}")
    print("=" * 78)
    print()
    print("## Spelling clusters (canonical ← variant spellings)\n")
    for canon in sorted(clusters):
        variants = clusters[canon]
        print(f"### {canon}")
        for v in variants:
            sample_aocs = ", ".join(v["aocs"])
            if v["aoc_count"] > 5:
                sample_aocs += f", … ({v['aoc_count']} AOCs)"
            raw_preview = " | ".join(v["raw_forms"][:3])
            tag = " [already in GRAPE_ALIAS]" if v["in_alias"] else ""
            print(
                f"  - {v['slug']:35s} d={v['distance']}  "
                f"n={v['count']:4d}  raw={raw_preview!r}  aocs=[{sample_aocs}]{tag}"
            )
        print()

    print("## Top unresolved observed slugs (no close canonical match)\n")
    for u in unresolved[:40]:
        nearest = u["nearest_canonical"] or "—"
        print(
            f"  - {u['slug']:35s} n={u['count']:4d}  "
            f"nearest={nearest:25s} raw={u['raw_forms']}"
        )

    out_path = ROOT / "raw" / "grape_typo_audit.json"
    out_path.write_text(json.dumps({
        "canonical_count": len(canonical),
        "observed_count": len(observed),
        "clusters": clusters,
        "unresolved": unresolved,
    }, indent=2, ensure_ascii=False, default=list), encoding="utf-8")
    print(f"\nFull report written to: {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
