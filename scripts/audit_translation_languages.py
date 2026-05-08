"""Sanity check that translated content is actually in the expected language.

Not a pipeline stage. Run on a fresh checkout (or after re-running 02b/02c/
02e) to catch translation pipeline bugs — wrong-language msgstr in a
gettext catalog, an EN summary that's still FR because the manual round-trip
imported the wrong column, a Wikipedia 'extract' that fell back to the
wrong-language page, etc.

Detection is offline via `lingua-language-detector`, restricted to the four
locales the project ships ({en, fr, es, nl}). Lingua is more accurate on
short strings than langdetect/langid, but very short bullets ( ≤ ~15 chars)
or strings dominated by proper nouns ('Coteaux du Layon', 'Vaillons') still
get noisy — pass --min-chars to set the floor.

Surfaces audited (each one keyed by the locale in its path / record):
  - summaries:    raw/translations/summaries/<lang>/*.json   (`summary`)
  - terroir:      raw/translations/terroir-facts/<lang>/*.json (`facts[*].bullet`)
  - wiki-grapes:  raw/wikipedia/grapes/<lang>/*.json          (`extract`)
  - wiki-styles:  raw/wikipedia/styles/<lang>/*.json          (`extract`)
  - wiki-aocs:    raw/wikipedia/aocs/fr/*.json                (`lead_extract`, FR-only)
  - cahier:       raw/inao/cahier-extracted/*.json            (`lien_au_terroir`, expect FR)
  - terroir-src:  raw/terroir-facts/*.json                    (`facts[*].bullet`, expect FR)
  - gettext:      locale/<lang>/LC_MESSAGES/messages.po       (`msgstr` per entry)

Outputs:
  - One stderr line per mismatching item (file + expected/detected + snippet).
  - Aggregate per-surface counts at the end.
  - Optional `--report PATH` writes the full audit (including matches) as JSON.

Exit code is non-zero only on internal errors; mismatches are reported but
don't fail the run.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parent.parent

EXPECTED_LANGS = ("en", "fr", "es", "nl")
DEFAULT_MIN_CHARS = 15
DEFAULT_CONFIDENCE = 0.5
SNIPPET_CHARS = 90


@dataclass
class Item:
    surface: str
    expected: str
    file: str
    locator: str  # e.g. "summary" or "facts[3].bullet" or "msgid:rouge"
    text: str


@dataclass
class Finding:
    surface: str
    expected: str
    detected: str | None
    confidence: float
    file: str
    locator: str
    snippet: str
    chars: int


# ──────────────────────────────────────────────────────── source iterators ──


def iter_summaries() -> Iterator[Item]:
    base = ROOT / "raw" / "translations" / "summaries"
    for lang in EXPECTED_LANGS:
        d = base / lang
        if not d.exists():
            continue
        for p in sorted(d.glob("*.json")):
            try:
                rec = json.loads(p.read_text())
            except Exception:  # noqa: BLE001
                continue
            text = (rec.get("summary") or "").strip()
            if text:
                yield Item("summaries", lang, str(p.relative_to(ROOT)), "summary", text)


def iter_terroir_translated() -> Iterator[Item]:
    base = ROOT / "raw" / "translations" / "terroir-facts"
    for lang in EXPECTED_LANGS:
        d = base / lang
        if not d.exists():
            continue
        for p in sorted(d.glob("*.json")):
            try:
                rec = json.loads(p.read_text())
            except Exception:  # noqa: BLE001
                continue
            for i, f in enumerate(rec.get("facts") or []):
                text = (f.get("bullet") or "").strip()
                if text:
                    yield Item(
                        "terroir", lang, str(p.relative_to(ROOT)),
                        f"facts[{i}].bullet", text,
                    )


def iter_wiki(subdir: str, surface: str, field: str) -> Iterator[Item]:
    base = ROOT / "raw" / "wikipedia" / subdir
    for lang in EXPECTED_LANGS:
        d = base / lang
        if not d.exists():
            continue
        for p in sorted(d.glob("*.json")):
            try:
                rec = json.loads(p.read_text())
            except Exception:  # noqa: BLE001
                continue
            if rec.get("missing") or rec.get("error"):
                continue
            text = (rec.get(field) or "").strip()
            if text:
                yield Item(surface, lang, str(p.relative_to(ROOT)), field, text)


def iter_cahier_summaries() -> Iterator[Item]:
    base = ROOT / "raw" / "inao" / "cahier-extracted"
    for p in sorted(base.glob("*.json")):
        if p.name == "_index.json":
            continue
        try:
            rec = json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            continue
        text = (rec.get("lien_au_terroir") or "").strip()
        if text:
            yield Item("cahier", "fr", str(p.relative_to(ROOT)), "lien_au_terroir", text)


def iter_terroir_source() -> Iterator[Item]:
    base = ROOT / "raw" / "terroir-facts"
    for p in sorted(base.glob("*.json")):
        if p.name == "manifest.json":
            continue
        try:
            rec = json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            continue
        for i, f in enumerate(rec.get("facts") or []):
            text = (f.get("bullet") or "").strip()
            if text:
                yield Item(
                    "terroir-src", "fr", str(p.relative_to(ROOT)),
                    f"facts[{i}].bullet", text,
                )


def iter_gettext() -> Iterator[Item]:
    from babel.messages.pofile import read_po
    base = ROOT / "locale"
    for lang in EXPECTED_LANGS:
        po_path = base / lang / "LC_MESSAGES" / "messages.po"
        if not po_path.exists():
            continue
        with po_path.open("rb") as fh:
            catalog = read_po(fh)
        for msg in catalog:
            if not msg.id:
                continue
            msgstr = msg.string if isinstance(msg.string, str) else (msg.string[0] if msg.string else "")
            msgstr = (msgstr or "").strip()
            if not msgstr:
                continue
            locator = f"msgid:{msg.id[:60]}"
            yield Item("gettext", lang, str(po_path.relative_to(ROOT)), locator, msgstr)


SURFACES = {
    "summaries": iter_summaries,
    "terroir": iter_terroir_translated,
    "wiki-grapes": lambda: iter_wiki("grapes", "wiki-grapes", "extract"),
    "wiki-styles": lambda: iter_wiki("styles", "wiki-styles", "extract"),
    "wiki-aocs": lambda: iter_wiki("aocs", "wiki-aocs", "lead_extract"),
    "cahier": iter_cahier_summaries,
    "terroir-src": iter_terroir_source,
    "gettext": iter_gettext,
}


# ─────────────────────────────────────────────────────────────── detection ──


def build_detector():
    from lingua import Language, LanguageDetectorBuilder
    return (
        LanguageDetectorBuilder
        .from_languages(Language.ENGLISH, Language.FRENCH, Language.SPANISH, Language.DUTCH)
        .with_preloaded_language_models()
        .build()
    )


ISO_TO_KEY = {"EN": "en", "FR": "fr", "ES": "es", "NL": "nl"}


def detect(detector, text: str) -> tuple[str | None, float]:
    confidences = detector.compute_language_confidence_values(text)
    if not confidences:
        return None, 0.0
    top = confidences[0]
    return ISO_TO_KEY.get(top.language.iso_code_639_1.name), top.value


# ────────────────────────────────────────────────────────────────── audit ──


def audit_items(
    items: Iterator[Item], detector, min_chars: int, confidence: float,
) -> tuple[list[Finding], dict]:
    findings: list[Finding] = []
    per_surface: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    per_pair: Counter[tuple[str, str, str]] = Counter()  # (surface, expected, detected)
    skipped_short = 0
    for it in items:
        per_surface[it.surface]["total"] += 1
        if len(it.text) < min_chars:
            per_surface[it.surface]["skipped_short"] += 1
            skipped_short += 1
            continue
        detected, conf = detect(detector, it.text)
        per_surface[it.surface]["checked"] += 1
        if detected == it.expected:
            per_surface[it.surface]["match"] += 1
            per_pair[(it.surface, it.expected, detected)] += 1
            continue
        if conf < confidence:
            per_surface[it.surface]["low_conf"] += 1
            continue
        per_surface[it.surface]["mismatch"] += 1
        per_pair[(it.surface, it.expected, detected or "?")] += 1
        snippet = " ".join(it.text.split())[:SNIPPET_CHARS]
        findings.append(Finding(
            surface=it.surface,
            expected=it.expected,
            detected=detected,
            confidence=round(conf, 3),
            file=it.file,
            locator=it.locator,
            snippet=snippet,
            chars=len(it.text),
        ))
    summary = {
        "per_surface": {k: dict(v) for k, v in per_surface.items()},
        "skipped_short": skipped_short,
        "pairs": {f"{s}:{e}->{d}": n for (s, e, d), n in per_pair.most_common()},
    }
    return findings, summary


def print_findings(findings: list[Finding]) -> None:
    if not findings:
        print("[audit] no language mismatches.", file=sys.stderr)
        return
    by_surface: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        by_surface[f.surface].append(f)
    for surface in sorted(by_surface):
        rows = by_surface[surface]
        print(f"\n[{surface}] {len(rows)} mismatch(es):", file=sys.stderr)
        for f in rows:
            det = f.detected or "?"
            print(
                f"  {f.expected}->{det} ({f.confidence:.2f}) "
                f"{f.file} :: {f.locator}\n      {f.snippet}",
                file=sys.stderr,
            )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--surface", action="append", choices=list(SURFACES.keys()) + ["all"],
        help="surfaces to audit; repeatable; default = all",
    )
    ap.add_argument(
        "--min-chars", type=int, default=DEFAULT_MIN_CHARS,
        help=f"skip items shorter than N chars (default {DEFAULT_MIN_CHARS})",
    )
    ap.add_argument(
        "--confidence", type=float, default=DEFAULT_CONFIDENCE,
        help=(
            "report a mismatch only when the detector's confidence in the "
            f"wrong language is ≥ this (default {DEFAULT_CONFIDENCE})"
        ),
    )
    ap.add_argument("--report", metavar="PATH", default=None, help="write full audit JSON to PATH")
    args = ap.parse_args()

    surfaces = args.surface or ["all"]
    if "all" in surfaces:
        surfaces = list(SURFACES.keys())

    print(f"[audit] loading lingua models for {EXPECTED_LANGS}…", file=sys.stderr)
    detector = build_detector()

    all_findings: list[Finding] = []
    all_summaries: dict[str, dict] = {}
    for s in surfaces:
        print(f"[audit] surface={s}", file=sys.stderr)
        findings, summary = audit_items(
            SURFACES[s](), detector,
            min_chars=args.min_chars, confidence=args.confidence,
        )
        all_findings.extend(findings)
        all_summaries[s] = summary

    print_findings(all_findings)

    print("\n[audit] summary:", file=sys.stderr)
    print(json.dumps(all_summaries, ensure_ascii=False, indent=2), file=sys.stderr)

    if args.report:
        Path(args.report).write_text(json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "min_chars": args.min_chars,
            "confidence_threshold": args.confidence,
            "summary": all_summaries,
            "findings": [asdict(f) for f in all_findings],
        }, ensure_ascii=False, indent=2) + "\n")
        print(f"[audit] full report → {args.report}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
