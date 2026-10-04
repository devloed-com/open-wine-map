"""INAO aires-communes lookup (scripts/_lib/aires.py): a SIQO typo must bind
to the near-identical CSV name, never to the appellation it happens to start
with."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.aires import _near_exact, lookup  # noqa: E402

_AIRES = {
    "calvados": {"2375": {"14001", "76276"}},
    "calvadosdomfrontais": {"1362": {"61145"}},
    "calvadospaysdauge": {"1361": {"14002"}},
    "champagne": {"1": {"51001"}},
}


def test_siqo_typo_binds_to_the_near_identical_csv_name_not_the_prefix():
    # "Calvados Domfontais" (SIQO) vs "Calvados Domfrontais" (CSV, cahier,
    # register): the substring fallback used to hand it the whole Calvados aire.
    assert lookup(_AIRES, "Calvados Domfontais") == {"61145"}
    assert lookup(_AIRES, "Calvados") == {"14001", "76276"}
    assert lookup(_AIRES, "Calvados Domfrontais") == {"61145"}


def test_substring_fallback_still_serves_a_missing_sub_name():
    assert lookup(_AIRES, "Champagne grand cru") == {"51001"}


def test_two_near_names_bind_nothing():
    aires = {"abcdefghij1": {"a": {"1"}}, "abcdefghij2": {"b": {"2"}}}
    assert _near_exact("abcdefghij3", aires) is None
    assert lookup(aires, "abcdefghij3") is None


def test_record_inside_a_longer_csv_name_binds_only_as_an_alias_part():
    """`_CSV_ALIAS_KEYS` is filled by load_aires from the raw labels; simulate
    it here. "Pouilly-sur-Loire" is an alias of the combined CSV label and
    binds; the new AOC "Montpeyroux" is only the trailing word of the DGC aire
    "Languedoc Montpeyroux" and must not take its two communes."""
    import _lib.aires as mod

    aires = {
        "pouillyfumeoublancfumedepouillyetpouillysurloire": {"7": {"58001"}},
        "languedocmontpeyroux": {"1256": {"34011", "34173"}},
    }
    saved = dict(mod._CSV_ALIAS_KEYS)
    mod._CSV_ALIAS_KEYS.clear()
    mod._CSV_ALIAS_KEYS.update({
        "pouillyfumeoublancfumedepouillyetpouillysurloire": {
            "pouillyfume", "blancfumedepouilly", "pouillysurloire",
        },
        "languedocmontpeyroux": set(),
    })
    try:
        assert lookup(aires, "Pouilly-sur-Loire") == {"58001"}
        assert lookup(aires, "Pouilly-Fumé ou Blanc Fumé de Pouilly") == {"58001"}
        assert lookup(aires, "Montpeyroux") is None
        assert lookup(aires, "Languedoc Montpeyroux") == {"34011", "34173"}
    finally:
        mod._CSV_ALIAS_KEYS.clear()
        mod._CSV_ALIAS_KEYS.update(saved)
