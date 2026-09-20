"""The claim-support gate over stage-02d terroir facts (review
2026-09-12, R2 / R3 / R7 / R8).

Stage 02d's coverage test only checks that a bullet's *quote* exists in
the source; it never checks that the bullet's *claim* is what the quote
says. Every failure mode the review verified — an unsupported causal
link, a wrong entity, an invented qualifier, a dropped hedge, a sibling
sub-zone presented as the whole, a narrowed attribution — passes it. The
gate asks a model, per record, to grade each bullet against the full
source text (the exact text 02d graded against, via
`terroir_sources`) plus the record's review feedback, and applies the
verdicts deterministically:

  supported   kept as is
  rewrite     the main fact holds but a qualifier / causal wrapper /
              hedge goes beyond the source → the bullet is replaced by
              the model's rewrite, which may only remove or soften
              (guarded: no new numbers, no arrows, sane length)
  drop        the main claim is unsupported, contradicted, about another
              appellation, a tautology, or restates another bullet

plus an optional `subsection` when a bullet is clearly misfiled (W7),
and `restates` (the index of the bullet it duplicates — the semantic
dedupe of R8). The `interactions` sub-section is earned: a bullet there
is `supported` only when the source sentence states the causal link.

Pure functions here (prompt building, verdict parsing, application);
the I/O, batch and cache writing live in
`scripts/02d_verify_terroir_facts.py`.
"""

from __future__ import annotations

import json
import re
import unicodedata

from rapidfuzz import fuzz

from _lib import llm_json
from _lib.terroir_dedupe import _numbers, dedupe_facts
from _lib.terroir_feedback import _clip, _safe
from _lib.terroir_interactions import DEMOTION_TARGET, unearned_indices
from _lib.terroir_normalize import normalize_bullet

SUBSECTION_KEYS = ("facteurs_naturels", "facteurs_humains", "produit", "interactions")
VERDICTS = ("supported", "rewrite", "drop")
MAX_SOURCE_CHARS = 60_000
MAX_HINT_CHARS = 2_000
REWRITE_MAX_CHARS = 420
# A rewrite this close to the original (rapidfuzz ratio, 0–100) whose
# differing words are all short is cosmetic — case, punctuation, an
# article — not a meaning change; the original is kept as supported so
# the rewritten cohort stays meaning changes only and the translations
# are not redone for nothing (44 % of the r1 rewrites were light edits,
# 9 % near-cosmetic). A hedge added to a long bullet scores ≈ 98 too,
# so the ratio alone is not the test: any differing word of
# COSMETIC_WORD_CHARS letters or more ("mainly", "esclusivamente") makes
# it a real rewrite.
NEAR_IDENTICAL_RATIO = 95
COSMETIC_WORD_CHARS = 4
GATE_VERSION = "gate-v2"

SYSTEM = """You are the claim-support verifier for Open Wine Map's terroir facts: short bullets an LLM extracted from a wine regulator's product specification (the "source text" — a cahier des charges, disciplinare, pliego, Einziges Dokument, …) and, secondarily, from the appellation's Wikipedia article (the "Wikipedia hints"). The bullets are in the source language; they will be translated and shown to wine enthusiasts as facts about the appellation.

Your job is adversarial: for EACH bullet decide whether every assertion it makes — entity, number, unit, direction, spatial or temporal qualifier, hedge, causal claim — is stated by the source text or the Wikipedia hints. The quotes attached to a bullet are only where the extractor looked; judge against the whole text you are given.

Verdicts:
- "supported": every assertion is stated by the sources. A simplification is not an error; a number written differently in the source (13°5, 22, 5, anni '60, XVIIIe) is not missing; a bullet grounded on the Wikipedia hint is legitimately grounded.
- "rewrite": the main fact is stated, but the bullet adds something the sources do not state — a causal wrapper on a mere co-occurrence ("volcanic soils give minerality" when the source only records volcanic soils and, elsewhere, minerality), a narrowed attribution (one factor credited with what the source credits to several), a spatial or temporal qualifier the source does not give, a hedge strengthened ("typically" → "exclusively", "weakly" → "moderately") or dropped, a detail from a neighbouring sub-zone applied to the whole appellation. Provide "rewrite": the bullet in the SAME language, keeping the supported fact and removing or softening only what goes beyond the source. Never add content, never add a number that is not in the bullet or the source, keep it one full sentence ending with a period. A "rewrite" verdict MUST carry a non-empty "rewrite" that differs in meaning from the bullet — if you cannot phrase the narrower sentence, choose "supported" (with the note) or "drop" instead; a rewrite that only changes wording, punctuation or word order is not a rewrite.
- "drop": the main claim itself is unsupported or contradicted, describes another appellation or a sub-zone/neighbour rather than this one, is a tautology true of any appellation ("the terroir gives the wines their typicity"), or restates a fact another bullet already gives (then set "restates" to that bullet's index; keep the more precise one and drop the other).

Sub-section rule: a bullet filed under "interactions" (causal terroir → wine links) is "supported" only when a source sentence itself states the link with an explicit connective (because, thanks to, gives, confers, results in, explains, favours, allows, or the equivalent in the source language). If the source merely lists factors and wine traits side by side, "rewrite" the bullet into the non-causal statement the source does make (and file it under the right sub-section via "subsection"), or "drop" it when that statement is already given by another bullet.

Misfiling (optional): set "subsection" to one of facteurs_naturels / facteurs_humains / produit / interactions ONLY when the current one is clearly wrong (a soil or climate fact under human factors, a yield rule or a history date under natural factors, a colour/aroma description under natural factors); otherwise null.

Prior-review constraints, when given, name claims that were verified misleading before: a bullet making one of them is "drop" or "rewrite" unless the source states it explicitly. Record cautions describe known defects of the source (a section copied from another appellation, a wrong Wikipedia article): do not credit text that a caution disqualifies.

Answer ONLY with JSON, no text before or after:
{"facts": [{"i": 0, "verdict": "supported|rewrite|drop", "note": "one precise sentence quoting the decisive source words, or the assertion the source lacks", "rewrite": "" , "restates": null, "subsection": null}, ...]}
One object per bullet, in order, with "i" equal to the bullet's index."""


def _constraints_block(fb: dict | None) -> str:
    if not fb:
        return ""
    lines: list[str] = []
    for c in fb.get("do_not_claim") or []:
        if (c.get("stage") or "extraction") == "translation":
            continue
        claim = _clip(c.get("claim_src") or c.get("claim_en") or "", 220)
        why = _clip(c.get("why") or "", 260)
        if claim:
            lines.append(f"- Verified misleading before: «{claim}» — {why}")
    for n in fb.get("record_cautions") or []:
        note = _clip(n.get("note") or "", 260)
        if note:
            lines.append(f"- Caution ({n.get('kind') or 'other'}): {note}")
    if not lines:
        return ""
    return "PRIOR-REVIEW CONSTRAINTS FOR THIS RECORD\n" + "\n".join(lines) + "\n\n"


def build_user_message(
    *, name: str, country: str, source_lang: str, cahier: str, hints: dict[str, str],
    facts: list[dict], feedback: dict | None,
) -> str:
    """The per-record user message: constraints, source text, per-sub-section
    Wikipedia hints, then the numbered bullets with their quotes."""
    src = cahier or ""
    if len(src) > MAX_SOURCE_CHARS:
        src = src[:MAX_SOURCE_CHARS] + "\n[… truncated …]"
    hint_lines = []
    for key in SUBSECTION_KEYS:
        h = (hints or {}).get(key) or ""
        if h:
            hint_lines.append(f"[{key}]\n{h[:MAX_HINT_CHARS]}")
    hint_block = "\n\n".join(hint_lines) or "(none)"
    fact_lines = []
    for i, f in enumerate(facts):
        fact_lines.append(
            f"#{i} [{f.get('subsection') or 'facteurs_naturels'} · {f.get('provenance') or ''}]\n"
            f"BULLET: {f.get('bullet') or ''}\n"
            f"CAHIER_QUOTE: {f.get('cahier_quote') or ''}\n"
            f"WIKI_QUOTE: {f.get('wiki_quote') or ''}"
        )
    return _safe(
        f"RECORD: {name} (country {country}, source language {source_lang}); {len(facts)} bullets.\n\n"
        f"{_constraints_block(feedback)}"
        f"SOURCE TEXT ({len(src)} chars)\n{src or '(no regulator text — grade against the Wikipedia hints only)'}\n\n"
        f"WIKIPEDIA HINTS (per sub-section)\n{hint_block}\n\n"
        f"BULLETS TO VERIFY\n" + "\n\n".join(fact_lines)
    )


# ─────────────────────────────────────────────────────────── parsing ──


_ROW_SPLIT_RE = re.compile(r"\}\s*,\s*\{")
_I_RE = re.compile(r'"i"\s*:\s*(\d+)')
_VERDICT_RE = re.compile(r'"verdict"\s*:\s*"([A-Za-z-]+)"')
_NOTE_RE = re.compile(r'"note"\s*:\s*"(.*?)"\s*,\s*"(?:rewrite|restates|subsection)"', re.S)
_REWRITE_RE = re.compile(r'"rewrite"\s*:\s*"(.*?)"\s*,\s*"(?:restates|subsection|note)"', re.S)
_REWRITE_LAST_RE = re.compile(r'"rewrite"\s*:\s*"(.*?)"\s*$', re.S)
_RESTATES_RE = re.compile(r'"restates"\s*:\s*(null|"?\d+"?)')
_SUBSECTION_RE = re.compile(r'"subsection"\s*:\s*(null|"[a-z_]+")')


def _recover_rows(s: str) -> list[dict]:
    """Structure-anchored recovery when the reply is almost-JSON: a note
    quoting the source («la "montille"») carries unescaped double quotes
    that break `json.loads`. Each row's fields are located by their
    key and the key that follows, the way `llm_json` recovers facts."""
    start = s.find('"facts"')
    body = s[start:] if start >= 0 else s
    rows: list[dict] = []
    for chunk in _ROW_SPLIT_RE.split(body):
        m_i = _I_RE.search(chunk)
        m_v = _VERDICT_RE.search(chunk)
        if not (m_i and m_v):
            continue
        m_n = _NOTE_RE.search(chunk)
        m_r = _REWRITE_RE.search(chunk) or _REWRITE_LAST_RE.search(chunk)
        m_s = _RESTATES_RE.search(chunk)
        m_sub = _SUBSECTION_RE.search(chunk)
        rows.append({
            "i": int(m_i.group(1)),
            "verdict": m_v.group(1),
            "note": m_n.group(1).replace('\\"', '"') if m_n else "",
            "rewrite": m_r.group(1).replace('\\"', '"') if m_r else "",
            "restates": None if (not m_s or m_s.group(1) == "null") else m_s.group(1).strip('"'),
            "subsection": None if (not m_sub or m_sub.group(1) == "null") else m_sub.group(1).strip('"'),
        })
    return rows


def parse_verdicts(raw: str, n_facts: int) -> tuple[list[dict] | None, str | None]:
    """{i → verdict row} as a list aligned on fact index, or (None, error).
    Tolerant of the model omitting a bullet (treated as supported) and of
    unescaped quotes inside a note (structure-anchored recovery), but not
    of a reply with no gradable rows."""
    s = llm_json.strip_fences(raw or "")
    rows = None
    try:
        data = json.loads(s)
        rows = data.get("facts") if isinstance(data, dict) else None
    except ValueError:
        m = re.search(r"\{.*\}", s, re.S)
        if not m:
            return None, "no JSON object in reply"
        try:
            data = json.loads(m.group(0))
            rows = data.get("facts") if isinstance(data, dict) else None
        except ValueError:
            rows = _recover_rows(m.group(0)) or None
            if rows is None:
                return None, "unparseable JSON and no recoverable rows"
    if not isinstance(rows, list):
        return None, "no `facts` list"
    out: list[dict] = [{"verdict": "supported", "note": "", "rewrite": "", "restates": None, "subsection": None}
                       for _ in range(n_facts)]
    seen = 0
    for r in rows:
        if not isinstance(r, dict):
            continue
        try:
            i = int(r.get("i"))
        except (TypeError, ValueError):
            continue
        if not 0 <= i < n_facts:
            continue
        verdict = str(r.get("verdict") or "supported").strip().lower()
        if verdict not in VERDICTS:
            verdict = "supported"
        restates = r.get("restates")
        try:
            restates = int(restates) if restates is not None and str(restates) != "" else None
        except (TypeError, ValueError):
            restates = None
        sub = r.get("subsection")
        sub = sub if sub in SUBSECTION_KEYS else None
        out[i] = {
            "verdict": verdict,
            "note": " ".join(str(r.get("note") or "").split())[:400],
            "rewrite": " ".join(str(r.get("rewrite") or "").split()),
            "restates": restates,
            "subsection": sub,
        }
        seen += 1
    if seen == 0 and n_facts:
        return None, "reply graded none of the bullets"
    return out, None


# ──────────────────────────────────────────────────────── application ──


def rewrite_ok(original: str, rewrite: str, source: str) -> str | None:
    """None when the rewrite is admissible, else the reason it is not: it
    must differ, be one sane sentence, carry no arrow, and introduce no
    number absent from the original bullet and the source."""
    rw = (rewrite or "").strip()
    if not rw:
        return "empty"
    if rw == (original or "").strip():
        return "unchanged"
    if "→" in rw:
        return "arrow"
    if len(rw) > REWRITE_MAX_CHARS or len(rw) < 20:
        return "length"
    new_nums = _numbers(rw) - _numbers(original) - _numbers(source or "")
    if new_nums:
        return f"new numbers {sorted(new_nums)}"
    return None


def _words(s: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", (s or "").lower())
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.findall(r"[^\W_]+", folded)


def is_cosmetic_rewrite(original: str, rewrite: str) -> bool:
    """True when `rewrite` differs from `original` only cosmetically:
    near-identical overall (ratio ≥ NEAR_IDENTICAL_RATIO) and every word
    present in one but not the other is shorter than COSMETIC_WORD_CHARS
    — so a hedge, a qualifier or a changed entity is never cosmetic."""
    o = " ".join((original or "").split())
    r = " ".join((rewrite or "").split())
    if o == r:
        return True
    if fuzz.ratio(o, r) < NEAR_IDENTICAL_RATIO:
        return False
    ow, rw = _words(o), _words(r)
    if ow == rw:
        return True
    diff = set(ow) ^ set(rw)
    return all(len(w) < COSMETIC_WORD_CHARS for w in diff)


def apply_verdicts(
    facts: list[dict], verdicts: list[dict], *, source: str, source_lang: str = "",
    run: str, model: str,
) -> dict:
    """Apply the gate's verdicts to a record's facts. Returns
    {facts, kept_indices, dropped, rewritten, moved, rejected_rewrites,
    cosmetic_rewrites, missing_rewrites, text_changed}. Every kept fact
    carries `support` ({verdict, note[, original_bullet][, moved_from]});
    dropped facts are listed with their reason so the cache and the
    feedback history can record them. A `rewrite` verdict with no rewrite
    text, or with a cosmetic one, keeps the original bullet as
    `supported` (the note is kept, the case is listed)."""
    kept: list[dict] = []
    kept_indices: list[int] = []
    dropped: list[dict] = []
    rewritten: list[dict] = []
    moved: list[dict] = []
    rejected: list[dict] = []
    cosmetic: list[dict] = []
    missing: list[dict] = []
    text_changed = False
    for i, (fact, v) in enumerate(zip(facts, verdicts)):
        verdict = v["verdict"]
        note = v.get("note") or ""
        # A `restates` pointing at a bullet that is itself dropped is not a
        # duplicate any more — keep the later one unless it has its own reason.
        if verdict == "drop" and v.get("restates") is not None:
            target = v["restates"]
            target_dropped = any(d["index"] == target for d in dropped)
            if target_dropped and target != i:
                verdict = "supported"
                note = f"kept: it restated #{target}, which was dropped"
        if verdict == "drop":
            dropped.append({
                "index": i, "bullet": fact.get("bullet") or "", "subsection": fact.get("subsection"),
                "note": note, "restates": v.get("restates"),
            })
            continue
        new = dict(fact)
        support = {"verdict": verdict, "note": note, "gate": GATE_VERSION, "run": run, "model": model}
        if verdict == "rewrite":
            original = fact.get("bullet") or ""
            proposed = (v.get("rewrite") or "").strip()
            reason = rewrite_ok(original, proposed, source)
            if not proposed:
                support["verdict"] = "supported"
                support["rewrite_missing"] = True
                missing.append({"index": i, "note": note})
            elif is_cosmetic_rewrite(original, proposed):
                support["verdict"] = "supported"
                support["cosmetic_rewrite"] = proposed
                cosmetic.append({"index": i, "from": original, "to": proposed, "note": note})
            elif reason is None:
                new_bullet = normalize_bullet(v["rewrite"], source_lang)
                support["original_bullet"] = fact.get("bullet") or ""
                new["bullet"] = new_bullet
                rewritten.append({"index": i, "from": fact.get("bullet") or "", "to": new_bullet, "note": note})
                text_changed = True
            else:
                support["verdict"] = "rewrite-rejected"
                support["rejected_reason"] = reason
                support["proposed_rewrite"] = v.get("rewrite") or ""
                rejected.append({"index": i, "reason": reason, "note": note})
        sub = v.get("subsection")
        if sub and sub != (fact.get("subsection") or "facteurs_naturels"):
            support["moved_from"] = fact.get("subsection") or "facteurs_naturels"
            new["subsection"] = sub
            moved.append({"index": i, "from": support["moved_from"], "to": sub})
        new["support"] = support
        kept.append(new)
        kept_indices.append(i)
    # The earned-interactions rule (R3), deterministic: a kept `interactions`
    # bullet whose grounding quote states no link — or beyond the cap — moves
    # to the natural factors; its causal wrapper, if any, was rewritten away
    # by the verdict above.
    for pos in unearned_indices(kept, source_lang):
        f = kept[pos]
        f["support"].setdefault("moved_from", "interactions")
        f["support"]["unearned_interaction"] = True
        f["subsection"] = DEMOTION_TARGET
        moved.append({"index": kept_indices[pos], "from": "interactions", "to": DEMOTION_TARGET})
    # A rewrite can make two bullets restate each other — collapse them.
    dd = dedupe_facts(kept)
    if dd.drops:
        survivors = set(dd.kept_indices)
        for pos, (orig_i, f) in enumerate(zip(kept_indices, kept)):
            if pos not in survivors:
                dropped.append({"index": orig_i, "bullet": f.get("bullet") or "", "subsection": f.get("subsection"),
                                "note": "duplicate after the gate (lexical dedupe)", "restates": None})
        kept_indices = [kept_indices[p] for p in dd.kept_indices]
        kept = dd.kept
    return {
        "facts": kept, "kept_indices": kept_indices, "dropped": sorted(dropped, key=lambda d: d["index"]),
        "rewritten": rewritten, "moved": moved, "rejected_rewrites": rejected,
        "cosmetic_rewrites": cosmetic, "missing_rewrites": missing,
        "text_changed": text_changed,
    }
