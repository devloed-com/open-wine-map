"""When a national specification's link text replaces the EU single
document's.

A single document on the 2024/1143 template carries only a summary of the
link — "Resumen del vínculo" (ES), "Sintesi del legame" (IT) — while the
national text the state filed is the full statement: the pliego's §7
VÍNCULO, the MASAF disciplinare's Article 9. The facts ground on the fuller
regulator text when the EU text is a summary (the marker in its head, or
under 1,000 characters) and the national text is substantially longer —
at least 1.5× and at least 1,000 characters — never on a national text of
the same size under a template heading (Terre Abruzzesi's 15 k-character
"Sintesi" against a 19 k Article 9 stays the EU text). ES since 2026-10-24
(decision 5), IT the same day: 40 non-stub records — Marsala's 1,286
characters against 4,522, Etna's 702 against 13,671 — had grounded on the
summary, Marsala with three facts.
"""
from __future__ import annotations

import re

SUMMARY_LINK_MAX_CHARS = 1000
NATIONAL_LINK_MIN_RATIO = 1.5

_SUMMARY_MARK_RE = re.compile(
    r"Resumen\s+del\s+v[ií]nculo|Sintesi\s+del\s+legame", re.IGNORECASE
)


def is_summary_link(text: str) -> bool:
    """True for a single document's summary-of-the-link text or any link
    text under 1,000 characters — the texts a national text replaces."""
    text = text or ""
    return len(text) < SUMMARY_LINK_MAX_CHARS or bool(_SUMMARY_MARK_RE.search(text[:400]))


def prefer_national_link(oj_text: str, national_text: str) -> bool:
    """True when the facts should ground on `national_text` instead of the
    EU single document's `oj_text`."""
    oj_text = oj_text or ""
    national_text = national_text or ""
    if not is_summary_link(oj_text):
        return False
    return len(national_text) >= max(
        SUMMARY_LINK_MAX_CHARS, int(NATIONAL_LINK_MIN_RATIO * len(oj_text)) + 1
    )
