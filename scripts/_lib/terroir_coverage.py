"""Grounding coverage for terroir-fact quotes (stages 02d, the audit, and
the cache post-passes).

A fact survives extraction only when at least one of its two verbatim
quotes (`cahier_quote`, `wiki_quote`) is found in its source text. The
test is the longest contiguous match between the normalised quote and
the normalised source, as a share of the quote's length; `FUZZY_THRESHOLD`
is the pass mark and `provenance_for` turns the two shares into the
per-fact `both` / `cahier` / `wiki` label.

The model legitimately joins two spans of the source with an ellipsis
("[…]", "[...]", "…"). A single contiguous match then covers at most the
longer span, which capped coverage well below the threshold and flipped
hundreds of cahier-grounded facts to `wiki` (or dropped them). Such a
quote is therefore also graded span by span: the coverage of a multi-span
quote is the better of the whole-quote match and the *weakest* span's
match, so every span has to ground for the split to help, and a quote
that already passed as a whole is never demoted. Spans shorter than
`MIN_SPAN_CHARS` are too short to grade on their own and are ignored
(unless every span is that short).

Every stage-02d script and the audit import `fuzzy_coverage` from here so
the grounding rule cannot drift between countries.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

FUZZY_THRESHOLD = 0.6
MIN_SPAN_CHARS = 15

# "[…]" / "[...]" / "(…)" / "(...)" / bare "…" / bare "..." — the joins the
# model uses when it stitches two source spans into one quote.
ELLIPSIS_RE = re.compile(r"[\[(]\s*(?:…|\.{3})\s*[\])]|…|\.{3}")


def normalize(s: str) -> str:
    return " ".join((s or "").split()).lower()


def split_spans(quote_norm: str) -> list[str]:
    """The non-empty pieces of a normalised quote between ellipsis joins."""
    return [p.strip() for p in ELLIPSIS_RE.split(quote_norm) if p.strip()]


class SourceMatcher:
    """One normalised source text with its match index built once, so a
    post-pass can grade every quote of a record without re-indexing a
    300 KB cahier per quote."""

    def __init__(self, source: str) -> None:
        self.source = normalize(source)
        self._sm = SequenceMatcher(None, "", self.source, autojunk=False)

    def contiguous(self, quote_norm: str) -> float:
        if not quote_norm:
            return 0.0
        self._sm.set_seq1(quote_norm)
        m = self._sm.find_longest_match(0, len(quote_norm), 0, len(self.source))
        return m.size / len(quote_norm)

    def coverage(self, quote: str) -> float:
        q = normalize(quote)
        if not q:
            return 0.0
        whole = self.contiguous(q)
        spans = split_spans(q)
        if len(spans) < 2:
            return whole
        graded = [p for p in spans if len(p) >= MIN_SPAN_CHARS] or spans
        return max(whole, min(self.contiguous(p) for p in graded))


def fuzzy_coverage(quote: str, source: str) -> float:
    """Share of `quote` grounded in `source` (0.0–1.0); ellipsis-aware."""
    return SourceMatcher(source).coverage(quote)


def provenance_for(
    cahier_coverage: float, wiki_coverage: float, threshold: float = FUZZY_THRESHOLD,
) -> str | None:
    """`both` / `cahier` / `wiki`, or None when neither source grounds."""
    c_ok = cahier_coverage >= threshold
    w_ok = wiki_coverage >= threshold
    if c_ok and w_ok:
        return "both"
    if c_ok:
        return "cahier"
    if w_ok:
        return "wiki"
    return None
