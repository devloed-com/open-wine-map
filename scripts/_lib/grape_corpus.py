"""Cross-country grape-slug inventory over the FR / ES / PT / IT corpora.

Walks `raw/inao/cahier-extracted/`, `raw/es/pliegos-extracted/`,
`raw/pt/cadernos-extracted/`, `raw/it/disciplinari-extracted/` and
`raw/it/masaf-disciplinari-extracted/` (the stage-02f MASAF sidecars —
their grapes never reach the doc-unico extractions, which stay stubs)
once and exposes three derived views that the downstream stages share:

- `collect_grape_slugs()` — full per-slug record: `{name, by_lang}`
  where `by_lang` is a `{country_code: count}` map. Single source of
  truth.
- `per_slug_display_name()` — legacy `{slug: display_name}` view (the
  shape 02b/grapes and 02g/VIVC consumed before this module existed).
- `per_slug_dominant_lang()` — `{slug: dominant_country_code}` where the
  dominant country is whichever corpus mentions the slug most often.
  Ties break alphabetical (`es` < `fr` < `pt`).

The dominant-cahier-language index drives the Wikipedia-source
preference chain in the new `02b_translate_grapes.py` and the locale
fallback in stage 04.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
_SOURCES: tuple[tuple[str, Path], ...] = (
    ("fr", ROOT / "raw" / "inao" / "cahier-extracted"),
    ("es", ROOT / "raw" / "es" / "pliegos-extracted"),
    ("pt", ROOT / "raw" / "pt" / "cadernos-extracted"),
    ("it", ROOT / "raw" / "it" / "disciplinari-extracted"),
    ("it", ROOT / "raw" / "it" / "masaf-disciplinari-extracted"),
    ("at", ROOT / "raw" / "at" / "dokumente-extracted"),
    ("de", ROOT / "raw" / "de" / "dokumente-extracted"),
    ("si", ROOT / "raw" / "si" / "dokumenti-extracted"),
    # National-spec sidecars (stage 02f) carry the grape rosters for the
    # grandfathered SI/HR wines whose EU-OJ document was never published —
    # the dokumenti-extracted stubs have none. Mirrors the IT MASAF entry.
    ("si", ROOT / "raw" / "si" / "specifikacije-extracted"),
    ("hr", ROOT / "raw" / "hr" / "dokumenti-extracted"),
    ("hr", ROOT / "raw" / "hr" / "specifikacije-extracted"),
    ("ro", ROOT / "raw" / "ro" / "dokumente-extracted"),
    ("bg", ROOT / "raw" / "bg" / "dokumenti-extracted"),
    ("gr", ROOT / "raw" / "gr" / "dokumenti-extracted"),
    ("sk", ROOT / "raw" / "sk" / "dokumenty-extracted"),
    ("cz", ROOT / "raw" / "cz" / "dokumenty-extracted"),
    ("ch", ROOT / "raw" / "ch" / "dokumente-extracted"),
)


def collect_grape_slugs() -> dict[str, dict]:
    """Return `{slug: {"name": display_name, "by_lang": {lang: count}}}`.

    `display_name` is the first occurrence encountered across the FR →
    ES → PT → IT walk; good enough for VIVC search (which is
    diacritic-tolerant) and for the Wikipedia fallback (which normalises
    via the existing slug-to-title path).
    """
    out: dict[str, dict] = {}
    for lang, src in _SOURCES:
        if not src.exists():
            continue
        for jp in src.glob("*.json"):
            if jp.name.startswith("_"):
                continue
            rec = json.loads(jp.read_text(encoding="utf-8"))
            for d in (rec.get("grapes") or {}).get("details") or []:
                s = d.get("slug")
                if not s:
                    continue
                entry = out.setdefault(
                    s,
                    {"name": d.get("name", s), "by_lang": Counter()},
                )
                entry["by_lang"][lang] += 1
    for entry in out.values():
        entry["by_lang"] = dict(entry["by_lang"])
    return out


def per_slug_display_name(corpus: dict[str, dict] | None = None) -> dict[str, str]:
    """Legacy `{slug: display_name}` view."""
    if corpus is None:
        corpus = collect_grape_slugs()
    return {slug: entry["name"] for slug, entry in corpus.items()}


def per_slug_dominant_lang(corpus: dict[str, dict] | None = None) -> dict[str, str]:
    """`{slug: dominant_country_code}`. Ties break alphabetical."""
    if corpus is None:
        corpus = collect_grape_slugs()
    out: dict[str, str] = {}
    for slug, entry in corpus.items():
        by_lang = entry["by_lang"]
        if not by_lang:
            continue
        out[slug] = sorted(by_lang.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return out
