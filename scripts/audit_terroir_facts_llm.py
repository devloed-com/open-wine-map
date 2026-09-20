"""LLM quality audit of the rendered terroir facts — the adversarial
verifier of the 2026-09-12 review as a repeatable script (R9).

For a sample of records it grades every ENGLISH bullet (the locale
readers see; `--lang` for another) against the source-language bullet,
the grounding quotes, the full regulator text stage 02d graded against
(`_lib/terroir_sources`) and the Wikipedia hints, and asks: would a
reader of this bullet believe something the sources do not support?
One request per record; the default grader is `claude-opus-5` — a
different, stronger model than the stage-02d extractor and the
claim-support gate (claude-sonnet-4-6), so the measure is independent
of the machinery it measures.

Paired before / after: `--from-backup RUN` grades the same records as
they were BEFORE a re-run (the snapshot under
`raw/terroir-facts-backup/<RUN>/`; a record the run did not touch is
read live), against the CURRENT sources. `--compare A.json B.json`
prints the paired comparison of two reports.

Outputs a JSON report (`tmp/terroir-facts-review/llm-audit-<run>.json`):
per bullet verdict / reader_misled / where / tags / reason /
corrected_en, plus a summary (misleading share with a Wilson 95 %
interval, by country, by stage, by tag). Read-only: never writes a cache.

Usage:
  .venv/bin/python scripts/audit_terroir_facts_llm.py --sample 100 --batch
  .venv/bin/python scripts/audit_terroir_facts_llm.py --sample 100 --batch --from-backup r1-2026-09-13 --report tmp/terroir-facts-review/llm-audit-before.json
  .venv/bin/python scripts/audit_terroir_facts_llm.py --compare before.json after.json
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import batch, cache, llm_json, providers, terroir_backup  # noqa: E402
from _lib.prompt_cache import mark_cached  # noqa: E402
from _lib.terroir_cache import TERROIR, TRANSLATIONS  # noqa: E402
from _lib.terroir_dedupe import facts_sha  # noqa: E402
from _lib.terroir_feedback import _safe  # noqa: E402
from _lib.terroir_sources import COUNTRIES, Sources, resolve_sources  # noqa: E402

DEFAULT_GRADER = providers.stage_default("audit")[0]
REPORT_DIR = ROOT / "tmp" / "terroir-facts-review"
BATCH_SIDECAR = ROOT / "raw" / ".batch" / "llm-audit.json"
MAX_TOKENS = 8000
MAX_SOURCE_CHARS = 60_000
TAGS = ("wrong-entity", "unsupported-causal-link", "invented-detail", "wrong-number-or-unit",
        "wrong-direction", "hedge-dropped-or-changed", "sibling-or-subzone-confusion",
        "narrowed-attribution", "added-qualifier", "mistranslation", "untranslated-term",
        "label-fragment", "duplicate", "misfiled-subsection", "tautology", "other")

SYSTEM = """You are the adversarial verifier for a terroir-fact quality audit (Open Wine Map: bullets an LLM extracted from wine-regulator appellation texts — cahier des charges, disciplinare, pliego, Einziges Dokument — then machine-translated for readers). For ONE record you receive every bullet as the reader sees it (the TARGET rendering), the source-language bullet it was translated from (SRC), the grounding quotes the extractor cited (CQ from the regulator text, WQ from Wikipedia), the record's full regulator SOURCE TEXT and the Wikipedia HINTS. Your job is to try to find, for each bullet, anything a reader would come to believe that the sources do not support.

For EACH bullet decide:
- verdict: "faithful" (every assertion is supported; a simplification is not an error; a number formatted differently in the source — 13°5, 22, 5, anni '60, XVIIIe — is not missing; a Wikipedia-grounded bullet is legitimately grounded), "defective" (a real defect that does not mislead: a clumsy phrase, a source-language common noun left untranslated, a label-style fragment, a misfiled sub-section, a restatement of another bullet) or "misleading" (the reader would believe something false or unsupported: a wrong entity, an unsupported causal link, an invented detail or qualifier, a wrong number, unit or direction, a dropped or strengthened hedge, a sub-zone or neighbour presented as the whole, one factor credited with what the source credits to several, a mistranslation that changes the meaning).
- reader_misled: true only for "misleading".
- where: "extraction" (the defect is already in SRC), "translation" (SRC is right, the TARGET rendering is wrong), "both", or "none".
- tags: zero or more of {tags}.
- reason: two precise sentences quoting the decisive source words.
- corrected: the bullet as it should read in the TARGET language if not faithful, else "".

Default to "faithful" when uncertain. Be strict about causation: "the soils give the wine minerality" is misleading unless a source sentence states that link.

Answer ONLY with JSON, no text before or after:
{"bullets": [{"i": 0, "verdict": "faithful|defective|misleading", "reader_misled": false, "where": "none", "tags": [], "reason": "", "corrected": ""}, ...]}
One object per bullet, in order, with "i" equal to the bullet's index."""


def log(msg: str) -> None:
    print(f"[llm-audit] {msg}", file=sys.stderr)


# ───────────────────────────────────────────────────────────── loading ──


def _read(path: Path, run: str | None, kind: str, lang: str = "") -> dict | None:
    """The live file, or — with `run` — the backup snapshot when the run
    touched this slug (else live)."""
    if run:
        rd = terroir_backup.run_dir(run)
        bp = rd / ("source" if kind == "source" else f"translations/{lang}") / path.name
        entry = cache.read_json_or_none(rd / "entries" / path.name)
        if entry is not None:
            if kind == "source":
                return cache.read_json_or_none(bp) if entry.get("source") else None
            return cache.read_json_or_none(bp) if lang in (entry.get("translations") or []) else None
    return cache.read_json_or_none(path)


def load_record(slug: str, lang: str, run: str | None) -> tuple[dict, dict] | str:
    """(source cache, translation cache) or a skip reason."""
    src = _read(TERROIR / f"{slug}.json", run, "source")
    if not src or src.get("mode") == "verbatim" or not src.get("facts"):
        return "no-facts"
    t = _read(TRANSLATIONS / lang / f"{slug}.json", run, "translation", lang)
    if not t or t.get("mode") == "verbatim" or not t.get("facts"):
        return "no-translation"
    if t.get("source_facts_sha") != facts_sha(src["facts"]) or len(t["facts"]) != len(src["facts"]):
        return "translation-misaligned"
    return src, t


def build_user_message(*, name: str, country: str, source_lang: str, lang: str, src: dict, t: dict, sources: Sources) -> str:
    text = sources.cahier or ""
    if len(text) > MAX_SOURCE_CHARS:
        text = text[:MAX_SOURCE_CHARS] + "\n[… truncated …]"
    hints = "\n\n".join(f"[{k}]\n{v[:2000]}" for k, v in (sources.hints or {}).items() if v) or "(none)"
    rows = []
    for i, (sf, tf) in enumerate(zip(src["facts"], t["facts"])):
        rows.append(
            f"#{i} [{sf.get('subsection') or ''} · {sf.get('provenance') or ''}]\n"
            f"TARGET ({lang}): {tf.get('bullet') or ''}\n"
            f"SRC ({source_lang}): {sf.get('bullet') or ''}\n"
            f"CQ: {sf.get('cahier_quote') or ''}\nWQ: {sf.get('wiki_quote') or ''}"
        )
    return _safe(
        f"RECORD: {name} (country {country}); {len(rows)} bullets.\n\n"
        f"SOURCE TEXT ({len(text)} chars)\n{text or '(no regulator text resolved — grade against the hints)'}\n\n"
        f"WIKIPEDIA HINTS\n{hints}\n\nBULLETS\n" + "\n\n".join(rows)
    )


def parse_reply(raw: str, n: int) -> list[dict] | None:
    s = llm_json.strip_fences(raw or "")
    data = None
    try:
        data = json.loads(s)
    except ValueError:
        import re
        m = re.search(r"\{.*\}", s, re.S)
        if m:
            try:
                data = json.loads(m.group(0))
            except ValueError:
                data = None
    rows = data.get("bullets") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return None
    out = [{"verdict": "faithful", "reader_misled": False, "where": "none", "tags": [], "reason": "", "corrected": ""}
           for _ in range(n)]
    seen = 0
    for r in rows:
        if not isinstance(r, dict):
            continue
        try:
            i = int(r.get("i"))
        except (TypeError, ValueError):
            continue
        if not 0 <= i < n:
            continue
        verdict = str(r.get("verdict") or "faithful").lower()
        verdict = verdict if verdict in ("faithful", "defective", "misleading") else "faithful"
        out[i] = {
            "verdict": verdict,
            "reader_misled": bool(r.get("reader_misled")) and verdict == "misleading",
            "where": str(r.get("where") or "none"),
            "tags": [str(x) for x in (r.get("tags") or []) if isinstance(x, str)][:5],
            "reason": " ".join(str(r.get("reason") or "").split())[:500],
            "corrected": " ".join(str(r.get("corrected") or "").split())[:400],
        }
        seen += 1
    return out if seen or not n else None


# ─────────────────────────────────────────────────────────── grading ──


class SourceResolver:
    def __init__(self) -> None:
        self._by_country: dict[str, dict[str, Sources] | None] = {}

    def get(self, country: str) -> dict[str, Sources] | None:
        if country not in self._by_country:
            try:
                self._by_country[country] = resolve_sources(country) if country in COUNTRIES else None
            except Exception as e:  # noqa: BLE001
                log(f"{country}: sources failed: {e!r}")
                self._by_country[country] = None
        return self._by_country[country]


def grade(provider, model_id: str, items: list[tuple[str, dict, dict]], resolver: SourceResolver, *, lang: str, quiet: bool) -> list[dict]:
    rows: list[dict] = []
    for slug, src, t in tqdm(items, desc="llm-audit", leave=False, disable=quiet):
        country = src.get("country") or "fr"
        source_lang = src.get("source_lang") or ("fr" if country == "fr" else country)
        sources = resolver.get(country)
        s = sources.get(slug) if sources else None
        if s is None:
            rows.append({"slug": slug, "country": country, "status": "no_source"})
            continue
        user = build_user_message(name=src.get("name") or slug, country=country, source_lang=source_lang,
                                  lang=lang, src=src, t=t, sources=s)
        try:
            raw = provider.chat(system=mark_cached(SYSTEM.replace("{tags}", ", ".join(TAGS))), user=user,
                                max_tokens=MAX_TOKENS)
        except Exception as e:  # noqa: BLE001
            rows.append({"slug": slug, "country": country, "status": "error", "error": str(e)[:200]})
            continue
        verdicts = parse_reply(raw, len(t["facts"]))
        if verdicts is None:
            rows.append({"slug": slug, "country": country, "status": "parse_error"})
            continue
        bullets = [{"i": i, "bullet": t["facts"][i].get("bullet") or "", "src": src["facts"][i].get("bullet") or "",
                    "subsection": src["facts"][i].get("subsection"), **v} for i, v in enumerate(verdicts)]
        rows.append({"slug": slug, "country": country, "status": "ok", "n": len(bullets),
                     "n_misleading": sum(1 for b in bullets if b["reader_misled"]),
                     "n_defective": sum(1 for b in bullets if b["verdict"] == "defective"), "bullets": bullets})
        if not quiet:
            log(f"{slug:40} {country:2} n={len(bullets):2} misleading={rows[-1]['n_misleading']} defective={rows[-1]['n_defective']}")
    return rows


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if not n:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - h) / d, (c + h) / d


def summarize(rows: list[dict]) -> dict:
    ok = [r for r in rows if r.get("status") == "ok"]
    n = sum(r["n"] for r in ok)
    mis = sum(r["n_misleading"] for r in ok)
    de = sum(r["n_defective"] for r in ok)
    by_country: dict[str, dict] = {}
    by_where: Counter = Counter()
    by_tag: Counter = Counter()
    for r in ok:
        c = by_country.setdefault(r["country"], {"records": 0, "bullets": 0, "misleading": 0, "defective": 0})
        c["records"] += 1
        c["bullets"] += r["n"]
        c["misleading"] += r["n_misleading"]
        c["defective"] += r["n_defective"]
        for b in r["bullets"]:
            if b["reader_misled"]:
                by_where[b["where"]] += 1
                for tag in b["tags"]:
                    by_tag[tag] += 1
    lo, hi = wilson(mis, n)
    return {
        "records": len(ok), "records_failed": len(rows) - len(ok), "bullets": n,
        "misleading": mis, "misleading_share": round(mis / n, 4) if n else 0,
        "misleading_ci95": [round(lo, 4), round(hi, 4)],
        "defective": de, "defective_share": round(de / n, 4) if n else 0,
        "records_with_misleading": sum(1 for r in ok if r["n_misleading"]),
        "by_where": dict(by_where), "by_tag": dict(by_tag.most_common()),
        "by_country": dict(sorted(by_country.items())),
    }


def compare(a_path: Path, b_path: Path) -> dict:
    a = json.loads(a_path.read_text(encoding="utf-8"))
    b = json.loads(b_path.read_text(encoding="utf-8"))
    ra = {r["slug"]: r for r in a["records"] if r.get("status") == "ok"}
    rb = {r["slug"]: r for r in b["records"] if r.get("status") == "ok"}
    common = sorted(set(ra) & set(rb))
    def _s(rs):
        n = sum(rs[s]["n"] for s in common)
        m = sum(rs[s]["n_misleading"] for s in common)
        lo, hi = wilson(m, n)
        return {"bullets": n, "misleading": m, "share": round(m / n, 4) if n else 0, "ci95": [round(lo, 4), round(hi, 4)],
                "records_with_misleading": sum(1 for s in common if rs[s]["n_misleading"])}
    better = sum(1 for s in common if rb[s]["n_misleading"] < ra[s]["n_misleading"])
    worse = sum(1 for s in common if rb[s]["n_misleading"] > ra[s]["n_misleading"])
    return {"paired_records": len(common), "before": _s(ra), "after": _s(rb),
            "records_improved": better, "records_worse": worse,
            "records_same": len(common) - better - worse,
            "worse_slugs": [s for s in common if rb[s]["n_misleading"] > ra[s]["n_misleading"]]}


def emit_feedback(rows: list[dict], out_dir: Path, *, lang: str) -> int:
    """Write the misleading verdicts in the review-evidence shape
    `scripts/build_terroir_feedback.py` reads (`confirmed-misleading.json`
    rows + a `merged.json` with empty record notes), so the next extraction
    of each record sees them as do-not-claim constraints. Only verdicts
    the grader marked reader-misleading; `mode` is the first tag."""
    out_dir.mkdir(parents=True, exist_ok=True)
    misleading = []
    for r in rows:
        if r.get("status") != "ok":
            continue
        for b in r["bullets"]:
            if not b["reader_misled"]:
                continue
            misleading.append({
                "id": f"{r['slug']}#{b['i']}", "slug": r["slug"], "i": b["i"], "country": r["country"],
                "subsection": b.get("subsection") or "", "mode": (b["tags"] or ["other"])[0],
                "where": b["where"] if b["where"] in ("extraction", "translation", "both") else "extraction",
                "severity": "high", "en" if lang == "en" else lang: b["bullet"], "src": b["src"],
                "reason": b["reason"], "corrected_en": b["corrected"],
            })
    (out_dir / "confirmed-misleading.json").write_text(json.dumps(misleading, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out_dir / "merged.json").write_text(json.dumps({"record_notes": {}}, indent=1) + "\n", encoding="utf-8")
    return len(misleading)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", default="anthropic", choices=("anthropic", "mistral", "ollama"))
    ap.add_argument("--model", default=DEFAULT_GRADER)
    ap.add_argument("--thinking", default=None, choices=("disabled", "adaptive"),
                    help="anthropic thinking mode (default: the audit stage default, adaptive)")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--sample", type=int, default=100)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--only", action="append", default=None)
    ap.add_argument("--slugs-file", default=None, help="JSON list of slugs to grade (overrides --sample)")
    ap.add_argument("--country", action="append", default=None)
    ap.add_argument("--from-backup", default=None, metavar="RUN", help="grade the pre-run state of the sample")
    ap.add_argument("--batch", action="store_true")
    ap.add_argument("--report", default=None)
    ap.add_argument("--compare", nargs=2, metavar=("A", "B"), default=None)
    ap.add_argument("--emit-feedback", default=None, metavar="DIR",
                    help="also write the misleading verdicts as a review-evidence dir "
                         "(confirmed-misleading.json + merged.json) for scripts/build_terroir_feedback.py")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if args.compare:
        print(json.dumps(compare(Path(args.compare[0]), Path(args.compare[1])), ensure_ascii=False, indent=2))
        return 0

    # Sample from the records that have facts today (so before / after share a frame).
    candidates: list[str] = []
    for p in sorted(TERROIR.glob("*.json")):
        if p.name.startswith("manifest"):
            continue
        d = cache.read_json_or_none(p)
        if not d or d.get("mode") == "verbatim" or not d.get("facts"):
            continue
        if args.country and (d.get("country") or "fr") not in set(args.country):
            continue
        candidates.append(p.stem)
    if args.slugs_file:
        wanted = json.loads(Path(args.slugs_file).read_text(encoding="utf-8"))
        wanted = wanted.get("slugs") if isinstance(wanted, dict) else wanted
        slugs = [s for s in wanted if s in set(candidates)]
    elif args.only:
        slugs = [s for s in candidates if s in set(args.only)]
    else:
        random.seed(args.seed)
        slugs = sorted(random.sample(candidates, min(args.sample, len(candidates))))
    items: list[tuple[str, dict, dict]] = []
    skipped: Counter = Counter()
    for slug in slugs:
        loaded = load_record(slug, args.lang, args.from_backup)
        if isinstance(loaded, str):
            skipped[loaded] += 1
            continue
        items.append((slug, *loaded))
    log(f"{len(items)} records to grade (skipped {dict(skipped)}); state={'backup ' + args.from_backup if args.from_backup else 'live'}; lang={args.lang}")
    if not items:
        return 1
    resolver = SourceResolver()
    t0 = time.monotonic()
    rows: list[dict] = []
    if args.batch:
        model_id = args.model

        def run_loop(prov):
            nonlocal rows
            rows = grade(prov, model_id, items, resolver, lang=args.lang, quiet=True)

        # One sidecar per graded state: a "before" batch still in flight must
        # not be resumed by an "after" run.
        sidecar = BATCH_SIDECAR.with_name(f"llm-audit-{args.from_backup or 'live'}-{args.lang}.json")
        batch.run_two_pass(provider=args.provider, model=model_id, sidecar=sidecar, run_loop=run_loop,
                           thinking=args.thinking or batch.default_thinking(args.provider, stage="audit"))
    else:
        provider, model_id = providers.make_provider(args.provider, model=args.model, stage="audit",
                                                    thinking=args.thinking)
        rows = grade(provider, model_id, items, resolver, lang=args.lang, quiet=args.quiet)
    summary = summarize(rows)
    summary.update({"model": model_id, "lang": args.lang, "state": args.from_backup or "live",
                    "seed": args.seed, "elapsed_seconds": round(time.monotonic() - t0, 1),
                    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "skipped": dict(skipped)})
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    report = Path(args.report) if args.report else REPORT_DIR / f"llm-audit-{stamp}.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"summary": summary, "records": rows}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), file=sys.stderr)
    log(f"report → {report}")
    if args.emit_feedback:
        n = emit_feedback(rows, Path(args.emit_feedback), lang=args.lang)
        log(f"feedback evidence ({n} misleading bullets) → {args.emit_feedback}; merge with "
            f"scripts/build_terroir_feedback.py --evidence {args.emit_feedback} --review-id llm-audit-{stamp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
