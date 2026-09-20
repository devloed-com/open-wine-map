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
