"""Search-only forms for the region facet.

The facet key and the label on screen stay the regulator's native string
(Μακεδονία, Тракийска низина, Piemonte); a visitor typing "Macedonia",
"Piedmont" or "makedonia" still has to find the row. Three form sources,
none of them displayed:

- the curated table `region_search_terms.json` (Wikidata labels in the four
  UI languages, CC0, one item URL per entry — refreshed by
  `scripts/refresh_region_search_terms.py`);
- the romanisations of a Greek or Cyrillic label (`_lib/romanise.py`);
- for the French bassins, whose label IS localised through gettext, every
  locale's label plus the INAO key, so "bourgogne" works on the English map
  and "burgundy" on the French one.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from unidecode import unidecode

from .i18n import load_translations
from .romanise import bg_streamlined, elot743, search_key

TABLE_PATH = Path(__file__).with_name("region_search_terms.json")
UI_LOCALES = ("en", "fr", "es", "nl")


def load_curated(path: Path = TABLE_PATH) -> dict[str, tuple[list[str], list[str]]]:
    """{facet key -> (forms, labels)}: every search form of the entry and the
    subset that are item labels (the only forms a suggestion row may echo)."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        key: (
            [f for f in (entry.get("forms") or []) if f],
            [f for f in (entry.get("labels") or []) if f],
        )
        for key, entry in data.items()
        if not key.startswith("__") and isinstance(entry, dict)
    }


def _script(text: str) -> str:
    if any("Ͱ" <= c <= "Ͽ" or "ἀ" <= c <= "῿" for c in text):
        return "greek"
    if any("Ѐ" <= c <= "ӿ" for c in text):
        return "cyrillic"
    return "latin"


def derived_forms(label: str) -> list[str]:
    script = _script(label)
    if script == "greek":
        return [elot743(label), unidecode(label)]
    if script == "cyrillic":
        return [bg_streamlined(label), unidecode(label)]
    return []


def fr_bassin_forms() -> dict[str, list[str]]:
    from .map_template import build_region_labels

    out: dict[str, list[str]] = {}
    for locale in UI_LOCALES:
        labels = build_region_labels(load_translations(locale).gettext)
        for key, label in labels.items():
            out.setdefault(key, []).append(label)
    return out


def region_search_terms_for(regions: Iterable[str]) -> dict[str, dict[str, list[str]]]:
    """{facet key -> {"forms": […], "labels": […]}} for the given region keys.
    `forms` are deduped after the search normalisation but NOT against the
    key: the French gettext label "Bourgogne" folds to the same key as the
    INAO "BOURGOGNE", and it is the proper-cased form the row must echo when
    a visitor types it on the English map (the index appends the raw key
    last, so a form wins the tie). `labels` are the echo-able subset: item
    labels and gettext labels, never an alias or a derived romanisation."""
    curated = load_curated()
    bassins = fr_bassin_forms()
    out: dict[str, dict[str, list[str]]] = {}
    for region in regions:
        if not region:
            continue
        cur_forms, cur_labels = curated.get(region, ([], []))
        echo = {search_key(f) for f in cur_labels} | {search_key(f) for f in bassins.get(region, [])}
        seen: set[str] = set()
        keep: list[str] = []
        for form in cur_forms + bassins.get(region, []) + derived_forms(region):
            key = search_key(form)
            if key and key not in seen:
                seen.add(key)
                keep.append(form)
        if keep:
            out[region] = {
                "forms": keep,
                "labels": [f for f in keep if search_key(f) in echo],
            }
    return out
