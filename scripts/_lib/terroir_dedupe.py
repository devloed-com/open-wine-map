"""Intra-record de-duplication of terroir facts.

Stage 02d extracts each record in four sub-section calls over overlapping
source text, so the same sentence is regularly restated two or three
times (a soil fact under "facteurs naturels", again under "produit" and
again under "interactions"). `dedupe_facts` collapses those restatements
inside one record; it is applied by `scripts/dedupe_terroir_facts.py` to
the existing caches and by stage 02d after its sub-section loop.

Two facts are duplicates when

- their bullets are near-identical (`token_set_ratio` ≥
  `BULLET_DUP_SIMILARITY`), or
- they cite the same source sentence (an identical normalised
  `cahier_quote` or `wiki_quote` of at least `QUOTE_MIN_CHARS`) *and*
  their bullets overlap substantially (≥ `QUOTE_DUP_BULLET_SIMILARITY`).
  A shared quote alone is not enough: one long source sentence often
  yields two distinct facts (alluvial soils / river water supply), and
  dropping either would lose information.

Neither rule fires when the two bullets carry different sets of numbers
with neither set contained in the other — different quantities are
different facts, however similar the wording.

Of a duplicate pair the more informative fact is kept: `both` provenance
first, then more numbers, then longer quotes; ties keep the earlier one.
The kept fact stays at the earlier fact's position, so within-sub-section
order is stable.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

QUOTE_MIN_CHARS = 30
QUOTE_DUP_BULLET_SIMILARITY = 60
BULLET_DUP_SIMILARITY = 85

_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")


def _norm(s: str) -> str:
    return " ".join((s or "").split()).lower()


def _numbers(text: str) -> frozenset[str]:
    return frozenset(n.replace(",", ".") for n in _NUM_RE.findall(text or ""))


def _numbers_compatible(a: frozenset[str], b: frozenset[str]) -> bool:
    return not a or not b or a <= b or b <= a


def _quotes(fact: dict) -> list[str]:
    out = []
    for key in ("cahier_quote", "wiki_quote"):
        q = _norm(fact.get(key) or "")
        if len(q) >= QUOTE_MIN_CHARS:
            out.append(q)
    return out


def duplicate_reason(a: dict, b: dict) -> str | None:
    """`similar-bullet` / `same-quote` when `a` and `b` restate one fact."""
    bullet_a = a.get("bullet") or ""
    bullet_b = b.get("bullet") or ""
    if not _numbers_compatible(_numbers(bullet_a), _numbers(bullet_b)):
        return None
    similarity = fuzz.token_set_ratio(bullet_a, bullet_b)
    if similarity >= BULLET_DUP_SIMILARITY:
        return "similar-bullet"
    if similarity >= QUOTE_DUP_BULLET_SIMILARITY and set(_quotes(a)) & set(_quotes(b)):
        return "same-quote"
    return None


def _rank(fact: dict) -> tuple[bool, int, int]:
    return (
        fact.get("provenance") == "both",
        len(_numbers(fact.get("bullet") or "")),
        len(fact.get("cahier_quote") or "") + len(fact.get("wiki_quote") or ""),
    )


@dataclass
class DedupeResult:
    kept: list[dict] = field(default_factory=list)
    kept_indices: list[int] = field(default_factory=list)
    drops: list[dict] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.drops)


def dedupe_facts(facts: list[dict]) -> DedupeResult:
    """Collapse restated facts; `drops` records each dropped fact with the
    index and bullet of the fact it duplicated."""
    kept: list[tuple[int, dict]] = []
    drops: list[dict] = []
    for idx, fact in enumerate(facts):
        twin_pos = None
        reason = None
        for pos, (_, k) in enumerate(kept):
            reason = duplicate_reason(k, fact)
            if reason:
                twin_pos = pos
                break
        if twin_pos is None:
            kept.append((idx, fact))
            continue
        twin_idx, twin = kept[twin_pos]
        if _rank(fact) > _rank(twin):
            kept[twin_pos] = (idx, fact)
            dropped_idx, dropped, winner_idx, winner = twin_idx, twin, idx, fact
        else:
            dropped_idx, dropped, winner_idx, winner = idx, fact, twin_idx, twin
        drops.append({
            "reason": reason,
            "dropped_index": dropped_idx,
            "dropped_bullet": dropped.get("bullet") or "",
            "dropped_subsection": dropped.get("subsection"),
            "dropped_provenance": dropped.get("provenance"),
            "kept_index": winner_idx,
            "kept_bullet": winner.get("bullet") or "",
            "kept_subsection": winner.get("subsection"),
            "kept_provenance": winner.get("provenance"),
        })
    return DedupeResult(
        kept=[f for _, f in kept],
        kept_indices=[i for i, _ in kept],
        drops=drops,
    )


def facts_sha(facts: list[dict]) -> str:
    """sha256 of the source-language bullets joined with "\\n" — the
    `source_facts_sha` every stage-02e translation cache is keyed on."""
    blob = "\n".join((f.get("bullet") or "") for f in facts)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
