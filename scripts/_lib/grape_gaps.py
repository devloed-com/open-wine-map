"""Records that render with no grape list at all.

A wine appellation card with an empty grape list is almost always an
extraction failure (a cahier layout the section parser did not read, a
national-spec sidecar that did not bind) or a stage-04 gap (a
sub-denomination that inherits nothing from a parent that does carry
grapes). Both are silent: the panel simply shows no pills. This module
classifies every record of a build so stage 04 can warn on each run and
`scripts/audit_empty_grapes.py` can list, review and gate them.

Buckets, in the order a curator should read them:

  FLAGGED   wine parent (or a sub-denomination whose parent is itself empty),
            not a stub, no grapes, not reviewed — an extraction gap.
  INHERIT   sub-denomination with no grapes whose parent has grapes — a
            stage-04 inheritance gap (CH grands crus, DE Einzellagen).
  REVIEWED  slug in `_lib/empty_grapes_overrides.json`: a curator verified
            that the regulator names no variety (a broad IGP rule, a
            cantonal règlement that defers to federal law).
  STUB      no source document at all (the coverage audits own these).
  NON-WINE  spirits and ciders — no grape list by design.

Every function takes the plain per-record dicts stage 04 builds (`aocs`),
so the same code runs on the in-memory build and on the emitted blob.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OVERRIDES = ROOT / "scripts" / "_lib" / "empty_grapes_overrides.json"

BUCKETS = ("FLAGGED", "INHERIT", "REVIEWED", "STUB", "NON-WINE")


def has_grapes(rec: dict) -> bool:
    return bool(rec.get("grapes_principal") or rec.get("grapes_accessory") or rec.get("grapes_all"))


def load_overrides(path: Path = OVERRIDES) -> dict[str, dict]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("__")}


def classify(aocs: dict[str, dict], overrides: dict[str, dict] | None = None) -> dict[str, list[dict]]:
    """Bucket every grape-less record. Each row carries slug, country, kind,
    parent (for sub-denominations) and the bucket; a FLAGGED sub-denomination
    is reported under its parent's `children` count instead of as its own
    row, so one unparsed cahier (Saint-Aubin, 32 premiers crus) is one line."""
    overrides = load_overrides() if overrides is None else overrides
    out: dict[str, list[dict]] = {b: [] for b in BUCKETS}
    child_of_empty: Counter[str] = Counter()
    for slug, rec in aocs.items():
        if has_grapes(rec):
            continue
        row = {
            "slug": slug, "country": rec.get("country", ""), "kind": rec.get("kind", ""),
            "name": rec.get("name", slug), "parent": rec.get("parent_slug") or "",
        }
        if not rec.get("is_wine", True):
            out["NON-WINE"].append(row)
        elif rec.get("is_stub"):
            out["STUB"].append(row)
        elif slug in overrides:
            row["reason"] = overrides[slug].get("reason", "")
            out["REVIEWED"].append(row)
        elif rec.get("is_sub_denomination") and row["parent"]:
            parent = aocs.get(row["parent"])
            if parent is not None and has_grapes(parent):
                out["INHERIT"].append(row)
            else:
                child_of_empty[row["parent"]] += 1
        else:
            out["FLAGGED"].append(row)
    flagged_slugs = {r["slug"] for r in out["FLAGGED"]}
    for r in out["FLAGGED"]:
        r["children"] = child_of_empty.get(r["slug"], 0)
    for parent, n in child_of_empty.items():
        if parent not in flagged_slugs and parent not in overrides:
            # parent absent from the build (or itself a stub / reviewed):
            # surface the orphans as one FLAGGED line so they are not lost
            out["FLAGGED"].append({"slug": parent, "country": "", "kind": "", "name": parent,
                                   "parent": "", "children": n, "orphan": True})
    for b in out:
        out[b].sort(key=lambda r: (r["country"], r["slug"]))
    return out


def summary_line(buckets: dict[str, list[dict]]) -> str:
    """One stderr line for stage 04."""
    fl = buckets["FLAGGED"]
    n_children = sum(r.get("children", 0) for r in fl)
    head = ", ".join(r["slug"] for r in fl[:6]) + (" …" if len(fl) > 6 else "")
    return (
        f"[grapes] wine records with no grape list: FLAGGED={len(fl)} parents"
        f" (+{n_children} sub-denominations under them) INHERIT={len(buckets['INHERIT'])}"
        f" REVIEWED={len(buckets['REVIEWED'])} STUB={len(buckets['STUB'])}"
        + (f" — {head}" if fl else "")
        + " — details: scripts/audit_empty_grapes.py"
    )
