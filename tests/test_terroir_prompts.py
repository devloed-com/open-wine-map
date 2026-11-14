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
    from _lib import terroir_prompts as tp
    from _lib import terroir_roster as tr
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


# ── the sub-section bullet cap (2026-10-24) ─────────────────────────────────

import re  # noqa: E402
from pathlib import Path  # noqa: E402

from _lib.terroir_prompts import LONG_TEXT_BONUS, LONG_TEXT_CHARS, sub_section_cap  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STAGE_02D = [ROOT / "scripts" / "02d_extract_terroir_facts.py"] + sorted(ROOT.glob("scripts/*/02d_extract_terroir_facts.py"))
BASE_CAPS = (("facteurs_naturels", 5), ("facteurs_humains", 2), ("produit", 2), ("interactions", 1))


def test_cap_is_the_base_up_to_the_threshold():
    for key, base in BASE_CAPS:
        sub = {"key": key, "max_bullets": base}
        assert sub_section_cap(sub, "x" * LONG_TEXT_CHARS) == base
        assert sub_section_cap(sub, "") == base
        assert sub_section_cap(sub, None) == base


def test_a_long_text_raises_the_descriptive_sub_sections_and_never_interactions():
    long_text = "x" * (LONG_TEXT_CHARS + 1)
    raised = {key: sub_section_cap({"key": key, "max_bullets": base}, long_text) for key, base in BASE_CAPS}
    assert raised == {"facteurs_naturels": 7, "facteurs_humains": 4, "produit": 3, "interactions": 1}
    assert LONG_TEXT_BONUS["interactions"] == 0


def test_style_rules_leave_the_allowance_to_the_number():
    assert "extra bullet" not in STYLE_RULES
    assert "already allows for the length of the text" in STYLE_RULES


def test_every_02d_script_sets_the_cap_through_the_helper():
    assert len(STAGE_02D) == 22
    for path in STAGE_02D:
        src = path.read_text(encoding="utf-8")
        assert re.search(r"from _lib\.terroir_prompts import (?:\([^)]*)?\bsub_section_cap\b", src, re.S), path
        assert not re.search(r'(sub|spec)\["max_bullets"\]', src), f"{path}: a cap site bypasses sub_section_cap"
        expected = 1 if path.parent.name == "es" else 2  # live call + the --emit-todo item (ES has no round-trip)
        assert len(re.findall(r"sub_section_cap\(", src)) >= expected, path


# ── the request line, the product topics and the second reading (2026-10-24) ──

from _lib.terroir_prompts import (  # noqa: E402
    _PRODUCT_TOPICS,
    ASK_LINES,
    RETRY_MIN_HITS,
    RETRY_VOCAB,
    ask_line,
    product_topics,
    retry_hits,
    should_retry,
)

SOURCE_LANGS = {"en", "fr", "de", "nl", "es", "it", "pt", "el", "bg", "cs", "sk", "hr", "sl", "hu", "ro"}
NON_FR_02D = [p for p in STAGE_02D if p.parent.name != "scripts"]


def test_every_source_language_has_a_request_line_topics_and_vocabulary():
    assert set(ASK_LINES) == set(_PRODUCT_TOPICS) == set(RETRY_VOCAB) == SOURCE_LANGS
    for lang in SOURCE_LANGS:
        base, again = ASK_LINES[lang]
        assert "{label}" in base and "{label}" in again and base != again
        assert ask_line(lang, "Soils") .count("Soils") == 1
        assert ask_line(lang, "Soils", retry=True) != ask_line(lang, "Soils")
        assert set(RETRY_VOCAB[lang]) == {"produit", "facteurs_naturels"}
        assert all(s.strip() and s == s.lower() for sub in RETRY_VOCAB[lang].values() for s in sub)
        assert "{" not in _PRODUCT_TOPICS[lang] and "}" not in _PRODUCT_TOPICS[lang]


def test_request_line_points_at_the_leading_document_block():
    assert ask_line("en", "Soils") == (
        "Sub-section to process: Soils. Work from the source text given at the very start of this "
        "prompt, before the instructions — read it in full.")
    assert "empty list" in ask_line("en", "Soils", retry=True)
    assert "πριν από τις οδηγίες" in ask_line("el", "X")


def test_product_topics_name_the_wine_types_and_take_a_country_lead():
    assert "tasting note" in product_topics("en")
    assert product_topics("en", "natural acidity").startswith("natural acidity; colours")
    assert product_topics("fr", "") == _PRODUCT_TOPICS["fr"]
    assert "sin nota de cata" in product_topics("es")


def test_should_retry_needs_the_vocabulary_and_only_fires_on_descriptive_sub_sections():
    greek = "Οίνος ερυθρός ξηρός με έντονο χρώμα και αρώματα κόκκινων φρούτων, γλυκός και λιαστός."
    assert len(retry_hits("produit", "el", greek)) >= RETRY_MIN_HITS
    assert should_retry("produit", "el", greek)
    assert not should_retry("produit", "el", "Η ιστορία της περιοχής είναι μακρά.")  # no product words
    assert not should_retry("interactions", "el", greek)  # earned, never retried
    assert not should_retry("facteurs_humains", "el", greek)
    assert not should_retry("produit", "xx", greek)  # unknown language
    assert not should_retry("produit", "el", "")
    assert should_retry("facteurs_naturels", "en", "Chalk soils, a cool maritime climate and south-facing slopes.")
    # German ß and Greek final sigma fold with the text
    assert "süß" in retry_hits("produit", "de", "ein SÜSSER Rotwein mit Säure")


def test_every_non_fr_02d_script_reads_twice_and_asks_for_the_follow_up_round():
    assert len(NON_FR_02D) == 21
    for path in NON_FR_02D:
        src = path.read_text(encoding="utf-8")
        assert src.count("should_retry(") == 1, path
        assert re.search(r'ask_line\((?:"[a-z]{2}"|lang), (?:sub\["label"\]|label), retry=True\)', src), path
        assert re.search(r'ask_line\((?:"[a-z]{2}"|lang), label\)', src), path
        assert "follow_up=True" in src and "follow_ups=True" in src, path
        if path.parent.name != "drinks":  # a drink's product topics are not wine types
            assert "product_topics(" in src, path
        assert "retried_subsections" in src, path
        assert "message below" not in src and "mensaje del usuario" not in src, path
