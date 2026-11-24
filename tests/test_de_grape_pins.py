"""German readings of a variety name that is another cultivar elsewhere
(scripts/_lib/de/grape_pins.py).

VIVC flags ROTER MUSKATELLER as the official name in Germany on MUSCAT A
PETITS GRAINS ROSES #8186 and in Austria on MUSCAT A PETITS GRAINS ROUGES
#8248 (both passports read live 2026-11-24); the lexicon's alias is the red
one, which every German list had shown."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.de.grape_pins import DE_NAME_PINS, german_match  # noqa: E402
from _lib.grape_entity import exact_match, match_variety  # noqa: E402

ROSES, ROUGES = "muscat-a-petits-grains-roses", "muscat-a-petits-grains-rouges"


def test_the_german_reading_is_the_pink_muscat_and_keeps_the_printed_name():
    hit = german_match(match_variety)("Roter Muskateller")
    assert (hit.slug, hit.name, hit.colour) == (ROSES, "Roter Muskateller", "rose")
    assert german_match(exact_match)("Roter Muskateller").slug == ROSES


def test_the_lexicon_default_is_untouched():
    """Outside the German stages the name stays the red Muscat — the Austrian
    official name and the Swiss federal list's «Muscat rouge à petits grains»."""
    assert match_variety("Roter Muskateller").slug == ROUGES


def test_other_names_pass_through_and_wrapping_twice_is_one_wrap():
    match = german_match(match_variety)
    assert german_match(match) is match
    assert match("Gelber Muskateller").slug == match_variety("Gelber Muskateller").slug
    assert match("Blauer Muskateller").slug == "muscat-a-petits-grains-noirs"
    assert match("kein Rebsortenname xyz") is None


def test_every_pin_binds():
    for surface, target in DE_NAME_PINS.items():
        assert exact_match(target) is not None, f"{surface}: {target} binds nothing"


def _grapes(path: Path) -> list[dict]:
    rec = json.loads(path.read_text(encoding="utf-8"))
    g = rec.get("grapes")
    return [x for x in ((g.get("details") if isinstance(g, dict) else g) or []) if isinstance(x, dict)]


def test_no_german_record_shows_the_red_muscat_for_roter_muskateller():
    dirs = [ROOT / "raw" / "de" / "dokumente-extracted",
            ROOT / "raw" / "de" / "produktspezifikationen-extracted"]
    if not all(d.exists() for d in dirs):
        pytest.skip("DE records not extracted")
    seen = 0
    for d in dirs:
        for path in d.glob("*.json"):
            if path.name.startswith("_") or path.stem == "manifest":
                continue
            for g in _grapes(path):
                if (g.get("name") or "").strip().lower() == "roter muskateller":
                    seen += 1
                    assert g["slug"] == ROSES, f"{path.name}: {g}"
    assert seen >= 30


def test_the_swiss_lists_keep_the_red_muscat():
    d = ROOT / "raw" / "ch" / "dokumente-extracted"
    if not (d / "glarus.json").exists():
        pytest.skip("CH records not extracted")
    for slug in ("glarus", "schwyz", "zurich", "zurichsee"):
        hits = [g for g in _grapes(d / f"{slug}.json") if g.get("name") == "Roter Muskateller"]
        assert hits and all(g["slug"] == ROUGES for g in hits), slug
