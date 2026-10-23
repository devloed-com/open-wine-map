"""Grape-identity review queue: names a regulator lists that the matcher did not
resolve, and names it resolved by fuzzy score.

Two lists, both read-only:

  unknown  — every `raw/<cc>/extraction-unknowns*.json` candidate that carries
             an OIV colour code ("Albarossa N.", "Timorasso B"): a variety the
             regulator lists and the lexicon lacks, grouped by name with the
             records it is missing from;
  fuzzy    — every distinct (surface, slug) pair in the extracted corpus that
             `match_variety` binds by fuzzy score, lowest score first. Most are
             spellings ("Mourverdre"), some are another cultivar ("Caloria" had
             bound Pelaverga on 39 cards, "Rubinet" the white Jacquère).

Fix a gap with a VIVC-verified entry in `scripts/_lib/grape_lexicon.py` (and a
pin in `raw/vivc/slug_overrides.json`), a wrong fuzzy binding with an exact
entry for the real cultivar, a style or place word with `_BANNED_SURFACES` in
`scripts/_lib/grape_entity.py`; then re-extract the affected countries. Built
after the Piemonte flag of 2026-10-22 (Albarossa missing).

    .venv/bin/python scripts/audit_grape_identity.py [--json PATH] [--min-score N]
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.grape_entity import match_variety  # noqa: E402

_COLOURS = frozenset({"N", "B", "G", "Gr", "Rs", "Rg", "R", "Bl"})
_UPPER_START = re.compile(r"[A-ZÀ-ÝĀ-ſ]")


def _split_colour(token: str) -> tuple[str, str] | None:
    """("Albarossa", "N") for "Albarossa N.", None when the last word is no
    OIV colour code."""
    head, _, last = token.strip().rpartition(" ")
    last = last.rstrip(".")
    if head and last in _COLOURS and _UPPER_START.match(head):
        return head.strip(" .,;:"), last
    return None


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.casefold())
    return "".join(c for c in s if not unicodedata.combining(c)).strip()


def _unknown_candidates():
    for path in sorted(ROOT.glob("raw/*/extraction-unknowns*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        cands = data.get("candidates") if isinstance(data, dict) else data
        for c in cands or []:
            yield path, c


def colour_coded_unknowns() -> list[dict]:
    groups: dict[tuple[str, str], dict] = {}
    for path, c in _unknown_candidates():
        tok = re.sub(r"^[\s*•·\-–—]+", "", (c.get("token") or "").strip())
        tok = re.sub(r"\s[–—-]\s.*$", "", tok)
        split = _split_colour(tok)
        if split is None:
            continue
        name, colour = split
        if len(name) < 3 or len(name.split()) > 5 or match_variety(tok) is not None:
            continue
        e = groups.setdefault((path.parent.name, _norm(name)), {
            "country": path.parent.name, "name": name, "colour": colour,
            "queue": path.name, "records": set()})
        e["records"].add(c.get("pliego_slug") or "?")
    out = [dict(v, records=sorted(v["records"])) for v in groups.values()]
    return sorted(out, key=lambda e: (-len(e["records"]), e["country"], e["name"]))


def _record_details(rec: object) -> list:
    """A record's grape details — `grapes.details`, or the flat `varieties`
    list of the ES national-pliego sidecars."""
    if not isinstance(rec, dict):
        return []
    grapes = rec.get("grapes")
    if isinstance(grapes, dict) and grapes.get("details"):
        return grapes["details"]
    return rec["varieties"] if isinstance(rec.get("varieties"), list) else []


def _corpus_pairs() -> dict[tuple[str, str], set[str]]:
    seen: dict[tuple[str, str], set[str]] = collections.defaultdict(set)
    for path in ROOT.glob("raw/*/*extracted/*.json"):
        if path.name.startswith("_"):
            continue
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for d in _record_details(rec):
            if isinstance(d, dict) and d.get("name") and d.get("slug"):
                seen[(d["name"], d["slug"])].add(f"{path.parts[-3]}:{rec.get('slug') or path.stem}")
    return seen


def fuzzy_bindings(min_score: int) -> list[dict]:
    out = []
    for (name, slug), recs in _corpus_pairs().items():
        m = match_variety(name)
        if m and m.slug == slug and m.method.startswith("fuzzy"):
            score = int(m.method.split(":")[1])
            if score >= min_score:
                out.append({"score": score, "name": name, "slug": slug, "records": sorted(recs)})
    return sorted(out, key=lambda e: (e["score"], e["name"]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", type=Path, help="also write both lists here")
    ap.add_argument("--min-score", type=int, default=0, help="hide fuzzy bindings below this score")
    args = ap.parse_args()
    unknown = colour_coded_unknowns()
    fuzzy = fuzzy_bindings(args.min_score)
    print(f"## Colour-coded names no entry resolves — {len(unknown)}")
    for e in unknown:
        print(f"  [{e['country']}] {e['name']} {e['colour']:3s} records={len(e['records']):3d}  "
              f"e.g. {', '.join(e['records'][:4])}  ({e['queue']})")
    print(f"\n## Fuzzy bindings in the corpus — {len(fuzzy)} (review: a spelling, or another cultivar?)")
    for e in fuzzy:
        print(f"  {e['score']:3d}  {e['name']!r} → {e['slug']}  records={len(e['records'])}  e.g. {', '.join(e['records'][:3])}")
    if args.json:
        args.json.write_text(json.dumps({"unknown": unknown, "fuzzy": fuzzy}, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
