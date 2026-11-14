#!/usr/bin/env python3
"""Per-record regression diff between two builds of the site — the step
every validator's fix-then-verify loop needs (docs/plan-validators.md § 4).

`snapshot` reduces a build to one small JSON: for every record of the EN
startup bundle, the fields a reader notices when they change — name,
classification, region, styles, the grape roster by role, the geometry
source, the drawn area, the commune count, the terroir bullets (count and
sha), the summary sha and the cited source URLs. `diff` compares two
snapshots record by record and lists what changed, where, by how much; its
`--slugs-out` is a `--slugs-file` for `audit_cards_llm.py`, so a re-run can
grade exactly the cards a change touched.

    .venv/bin/python scripts/diff_records.py snapshot --out tmp/validation/records-before.json
    … rebuild …
    .venv/bin/python scripts/diff_records.py snapshot --out tmp/validation/records-after.json
    .venv/bin/python scripts/diff_records.py diff tmp/validation/records-before.json tmp/validation/records-after.json --slugs-out tmp/validation/changed.json

`snapshot --site DIR` reads another checkout's `wiki/` (a deployed
snapshot). Read-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FIELDS = ("name", "class_label", "region", "styles", "grapes_principal", "grapes_accessory",
          "geom_source", "area", "communes", "facts_n", "facts_sha", "summary_sha", "source_urls",
          "is_stub", "parent_slug", "children_n", "product_class", "drink_category", "country_aliases")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def load_startup(site: Path, locale: str = "en") -> dict:
    paths = sorted((site / "data").glob(f"aocs.{locale}.*.js"))
    if not paths:
        sys.exit(f"no startup bundle under {site}/data — build the site first")
    m = re.search(r"__OWM_DATA\s*=\s*(\{.*\})\s*;?\s*$", paths[-1].read_text(encoding="utf-8"), re.S)
    return json.loads(m.group(1)).get("aocs") or {}


def snapshot(site: Path, locale: str = "en") -> dict:
    aocs = load_startup(site, locale)
    out: dict[str, dict] = {}
    for slug, rec in aocs.items():
        p = site / "data" / "d" / locale / f"{slug}.json"
        payload = {}
        if p.exists():
            try:
                payload = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                payload = {}
        tf = payload.get("terroir_facts") or {}
        facts = (tf.get("facts") or []) if isinstance(tf, dict) else (tf or [])
        bullets = [f.get("bullet") or "" for f in facts if isinstance(f, dict)]
        srcs = payload.get("sources") or {}
        urls = sorted({v for v in srcs.values() if isinstance(v, str) and v.startswith("http")}
                      | {v.get("url") for v in srcs.values() if isinstance(v, dict) and v.get("url")})
        out[slug] = {
            "name": rec.get("name"), "class_label": rec.get("class_label"), "region": rec.get("region"),
            "country": rec.get("country"), "styles": sorted(rec.get("styles") or []),
            "grapes_principal": sorted(rec.get("grapes_principal") or []),
            "grapes_accessory": sorted(rec.get("grapes_accessory") or []),
            "geom_source": rec.get("geom_source"), "area": round(float(payload.get("area") or 0), 6),
            "communes": payload.get("communes_matched"), "facts_n": len(bullets),
            "facts_sha": _sha("\n".join(bullets)) if bullets else "",
            "summary_sha": _sha(payload.get("summary") or "") if payload.get("summary") else "",
            "source_urls": urls, "is_stub": bool(payload.get("is_stub")),
            "parent_slug": rec.get("parent_slug") or "", "children_n": len(payload.get("children") or []),
            # the class model (sparse on the records: a wine carries neither)
            "product_class": rec.get("product_class") or "", "drink_category": rec.get("drink_category") or "",
            "country_aliases": sorted(rec.get("country_aliases") or []),
        }
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "site": str(site), "locale": locale, "records": out}


def diff(a: dict, b: dict, *, area_tolerance: float = 0.02) -> dict:
    ra, rb = a["records"], b["records"]
    added = sorted(set(rb) - set(ra))
    removed = sorted(set(ra) - set(rb))
    changed: dict[str, dict] = {}
    by_field: Counter = Counter()
    for slug in sorted(set(ra) & set(rb)):
        x, y = ra[slug], rb[slug]
        delta: dict[str, dict] = {}
        for f in FIELDS:
            if f == "area":
                ax, ay = x.get("area") or 0, y.get("area") or 0
                base = max(ax, ay, 1e-9)
                if abs(ax - ay) / base > area_tolerance:
                    delta[f] = {"before": ax, "after": ay, "ratio": round(ay / ax, 3) if ax else None}
                continue
            # a snapshot older than a field carries no key for it: an absent
            # value and an empty one are the same statement
            if (x.get(f) or None) != (y.get(f) or None):
                if isinstance(x.get(f), list) and isinstance(y.get(f), list):
                    delta[f] = {"added": sorted(set(y[f]) - set(x[f])), "removed": sorted(set(x[f]) - set(y[f]))}
                else:
                    delta[f] = {"before": x.get(f), "after": y.get(f)}
        if delta:
            changed[slug] = {"country": y.get("country"), "name": y.get("name"), "fields": delta}
            for f in delta:
                by_field[f] += 1
    return {"records_before": len(ra), "records_after": len(rb), "added": added, "removed": removed,
            "changed": changed, "n_changed": len(changed), "by_field": dict(by_field.most_common())}


def markdown(d: dict) -> str:
    out = [f"# Record diff — {d['records_before']} → {d['records_after']} records; {d['n_changed']} changed, "
           f"{len(d['added'])} added, {len(d['removed'])} removed", ""]
    if d["by_field"]:
        out += ["| field | records |", "|---|---:|"] + [f"| {k} | {v} |" for k, v in d["by_field"].items()] + [""]
    if d["added"]:
        out += ["## Added", ""] + [f"- `{s}`" for s in d["added"]] + [""]
    if d["removed"]:
        out += ["## Removed", ""] + [f"- `{s}`" for s in d["removed"]] + [""]
    if d["changed"]:
        out += ["## Changed", ""]
        for slug, c in d["changed"].items():
            bits = []
            for f, v in c["fields"].items():
                if "added" in v:
                    bits.append(f"{f}: +{len(v['added'])} −{len(v['removed'])}"
                                + (f" (+{', '.join(v['added'][:4])})" if v["added"] else "")
                                + (f" (−{', '.join(v['removed'][:4])})" if v["removed"] else ""))
                elif "ratio" in v:
                    bits.append(f"{f}: ×{v['ratio']}")
                else:
                    bits.append(f"{f}: {v['before']!r} → {v['after']!r}")
            out.append(f"- `{slug}` ({c['country']}): " + "; ".join(bits))
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("--site", default=str(ROOT / "wiki"))
    s.add_argument("--locale", default="en")
    s.add_argument("--out", required=True)
    d = sub.add_parser("diff")
    d.add_argument("before")
    d.add_argument("after")
    d.add_argument("--area-tolerance", type=float, default=0.02)
    d.add_argument("--json", default=None)
    d.add_argument("--md", default=None)
    d.add_argument("--slugs-out", default=None, help="write the changed slugs as a --slugs-file for audit_cards_llm.py")
    args = ap.parse_args()
    if args.cmd == "snapshot":
        snap = snapshot(Path(args.site), args.locale)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(snap, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
        print(f"[diff-records] {len(snap['records'])} records → {args.out}", file=sys.stderr)
        return 0
    a = json.loads(Path(args.before).read_text(encoding="utf-8"))
    b = json.loads(Path(args.after).read_text(encoding="utf-8"))
    res = diff(a, b, area_tolerance=args.area_tolerance)
    if args.json:
        Path(args.json).write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    md = markdown(res)
    if args.md:
        Path(args.md).write_text(md, encoding="utf-8")
    else:
        print(md)
    if args.slugs_out:
        Path(args.slugs_out).write_text(json.dumps({"slugs": sorted(res["changed"]) + res["added"]}, indent=0) + "\n", encoding="utf-8")
        print(f"[diff-records] {len(res['changed']) + len(res['added'])} slugs → {args.slugs_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
