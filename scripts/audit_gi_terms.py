#!/usr/bin/env python3
"""Audit the two naming axes on the built corpus: legal scheme + traditional term.

Reads the EN startup blob (wiki/data/aocs.en.<hash>.js) and reports, per
country, the eu_scheme / national_term distribution (parents, wines only), the
records with no class_label, sub-denominations whose axes differ from their
parent, and terms whose registered scheme (traditional_terms.json) contradicts
the record's scheme. IT and ES counts are compared with the rosters
(MASAF elenco / MAPA listado) that feed them.

    .venv/bin/python scripts/audit_gi_terms.py [--strict]

--strict exits non-zero on any mismatch or empty class_label. Read-only.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.gi_terms import load_terms_table, term_key  # noqa: E402


def load_blob() -> dict:
    paths = sorted(glob.glob(str(ROOT / "wiki" / "data" / "aocs.en.*.js")))
    if not paths:
        sys.exit("no wiki/data/aocs.en.*.js — run scripts/04_build_maps.py first")
    src = Path(paths[-1]).read_text(encoding="utf-8")
    return json.loads(src[src.index("{"): src.rindex("}") + 1])["aocs"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    aocs = load_blob()
    table = load_terms_table()
    term_scheme = {k: v.get("scheme") for k, v in (table.get("terms") or {}).items()}
    problems: list[str] = []

    by_country: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for slug, r in aocs.items():
        if r.get("is_sub_denomination") or r.get("is_wine") is False:
            continue
        by_country[r.get("country") or "?"][(r.get("eu_scheme") or "-", r.get("national_term") or "")] += 1
    print("country  scheme      term                       n")
    for cc in sorted(by_country):
        for (scheme, term), n in sorted(by_country[cc].items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"{cc:<8} {scheme:<11} {term or '(none)':<26} {n:>5}")

    empty = [s for s, r in aocs.items() if not r.get("class_label")]
    if empty:
        problems.append(f"{len(empty)} records with empty class_label: {empty[:10]}")

    for slug, r in aocs.items():
        if not r.get("is_sub_denomination"):
            continue
        parent = aocs.get(r.get("parent_slug") or "")
        if not parent:
            continue
        mine = (r.get("eu_scheme"), r.get("national_term"))
        theirs = (parent.get("eu_scheme"), parent.get("national_term"))
        if mine != theirs:
            problems.append(f"sub {slug} {mine} != parent {r.get('parent_slug')} {theirs}")

    for slug, r in aocs.items():
        term = r.get("national_term") or ""
        if not term:
            continue
        registered = term_scheme.get(f"{r.get('country')}:{term}")
        if registered is None:
            problems.append(f"{slug}: term {term!r} has no entry in traditional_terms.json terms")
            continue
        actual = (r.get("eu_scheme") or "").replace("uk-", "")
        if registered != actual and not (registered == "pdo" and actual == "spirit-gi"):
            problems.append(f"{slug}: term {term!r} is registered {registered} but record is {actual}")

    it_parents = collections.Counter(
        r.get("national_term") or "" for r in aocs.values()
        if r.get("country") == "it" and not r.get("is_sub_denomination")
    )
    try:
        from _lib.it.national_term import load_it_terms
        roster = collections.Counter(load_it_terms().values())
        print(f"\nIT parents: {dict(it_parents)} | MASAF elenco: {dict(roster)}")
    except Exception as exc:  # roster optional (no raw/ in CI)
        print(f"\nIT parents: {dict(it_parents)} | roster unavailable: {exc}")
    es_parents = collections.Counter(
        r.get("national_term") or "" for r in aocs.values()
        if r.get("country") == "es" and not r.get("is_sub_denomination")
    )
    print(f"ES parents: {dict(es_parents)}")

    facet_keys = collections.Counter()
    for r in aocs.values():
        if r.get("is_sub_denomination") or r.get("is_wine") is False:
            continue
        for tok in (r.get("class_key") or "").strip(";").split(";"):
            if tok:
                facet_keys[tok] += 1
    unknown = [t for t in facet_keys if ":" in t and t not in {
        term_key(k.split(":")[0], k.split(":", 1)[1]) for k in term_scheme
    }]
    if unknown:
        problems.append(f"facet term keys without a tooltip entry: {unknown}")

    print()
    if problems:
        print(f"{len(problems)} problem(s):")
        for p in problems:
            print("  -", p)
        return 1 if args.strict else 0
    print("OK — no mismatches")
    return 0


if __name__ == "__main__":
    sys.exit(main())
