"""Loaders for the per-locale translation caches.

Stages 02c and 02e write per-(slug, lang) JSON caches under
`raw/translations/summaries/<lang>/` and `raw/translations/terroir-facts/<lang>/`.
Both stages 03 and 04 consume them to overlay translated content onto the
canonical FR cahier data; this module is the shared loader so the two stages
stay in lockstep on cache shape.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SUMMARIES_DIR = ROOT / "raw" / "translations" / "summaries"
FACTS_DIR = ROOT / "raw" / "translations" / "terroir-facts"


def load_summary_translations(lang: str) -> dict[str, dict]:
    """Read cached machine-translated summaries for `lang`. Returns
    {slug: {summary, source_pdf_url, source_pdf_filename, translator,
    source_summary_sha}}.

    `lang == "fr"` is accepted: the FR cache holds hand-rewritten summaries
    that fix cahier-extraction quirks (shared cahiers, mid-paragraph cuts).
    Same provenance as the cahier PDF, so the source block already covers
    attribution — the caller should not set a "translation" attribution line
    on FR records.
    """
    cache_dir = SUMMARIES_DIR / lang
    if not cache_dir.exists():
        return {}
    out: dict[str, dict] = {}
    for f in cache_dir.glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        if not d.get("summary"):
            continue
        out[d["slug"]] = {
            "summary": d["summary"],
            "source_pdf_url": d.get("source_pdf_url") or "",
            "source_pdf_filename": d.get("source_pdf_filename") or "",
            "translator": d.get("translator") or "",
            "source_summary_sha": d.get("source_summary_sha") or "",
        }
    return out


def load_terroir_facts_translations(lang: str) -> dict[str, dict]:
    """Per-locale translated terroir-facts bullets, from stage 02e cache.
    Returns {slug: {facts: [{bullet, subsection, provenance}], ...}}.
    The caller overlays the FR `terroir_facts.facts[i].bullet` with the
    translated string at the same index."""
    cache_dir = FACTS_DIR / lang
    if not cache_dir.exists():
        return {}
    out: dict[str, dict] = {}
    for f in cache_dir.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not d.get("facts"):
            continue
        out[d["slug"]] = d
    return out
