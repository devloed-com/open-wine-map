"""A FR per-record grape pin (scripts/_lib/fr/grape_context_overrides.json,
grape_lexicon._fr_context_pin, 2026-11-07).

Saint-Mont's rosé clause lists "manseng B" beside "petit manseng B"; the bare
alias binds Manseng noir, the record's adaptation variety ("manseng N"). The
pin reads the white Manseng left — Gros Manseng — on that record only.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import grape_entity  # noqa: E402
from _lib.grape_lexicon import DEFAULT_COLOUR, GRAPE_ALIAS, fr_context_pins, parse_grapes  # noqa: E402

ROSE = ("b) Vins rosés\n- cépage principaux : tannat N, cabernet-sauvignon N, fer N\n"
        "- cépages accessoires : cabernet franc N, merlot N, tardif N, manseng B, arrufiac B, "
        "petit courbu B, courbu B, petit manseng B\n"
        "- variété d'intérêt à fin d'adaptation : manseng N, sous réserve de la signature d’une convention.\n")


def _roles(text):
    return {t["slug"]: t["role"] for t in parse_grapes(text)["all"]}


def test_every_pin_names_a_lexicon_slug_and_carries_its_evidence():
    pins = fr_context_pins()
    assert "saint-mont" in pins
    for slug, table in pins.items():
        for surface, pin in table.items():
            assert surface == surface.lower() and " " in surface, surface
            assert pin["slug"] in DEFAULT_COLOUR or pin["slug"] in GRAPE_ALIAS.values(), pin["slug"]
            assert pin.get("reason") and pin.get("source") and pin.get("verified")


def test_saint_mont_reads_manseng_b_as_gros_manseng_and_keeps_manseng_noir():
    grape_entity.set_pliego_context("saint-mont")
    try:
        roles = _roles(ROSE)
    finally:
        grape_entity.set_pliego_context(None)
    assert roles["gros-manseng"] == "accessory"
    assert roles["manseng-noir"] == "observation"
    assert roles["petit-manseng"] == "accessory"


def test_outside_the_record_the_bare_alias_stands():
    grape_entity.set_pliego_context(None)
    roles = _roles(ROSE)
    assert "gros-manseng" not in roles
    assert roles["manseng-noir"] in ("accessory", "observation")
