"""Per-record review feedback for the terroir-fact stages.

`raw/terroir-facts-feedback/<slug>.json` keeps what a quality review
found about ONE record, as constraints stage 02d can read on its next
extraction — not as bullets to reproduce:

  do_not_claim        verified misleading claims: the English and
                      source-language bullet, the failure mode, the stage
                      that produced it (extraction / translation / both)
                      and the verifier's source-quoting reason
  capture_if_present  what the reviewer saw the source describe
                      prominently and no bullet captured (hints)
  record_cautions     sibling text inside the source, a wrong source
                      binding, a source typo, a wrong Wikipedia article
  history             one entry per later run: bullets a gate dropped or
                      rewrote, so the file becomes the record's QA trail

`with_feedback(system, slug)` appends the prompt block to a 02d system
prompt (the country scripts call it right after `EXTRACT_SYSTEM.format`);
only the `extraction` / `both` entries go to 02d — `translation` entries
are for a 02e back-check. The block phrases every negative as "only if
the source states it explicitly", so a claim that IS grounded survives.
`recurrence_findings` is the audit's regression check: a do-not-claim
entry whose source-language bullet still matches a current bullet.

Built by `scripts/build_terroir_feedback.py` from a review's evidence
directory; never shown on the map or in the wiki.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from rapidfuzz import fuzz

from _lib.terroir_dedupe import is_cosmetic_rewrite
from _lib.terroir_prompts import appellation_context

ROOT = Path(__file__).resolve().parents[2]
FEEDBACK_DIR = ROOT / "raw" / "terroir-facts-feedback"

RECURRENCE_THRESHOLD = 85
MAX_CLAIMS = 6
MAX_CAPTURE = 4
MAX_CAUTIONS = 3
_WHY_CHARS = 320
_HINT_CHARS = 320
_NOTE_CHARS = 320

_cache: dict[str, dict | None] = {}


def feedback_path(slug: str) -> Path:
    return FEEDBACK_DIR / f"{slug}.json"


def load_feedback(slug: str) -> dict | None:
    """The record's feedback sidecar, or None. Cached per process; call
    `clear_cache()` after writing."""
    if slug in _cache:
        return _cache[slug]
    path = feedback_path(slug)
    fb = None
    if path.exists():
        try:
            fb = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            fb = None
    _cache[slug] = fb
    return fb


def clear_cache() -> None:
    _cache.clear()


def is_stale(fb: dict, cahier_sha: str | None, wiki_revision) -> bool:
    """True when the sources the review graded against have changed since
    — the constraints may be obsolete, which is why the prompt block never
    asserts them unconditionally."""
    graded = fb.get("graded_against") or {}
    if cahier_sha and graded.get("cahier_source_sha") and graded["cahier_source_sha"] != cahier_sha:
        return True
    if (
        wiki_revision is not None and graded.get("wiki_source_revision") is not None
        and str(graded["wiki_source_revision"]) != str(wiki_revision)
    ):
        return True
    return False


def _clip(text: str, n: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _safe(text: str) -> str:
    """No `{` / `}`: a script that formats its prompt after appending the
    block must not trip on feedback text."""
    return text.replace("{", "(").replace("}", ")")


def feedback_prompt_block(
    fb: dict | None, *, stage: str = "extraction",
    max_claims: int = MAX_CLAIMS, max_capture: int = MAX_CAPTURE, max_cautions: int = MAX_CAUTIONS,
) -> str:
    """The English block appended to a 02d prompt, or "" when the record
    has nothing for this stage. `stage` selects the do-not-claim entries:
    `extraction` takes extraction + both, `translation` takes translation
    + both."""
    if not fb:
        return ""
    wanted = {"extraction", "both"} if stage == "extraction" else {"translation", "both"}
    claims = [c for c in fb.get("do_not_claim") or [] if (c.get("stage") or "extraction") in wanted]
    capture = fb.get("capture_if_present") or []
    cautions = fb.get("record_cautions") or []
    if not (claims or capture or cautions):
        return ""
    reviews = fb.get("reviews") or []
    dates = sorted({r.get("date", "") for r in reviews if r.get("date")})
    when = f" ({', '.join(dates)})" if dates else ""
    lines = [
        f"Lessons from the previous review of this record{when}. They are constraints on "
        "grounding, not facts to reproduce; every bullet must still be a verbatim-quotable "
        "claim of the text you are given:"
    ]
    for c in claims[:max_claims]:
        claim = _clip(c.get("claim_en") or c.get("claim_src") or "", 200)
        why = _clip(c.get("why") or "", _WHY_CHARS)
        lines.append(f"- Do not assert «{claim}» unless the source states it explicitly — {why}")
    if len(claims) > max_claims:
        lines.append(f"- ({len(claims) - max_claims} more claims of the same kind were unsupported.)")
    for h in capture[:max_capture]:
        lines.append(f"- If the text describes it, capture: {_clip(h.get('hint') or '', _HINT_CHARS)}")
    for n in cautions[:max_cautions]:
        lines.append(f"- Caution ({n.get('kind') or 'other'}): {_clip(n.get('note') or '', _NOTE_CHARS)}")
    return _safe("\n".join(lines))


def with_feedback(system: str, slug: str, *, stage: str = "extraction") -> str:
    """`system` + the record's per-record block: its review feedback
    (do-not-claim constraints, cautions) and, for a record whose bullets
    are inherited by sub-denomination pages, the instruction to name the
    appellation where the source says "the appellation"
    (`terroir_prompts.appellation_context`). `system` unchanged when the
    record has neither."""
    parts = [system.rstrip()]
    block = feedback_prompt_block(load_feedback(slug), stage=stage)
    if block:
        parts.append(block)
    ctx = appellation_context(slug, for_translation=False)
    if ctx:
        parts.append(ctx)
    return "\n\n".join(parts) if len(parts) > 1 else system


def recurrence_findings(
    fb: dict | None, facts: list[dict], *, threshold: int = RECURRENCE_THRESHOLD,
) -> list[dict]:
    """Do-not-claim entries (extraction / both) whose source-language bullet
    still matches a current fact's bullet — the known error is still there
    (before a re-run) or came back (after one).

    The match is lexical (token-set ratio), so a bullet the gate has since
    rewritten still matches its own misleading original on most of its
    words. Such an entry is counted as resolved, not recurring, when the
    matched fact carries `support.original_bullet`, the claim matches that
    original at least as well as it matches the current bullet, and the
    rewrite was not cosmetic (5 of the 6 residual hits of the r1 audit were
    fixed bullets)."""
    if not fb:
        return []
    out: list[dict] = []
    bullets = [(i, (f.get("bullet") or "")) for i, f in enumerate(facts)]
    for c in fb.get("do_not_claim") or []:
        if (c.get("stage") or "extraction") == "translation":
            continue
        probe = c.get("claim_src") or c.get("claim_en") or ""
        if not probe:
            continue
        best_i, best = -1, 0.0
        for i, b in bullets:
            if not b:
                continue
            score = fuzz.token_set_ratio(probe, b)
            if score > best:
                best_i, best = i, score
        if best < threshold:
            continue
        current = facts[best_i].get("bullet") or ""
        original = (facts[best_i].get("support") or {}).get("original_bullet") or ""
        if (
            original
            and fuzz.token_set_ratio(probe, original) >= best
            and not is_cosmetic_rewrite(original, current)
        ):
            continue
        out.append({
            "index": best_i, "score": round(best, 1), "mode": c.get("mode"),
            "review": c.get("review"), "claim": _clip(c.get("claim_en") or probe, 160),
        })
    return out


def append_history(slug: str, entry: dict) -> None:
    """Add a run entry (`{run, kind, ...}`) to the record's `history`,
    creating a minimal sidecar when none exists."""
    path = feedback_path(slug)
    fb = load_feedback(slug) or {"slug": slug, "do_not_claim": [], "capture_if_present": [],
                                 "record_cautions": [], "reviews": [], "history": []}
    entry = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry}
    fb.setdefault("history", []).append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    _cache[slug] = fb
