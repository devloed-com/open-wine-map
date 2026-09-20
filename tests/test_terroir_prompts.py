"""Shared extraction-prompt style block (scripts/_lib/terroir_prompts.py)."""
from __future__ import annotations

from _lib.terroir_prompts import STYLE_RULES, with_style_rules

PROMPT = "Intro {wiki_hint}\n\nRules:\n- a\n- b\n\nRéponds UNIQUEMENT en JSON :\n{{\"facts\": []}}"


def test_rules_land_before_the_json_paragraph_and_keep_format_fields():
    out = with_style_rules(PROMPT)
    assert out.endswith("Réponds UNIQUEMENT en JSON :\n{\"facts\": []}".replace("{", "{{").replace("}", "}}"))
    assert out.index(STYLE_RULES) < out.index("Réponds UNIQUEMENT")
    assert "{" not in STYLE_RULES and "}" not in STYLE_RULES
    assert out.format(wiki_hint="x").startswith("Intro x")


def test_dict_prompts_are_handled_per_language():
    out = with_style_rules({"fr": PROMPT, "de": "Kurz.\n\nAntworte NUR in JSON."})
    assert set(out) == {"fr", "de"}
    assert out["de"] == f"Kurz.\n\n{STYLE_RULES}\n\nAntworte NUR in JSON."


def test_single_paragraph_prompt_gets_rules_appended():
    assert with_style_rules("Only one paragraph.") == f"Only one paragraph.\n\n{STYLE_RULES}"


def test_appellation_context_only_for_records_with_sub_denominations(monkeypatch):
    from _lib import terroir_prompts as tp, terroir_roster as tr
    monkeypatch.setattr(tr, "_load", lambda: ({"rioja": ["Rioja Alavesa", "Rioja Alta", "Rioja Oriental"],
                                                "big": [f"Sub {i}" for i in range(9)]},
                                               {"rioja": "Rioja", "big": "Big", "leaf": "Leaf"}, {}))
    tr._load.cache_clear() if hasattr(tr._load, "cache_clear") else None
    ctx = tp.appellation_context("rioja", for_translation=True)
    assert "«Rioja»" in ctx and "3 sub-denominations (Rioja Alavesa, Rioja Alta, Rioja Oriental)" in ctx
    assert "in the translation" in ctx and '"the Rioja appellation"' in ctx
    assert "in the bullet" in tp.appellation_context("rioja", for_translation=False)
    assert tp.appellation_context("leaf", for_translation=True) == ""
    assert "Sub 5 and 3 more" in tp.appellation_context("big", for_translation=True)
    assert tp.with_appellation_context("Translate:\n1. x", "leaf") == "Translate:\n1. x"
    assert tp.with_appellation_context("Translate:\n1. x", "rioja").startswith("Translate:\n1. x\n\nCONTEXT:")
