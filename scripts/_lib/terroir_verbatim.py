"""Verbatim-mode fallback for 02d when the cahier's `link_to_terroir`
is non-empty but below the LLM-extraction threshold.

A handful of appellations across the corpus have a genuinely short
narrative section because the regulated wine territory is tiny — the
Einziges Dokument itself may openly note "few isolated producers"
(Austria's Oberösterreich is 347 chars; Spain's Costa de Cantabria is
193 chars after the i18n-placeholder scrub). Running the LLM on so
little text either drops the record (the historical behaviour, which
silently hides the appellation's narrative from the map) or produces
weakly-grounded bullets. Both outcomes are wrong.

This module emits a `mode="verbatim"` terroir-facts record that carries
the source text instead of LLM-extracted bullets:

  - Stage 02d writes the verbatim payload via `write_verbatim_record`.
  - Stage 02e translates `verbatim_text` (a single string) into target
    locales — see `terroir_verbatim_translate.py` for the shared loop.
  - Stage 04's panel renderer detects `mode="verbatim"` and renders the
    text as a single quoted block with cahier attribution (no LLM
    chrome). A "to-verify" badge surfaces the `validation_flag`.
  - Country audits surface the verbatim-mode count via
    `count_verbatim_records`.

Cache key is the sha256 of the source `lien` text — same as the LLM
path — so re-running 02d after a parser fix that lengthens the lien
beyond MIN_LIEN_CHARS invalidates the verbatim cache and re-routes to
the LLM path automatically.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

MIN_LIEN_CHARS = 400
MIN_VERBATIM_CHARS = 30


def should_use_verbatim(lien: str) -> bool:
    """True if the lien text is non-empty but too short for the LLM."""
    return 0 < len(lien or "") < MIN_LIEN_CHARS


def validation_flag(lien: str) -> str:
    """Stable code describing why this record needs human review.
    Empty string means no flag needed."""
    n = len(lien or "")
    if n == 0:
        return ""
    if n < MIN_VERBATIM_CHARS:
        return "very-short"
    if n < MIN_LIEN_CHARS:
        return "below-threshold"
    return ""


def cahier_sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def build_verbatim_payload(
    *,
    slug: str,
    name: str,
    country: str,
    source_lang: str,
    lien: str,
    cahier_source_pdf_url: str = "",
    cahier_source_kind: str = "",
    wiki_source_url: str = "",
    wiki_source_revision: str | int | None = None,
    fetched_at: str | None = None,
) -> dict:
    """Build a terroir-facts cache record carrying verbatim source text
    instead of LLM-extracted bullets. Schema is intentionally close to
    the bullet-mode record so stage 04 + 02e can detect `mode` and
    branch with minimal special-casing."""
    if fetched_at is None:
        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "country": country,
        "source_lang": source_lang,
        "slug": slug,
        "name": name,
        "mode": "verbatim",
        "verbatim_text": lien,
        "verbatim_chars": len(lien),
        "validation_flag": validation_flag(lien),
        "facts": [],
        "n_dropped": 0,
        "model": "",
        "model_kind": "verbatim",
        "fetched_at": fetched_at,
        "cahier_source_sha": cahier_sha(lien),
        "cahier_source_pdf_url": cahier_source_pdf_url,
        "cahier_source_kind": cahier_source_kind,
        "wiki_source_revision": wiki_source_revision,
        "wiki_source_url": wiki_source_url,
        "subsection_errors": [],
    }


def is_verbatim_cache_valid(cache_path: Path, country: str, lien: str) -> bool:
    """Cache hit iff (country, mode, sha) all match. Sha mismatch on a
    grown lien rolls the record forward into the LLM path on next run."""
    if not cache_path.exists():
        return False
    try:
        existing = json.loads(cache_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return False
    if existing.get("country") != country:
        return False
    if existing.get("mode") != "verbatim":
        return False
    return existing.get("cahier_source_sha") == cahier_sha(lien)


def write_verbatim_record(cache_path: Path, payload: dict) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _load_record(jp: Path) -> dict | None:
    if jp.name.startswith("_"):
        return None
    try:
        return json.loads(jp.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def _should_emit_verbatim(
    rec: dict, country: str, cache_dir: Path, needles: list[str],
) -> tuple[bool, str, str]:
    """Return (should_emit, slug, lien). Filters out non-eligible records
    (no slug, sub-denomination, lien outside window, already cached)."""
    slug = rec.get("slug") or ""
    if not slug:
        return False, "", ""
    if needles and not any(n in slug.lower() for n in needles):
        return False, slug, ""
    if rec.get("is_sub_denomination"):
        return False, slug, ""
    lien = rec.get("link_to_terroir") or ""
    if not should_use_verbatim(lien):
        return False, slug, lien
    if is_verbatim_cache_valid(cache_dir / f"{slug}.json", country, lien):
        return False, slug, lien
    return True, slug, lien


def emit_for_country(
    *,
    country: str,
    extracted_dir: Path,
    cache_dir: Path,
    default_source_lang: str,
    cahier_source_kind: str = "",
    only: list[str] | None = None,
    log_prefix: str = "",
    print_fn = None,
) -> int:
    """Walk a country's extracted-records directory and write verbatim-mode
    terroir-facts records for every record with `0 < len(link_to_terroir)
    < MIN_LIEN_CHARS`. Returns the count of newly-written records (cached
    entries with matching sha are skipped). Each record's per-record
    `source_lang` is used if present; otherwise `default_source_lang`.
    Sub-denomination records are skipped (they inherit the parent's
    bullets at rendering time, mirroring the LLM path).

    Designed to be called from each country's 02d main() as a one-line
    replacement for the per-country `collect_verbatim_targets` +
    `_write_verbatim_records` plumbing. Country-specific lien resolution
    (DE BLE backfill, IT MASAF augmentation, …) lives in each 02d's
    `_resolve_lien_and_source` — those resolved liens are typically
    long enough that they never fall into the verbatim window, so
    reading `link_to_terroir` directly from the extracted record is
    correct for the verbatim path.
    """
    import sys
    if print_fn is not None:
        log = print_fn
    else:
        def log(msg):
            print(msg, file=sys.stderr)
    if not extracted_dir.exists():
        return 0
    cache_dir.mkdir(parents=True, exist_ok=True)
    needles = [s.lower() for s in (only or [])]
    written = 0
    for jp in sorted(extracted_dir.glob("*.json")):
        rec = _load_record(jp)
        if rec is None:
            continue
        emit, slug, lien = _should_emit_verbatim(rec, country, cache_dir, needles)
        if not emit:
            continue
        source = rec.get("source") or {}
        payload = build_verbatim_payload(
            slug=slug,
            name=rec.get("name") or slug,
            country=country,
            source_lang=rec.get("source_lang") or default_source_lang,
            lien=lien,
            cahier_source_pdf_url=source.get("source_url") or "",
            cahier_source_kind=cahier_source_kind,
        )
        write_verbatim_record(cache_dir / f"{slug}.json", payload)
        written += 1
        prefix = f"{log_prefix}: " if log_prefix else ""
        log(
            f"{prefix}verbatim: {slug} ({len(lien)} chars, "
            f"flag={payload['validation_flag']})"
        )
    return written


def count_verbatim_records(cache_dir: Path, country: str) -> tuple[int, list[dict]]:
    """Return (count, [{slug, chars, flag}, ...]) for verbatim-mode
    records of the given country. Used by audit_<country>_coverage.py."""
    if not cache_dir.exists():
        return 0, []
    found: list[dict] = []
    for jp in sorted(cache_dir.glob("*.json")):
        if jp.name.startswith(("_", "manifest")):
            continue
        try:
            rec = json.loads(jp.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if rec.get("country") != country:
            continue
        if rec.get("mode") != "verbatim":
            continue
        found.append({
            "slug": rec.get("slug", ""),
            "chars": rec.get("verbatim_chars", 0),
            "flag": rec.get("validation_flag", ""),
        })
    return len(found), found
