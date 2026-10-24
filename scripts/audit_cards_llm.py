#!/usr/bin/env python3
"""Independent LLM reading of the whole appellation card against its
sources — the `/validate-cards` validator (docs/plan-validators.md § 2).

For each record the judge receives the card exactly as a reader sees it in
one locale (the server-rendered card as plain text plus its structured
fields — `_lib/card_packet.py`) and every source document behind it: the
regulator's text section by section, the national-spec and EU-register
sidecars where the country has them, and the Wikipedia page stage 02b
fetched. It never sees the pipeline's grounding quotes, prompts or gate
verdicts, and it runs on a different model family from the extractor
(`providers.STAGE_DEFAULTS["audit"]`, Opus; the extractor is Sonnet) — so
the measure is independent of the machinery it measures.

Per card section (name, classification, region, styles, grapes, area,
terroir facts, summary, sub-denomination relation, sources) it reports:

  error        the card states what a document contradicts;
  omission     a document states it prominently and the card lacks it;
  unsupported  the card states what no document states;
  stale        the documents disagree with each other on a dated point.

Each finding carries a severity (misleads / defective / cosmetic), a
failure-mode tag, the card's claim, a verbatim quote from a numbered
document and a one-line fix. Every quote is re-checked against the
documents with the terroir-coverage matcher: a quote that does not ground
(< 0.6) marks the finding `verified: false` — a judge's evidence is not
trusted on its word either.

Read-only: writes a JSON report (and optionally review-evidence / curator
rows), never a cache. `--compare A B` prints the paired before / after.

Usage:
  .venv/bin/python scripts/audit_cards_llm.py --only rioja-rioja-alta --only pauillac
  .venv/bin/python scripts/audit_cards_llm.py --sample 200 --batch
  .venv/bin/python scripts/audit_cards_llm.py --top-viewed 100 --batch --locale fr
  .venv/bin/python scripts/audit_cards_llm.py --slugs-file changed.json --batch --emit-curator-md tmp/validation/cards-rows.md
  .venv/bin/python scripts/audit_cards_llm.py --compare before.json after.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from rapidfuzz import fuzz
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import batch, card_packet, llm_json, providers  # noqa: E402
from _lib.env import load_dotenv  # noqa: E402
from _lib.prompt_cache import mark_cached  # noqa: E402
from _lib.terroir_coverage import SourceMatcher  # noqa: E402

DEFAULT_JUDGE = providers.stage_default("audit")[0]
REPORT_DIR = ROOT / "tmp" / "validation"
BATCH_SIDECAR = ROOT / "raw" / ".batch" / "cards-llm.json"
MAX_TOKENS = 8000
GROUNDING_MIN = 0.6
MAX_FINDINGS = 25

SECTIONS = ("name", "classification", "region", "styles", "grapes", "area", "terroir_facts",
            "summary", "sub_denomination", "sources", "other")
KINDS = ("error", "omission", "unsupported", "stale")
SEVERITIES = ("misleads", "defective", "cosmetic")
TAGS = (
    # the bullet-level catalogue of audit_terroir_facts_llm.py
    "wrong-entity", "unsupported-causal-link", "invented-detail", "wrong-number-or-unit",
    "wrong-direction", "hedge-dropped-or-changed", "sibling-or-subzone-confusion",
    "narrowed-attribution", "added-qualifier", "mistranslation", "untranslated-term",
    "label-fragment", "duplicate", "misfiled-subsection", "tautology",
    # header / roster / style / area
    "wrong-role", "missing-grape", "extra-grape", "wrong-grape-identity", "missing-style",
    "extra-style", "wrong-region", "wrong-scheme", "wrong-name", "area-mismatch",
    "sibling-leak", "stub-shown-as-content", "source-not-cited", "source-vintage", "other",
)

SYSTEM = """You are the independent validator of Open Wine Map, a reference map of Europe's protected wine appellations built mechanically from the regulators' own specifications (cahier des charges, pliego de condiciones, disciplinare, Einziges Dokument, EU single document, national product specification). For ONE appellation you receive the CARD exactly as a reader sees it, its structured FIELDS, and the numbered SOURCE DOCUMENTS the card was built from. You have NOT seen how the card was produced. Your job: find everything a reader of this card would come to believe that the documents contradict or do not support, and everything the documents state prominently that the card leaves out.

Grade these card sections: name, classification, region, styles, grapes, area, terroir_facts, summary, sub_denomination, sources, other.

For each defect return one finding:
- section: one of the sections above.
- kind: "error" (the card states what a document contradicts), "omission" (a document states it prominently — a variety in the roster, a wine category or colour the GI covers, a restriction such as a sub-denomination reserved to one colour — and the card lacks it), "unsupported" (the card states what no document states), or "stale" (two documents disagree on a dated point — a roster, a commune list, a date — and the card follows the older one).
- severity: "misleads" (a reader would believe something false: a wrong variety, role, colour, region, scheme, number, entity, causal link, a sibling zone's statement presented as this one's), "defective" (a real defect that does not mislead: a clumsy or untranslated term, a duplicate, a label fragment, a cosmetic omission), or "cosmetic".
- tag: one of {tags}.
- claim: what the card says, or lacks, in at most 200 characters.
- evidence: a VERBATIM quote (at most 300 characters, in the document's own language) from the document that decides the finding, and "document": its number. For an "unsupported" finding quote the closest passage, or leave evidence empty if the documents say nothing at all.
- fix: one line, what the card should say instead.

Rules of the house you must respect (these are NOT defects):
- Grape pills show the regulator's own spelling, with the VIVC prime name in brackets when it differs — "Macabeo (Viura)", "Mazuela (Carignan Noir)". A spelling or a colour code the regulator used is not an error.
- Principal / accessory follow the regulator's roles; where the regulator splits no roles, every variety is shown as principal — that is the convention, not an omission, and no note is owed for it. Where only the EU register fiche technique splits MAIN / OTHER and the national specification the card follows lists its varieties without roles, report the flattening once as `defective` (tag wrong-role), never as misleading.
- Style pills are nodes of one taxonomy, parent and leaf shown together ("Sparkling · Quality Sparkling · Traditional Method" is one category rendered at three depths, not a duplicate); the buckets are coarse (red, white, rosé, sparkling, sweet, fortified, …) for the GI as a whole, derived from the wine categories and colours the documents list. A missing bucket the documents clearly list (sweet wines, a rosé) IS an omission.
- A sub-denomination (DGC, subzona, sottozona, sub-região, Einzellage, cru) inherits its parent's roster, styles and terroir facts unless the regulator singles it out; the card says so ("Sub-region of …", "These highlights describe the wider … appellation"). An inherited fact that describes ANOTHER sibling sub-zone as if it were this one IS a defect (tag sibling-leak, misleads).
- The terroir facts are an LLM's summary of the terroir-link section, machine-translated; a simplification is fine, a hedge dropped, a cause invented, a number changed, an entity swapped or a neighbouring zone's statement is not. A fact marked "via Wikipedia" is legitimately grounded on the Wikipedia document.
- "About this boundary" lines are disclosures of what the polygon is; they are not claims about the delimitation and are never defects.
- The card locale may differ from the regulator's language; names, communes and regulator terms stay in the source language by design.
- A STUB card (said in KNOWN) shows the catalogue entry only; do not report its emptiness as omissions.
- Things listed under KNOWN are already on file: do not re-report them.

Be strict and specific, quote the decisive words, and default to NO finding when the documents do not settle the point. Prefer few sharp findings over many weak ones; at most {max_findings}.

Answer ONLY with JSON, nothing before or after:
{{"verdict": "trust|caution|do-not-trust", "summary": "one sentence on the card's reliability", "findings": [{{"section": "grapes", "kind": "omission", "severity": "misleads", "tag": "missing-grape", "claim": "", "evidence": "", "document": 0, "fix": ""}}]}}
"verdict" is "trust" with no misleading finding, "caution" with one or two, "do-not-trust" with more or with a wrong name / scheme / roster."""


def log(msg: str) -> None:
    print(f"[cards-llm] {msg}", file=sys.stderr)


# ────────────────────────────────────────────────────────── selection ──


def candidates(locale: str, *, countries: list[str] | None, include_stubs: bool,
               wine_only: bool) -> list[tuple[str, dict]]:
    aocs, _ = card_packet.load_startup(locale)
    out = []
    for slug, rec in aocs.items():
        if countries and rec.get("country") not in set(countries):
            continue
        if wine_only and rec.get("is_wine") is False:
            continue
        out.append((slug, rec))
    if not include_stubs:
        # A stub with an augmented roster or facts (the national-spec layers
        # leave `is_stub` on the on-disk record) is a card worth grading;
        # only the empty catalogue entry is left out.
        keep = []
        for slug, rec in out:
            payload = card_packet.load_payload(locale, slug) or {}
            has_content = bool(rec.get("grapes_principal") or rec.get("grapes_accessory")
                               or (payload.get("terroir_facts") or {}).get("facts"))
            if not payload.get("is_stub") or has_content:
                keep.append((slug, rec))
        out = keep
    return out


def stratified_sample(cands: list[tuple[str, dict]], n: int, seed: int) -> list[str]:
    """Round-robin over (country, geom_source) strata so a sample of 100 is
    not 60 French parcellaire records."""
    rnd = random.Random(seed)
    strata: dict[tuple, list[str]] = defaultdict(list)
    for slug, rec in cands:
        strata[(rec.get("country"), (rec.get("geom_source") or "").split(":")[0])].append(slug)
    for v in strata.values():
        rnd.shuffle(v)
    keys = sorted(strata)
    rnd.shuffle(keys)
    picked: list[str] = []
    while len(picked) < n and any(strata[k] for k in keys):
        for k in keys:
            if strata[k] and len(picked) < n:
                picked.append(strata[k].pop())
    return sorted(picked)


def top_viewed(n: int, *, site: str, date_range: str) -> list[str]:
    """The n most-opened appellations in Plausible (`Appellation Viewed`
    by slug) — the top-200 review's frame."""
    from _lib.env import load_dotenv, plausible_host
    load_dotenv()
    key = os.environ.get("PLAUSIBLE_API_KEY")
    if not key:
        sys.exit("--top-viewed needs PLAUSIBLE_API_KEY in the environment or .env")
    import feedback_report as fr
    rows = fr.goal_rows(plausible_host(), key, site, fr.parse_range(date_range), fr.VIEWED,
                        ["event:props:slug"])
    ranked = sorted(((dims[0], count) for dims, count in rows if dims and dims[0]), key=lambda x: -x[1])
    return [s for s, _ in ranked[:n]]


# ─────────────────────────────────────────────────────────── grading ──


def system_prompt(section: str | None) -> str:
    s = SYSTEM.replace("{tags}", ", ".join(TAGS)).replace("{max_findings}", str(MAX_FINDINGS))
    if section:
        s += f"\n\nThis run grades ONLY the card section \"{section}\": report findings for it alone."
    return s


def parse_reply(raw: str) -> dict | None:
    s = llm_json.strip_fences(raw or "")
    data = None
    try:
        data = json.loads(s)
    except ValueError:
        m = re.search(r"\{.*\}", s, re.S)
        if m:
            try:
                data = json.loads(m.group(0))
            except ValueError:
                data = None
    if not isinstance(data, dict):
        return None
    rows = data.get("findings")
    if not isinstance(rows, list):
        return None
    findings = []
    for r in rows[:MAX_FINDINGS]:
        if not isinstance(r, dict):
            continue
        section = str(r.get("section") or "other").lower()
        kind = str(r.get("kind") or "").lower()
        sev = str(r.get("severity") or "").lower()
        if kind not in KINDS or sev not in SEVERITIES:
            continue
        tag = str(r.get("tag") or "other")
        try:
            doc = int(r.get("document")) if r.get("document") is not None else None
        except (TypeError, ValueError):
            doc = None
        findings.append({
            "section": section if section in SECTIONS else "other", "kind": kind, "severity": sev,
            "tag": tag if tag in TAGS else "other",
            "claim": " ".join(str(r.get("claim") or "").split())[:300],
            "evidence": " ".join(str(r.get("evidence") or "").split())[:400],
            "document": doc,
            "fix": " ".join(str(r.get("fix") or "").split())[:400],
        })
    verdict = str(data.get("verdict") or "").lower()
    if verdict not in ("trust", "caution", "do-not-trust"):
        n_mis = sum(1 for f in findings if f["severity"] == "misleads")
        verdict = "trust" if not n_mis else ("caution" if n_mis <= 2 else "do-not-trust")
    return {"verdict": verdict, "summary": " ".join(str(data.get("summary") or "").split())[:400],
            "findings": findings}


def ground(findings: list[dict], documents: list[dict]) -> None:
    """Score every quote against the document it names (else all of them);
    a quote below GROUNDING_MIN leaves the finding `verified: false`."""
    matchers: dict[int, SourceMatcher] = {}
    all_text = "\n".join(d["text"] for d in documents)
    all_m = SourceMatcher(all_text) if all_text else None
    for f in findings:
        q = f.get("evidence") or ""
        if not q:
            f["grounding"] = None
            f["verified"] = f["kind"] == "unsupported"
            continue
        m = None
        if f.get("document") is not None and 0 <= f["document"] < len(documents):
            m = matchers.setdefault(f["document"], SourceMatcher(documents[f["document"]]["text"]))
        score = m.coverage(q) if m else 0.0
        if score < GROUNDING_MIN and all_m is not None:
            score = max(score, all_m.coverage(q))
        f["grounding"] = round(score, 3)
        f["verified"] = score >= GROUNDING_MIN


def grade(provider, items: list[tuple[str, dict]], *, section: str | None, quiet: bool) -> list[dict]:
    rows: list[dict] = []
    system = mark_cached(system_prompt(section))
    for slug, packet in tqdm(items, desc="cards-llm", leave=False, disable=quiet):
        user = card_packet.packet_user_message(packet)
        try:
            raw = provider.chat(system=system, user=user, max_tokens=MAX_TOKENS)
        except Exception as e:  # noqa: BLE001
            rows.append({"slug": slug, "country": packet["country"], "status": "error", "error": str(e)[:200]})
            continue
        parsed = parse_reply(raw)
        if parsed is None:
            rows.append({"slug": slug, "country": packet["country"], "status": "parse_error", "raw": (raw or "")[:500]})
            continue
        if section:
            parsed["findings"] = [f for f in parsed["findings"] if f["section"] == section]
        ground(parsed["findings"], packet["documents"])
        n_mis = sum(1 for f in parsed["findings"] if f["severity"] == "misleads" and f["verified"])
        rows.append({
            "slug": slug, "country": packet["country"], "locale": packet["locale"], "status": "ok",
            "name": packet["card"].get("name"), "geom_source": packet["card"].get("geom_source"),
            "is_sub_denomination": packet["card"].get("is_sub_denomination"),
            "verdict": parsed["verdict"], "summary": parsed["summary"],
            "n_findings": len(parsed["findings"]), "n_misleads": n_mis,
            "n_unverified": sum(1 for f in parsed["findings"] if not f["verified"]),
            "card_sha": packet["card_sha"], "documents_sha": packet["documents_sha"],
            "documents": [{"kind": d["kind"], "label": d["label"], "url": d["url"], "chars": d["chars"]}
                          for d in packet["documents"]],
            "findings": parsed["findings"],
        })
        if not quiet:
            log(f"{slug:40} {packet['country']:2} verdict={parsed['verdict']:12} findings={len(parsed['findings']):2} misleads={n_mis}")
    return rows


# ──────────────────────────────────────────────────────────── reports ──


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
    n = len(ok)
    with_mis = sum(1 for r in ok if r["n_misleads"])
    lo, hi = wilson(with_mis, n)
    by_section: Counter = Counter()
    by_kind: Counter = Counter()
    by_tag: Counter = Counter()
    by_country: dict[str, dict] = {}
    for r in ok:
        c = by_country.setdefault(r["country"], {"records": 0, "with_misleads": 0, "findings": 0, "misleads": 0})
        c["records"] += 1
        c["with_misleads"] += 1 if r["n_misleads"] else 0
        c["findings"] += r["n_findings"]
        c["misleads"] += r["n_misleads"]
        for f in r["findings"]:
            if f["severity"] == "misleads" and f["verified"]:
                by_section[f["section"]] += 1
                by_kind[f["kind"]] += 1
                by_tag[f["tag"]] += 1
    return {
        "records": n, "records_failed": len(rows) - n,
        "records_with_misleads": with_mis, "share_with_misleads": round(with_mis / n, 4) if n else 0,
        "share_ci95": [round(lo, 4), round(hi, 4)],
        "findings": sum(r["n_findings"] for r in ok), "misleads": sum(r["n_misleads"] for r in ok),
        "unverified": sum(r["n_unverified"] for r in ok),
        "verdicts": dict(Counter(r["verdict"] for r in ok)),
        "by_section": dict(by_section.most_common()), "by_kind": dict(by_kind.most_common()),
        "by_tag": dict(by_tag.most_common()), "by_country": dict(sorted(by_country.items())),
    }


def compare(a_path: Path, b_path: Path) -> dict:
    a = json.loads(a_path.read_text(encoding="utf-8"))
    b = json.loads(b_path.read_text(encoding="utf-8"))
    ra = {r["slug"]: r for r in a["records"] if r.get("status") == "ok"}
    rb = {r["slug"]: r for r in b["records"] if r.get("status") == "ok"}
    common = sorted(set(ra) & set(rb))

    def _s(rs):
        k = sum(1 for s in common if rs[s]["n_misleads"])
        lo, hi = wilson(k, len(common))
        return {"records_with_misleads": k, "share": round(k / len(common), 4) if common else 0,
                "ci95": [round(lo, 4), round(hi, 4)], "misleads": sum(rs[s]["n_misleads"] for s in common)}
    better = [s for s in common if rb[s]["n_misleads"] < ra[s]["n_misleads"]]
    worse = [s for s in common if rb[s]["n_misleads"] > ra[s]["n_misleads"]]
    return {"paired_records": len(common), "before": _s(ra), "after": _s(rb),
            "records_improved": len(better), "records_worse": len(worse),
            "records_same": len(common) - len(better) - len(worse), "worse_slugs": worse}


def markdown_report(summary: dict, rows: list[dict], *, title: str) -> str:
    out = [f"# {title}", "",
           f"Records graded: {summary['records']} (failed {summary['records_failed']}) · "
           f"with a verified misleading finding: {summary['records_with_misleads']} "
           f"({summary['share_with_misleads'] * 100:.1f} %, Wilson 95 % "
           f"{summary['share_ci95'][0] * 100:.1f}–{summary['share_ci95'][1] * 100:.1f} %) · "
           f"findings {summary['findings']}, misleading {summary['misleads']}, unverified quotes {summary['unverified']}.",
           "", "| section | misleading |", "|---|---:|"]
    out += [f"| {k} | {v} |" for k, v in summary["by_section"].items()]
    out += ["", "| tag | misleading |", "|---|---:|"]
    out += [f"| {k} | {v} |" for k, v in summary["by_tag"].items()]
    out += ["", "| country | records | with misleads | findings |", "|---|---:|---:|---:|"]
    out += [f"| {c} | {v['records']} | {v['with_misleads']} | {v['findings']} |" for c, v in summary["by_country"].items()]
    out += ["", "## Records with findings", ""]
    for r in sorted((r for r in rows if r.get("status") == "ok" and r["n_findings"]),
                    key=lambda r: (-r["n_misleads"], r["slug"])):
        out.append(f"### {r['name']} (`{r['slug']}`, {r['country']}) — {r['verdict']}")
        if r.get("summary"):
            out.append(f"_{r['summary']}_")
        out += ["", "| section | kind | severity | tag | claim | evidence | fix | verified |", "|---|---|---|---|---|---|---|---|"]
        for f in r["findings"]:
            cell = lambda s: (s or "").replace("|", "\\|").replace("\n", " ")  # noqa: E731
            out.append(f"| {f['section']} | {f['kind']} | {f['severity']} | {f['tag']} | {cell(f['claim'])} | {cell(f['evidence'])} | {cell(f['fix'])} | {'yes' if f['verified'] else 'NO'} |")
        out.append("")
    failed = [r for r in rows if r.get("status") != "ok"]
    if failed:
        out += ["## Not graded", ""] + [f"- `{r['slug']}`: {r['status']} {r.get('error', '')}" for r in failed]
    return "\n".join(out) + "\n"


def curator_rows(rows: list[dict]) -> str:
    """CURATOR_TODO rows for the header / roster / style / area findings
    (the fact findings go to the feedback sidecars instead), grouped by
    country, one failure mode per row with the sweep still to do."""
    by_country: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        if r.get("status") != "ok":
            continue
        for f in r["findings"]:
            if f["section"] in ("terroir_facts",) or not f["verified"] or f["severity"] == "cosmetic":
                continue
            cell = lambda s: (s or "").replace("|", "\\|")  # noqa: E731
            by_country[r["country"]].append(
                f"| ❌ | `{r['slug']}` | {f['section']} · {f['kind']} · {f['tag']} | {cell(f['claim'])} | {cell(f['evidence'][:160])} | {cell(f['fix'])} | sweep: same {f['tag']} in {r['country']} |")
    out = []
    for cc in sorted(by_country):
        out += [f"### {cc.upper()} — validate-cards findings", "",
                "| | slug | finding | claim | evidence | fix | isolated or broader? |", "|---|---|---|---|---|---|---|"]
        out += by_country[cc] + [""]
    return "\n".join(out)


def emit_feedback(rows: list[dict], packets: dict[str, dict], out_dir: Path, *, locale: str) -> int:
    """The verified misleading terroir-fact findings in the review-evidence
    shape `scripts/build_terroir_feedback.py` reads, so the next extraction
    sees them as do-not-claim constraints. The bullet index is recovered by
    matching the finding's claim to the card's bullets; `owner` names the
    record whose cache the card's facts come from (a sub-denomination shows
    its parent's) and `locale` the language of the card bullet — the builder
    files the row under the owner and recovers its source-language bullet."""
    out_dir.mkdir(parents=True, exist_ok=True)
    misleading = []
    for r in rows:
        if r.get("status") != "ok":
            continue
        card = (packets.get(r["slug"]) or {}).get("card", {})
        facts = card.get("terroir_facts") or []
        owner = card.get("facts_inherited_from") or r["slug"]
        for f in r["findings"]:
            if f["section"] != "terroir_facts" or f["severity"] != "misleads" or not f["verified"]:
                continue
            best_i, best = None, 0
            for i, fact in enumerate(facts):
                sc = fuzz.token_set_ratio(f["claim"], fact.get("bullet") or "")
                if sc > best:
                    best_i, best = i, sc
            if best_i is None or best < 60:
                continue
            misleading.append({
                "id": f"{r['slug']}#{best_i}", "slug": r["slug"], "owner": owner, "locale": locale,
                "i": best_i, "country": r["country"],
                "subsection": facts[best_i].get("subsection") or "", "mode": f["tag"],
                "where": "extraction", "severity": "high", locale: facts[best_i].get("bullet") or "",
                "src": "", "reason": f"{f['claim']} — evidence: {f['evidence']}", "corrected_en": f["fix"],
            })
    (out_dir / "confirmed-misleading.json").write_text(json.dumps(misleading, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out_dir / "merged.json").write_text(json.dumps({"record_notes": {}}, indent=1) + "\n", encoding="utf-8")
    return len(misleading)


def estimate_usd(items: list[tuple[str, dict]], model: str, *, system_chars: int, batch_mode: bool) -> float | None:
    prices = batch.BATCH_PRICES_USD_PER_M.get(model)
    if not prices:
        return None
    inp, outp = prices
    if not batch_mode:
        inp, outp = inp * 2, outp * 2
    tokens_in = sum((len(card_packet.packet_user_message(p)) + system_chars) / 3.5 for _, p in items)
    tokens_out = 1500 * len(items)
    return tokens_in / 1e6 * inp + tokens_out / 1e6 * outp


# ─────────────────────────────────────────────────────────────── main ──


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", default="anthropic", choices=("anthropic", "mistral", "ollama"))
    ap.add_argument("--model", default=DEFAULT_JUDGE)
    ap.add_argument("--thinking", default=None, choices=("disabled", "adaptive"))
    ap.add_argument("--locale", default="en", choices=card_packet.LOCALES)
    ap.add_argument("--sample", type=int, default=50)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--only", action="append", default=None)
    ap.add_argument("--slugs-file", default=None, help="JSON list of slugs (or {slugs: [...]})")
    ap.add_argument("--country", action="append", default=None)
    ap.add_argument("--top-viewed", type=int, default=0, metavar="N", help="the N most-opened cards in Plausible")
    ap.add_argument("--site", default="openwinemap.com")
    ap.add_argument("--range", default="all", help="Plausible period for --top-viewed")
    ap.add_argument("--include-stubs", action="store_true")
    ap.add_argument("--all-products", action="store_true", help="include spirits and ciders (default: wine only)")
    ap.add_argument("--section", default=None, choices=SECTIONS, help="grade one card section only")
    ap.add_argument("--max-source-chars", type=int, default=card_packet.MAX_SOURCE_CHARS)
    ap.add_argument("--batch", action="store_true")
    ap.add_argument("--second-opinion", default=None, metavar="MODEL",
                    help="re-grade the records with a verified misleading finding on this model")
    ap.add_argument("--max-usd", type=float, default=25.0, help="refuse a run whose estimate exceeds this (0 = no ceiling)")
    ap.add_argument("--yes", action="store_true", help="run even above --max-usd")
    ap.add_argument("--report", default=None)
    ap.add_argument("--md", default=None, help="Markdown summary path (default: next to the report)")
    ap.add_argument("--emit-feedback", default=None, metavar="DIR")
    ap.add_argument("--emit-curator-md", default=None, metavar="PATH")
    ap.add_argument("--compare", nargs=2, metavar=("A", "B"), default=None)
    ap.add_argument("--dry-run", action="store_true", help="build the packets and print the estimate only")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    load_dotenv()  # the synchronous provider reads the key from the environment

    if args.compare:
        print(json.dumps(compare(Path(args.compare[0]), Path(args.compare[1])), ensure_ascii=False, indent=2))
        return 0

    cands = candidates(args.locale, countries=args.country, include_stubs=args.include_stubs,
                       wine_only=not args.all_products)
    if not cands:
        sys.exit("no records: is the site built (wiki/data/aocs.<locale>.*.js)?")
    cand_set = {s for s, _ in cands}
    if args.slugs_file:
        wanted = json.loads(Path(args.slugs_file).read_text(encoding="utf-8"))
        wanted = wanted.get("slugs") if isinstance(wanted, dict) else wanted
        slugs = [s for s in wanted if s in cand_set]
    elif args.only:
        slugs = [s for s in args.only if s in cand_set]
        missing = [s for s in args.only if s not in cand_set]
        if missing:
            log(f"not in the candidate set (stub, non-wine or unknown): {missing}")
    elif args.top_viewed:
        slugs = [s for s in top_viewed(args.top_viewed * 2, site=args.site, date_range=args.range) if s in cand_set][:args.top_viewed]
    else:
        slugs = stratified_sample(cands, args.sample, args.seed)

    items: list[tuple[str, dict]] = []
    for slug in slugs:
        p = card_packet.build_packet(args.locale, slug, max_source_chars=args.max_source_chars)
        if p is None or not p["documents"]:
            log(f"{slug}: no packet (no documents) — skipped")
            continue
        items.append((slug, p))
    if not items:
        return 1
    system_chars = len(system_prompt(args.section))
    est = estimate_usd(items, args.model, system_chars=system_chars, batch_mode=args.batch)
    chars = sum(len(card_packet.packet_user_message(p)) for _, p in items)
    log(f"{len(items)} records · locale {args.locale} · model {args.model} · {chars / 1e6:.1f} M chars"
        + (f" · estimate ≈ ${est:.2f}" if est is not None else " · no price for this model"))
    if args.dry_run:
        for slug, p in items:
            print(json.dumps({"slug": slug, "country": p["country"], "card_chars": len(p["card_text"]),
                              "documents": [(d["kind"], d["chars"]) for d in p["documents"]]}))
        return 0
    if est is not None and args.max_usd and est > args.max_usd and not args.yes:
        sys.exit(f"estimate ${est:.2f} exceeds --max-usd {args.max_usd}; pass --yes to run anyway")

    t0 = time.monotonic()
    rows: list[dict] = []

    def run(model: str, subset: list[tuple[str, dict]], sidecar_tag: str) -> list[dict]:
        if args.batch:
            out: list[dict] = []

            def run_loop(prov):
                nonlocal out
                out = grade(prov, subset, section=args.section, quiet=True)
            sidecar = BATCH_SIDECAR.with_name(f"cards-llm-{sidecar_tag}-{args.locale}.json")
            batch.run_two_pass(provider=args.provider, model=model, sidecar=sidecar, run_loop=run_loop,
                               thinking=args.thinking or batch.default_thinking(args.provider, stage="audit"))
            return out
        provider, _ = providers.make_provider(args.provider, model=model, stage="audit", thinking=args.thinking)
        return grade(provider, subset, section=args.section, quiet=args.quiet)

    rows = run(args.model, items, "first")
    second = None
    if args.second_opinion:
        flagged = {r["slug"] for r in rows if r.get("status") == "ok" and r["n_misleads"]}
        subset = [(s, p) for s, p in items if s in flagged]
        if subset:
            log(f"second opinion on {len(subset)} records with {args.second_opinion}")
            second = run(args.second_opinion, subset, "second")
            by_slug = {r["slug"]: r for r in second}
            for r in rows:
                s = by_slug.get(r["slug"])
                if s and s.get("status") == "ok":
                    r["second_opinion"] = {"model": args.second_opinion, "verdict": s["verdict"],
                                           "n_misleads": s["n_misleads"], "findings": s["findings"]}
                    agreed = []
                    for f in r["findings"]:
                        f["second_agrees"] = any(
                            g["section"] == f["section"] and fuzz.token_set_ratio(g["claim"], f["claim"]) >= 60
                            for g in s["findings"])
                        if f["second_agrees"]:
                            agreed.append(f)
                    r["n_misleads_agreed"] = sum(1 for f in agreed if f["severity"] == "misleads" and f["verified"])

    summary = summarize(rows)
    summary.update({"model": args.model, "second_opinion": args.second_opinion, "locale": args.locale,
                    "section": args.section, "seed": args.seed,
                    "estimate_usd": round(est, 2) if est is not None else None,
                    "elapsed_seconds": round(time.monotonic() - t0, 1),
                    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    report = Path(args.report) if args.report else REPORT_DIR / f"cards-{stamp}.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"summary": summary, "records": rows}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    md = Path(args.md) if args.md else report.with_suffix(".md")
    md.write_text(markdown_report(summary, rows, title=f"validate-cards — {stamp} ({args.locale}, {args.model})"), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), file=sys.stderr)
    log(f"report → {report}\nmarkdown → {md}")
    packets = dict(items)
    if args.emit_feedback:
        n = emit_feedback(rows, packets, Path(args.emit_feedback), locale=args.locale)
        log(f"feedback evidence ({n} misleading fact findings) → {args.emit_feedback}; merge with "
            f"scripts/build_terroir_feedback.py --evidence {args.emit_feedback} --review-id cards-{stamp}")
    if args.emit_curator_md:
        Path(args.emit_curator_md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.emit_curator_md).write_text(curator_rows(rows), encoding="utf-8")
        log(f"curator rows → {args.emit_curator_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
