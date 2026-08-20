"""Flag VIVC synonyms claimed by several varieties and used as a surface.

VIVC lists a synonym under every variety that has ever borne the name, so
one surface can be claimed by several prime records. The vocabulary
builder in `_lib.grape_entity` resolves such a surface first-write-wins,
which means the binding is decided by iteration order rather than by what
the name means in the country whose spec is being parsed. "Hermitage" is
claimed by five records — the builder bound it to Cinsaut (the South
African reading) while every Swiss règlement using it means Marsanne.

That failure is silent: the wrong variety simply appears on the panel.
This audit makes it visible. It intersects the ambiguous surfaces with
the surfaces the corpora actually use, and buckets each finding:

  PINNED      a GRAPE_ALIAS entry decides the binding — curator-reviewed.
  UNREVIEWED  no pin; the binding is iteration order. The risk bucket.

A finding is not automatically a bug: many ambiguous names resolve to the
right variety by luck or because only one claimant is in the corpus. The
bucket says who decided, not who is right.

Usage:
    .venv/bin/python scripts/audit_ambiguous_synonyms.py
    .venv/bin/python scripts/audit_ambiguous_synonyms.py --strict
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _lib.grape_entity import (  # noqa: E402
    _normalise,
    _slug_to_search_surface,
    _vivc_canonical_by_id,
)
from _lib.grape_lexicon import GRAPE_ALIAS  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
VIVC_DIR = ROOT / "raw" / "vivc" / "by-slug"


def extracted_dirs() -> list[pathlib.Path]:
    """Every per-record corpus directory that carries `grapes.details`."""
    out = []
    for d in sorted((ROOT / "raw").glob("*/*extracted*")):
        if d.is_dir():
            out.append(d)
    return out


def claimants_by_surface() -> dict[str, set[str]]:
    """Normalised VIVC surface → the canonical slugs claiming it."""
    canonical_by_id = _vivc_canonical_by_id()
    claims: dict[str, set[str]] = collections.defaultdict(set)
    for path in sorted(VIVC_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        vid = data.get("vivc_id")
        canonical = canonical_by_id.get(vid) if isinstance(vid, int) else None
        if canonical is None:
            canonical = GRAPE_ALIAS.get(path.stem, path.stem)
        names = [data.get("prime_name")]
        names += [s.get("name") for s in (data.get("synonyms") or [])
                  if isinstance(s, dict)]
        for name in names:
            if isinstance(name, str) and name:
                key = _normalise(name)
                if len(key) >= 3:
                    claims[key].add(canonical)
    return claims


def corpus_surfaces() -> dict[str, dict]:
    """Normalised surface → {slug, display, countries, records}."""
    used: dict[str, dict] = {}
    for d in extracted_dirs():
        for path in d.glob("*.json"):
            if path.name.startswith("_"):
                continue
            try:
                rec = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(rec, dict):
                continue
            grapes = rec.get("grapes")
            if not isinstance(grapes, dict):
                continue
            country = rec.get("country") or d.parts[-2]
            for det in grapes.get("details") or []:
                if not isinstance(det, dict):
                    continue
                name, slug = det.get("name"), det.get("slug")
                if not isinstance(name, str) or not isinstance(slug, str):
                    continue
                key = _normalise(name)
                if len(key) < 3:
                    continue
                e = used.setdefault(key, {"slug": slug, "display": name,
                                          "countries": set(), "records": 0})
                e["countries"].add(country)
                e["records"] += 1
    return used


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero when an UNREVIEWED finding remains")
    args = ap.parse_args()

    claims = claimants_by_surface()
    used = corpus_surfaces()
    alias_keys = {_normalise(k) for k in GRAPE_ALIAS}

    findings = []
    for key, entry in used.items():
        owners = claims.get(key) or set()
        if len(owners) < 2:
            continue
        # A surface that IS the bound variety's own name carries no risk:
        # "Chardonnay" is claimed by Pinot blanc too, but nobody writing
        # Chardonnay means Pinot blanc. The dangerous case is a surface
        # that is only a SYNONYM of what it bound to — that is where
        # iteration order silently picks the wrong country's reading.
        is_own_name = key == _normalise(_slug_to_search_surface(entry["slug"]))
        findings.append({
            "surface": entry["display"], "key": key, "bound": entry["slug"],
            "claimants": sorted(owners), "countries": sorted(entry["countries"]),
            "records": entry["records"], "pinned": key in alias_keys,
            "own_name": is_own_name,
        })

    pinned = [f for f in findings if f["pinned"]]
    rest = [f for f in findings if not f["pinned"]]
    own = sorted([f for f in rest if f["own_name"]], key=lambda f: -f["records"])
    risky = sorted([f for f in rest if not f["own_name"]], key=lambda f: -f["records"])

    print(f"VIVC surfaces in the corpora        : {len(used)}")
    print(f"ambiguous (claimed by 2+ varieties) : {len(findings)}")
    print(f"  RISKY  bound via synonym, no pin  : {len(risky)}")
    print(f"  OWN-NAME  surface is its own name : {len(own)}")
    print(f"  PINNED  GRAPE_ALIAS decides       : {len(pinned)}")

    print(f"\n=== RISKY ({len(risky)}) — review these ===")
    for f in risky:
        others = [c for c in f["claimants"] if c != f["bound"]]
        print(f"  {f['surface']!r} → {f['bound']}"
              f"   ({f['records']} rec, {'/'.join(f['countries'])})")
        print(f"      also claimed by: {', '.join(others) or '—'}")

    if args.strict and risky:
        print(f"\nFAIL: {len(risky)} risky ambiguous surface(s)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
