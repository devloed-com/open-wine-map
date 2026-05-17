"""Shared cahier-summary derivation.

Stage 02c (translation) and stage 04 (map build) both need the same FR
summary derivation, including the same truncation rules, so the SHA of the
input is stable across stages and translations stay cache-valid.
"""

from __future__ import annotations

import hashlib
import re

MAX_CHARS = 480
SOFT_MAX_CHARS = 1200


def derive_summary(record: dict) -> str:
    """Trim source-document text into a one-paragraph blurb.

    For ES records, stage 02 (`scripts/es/02_extract_pliegos.py`) already
    pre-computes a `summary` field from the EU-OJ single document's
    description + geographical-area sections, so we just return that
    verbatim — the FR-specific section I + III concatenation does not
    apply (ES single-document templates use sections 4/6 or 6/9, routed
    semantically rather than numerically).

    For FR records, two-tier cap: keep the combined section I + couleur
    verbatim up to SOFT_MAX_CHARS so the cahier's full intro + style
    description survives, and only fall back to the legacy MAX_CHARS
    sentence-boundary cut when the combined text exceeds the soft
    ceiling. Entries whose existing output already fit under MAX_CHARS
    keep the same SHA — the cache only re-translates AOCs whose summary
    was previously clipped mid-clause.
    """
    if record.get("country") in ("es", "pt"):
        return record.get("summary", "") or ""
    sections = record.get("sections", {})
    roles = record.get("section_roles") or {}
    # Prefer the routed "nom" role so spiritueux/EDV records (where the
    # name section lives under a letter or arabic label, not a Roman "I")
    # produce the same shape of summary as AOC records. For AOCs the role
    # equals sections["I"] when title routing succeeded, so output is
    # unchanged.
    s = roles.get("nom") or sections.get("I") or sections.get("1") or ""
    s += " " + (roles.get("couleur") or sections.get("III") or sections.get("3") or "")
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) <= SOFT_MAX_CHARS:
        return s
    cut = s[:MAX_CHARS].rsplit(". ", 1)[0]
    return cut + ("." if not cut.endswith(".") else "")


def summary_sha(text: str) -> str:
    """Stable hash of the FR summary used as the translation-cache key."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
