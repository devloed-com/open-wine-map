#!/usr/bin/env python3
"""Audit — wine-style coverage across the resolved appellation map.

Reads the final `wiki/map-data/appellations.geojson` and reports, per country,
how many appellations carry a wine-style tag, how many don't, and — for those
that don't — whether the gap is *fixable* (the spec just never named a colour,
but the authorised grapes have a known berry colour the stage-04 floor can
derive) or *honest* (no grapes catalogued at all, e.g. the tiny Swiss cantons,
so no colour can be inferred from any public source).

It mirrors the stage-04 grape-colour floor (`_base_colour_styles_from_grapes`
in scripts/04_build_maps.py): berry colour blanc/gris/rose → white, noir → red,
resolved from DEFAULT_COLOUR + VIVC `color`, with the same sparkling-only-red
refinement. So `fixable` is the set the floor should have filled — run before a
rebuild it estimates the work; run after, it should read 0 (only honest no-grape
empties remain). The geojson lacks per-grape `details[].colour`, so the audit
resolves colour from DEFAULT_COLOUR + VIVC only — a strict subset of what the
build uses, so the audit never over-reports a gap.

The geojson is streamed feature-by-feature (it is hundreds of MB) so the audit
runs in tens of MB of RAM.

Exit code is 0 normally; with --strict it is non-zero when any `fixable` gap
remains (use after a rebuild to gate CI).

Usage:
  .venv/bin/python scripts/audit_styles.py
  .venv/bin/python scripts/audit_styles.py --strict
  .venv/bin/python scripts/audit_styles.py --geojson wiki/map-data/appellations.geojson
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.grape_lexicon import DEFAULT_COLOUR  # noqa: E402

DEFAULT_GEOJSON = ROOT / "wiki" / "map-data" / "appellations.geojson"
VIVC_BY_SLUG = ROOT / "raw" / "vivc" / "by-slug"

# Same tables as the stage-04 floor — kept in sync deliberately.
BERRY_TO_STYLE = {"blanc": "white", "gris": "white", "rose": "white", "noir": "red"}
COLOUR_STYLES = {"white", "red", "rose"}
SPARKLING_FAMILY = {"sparkling", "semi-sparkling", "cremant"}


def load_vivc_colour() -> dict[str, str]:
    """`{slug: blanc|gris|noir|rose}` from raw/vivc/by-slug/<slug>.json `color`."""
    out: dict[str, str] = {}
    fold = {"NOIR": "noir", "BLANC": "blanc", "GRIS": "gris", "ROSE": "rose"}
    if VIVC_BY_SLUG.exists():
        for f in VIVC_BY_SLUG.glob("*.json"):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            colour = fold.get((d.get("color") or "").strip().upper())
            slug = d.get("slug")
            if colour and slug:
                out[slug] = colour
    return out


def stream_features(path: Path) -> Iterator[dict]:
    """Yield GeoJSON features one at a time without loading the whole file
    (it is a single compact line, hundreds of MB)."""
    dec = json.JSONDecoder()
    chunk = 1 << 20
    with path.open(encoding="utf-8") as fh:
        buf = ""
        while '"features"' not in buf:
            more = fh.read(chunk)
            if not more:
                raise ValueError(f"{path} has no 'features' key — not a GeoJSON")
            buf += more
        buf = buf[buf.index('"features"'):]
        while "[" not in buf:
            more = fh.read(chunk)
            if not more:
                raise ValueError(f"{path} has no 'features' array")
            buf += more
        buf = buf[buf.index("[") + 1:]
        while True:
            buf = buf.lstrip()
            while buf.startswith(","):
                buf = buf[1:].lstrip()
            if buf.startswith("]"):
                return
            if not buf:
                more = fh.read(chunk)
                if not more:
                    raise ValueError(f"{path} truncated — wait for stage 04 to finish")
                buf += more
                continue
            try:
                obj, end = dec.raw_decode(buf)
            except json.JSONDecodeError:
                more = fh.read(chunk)
                if not more:
                    raise ValueError(f"{path} truncated — wait for stage 04 to finish") from None
                buf += more
                continue
            yield obj
            buf = buf[end:]


def _split(s: str | None) -> list[str]:
    return [x for x in (s or "").split(";") if x]


def floor_add(grape_slugs: list[str], existing_styles: set[str],
              vivc: dict[str, str]) -> set[str]:
    """Colours the stage-04 floor would add (white / red), from DEFAULT_COLOUR
    + VIVC. Mirrors `_base_colour_styles_from_grapes`, incl. the sparkling-red
    refinement."""
    add: set[str] = set()
    for s in grape_slugs:
        berry = DEFAULT_COLOUR.get(s) or vivc.get(s)
        style = BERRY_TO_STYLE.get(berry or "")
        if style:
            add.add(style)
    if "red" in add and existing_styles and existing_styles <= SPARKLING_FAMILY:
        add.discard("red")
    return add


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--geojson", type=Path, default=DEFAULT_GEOJSON)
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero if any fixable gap remains")
    args = ap.parse_args()

    if not args.geojson.exists():
        print(f"error: {args.geojson} missing — run scripts/04_build_maps.py",
              file=sys.stderr)
        return 1

    vivc = load_vivc_colour()
    total = Counter()
    empty = Counter()           # no style at all
    empty_grapes = Counter()    # empty AND has grapes (fixable-by-colour)
    empty_no_grapes = Counter() # empty AND no grapes (honest residual)
    no_colour = Counter()       # has no white/red/rose style
    fixable = Counter()         # no colour + wine + grapes resolve to a colour
    fix_examples: dict[str, list[str]] = defaultdict(list)
    honest_examples: dict[str, list[str]] = defaultdict(list)

    print(f"scanning {args.geojson.relative_to(ROOT)} …", file=sys.stderr)
    for ft in stream_features(args.geojson):
        p = ft.get("properties", {})
        c = p.get("country", "?")
        total[c] += 1
        styles = set(_split(p.get("styles")))
        grapes = _split(p.get("grapes_all")) or (
            _split(p.get("grapes_principal"))
            + _split(p.get("grapes_accessory"))
            + _split(p.get("grapes_observation"))
        )
        has_grapes = bool(grapes)
        if not styles:
            empty[c] += 1
            if has_grapes:
                empty_grapes[c] += 1
            else:
                empty_no_grapes[c] += 1
                if len(honest_examples[c]) < 6:
                    honest_examples[c].append(p.get("slug", "?"))
        if not (styles & COLOUR_STYLES):
            no_colour[c] += 1
            if p.get("is_wine") == "1" and has_grapes and floor_add(grapes, styles, vivc):
                fixable[c] += 1
                if len(fix_examples[c]) < 6:
                    fix_examples[c].append(p.get("slug", "?"))

    print(file=sys.stderr)
    print("STYLE-COVERAGE AUDIT", file=sys.stderr)
    print("=" * 78, file=sys.stderr)
    print(f"source: {args.geojson.relative_to(ROOT)}", file=sys.stderr)
    print(file=sys.stderr)
    hdr = f"{'cc':>4} {'total':>7} {'noStyle':>8} {'noColour':>9} {'fixable':>8} {'honest(noGrapes)':>17}"
    print(hdr, file=sys.stderr)
    print("-" * len(hdr), file=sys.stderr)
    for c in sorted(total, key=lambda x: (-fixable[x], -no_colour[x], x)):
        if no_colour[c] == 0 and empty[c] == 0:
            continue
        print(f"{c:>4} {total[c]:>7} {empty[c]:>8} {no_colour[c]:>9} "
              f"{fixable[c]:>8} {empty_no_grapes[c]:>17}", file=sys.stderr)
    print("-" * len(hdr), file=sys.stderr)
    print(f"{'ALL':>4} {sum(total.values()):>7} {sum(empty.values()):>8} "
          f"{sum(no_colour.values()):>9} {sum(fixable.values()):>8} "
          f"{sum(empty_no_grapes.values()):>17}", file=sys.stderr)
    print(file=sys.stderr)

    if sum(fixable.values()):
        print(f"FIXABLE — no colour style but grapes resolve one  "
              f"[{sum(fixable.values())}]  (floor should fill these)", file=sys.stderr)
        for c in sorted(fix_examples, key=lambda x: -fixable[x]):
            print(f"  {c}: {fixable[c]:>4}  e.g. {', '.join(fix_examples[c])}",
                  file=sys.stderr)
        print(file=sys.stderr)

    honest = sum(empty_no_grapes.values())
    if honest:
        print(f"HONEST — empty styles, no grapes catalogued  [{honest}]  "
              f"(no colour inferrable from any public source)", file=sys.stderr)
        for c in sorted(honest_examples, key=lambda x: -empty_no_grapes[x]):
            print(f"  {c}: {empty_no_grapes[c]:>4}  e.g. {', '.join(honest_examples[c])}",
                  file=sys.stderr)
        print(file=sys.stderr)

    if args.strict and sum(fixable.values()):
        print(f"FAIL (--strict): {sum(fixable.values())} fixable gaps remain — "
              "re-run scripts/04_build_maps.py", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
