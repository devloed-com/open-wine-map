"""Shared stage-02e translation rules (scripts/_lib/terroir_prompts.py, plan W1 + W5)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from _lib.terroir_prompts import translation_rules, translation_system_prompt
from _lib.translation_glossary import glossary_for

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
COUNTRIES = (
    "at", "be", "bg", "ch", "cy", "cz", "de", "es", "gb", "gr", "hr", "hu", "it", "lu", "mt",
    "nl", "pt", "ro", "si", "sk",
)
ROSTER = "appellation names (Barolo, Soave); grape names (Nebbiolo)"


def _load_script(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("source_lang,target_lang", [("it", "en"), ("el", "nl"), ("bg", "fr"), ("de", "es")])
def test_rules_block_has_no_braces(source_lang, target_lang):
    rules = translation_rules(source_lang, target_lang, proper_nouns=ROSTER)
    assert "{" not in rules and "}" not in rules
    assert rules.startswith("Terminology rules (")
    assert "In this corpus: " + ROSTER in rules


def test_roster_braces_are_neutralised_and_empty_roster_is_fine():
    rules = translation_rules("it", "en", proper_nouns="names {x}")
    assert "{" not in rules and "}" not in rules
    assert "In this corpus" not in translation_rules("it", "en", proper_nouns="")


def test_latin_script_rule_only_for_greek_and_cyrillic_sources():
    latin = "entirely in Latin script"
    assert latin in translation_rules("el", "en", proper_nouns="")
    assert latin in translation_rules("bg", "es", proper_nouns="")
    for src in ("it", "fr", "hu", "de", "hr"):
        assert latin not in translation_rules(src, "en", proper_nouns="")


def test_target_language_is_named_and_w5_rules_present():
    rules = translation_rules("it", "nl", proper_nouns="")
    assert "Translate into Dutch" in rules
    assert "PDO / PGI in their Dutch form" in rules
    assert 'never "Pinot noir N"' in rules
    assert "End every bullet with a period." in rules
    assert "never strengthen them" in rules


def test_glossary_appended_for_en_and_nl_only():
    for target in ("en", "nl"):
        out = translation_system_prompt("BASE", source_lang="it", target_lang=target, proper_nouns="")
        assert out.endswith(glossary_for(target))
    out_es = translation_system_prompt("BASE", source_lang="it", target_lang="es", proper_nouns="")
    assert glossary_for("en") not in out_es and glossary_for("nl") not in out_es
    assert out_es.endswith(translation_rules("it", "es", proper_nouns=""))


def test_output_starts_with_base_prompt():
    base = "You translate short Italian bullets into English.\n\nRules:\n- a\n- b"
    out = translation_system_prompt(base, source_lang="it", target_lang="en", proper_nouns=ROSTER)
    assert out.startswith(base + "\n\n" + "Terminology rules (Italian → English):")
    assert "{" not in out and "}" not in out


@pytest.mark.parametrize("cc", COUNTRIES)
def test_country_script_roster_and_only_flag(cc):
    mod = _load_script(SCRIPTS / cc / "02e_translate_terroir_facts.py", f"owm_02e_{cc}")
    roster = mod.PROPER_NOUNS
    rosters = list(roster.values()) if isinstance(roster, dict) else [roster]
    assert rosters and all(isinstance(r, str) and r for r in rosters)
    for r in rosters:
        assert "{" not in r and "}" not in r
    for attr in ("SYSTEM_PROMPT", "SYSTEM_PROMPT_TEMPLATE", "SYSTEM_PROMPT_NL", "SYSTEM_PROMPT_FR"):
        if hasattr(mod, attr):
            assert "- Preserve " not in getattr(mod, attr)
    assert mod.translation_system_prompt is translation_system_prompt
    args = mod._build_argparser().parse_args(["--only", "a", "--only", "b"])
    assert args.only == ["a", "b"] and args.refresh is False


def test_fr_base_script_builds_through_the_shared_helper():
    mod = _load_script(SCRIPTS / "02e_translate_terroir_facts.py", "owm_02e_fr")
    out = mod.build_system_prompt(source_lang="fr", target_lang="en")
    assert out.startswith("You translate short French bullets")
    assert "- Preserve " not in out
    assert "Terminology rules (French → English):" in out
    assert "Marnes à exogyra virgula" in out and "caillottes" in out
    assert out.endswith(glossary_for("en"))
    args = mod._build_argparser().parse_args(["--only", "chablis"])
    assert args.only == ["chablis"]
