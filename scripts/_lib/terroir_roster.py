"""The sub-denomination roster as stage 04 renders it: parent slug → the
names of the sub-denominations whose pages inherit the parent's terroir
facts (FR DGCs, ES subzonas, IT sottozone, PT sub-regiões, DE
Einzellagen, CH régionale / locale tiers, LU communes, …).

`wiki/_index.json` (stage 03) carries `parent_slug` for every on-disk
sub-denomination; the sottozone stage 04 synthesises from the MASAF
sidecars exist only in the startup blob, where the parent is the longest
parent slug prefixing the sottozona slug (chianti-rufina → chianti).
Used by the dedupe post-pass (never collapse two bullets leading with
different sub-denomination names) and by the extraction / translation
prompts (name the appellation where the source says "the appellation",
because the bullet is also shown on the sub-denominations' pages).
"""

from __future__ import annotations

import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def _load() -> tuple[dict[str, list[str]], dict[str, str], dict[str, int]]:
    children: dict[str, list[str]] = defaultdict(list)
    names: dict[str, str] = {}
    index_path = ROOT / "wiki" / "_index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    for slug, rec in index.items():
        if rec.get("name"):
            names[slug] = rec["name"]
        if rec.get("parent_slug") and rec.get("name"):
            children[rec["parent_slug"]].append(rec["name"])
    n_index = sum(len(v) for v in children.values())
    blobs = sorted((ROOT / "wiki" / "data").glob("aocs.en.*.js"))
    n_blob = 0
    if blobs:
        text = blobs[-1].read_text(encoding="utf-8")
        aocs = json.loads(text[text.index("=") + 1:].strip().rstrip(";")).get("aocs") or {}
        parents = sorted((s for s, r in aocs.items() if not r.get("is_sub_denomination")), key=len, reverse=True)
        for slug, rec in aocs.items():
            if rec.get("name") and slug not in names:
                names[slug] = rec["name"]
            if not rec.get("is_sub_denomination") or not rec.get("name"):
                continue
            if slug in index and index[slug].get("parent_slug"):
                continue
            parent = next((p for p in parents if slug.startswith(p + "-")), None)
            if parent:
                children[parent].append(rec["name"])
                n_blob += 1
    return dict(children), names, {"index": n_index, "blob": n_blob}


def children_names(slug: str) -> list[str]:
    """Names of the sub-denominations of `slug` (empty for a leaf)."""
    return list(_load()[0].get(slug) or [])


def load_children_names() -> dict[str, list[str]]:
    return dict(_load()[0])


def record_name(slug: str) -> str:
    return _load()[1].get(slug, "")


def roster_stats() -> dict[str, int]:
    return dict(_load()[2])
