"""Flag grape names that look like parsed prose rather than a variety.

Whole-document and column-layout parsers hand the matcher whatever the
regulator's text happens to contain, so a variety pill can end up reading
"Art. 28 5 Compensation Pinot noir - Gamay", or a place name can resolve
to a grape ("d'Essertines-sur-Rolle" gave nine Vaud AOCs Vermentino).
The slug is often still right, which is why these survive: nothing
crashes, the panel just says something false or ugly.

Run this straight after a country's stage-02 extraction. It reads the
extracted JSON, so it answers in seconds and needs no map build.

Buckets:
  ARTIFACT   the surface carries prose punctuation, a column gutter, a
             section marker, or runs far longer than a variety name.
  TRUNCATED  the surface has fewer words than its own slug, so a split
             cut a multi-word name in half ("Pinot" for pinot-noir).
  STYLE      a known wine-style or appellation term sitting in a variety
             list (Dôle, Œil-de-Perdrix, Amarone …).

Usage:
    .venv/bin/python scripts/audit_grape_surfaces.py
    .venv/bin/python scripts/audit_grape_surfaces.py --country ch
    .venv/bin/python scripts/audit_grape_surfaces.py --strict
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

_PROSE_PREFIX = re.compile(
    r"^(?:art|article|artikel|al|abs|ziff|lit|lettre|mention|menzione|"
    r"communes?|gemeinden?|comuni?|territoire|gebiet|zona|zone|cf|voir|siehe)\b\.?",
    re.IGNORECASE,
)
_GUTTER = re.compile(r"\s{2,}")
_PROSE_PUNCT = re.compile(r"[\"«»:;]")
_UNIT = re.compile(r"\d\s*(?:kg|hl|ha|%|°(?:oe|brix)?)\b", re.IGNORECASE)

# Wine styles and appellation terms that regulators list beside varieties.
_STYLE_TERMS = {
    "dole", "oeildeperdrix", "amarone", "recioto", "vinsanto", "vinsanto",
    "ripasso", "passito", "clairet", "federspiel", "smaragd", "steinfeder",
}


def _norm(s: str) -> str:
    from unidecode import unidecode
    return "".join(c for c in unidecode(s).casefold() if c.isalpha())


def classify(name: str, slug: str) -> str | None:
    if _norm(name) in _STYLE_TERMS:
        return "STYLE"
    if (_GUTTER.search(name) or _PROSE_PUNCT.search(name)
            or _PROSE_PREFIX.match(name.strip()) or _UNIT.search(name)
            or len(name) > 40 or len(name.split()) > 5):
        return "ARTIFACT"
    words = [w for w in re.split(r"[\s-]+", name.strip()) if w]
    if words and len(words) < len(slug.split("-")) and slug.startswith(words[0].lower()):
        return "TRUNCATED"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--country", help="restrict to one country code")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero when anything is flagged")
    args = ap.parse_args()

    found: dict[str, list[tuple]] = collections.defaultdict(list)
    scanned = 0
    for d in sorted((ROOT / "raw").glob("*/*-extracted")):
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
            cc = rec.get("country") or d.parts[-2]
            if args.country and cc != args.country:
                continue
            for det in grapes.get("details") or []:
                if not isinstance(det, dict):
                    continue
                name, slug = det.get("name"), det.get("slug")
                if not isinstance(name, str) or not isinstance(slug, str):
                    continue
                scanned += 1
                bucket = classify(name, slug)
                if bucket:
                    found[bucket].append((cc, path.stem, name, slug))

    total = sum(len(v) for v in found.values())
    print(f"grape surfaces scanned: {scanned}")
    print(f"flagged: {total}")
    for bucket in ("ARTIFACT", "TRUNCATED", "STYLE"):
        rows = found.get(bucket) or []
        if not rows:
            continue
        uniq = collections.Counter((n, s) for _, _, n, s in rows)
        print(f"\n=== {bucket} ({len(rows)} entries / {len(uniq)} distinct) ===")
        for (n, s), c in uniq.most_common(20):
            where = {cc for cc, _, nn, ss in rows if (nn, ss) == (n, s)}
            print(f"  {c:4d}x [{'/'.join(sorted(where))}] {n[:52]!r} -> {s}")

    if args.strict and total:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
