"""Detect untranslated source-language residue in the stage-02e caches (W1).

Scans `raw/translations/terroir-facts/<lang>/*.json` for lang in en / fr /
es / nl (caches with `mode == "verbatim"` are skipped) and flags every
bullet that still carries non-Latin script or one of the common-noun leaks
the 2026-09-11 review catalogued in docs/plan-terroir-facts-quality.md —
soils, climates, harvest categories, site words and scheme abbreviations
that the old per-country "Preserve … verbatim" prompt lists told the model
to keep. Prints a per-country × per-locale count table to stderr and
writes a JSON report with the flagged rows plus, per country, the exact
`02e … --batch --provider anthropic --refresh --only …` command that
re-translates them.

No LLM call, no cache write. `--strict` exits non-zero when anything is
flagged (for CI).

    .venv/bin/python scripts/detect_untranslated_terroir_facts.py
    .venv/bin/python scripts/detect_untranslated_terroir_facts.py --strict
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.exonyms import exonym_hits, gi_forms_from_names  # noqa: E402

TERROIR_FACTS = ROOT / "raw" / "terroir-facts"
CACHE_ROOT = ROOT / "raw" / "translations" / "terroir-facts"
DEFAULT_REPORT = ROOT / "tmp" / "terroir-facts-review" / "untranslated.json"

TARGET_LOCALES = ("en", "fr", "es", "nl")

# Cyrillic + Greek blocks — any hit in a Latin-target cache is a leak.
NON_LATIN = re.compile(r"[Ѐ-ӿͰ-Ͽ]")

# Verbatim from docs/plan-terroir-facts-quality.md, section W1.
LEAK = re.compile(r"(?i)\b(lösz|mészkő|homokkő|argille|argilliti|arenari[ae]|calcar[ei]|marn[ae]|scisti|"
                  r"podgori\w*|mineralité|kasna berba|desertn\w+ vin\w*|predikatn\w+|pozna trgatev|"
                  r"ledeno vino|okoliš|vapnen\w+|crvenic\w+|fliš|apnen\w+|xisto\w*|leem|zandleem|mergel|"
                  r"viničn\w+|dűlő\w*|lege\b|Steillage\w*|Lagenwein\w*|Urgestein|typology|must varieties)\b")

# The plan's regex is source-language-agnostic, so a few of its tokens are
# the *correct* word in one target locale: NL "leem" / "zandleem" / "mergel"
# are the Dutch for loam / sandy loam / marl and "lege" is Dutch for
# "empty"; FR "marne" is the French for marl. Those are not leaks in that
# locale. `--raw` disables the exemption.
_TARGET_NATIVE = {
    "nl": {"leem", "zandleem", "mergel", "lege"},
    "fr": {"marne"},
}
# "Marne" capitalised is the river / département (Haute-Marne, vallée de la
# Marne), a proper noun in every locale.
_PROPER_NOUN_TOKENS = {"Marne"}


def _load(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _country_of(slug: str, cache: dict, memo: dict[str, str]) -> str:
    if slug in memo:
        return memo[slug]
    src = _load(TERROIR_FACTS / f"{slug}.json")
    if src is not None:
        cc = src.get("country") or "fr"
    else:
        cc = cache.get("country") or "fr"
    memo[slug] = cc
    return cc


def _script_for(country: str) -> str:
    if country == "fr":
        return "scripts/02e_translate_terroir_facts.py"
    return f"scripts/{country}/02e_translate_terroir_facts.py"


_GI_FORMS: frozenset[str] | None = None


def _gi_forms() -> frozenset[str]:
    """Exonym source forms that also occur in an appellation name (wiki/_index.json)."""
    global _GI_FORMS
    if _GI_FORMS is None:
        index = ROOT / "wiki" / "_index.json"
        names = []
        if index.exists():
            names = [v.get("name") or "" for v in json.loads(index.read_text(encoding="utf-8")).values()]
        _GI_FORMS = gi_forms_from_names(names)
    return _GI_FORMS


def _reasons(bullet: str, lang: str, *, raw: bool) -> list[str]:
    reasons: list[str] = []
    m = NON_LATIN.search(bullet)
    if m:
        reasons.append(f"non-latin:{m.group(0)}")
    for form in exonym_hits(bullet, lang, gi_forms=_gi_forms()):
        reasons.append(f"exonym:{form}")
    native = set() if raw else _TARGET_NATIVE.get(lang, set())
    for m in LEAK.finditer(bullet):
        tok = m.group(1)
        if not raw and (tok.lower() in native or tok in _PROPER_NOUN_TOKENS):
            continue
        reasons.append(f"leak:{tok}")
    return reasons


def scan(languages: tuple[str, ...], *, raw: bool) -> list[dict]:
    memo: dict[str, str] = {}
    rows: list[dict] = []
    for lang in languages:
        for path in sorted((CACHE_ROOT / lang).glob("*.json")):
            d = _load(path)
            if not d or d.get("mode") == "verbatim":
                continue
            slug = d.get("slug") or path.stem
            country = _country_of(slug, d, memo)
            for i, fact in enumerate(d.get("facts") or []):
                bullet = fact.get("bullet") or ""
                reasons = _reasons(bullet, lang, raw=raw)
                if reasons:
                    rows.append({
                        "slug": slug, "lang": lang, "country": country, "index": i,
                        "bullet": bullet, "reason": "; ".join(reasons),
                    })
    return rows


def _table(rows: list[dict], languages: tuple[str, ...], key) -> str:
    cells: dict[str, dict[str, set | int]] = defaultdict(lambda: defaultdict(set))
    for r in rows:
        cells[r["country"]][r["lang"]].add(key(r))
    countries = sorted(cells)
    head = f"{'country':<8}" + "".join(f"{lang:>7}" for lang in languages) + f"{'total':>8}"
    lines = [head, "-" * len(head)]
    col_tot = defaultdict(int)
    for cc in countries:
        n = [len(cells[cc].get(lang, ())) for lang in languages]
        for lang, v in zip(languages, n):
            col_tot[lang] += v
        lines.append(f"{cc:<8}" + "".join(f"{v:>7}" for v in n) + f"{sum(n):>8}")
    lines.append("-" * len(head))
    tot = [col_tot[lang] for lang in languages]
    lines.append(f"{'all':<8}" + "".join(f"{v:>7}" for v in tot) + f"{sum(tot):>8}")
    return "\n".join(lines)


def _commands(rows: list[dict]) -> dict[str, dict]:
    by_cc: dict[str, dict[str, set]] = defaultdict(lambda: {"slugs": set(), "langs": set()})
    for r in rows:
        by_cc[r["country"]]["slugs"].add(r["slug"])
        by_cc[r["country"]]["langs"].add(r["lang"])
    out: dict[str, dict] = {}
    for cc in sorted(by_cc):
        slugs = sorted(by_cc[cc]["slugs"])
        langs = [lang for lang in TARGET_LOCALES if lang in by_cc[cc]["langs"]]
        cmd = (
            f".venv/bin/python {_script_for(cc)} --batch --provider anthropic --refresh"
            + "".join(f" --lang {lang}" for lang in langs)
            + "".join(f" --only {s}" for s in slugs)
        )
        out[cc] = {
            "script": _script_for(cc),
            "slugs": slugs,
            "langs": langs,
            "command": cmd,
            "note": (
                "--refresh re-translates every listed slug in every listed locale, so a "
                "slug flagged in only some of these locales is re-done in the others too."
            ),
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--report", default=str(DEFAULT_REPORT), help="JSON report path")
    ap.add_argument(
        "--lang", action="append", choices=TARGET_LOCALES, default=None,
        help="restrict to a target locale (repeatable); default: all 4",
    )
    ap.add_argument("--raw", action="store_true",
                    help="no target-native exemptions (flag NL leem/mergel, FR marne, Marne)")
    ap.add_argument("--strict", action="store_true", help="exit non-zero when anything is flagged")
    args = ap.parse_args()

    languages = tuple(args.lang) if args.lang else TARGET_LOCALES
    if not CACHE_ROOT.exists():
        print(f"error: {CACHE_ROOT} is missing", file=sys.stderr)
        return 1
    rows = scan(languages, raw=args.raw)

    pairs = {(r["slug"], r["lang"]) for r in rows}
    slugs = {r["slug"] for r in rows}
    print("[detect-untranslated] flagged bullets per country × locale:", file=sys.stderr)
    print(_table(rows, languages, key=lambda r: (r["slug"], r["index"])), file=sys.stderr)
    print("[detect-untranslated] flagged (slug, lang) pairs per country × locale:", file=sys.stderr)
    print(_table(rows, languages, key=lambda r: r["slug"]), file=sys.stderr)
    print(
        f"[detect-untranslated] {len(rows)} bullets, {len(pairs)} (slug, lang) pairs, "
        f"{len(slugs)} slugs flagged" + (" (raw)" if args.raw else ""),
        file=sys.stderr,
    )

    by_country: dict[str, dict[str, dict[str, int]]] = defaultdict(dict)
    for cc in sorted({r["country"] for r in rows}):
        for lang in languages:
            sub = [r for r in rows if r["country"] == cc and r["lang"] == lang]
            if sub:
                by_country[cc][lang] = {
                    "bullets": len(sub), "pairs": len({r["slug"] for r in sub}),
                }
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "languages": list(languages),
        "raw": args.raw,
        "summary": {
            "flagged_bullets": len(rows),
            "flagged_pairs": len(pairs),
            "flagged_slugs": len(slugs),
            "by_country": by_country,
        },
        "rows": rows,
        "commands": _commands(rows),
    }
    out = Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[detect-untranslated] report → {out}", file=sys.stderr)
    return 1 if (args.strict and rows) else 0


if __name__ == "__main__":
    sys.exit(main())
