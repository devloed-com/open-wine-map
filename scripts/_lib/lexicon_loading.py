"""Grape + style lexicon loading / merging + VIVC + grapes_info assembly (stage 04).

Moved verbatim out of 04_build_maps.py — no behaviour change. Self-contained:
no stage-04 function dependencies. The public loaders + `_latin_form_or_empty`
(used by the aocs-blob phase for grape_names_latin) are imported back into 04.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from _lib.grape_wiki_identity import passport_match_is_stale
from _lib.script_display import latin_name, romanise_name
from _lib.wiki import is_grape_summary

ROOT = Path(__file__).resolve().parents[2]
LEXICON_DIR = ROOT / "raw" / "wikipedia" / "grapes"
GRAPE_TRANSLATIONS_DIR = ROOT / "raw" / "translations" / "grapes"
VIVC_BY_SLUG = ROOT / "raw" / "vivc" / "by-slug"
STYLE_LEXICON_DIR = ROOT / "raw" / "wikipedia" / "styles"
STYLE_TRANSLATIONS_DIR = ROOT / "raw" / "translations" / "styles"
_DISAMBIG_SUFFIX = re.compile(r"\s*\([^)]*\)\s*$")


def load_grape_lexicon(lang: str, max_chars: int = 280) -> dict:
    """Load Wikipedia grape data for a locale; returns {slug: {name, extract?,
    page_url?, revision_id?, thumbnail?}} for any entry that has at least a
    `wikipedia_title` (so a localised display name is available even when
    the article summary is filtered out). Truncates `extract` to ~max_chars
    at the nearest sentence boundary when present.

    Wikipedia titles often include a parenthetical disambiguator —
    "Pinot noir (cépage)", "Mauzac (grape)" — which is article-DB hygiene,
    not how the variety is referenced in the wine world. Strip it for
    display so the chip reads cleanly."""
    lang_dir = LEXICON_DIR / lang
    if not lang_dir.exists():
        return {}
    out: dict[str, dict] = {}
    for f in lang_dir.glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("missing") or d.get("error"):
            continue
        title = (d.get("wikipedia_title") or "").strip()
        if not title:
            continue
        display_name = _DISAMBIG_SUFFIX.sub("", title).strip() or title
        entry: dict = {
            "name": display_name,
            "page_url": d.get("page_url"),
        }
        extract = (d.get("extract") or "").strip()
        if extract and is_grape_summary(lang, d.get("description", ""), extract):
            if len(extract) > max_chars:
                cut = extract[:max_chars].rsplit(". ", 1)[0]
                extract = cut + ("." if not cut.endswith(".") else "") + " […]"
            entry["extract"] = extract
            entry["revision_id"] = d.get("revision_id")
            if d.get("thumbnail"):
                entry["thumbnail"] = d.get("thumbnail")
        out[d["slug"]] = entry
    return out


def merge_grape_lexicon(lang_lex: dict, fr_lex: dict) -> dict:
    """Legacy FR-fallback merge. Retained for the styles path which still
    uses it; the grapes path now goes through `build_grapes_info()`."""
    if lang_lex is fr_lex:
        return lang_lex
    out: dict[str, dict] = {}
    for slug, fr_entry in fr_lex.items():
        local = lang_lex.get(slug)
        if local is None:
            merged = dict(fr_entry)
            merged["lang_fallback"] = True
            out[slug] = merged
        else:
            merged = dict(local)
            if "extract" not in merged and "extract" in fr_entry:
                merged["extract"] = fr_entry["extract"]
                if "thumbnail" not in merged and "thumbnail" in fr_entry:
                    merged["thumbnail"] = fr_entry["thumbnail"]
                merged["lang_fallback"] = True
            out[slug] = merged
    for slug, local in lang_lex.items():
        out.setdefault(slug, local)
    return out


_VIVC_BY_SLUG_CACHE: dict[str, dict] | None = None


def _load_vivc_by_slug() -> dict[str, dict]:
    """`{slug: {canonical_name, vivc_id, vivc_url}}` from raw/vivc/by-slug/."""
    global _VIVC_BY_SLUG_CACHE
    if _VIVC_BY_SLUG_CACHE is not None:
        return _VIVC_BY_SLUG_CACHE
    out: dict[str, dict] = {}
    if not VIVC_BY_SLUG.exists():
        _VIVC_BY_SLUG_CACHE = out
        return out
    for f in VIVC_BY_SLUG.glob("*.json"):
        rec = json.loads(f.read_text(encoding="utf-8"))
        prime = (rec.get("prime_name") or "").strip()
        vid = rec.get("vivc_id")
        if not prime or not isinstance(vid, int):
            continue
        # str.title() handles apostrophes correctly ("D'AUNIS" → "D'Aunis"),
        # which a per-token .capitalize() does not ("D'aunis").
        canonical = prime.title()
        out[rec["slug"]] = {
            "canonical_name": canonical,
            "vivc_id": vid,
            "vivc_url": rec.get("source_url"),
        }
    _VIVC_BY_SLUG_CACHE = out
    return out


_VIVC_COLOUR_BY_SLUG_CACHE: dict[str, str] | None = None


def _load_vivc_colour_by_slug() -> dict[str, str]:
    """`{slug: 'blanc'|'gris'|'noir'|'rose'}` from raw/vivc/by-slug/<slug>.json
    `color` (UPPERCASE NOIR/BLANC/GRIS/ROSE). Berry colour — not a wine style.
    VIVC carries colours absent from the curated DEFAULT_COLOUR table
    (nebbiolo, chasselas, …), so it is the gap-filler for the style floor.
    Kept separate from `_load_vivc_by_slug` so that function's return shape
    (consumed by `facets`) is untouched."""
    global _VIVC_COLOUR_BY_SLUG_CACHE
    if _VIVC_COLOUR_BY_SLUG_CACHE is not None:
        return _VIVC_COLOUR_BY_SLUG_CACHE
    out: dict[str, str] = {}
    _MAP = {"NOIR": "noir", "BLANC": "blanc", "GRIS": "gris", "ROSE": "rose"}
    if VIVC_BY_SLUG.exists():
        for f in VIVC_BY_SLUG.glob("*.json"):
            rec = json.loads(f.read_text(encoding="utf-8"))
            colour = _MAP.get((rec.get("color") or "").strip().upper())
            slug = rec.get("slug")
            if colour and slug:
                out[slug] = colour
    _VIVC_COLOUR_BY_SLUG_CACHE = out
    return out


def _load_native_grape(lang: str, slug: str, max_chars: int = 280) -> dict | None:
    """Native Wikipedia entry for (slug, lang), or None when missing/empty.
    Returns the trimmed entry with name, extract, page_url, revision_id,
    thumbnail, matched_via."""
    f = LEXICON_DIR / lang / f"{slug}.json"
    if not f.exists():
        return None
    d = json.loads(f.read_text(encoding="utf-8"))
    if d.get("missing") or d.get("error"):
        return None
    # an article found through a VIVC passport the slug no longer has
    # (Pugnitello's Montepulciano, Picardan's Bourboulenc) is not its own
    if passport_match_is_stale(d, slug):
        return None
    title = (d.get("wikipedia_title") or "").strip()
    extract = (d.get("extract") or "").strip()
    if not extract or not is_grape_summary(lang, d.get("description", ""), extract):
        return None
    display = _DISAMBIG_SUFFIX.sub("", title).strip() if title else slug
    if len(extract) > max_chars:
        cut = extract[:max_chars].rsplit(". ", 1)[0]
        extract = cut + ("." if not cut.endswith(".") else "") + " […]"
    out: dict = {
        "name": display or slug,
        "extract": extract,
        "page_url": d.get("page_url"),
        "revision_id": d.get("revision_id"),
        "matched_via": d.get("matched_via") or "primary",
    }
    if d.get("thumbnail"):
        out["thumbnail"] = d["thumbnail"]
    return out


def _translation_source_stands(d: dict, slug: str) -> bool:
    """A translated extract is only as good as the article it translates: it
    is withheld when the slug's source-locale entry is no longer that article
    — found through a VIVC passport the slug has lost, re-fetched as missing,
    or re-fetched as another title. An older revision of the same article
    stands (02b-translate re-translates it in its own time)."""
    src = LEXICON_DIR / str(d.get("source_lang") or "") / f"{slug}.json"
    if not d.get("source_lang") or not src.exists():
        return True
    try:
        source = json.loads(src.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return True
    if source.get("missing") or source.get("error") or passport_match_is_stale(source, slug):
        return False
    was, now = d.get("source_wikipedia_title"), source.get("wikipedia_title")
    return not (was and now and was != now)


def _load_translated_grape(lang: str, slug: str, max_chars: int = 280) -> dict | None:
    f = GRAPE_TRANSLATIONS_DIR / lang / f"{slug}.json"
    if not f.exists():
        return None
    d = json.loads(f.read_text(encoding="utf-8"))
    extract = (d.get("extract") or "").strip()
    if not extract:
        return None
    if not _translation_source_stands(d, slug):
        return None
    if len(extract) > max_chars:
        cut = extract[:max_chars].rsplit(". ", 1)[0]
        extract = cut + ("." if not cut.endswith(".") else "") + " […]"
    return {
        "extract": extract,
        "source_lang": d.get("source_lang"),
        "page_url": d.get("source_page_url"),
        "name": (d.get("source_wikipedia_title") or slug).strip() or slug,
        "translator": d.get("translator"),
        "translator_kind": d.get("translator_kind"),
    }


def _corpus_grape_names() -> dict[str, str]:
    """Per-slug regulator spelling from the corpus (`grape_corpus.pick_label`:
    the spelling that writes the slug, else the most frequent one, colour
    codes and line-break hyphens dropped), e.g. `cot → 'cot'`, `malbec →
    'malbec'`, `mancin → 'mancin'`. Used as the canonical sidebar / pill
    label so three different slugs sharing a Wikipedia article (Cot ↔
    Malbec via vivc, plus a misattributed Mancin) read as their three
    distinct cahier names — not three identical "Malbec" rows."""
    from _lib.grape_corpus import collect_grape_slugs as _c  # noqa: PLC0415
    return {slug: entry["name"] for slug, entry in _c().items() if entry.get("name")}


_CORPUS_GRAPE_NAMES: dict[str, str] | None = None


def _corpus_name_for(slug: str) -> str | None:
    global _CORPUS_GRAPE_NAMES
    if _CORPUS_GRAPE_NAMES is None:
        _CORPUS_GRAPE_NAMES = _corpus_grape_names()
    return _CORPUS_GRAPE_NAMES.get(slug)


def _latin_form_or_empty(name: str) -> str:
    """The Latin form of a Greek or Cyrillic spelling, for the pill's bracket:
    the national standard — ELOT 743, the Bulgarian Streamlined System — with
    the regulator's colour code dropped; "" for a name in Latin script. Until
    2026-11-17 this was unidecode, a mechanical ASCII fold ("Atheri B" for
    Αθήρι Β, "Akheloi" for Ахелой), returned for every accented Latin name
    too (`_lib/script_display.py` has the rules)."""
    return romanise_name(name)


def _override_name_with_corpus(entry: dict, slug: str) -> None:
    """Give `entry` the regulator's spelling as `name` — after
    `_load_native_grape` it is the Wikipedia article title, which stays in
    `wikipedia_title` for the tooltip header — and, for a Greek or Cyrillic
    spelling, the Latin form interface text leads with as `name_latin`: the
    catalogue's name (the VIVC prime) where one is resolved, else the national
    standard."""
    cahier = _corpus_name_for(slug)
    if not cahier:
        return
    if "wikipedia_title" not in entry and entry.get("name"):
        entry["wikipedia_title"] = entry["name"]
    entry["name"] = cahier
    latin = latin_name(cahier, entry.get("canonical_name") or "")
    if latin:
        entry["name_latin"] = latin


def build_grapes_info(target_locale: str) -> dict:
    """Per-slug grape data for the target locale's map page.

    Resolution per (slug, target_locale):
      1. Native target-locale Wikipedia entry → `is_translated=false`,
         `source_lang=target_locale`.
      2. Translated cache (`02b_translate_grapes.py`) →
         `is_translated=true`, `source_lang` from the cache record.
      3. Neither → emit `{canonical_name, vivc_id, vivc_url}` only when
         a VIVC record exists; the pill still renders (cahier name +
         optional canonical bracket + VIVC link), just without a tooltip
         body.

    VIVC `canonical_name`/`vivc_id`/`vivc_url` ride alongside the
    Wikipedia entry for every slug that has a resolved VIVC record;
    unresolved/missed slugs simply lack those fields.
    """
    vivc = _load_vivc_by_slug()
    slugs: set[str] = set()
    if (LEXICON_DIR / target_locale).exists():
        slugs.update(p.stem for p in (LEXICON_DIR / target_locale).glob("*.json"))
    if (GRAPE_TRANSLATIONS_DIR / target_locale).exists():
        slugs.update(p.stem for p in (GRAPE_TRANSLATIONS_DIR / target_locale).glob("*.json"))
    slugs.update(vivc.keys())
    # Keep only slugs that the *current* corpus actually emits. Stale
    # Wikipedia / translation cache entries for slugs that no longer
    # appear in the FR/ES/PT extracted JSONs (e.g. `tempranillo-cencibel`
    # after the ES EU-OJ splitter fix) otherwise leak into GRAPES_INFO
    # and reappear in the chip-filter index as ghost entries.
    corpus_names = set(_corpus_grape_names().keys())
    corpus_slugs = corpus_names | set(vivc.keys())
    slugs &= corpus_slugs
    # Every slug a record carries is in the table with its label, tooltip or
    # not: until 2026-11-17 the label was set only beside a tooltip, so 221
    # filter and search labels were the title-cased slug ("Zahringer",
    # "Roussette D Ayze", "Dimyat") and 118 varieties with neither a VIVC
    # record nor an article could not be found by the grape search at all.
    slugs |= corpus_names

    out: dict[str, dict] = {}
    for slug in slugs:
        vivc_fields = vivc.get(slug) or {}
        native = _load_native_grape(target_locale, slug)
        if native is not None:
            entry = {
                **vivc_fields,
                **native,
                "source_lang": target_locale,
                "is_translated": False,
            }
            _override_name_with_corpus(entry, slug)
            out[slug] = entry
            continue
        translated = _load_translated_grape(target_locale, slug)
        if translated is not None:
            entry = {
                **vivc_fields,
                **translated,
                "is_translated": True,
                "matched_via": "translation",
            }
            _override_name_with_corpus(entry, slug)
            out[slug] = entry
            continue
        entry = {**vivc_fields, "is_translated": False, "source_lang": None}
        _override_name_with_corpus(entry, slug)
        if vivc_fields or entry.get("name"):
            out[slug] = entry
    return out


def _truncate_extract(extract: str, max_chars: int) -> str:
    extract = (extract or "").strip()
    if not extract or len(extract) <= max_chars:
        return extract
    cut = extract[:max_chars].rsplit(". ", 1)[0]
    return cut + ("." if not cut.endswith(".") else "") + " […]"


def load_style_lexicon(lang: str, max_chars: int = 320) -> dict:
    """Load wine-style data for a locale; returns
    {slug: {extract, page_url, revision_id, thumbnail?, translation?}}
    for each curated entry that has usable text.

    Native Wikipedia fetches (raw/wikipedia/styles/<lang>/) are preferred.
    When a slug has no native entry in `lang` but a translated entry exists
    (raw/translations/styles/<lang>/), the translation is used and a
    `translation` metadata block is attached so the UI can render the
    "translated from <source-locale> Wikipedia" attribution."""
    out: dict[str, dict] = {}
    lang_dir = STYLE_LEXICON_DIR / lang
    if lang_dir.exists():
        for f in lang_dir.glob("*.json"):
            d = json.loads(f.read_text(encoding="utf-8"))
            if d.get("missing") or d.get("error"):
                continue
            extract = _truncate_extract(d.get("extract") or "", max_chars)
            if not extract:
                continue
            entry: dict = {
                "extract": extract,
                "page_url": d.get("page_url"),
                "revision_id": d.get("revision_id"),
            }
            if d.get("thumbnail"):
                entry["thumbnail"] = d.get("thumbnail")
            out[d["slug"]] = entry

    tx_dir = STYLE_TRANSLATIONS_DIR / lang
    if tx_dir.exists():
        for f in tx_dir.glob("*.json"):
            d = json.loads(f.read_text(encoding="utf-8"))
            slug = d.get("slug") or f.stem
            if slug in out:
                continue  # native fetch wins
            extract = _truncate_extract(d.get("extract") or "", max_chars)
            if not extract:
                continue
            out[slug] = {
                "extract": extract,
                "page_url": d.get("source_page_url") or "",
                "revision_id": d.get("source_revision_id"),
                "translation": {
                    "source_lang": d.get("source_lang") or "",
                    "source_page_url": d.get("source_page_url") or "",
                    "source_wikipedia_title": d.get("source_wikipedia_title") or "",
                    "translator": d.get("translator") or "",
                    "translator_kind": d.get("translator_kind") or "",
                },
            }
    return out


def merge_style_lexicon(lang_lex: dict, fr_lex: dict) -> dict:
    """FR-fallback for slugs the target locale lacks entirely — both as a
    native fetch and as a translation. Used as a last resort so the UI still
    renders something rather than an empty pill."""
    if lang_lex is fr_lex:
        return lang_lex
    out: dict[str, dict] = {}
    for slug, fr_entry in fr_lex.items():
        local = lang_lex.get(slug)
        if local is None:
            merged = dict(fr_entry)
            merged["lang_fallback"] = True
            out[slug] = merged
        else:
            out[slug] = dict(local)
    for slug, local in lang_lex.items():
        out.setdefault(slug, local)
    return out
