"""The exact source text stage 02d graded each country's terroir facts
against, resolved through the country's own 02d module.

Every `scripts/<cc>/02d_extract_terroir_facts.py` owns its source
resolution — the lien (or, for CH/MT/GB, the règlement / spec context
block), the national-spec sidecar fallbacks, and the per-sub-section
Wikipedia hint with its country-specific heading table and character
cap. Anything that wants to re-grade or audit the cached facts (the
provenance post-pass, `audit_terroir_facts.py`) must use precisely that
text, or a perfectly grounded quote reports as eroded. Rather than
mirroring 21 heading tables, this module loads each stage module with
importlib and calls its `enumerate_aocs()` / `collect_targets()` and
`_wiki_hint_for_subsection()`.
"""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
from dataclasses import dataclass
from pathlib import Path

from _lib.terroir_coverage import SourceMatcher

ROOT = Path(__file__).resolve().parents[2]
COUNTRIES = ("fr", "at", "be", "bg", "ch", "cy", "cz", "de", "es", "gb", "gr", "hr", "hu",
             "it", "lu", "mt", "nl", "pt", "ro", "si", "sk")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stage_path(country: str) -> Path:
    if country == "fr":
        return ROOT / "scripts" / "02d_extract_terroir_facts.py"
    return ROOT / "scripts" / country / "02d_extract_terroir_facts.py"


def load_stage(country: str):
    path = stage_path(country)
    spec = importlib.util.spec_from_file_location(f"owm_02d_{country}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@dataclass
class Sources:
    cahier: str
    cahier_sha: str
    wiki_revision: object
    hints: dict[str, str]
    _matcher: SourceMatcher | None = None

    @property
    def matcher(self) -> SourceMatcher:
        if self._matcher is None:
            self._matcher = SourceMatcher(self.cahier)
        return self._matcher


def _wiki_record(mod, rec: dict, lang: str) -> dict:
    slug = rec["slug"]
    if hasattr(mod, "_wiki_record_for"):
        params = inspect.signature(mod._wiki_record_for).parameters
        return mod._wiki_record_for(slug, lang) if "lang" in params else mod._wiki_record_for(slug)
    wiki_path = mod.WIKI_AOCS / f"{slug}.json"
    if not wiki_path.exists():
        return {}
    try:
        return json.loads(wiki_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def _hints(mod, wiki: dict, lang: str, sub_keys: list[str]) -> dict[str, str]:
    fn = mod._wiki_hint_for_subsection
    if "lang" in inspect.signature(fn).parameters:
        return {k: fn(wiki, lang, k) for k in sub_keys}
    return {k: fn(wiki, k) for k in sub_keys}


def resolve_sources(country: str) -> dict[str, Sources]:
    """slug → the exact cahier text + per-sub-section wiki hints stage 02d
    grades against for this country, built through the stage's own code."""
    mod = load_stage(country)
    out: dict[str, Sources] = {}
    if country == "fr":
        for job in mod.enumerate_aocs():
            out[job["slug"]] = Sources(
                job["lien"], job["lien_sha"],
                job["wiki_meta"]["wiki_source_revision"], dict(job["wiki_hints"]),
            )
        return out
    sub_keys = [s["key"] for s in mod.SUBSECTIONS]
    default_lang = getattr(mod, "SOURCE_LANG", None) or "fr"
    for rec in mod.collect_targets():
        lang = rec.get("source_lang") or default_lang
        if "_cahier_ctx" in rec:
            cahier = rec["_cahier_ctx"] or ""
            wiki = rec.get("_wiki_record") or {}
        else:
            cahier = rec.get("link_to_terroir") or ""
            wiki = _wiki_record(mod, rec, lang)
        out[rec["slug"]] = Sources(
            cahier, _sha(cahier), wiki.get("revision") if wiki else None,
            _hints(mod, wiki, lang, sub_keys),
        )
    return out
