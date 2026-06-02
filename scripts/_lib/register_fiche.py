"""Shared accessor for the EU-register fiche-technique sidecars
(`raw/<cc>/register-fiches-extracted/<slug>.json`) produced by
`scripts/extract_register_fiches.py`.

Two consumers:
- stage 04 `augment_records_with_register_fiches()` — merges the per-DOP
  terroir text + variety list + provenance into the in-memory record so the
  map panel shows them.
- each country's `02d` `_resolve_lien_and_source` — grounds terroir-fact
  extraction on the per-DOP §7 (link) text.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=None)
def load_sidecar(cc: str, slug: str) -> dict | None:
    p = ROOT / "raw" / cc / "register-fiches-extracted" / f"{slug}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def fiche_terroir(cc: str, slug: str, min_chars: int = 120) -> tuple[str, dict] | None:
    """Return (link_to_terroir text, provenance dict) from the register
    fiche, or None if absent/too short."""
    d = load_sidecar(cc, slug)
    if not d:
        return None
    text = (d.get("link_to_terroir") or "").strip()
    if len(text) < min_chars:
        return None
    src = d.get("source") or {}
    return text, {
        "pdf_url": src.get("url", ""),
        "kind": "eambrosia-register-fiche",
        "ref": src.get("ref"),
        "attachment_uri": src.get("attachment_uri"),
    }


def fiche_grape_slugs(cc: str, slug: str) -> list[str]:
    """Return the fiche's principal-variety slugs (may be empty)."""
    d = load_sidecar(cc, slug)
    if not d:
        return []
    return list((d.get("grapes") or {}).get("principal") or [])
