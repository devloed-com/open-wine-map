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


def test_a_spirit_named_after_a_wine_region_does_not_take_the_wines_aire():
    """Marc de Champagne and Ratafia champenois have no CSV row; the
    contained-name step used to hand them the wine Champagne's 635 communes.
    A contained CSV name that is no wine's stays a bind — the CSV cuts its
    labels at 70 characters, so a long rum name finds its own truncated row,
    and Marc d'Alsace Gewurztraminer finds "Marc d'Alsace"."""
    import _lib.aires as mod

    aires = {
        "champagne": {"1": {"51001"}},
        "marcdalsace": {"2": {"67001"}},
        "languedoc": {"3": {"34001"}},
        "eaudeviedevinoriginairedulanguedocoufinedulanguedocou": {"4": {"34002"}},
    }
    saved = (set(mod._SPIRIT_KEYS), set(mod._WINE_KEYS))
    try:
        # the guard alone: the cited references (aire_references.json, which
        # bind the Champagne spirits to the Champagne aire on purpose) are off
        mod._AIRE_REFERENCES = {}
        mod.register_product_names(
            ["Marc de Champagne ou Marc champenois ou Eau-de-vie de marc champenois",
             "Ratafia de Champagne ou Ratafia champenois",
             "Marc d'Alsace Gewurztraminer",
             "Eau-de-vie de vin originaire du Languedoc ou Fine du Languedoc ou "
             "Eau-de-vie de vin du Languedoc"],
            ["Champagne", "Languedoc", "Alsace ou Vin d'Alsace"],
        )
        assert lookup(aires, "Marc de Champagne ou Marc champenois ou "
                             "Eau-de-vie de marc champenois") is None
        assert lookup(aires, "Ratafia de Champagne ou Ratafia champenois") is None
        assert lookup(aires, "Marc d'Alsace Gewurztraminer") == {"67001"}
        # with the wine "Languedoc" out of the running, its own cut row is the
        # one candidate left
        assert lookup(aires, "Eau-de-vie de vin originaire du Languedoc ou Fine du "
                             "Languedoc ou Eau-de-vie de vin du Languedoc") == {"34002"}
        # a wine keeps the contained-name step
        assert lookup(aires, "Champagne grand cru") == {"51001"}
    finally:
        mod._AIRE_REFERENCES = None
        mod._SPIRIT_KEYS.clear()
        mod._SPIRIT_KEYS.update(saved[0])
        mod._WINE_KEYS.clear()
        mod._WINE_KEYS.update(saved[1])
