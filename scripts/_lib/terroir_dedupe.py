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
- they cite the same source sentence (a normalised `cahier_quote` or
  `wiki_quote` of at least `QUOTE_MIN_CHARS` that is identical, or one a
  longer cut of the other) *and* their bullets overlap substantially
  (≥ `QUOTE_DUP_BULLET_SIMILARITY`). A shared quote alone is not enough:
  one long source sentence often yields two distinct facts (alluvial
  soils / river water supply), and dropping either would lose
  information.

Neither rule fires when the two bullets carry different sets of numbers
with neither set contained in the other — different quantities are
different facts, however similar the wording. Nor when the bullets lead
with different `protected_names` (the record's sub-denominations, as
stage 04's sibling filter sees them): a parent's bullet "Rioja Alavesa:
…" must survive next to "Rioja Oriental: …" or an unlabelled twin, or a
sub-denomination page loses the one bullet that was about it.

Duplicates are transitive: a fact restating an already-dropped fact is
dropped too (the third cut of one sentence rarely resembles the first as
closely as it resembles the second).

Of a duplicate pair the more informative fact is kept: `both` provenance
first, then more numbers, then longer quotes; ties keep the earlier one.
The kept fact stays at the earlier fact's position, so within-sub-section
order is stable.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable
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


def _share_quote(a: dict, b: dict) -> bool:
    return any(x == y or x in y or y in x for x in _quotes(a) for y in _quotes(b))


def _norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.casefold().split())


def _leads_with_name(bullet: str, name: str) -> bool:
    """Mirror of stage 04's sibling test (`_leads_with_name` in
    04_build_maps.py): the bullet starts with the name as a whole word."""
    nb, nn = _norm_name(bullet), _norm_name(name)
    if not nn or not nb.startswith(nn):
        return False
    return len(nb) == len(nn) or not nb[len(nn)].isalnum()


def _lead_name(bullet: str, names: Iterable[str]) -> str | None:
    return next((n for n in names if _leads_with_name(bullet, n)), None)


def duplicate_reason(a: dict, b: dict, protected_names: Iterable[str] = ()) -> str | None:
    """`similar-bullet` / `same-quote` when `a` and `b` restate one fact."""
    bullet_a = a.get("bullet") or ""
    bullet_b = b.get("bullet") or ""
    if not _numbers_compatible(_numbers(bullet_a), _numbers(bullet_b)):
        return None
    names = tuple(protected_names)
    if names and _lead_name(bullet_a, names) != _lead_name(bullet_b, names):
        return None
    similarity = fuzz.token_set_ratio(bullet_a, bullet_b)
    if similarity >= BULLET_DUP_SIMILARITY:
        return "similar-bullet"
    if similarity >= QUOTE_DUP_BULLET_SIMILARITY and _share_quote(a, b):
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


def dedupe_facts(facts: list[dict], protected_names: Iterable[str] = ()) -> DedupeResult:
    """Collapse restated facts; `drops` records each dropped fact with the
    index and bullet of the fact it duplicated. `protected_names` are the
    record's sub-denomination names (see `duplicate_reason`)."""
    names = tuple(protected_names)
    kept: list[tuple[int, dict]] = []
    group_of: dict[int, int] = {}  # original index → position in `kept` of its group's survivor
    drops: list[dict] = []
    for idx, fact in enumerate(facts):
        twin_pos = None
        reason = None
        for j in range(idx):
            reason = duplicate_reason(facts[j], fact, names)
            if reason:
                twin_pos = group_of[j]
                break
        if twin_pos is None:
            group_of[idx] = len(kept)
            kept.append((idx, fact))
            continue
        group_of[idx] = twin_pos
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
