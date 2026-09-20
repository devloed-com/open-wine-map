"""The decided model configuration (2026-09-14): Sonnet 5 extractor with
thinking off, Opus 5 gate / audit with adaptive thinking, Sonnet 4.6 for
translation and the back-check — and that every stage script asks for its
own stage default rather than the generic one."""
from __future__ import annotations

import re
from pathlib import Path

from _lib import batch, providers

ROOT = Path(__file__).resolve().parents[1]


def test_stage_defaults_are_the_decided_configuration():
    assert providers.stage_default("02d") == ("claude-sonnet-5", "disabled")
    assert providers.stage_default("gate") == ("claude-opus-5", "adaptive")
    assert providers.stage_default("audit") == ("claude-opus-5", "adaptive")
    assert providers.stage_default("02e") == ("claude-sonnet-5", None)
    assert providers.stage_default("backcheck") == ("claude-sonnet-5", None)
    assert providers.stage_default(None) == (providers.DEFAULT_ANTHROPIC_MODEL, None)
    assert batch.default_model("anthropic", "02d") == "claude-sonnet-5"
    assert batch.default_thinking("anthropic", "gate") == "adaptive"
    assert batch.default_model("mistral", "02d") == "mistral-medium-latest"
    assert batch.default_thinking("mistral", "gate") is None


def test_every_02d_script_asks_for_the_02d_stage_default():
    paths = [ROOT / "scripts" / "02d_extract_terroir_facts.py"] + sorted(ROOT.glob("scripts/*/02d_extract_terroir_facts.py"))
    assert len(paths) == 21
    for p in paths:
        src = p.read_text(encoding="utf-8")
        assert 'batch.default_model(args.provider, stage="02d")' in src, p
        assert 'thinking=batch.default_thinking(args.provider, stage="02d")' in src, p
        assert re.search(r'make_provider\(\s*args\.provider, model=args\.model, stage="02d"', src), p


def test_gate_backcheck_and_audit_use_their_stage():
    for name, stage in (("02d_verify_terroir_facts.py", "gate"), ("02e_verify_terroir_facts.py", "backcheck"),
                        ("audit_terroir_facts_llm.py", "audit")):
        src = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert f'stage="{stage}"' in src, name


def test_every_02e_script_resolves_its_model_through_the_02e_stage():
    # Without stage="02e" a script silently takes the generic default and a
    # change to STAGE_DEFAULTS["02e"] changes nothing (2026-09-15).
    scripts = [ROOT / "scripts" / "02e_translate_terroir_facts.py"] + sorted(
        (ROOT / "scripts").glob("*/02e_translate_terroir_facts.py"))
    assert len(scripts) == 21
    for p in scripts:
        src = p.read_text(encoding="utf-8")
        assert src.count('stage="02e"') == 2, p


def test_anthropic_params_carry_the_thinking_mode(monkeypatch):
    monkeypatch.delenv("OWM_BATCH_THINKING", raising=False)
    r = {"custom_id": "x", "system": "s", "user": "u", "max_tokens": 10}
    assert "thinking" not in batch._anthropic_params("m", r, None)
    assert batch._anthropic_params("m", r, "adaptive")["thinking"] == {"type": "adaptive"}
    monkeypatch.setenv("OWM_BATCH_THINKING", "disabled")
    assert batch._anthropic_params("m", r, "adaptive")["thinking"] == {"type": "disabled"}


def test_claude5_models_get_thinking_disabled_when_the_stage_sets_no_mode(monkeypatch):
    monkeypatch.delenv("OWM_BATCH_THINKING", raising=False)
    assert providers.effective_thinking("claude-sonnet-5", None) == "disabled"
    assert providers.effective_thinking("claude-opus-5", "adaptive") == "adaptive"
    assert providers.effective_thinking("claude-sonnet-4-6", None) is None
    r = {"custom_id": "x", "system": "s", "user": "u", "max_tokens": 10}
    assert batch._anthropic_params("claude-sonnet-5", r, None)["thinking"] == {"type": "disabled"}
    assert "thinking" not in batch._anthropic_params("claude-sonnet-4-6", r, None)
    assert batch._anthropic_params("claude-opus-5", r, "adaptive")["thinking"] == {"type": "adaptive"}
