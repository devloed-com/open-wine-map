"""Wiring lint for the validator skills and scripts (docs/plan-validators.md):
every script a skill names exists and parses, every registry command of the
release umbrella points at a real script, CLAUDE.md documents the layer."""
from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

SKILLS = ("validate-cards", "validate-sources", "validate-geometry", "validate-release", "triage-feedback")
SCRIPTS = ("scripts/audit_cards_llm.py", "scripts/audit_source_freshness.py", "scripts/audit_geometry_vs_text.py",
           "scripts/diff_records.py", "scripts/validate_release.py", "scripts/_lib/card_packet.py",
           "scripts/_lib/freshness/__init__.py")


@pytest.mark.parametrize("skill", SKILLS)
def test_skill_exists_with_frontmatter_and_real_script_paths(skill):
    p = ROOT / ".claude" / "skills" / skill / "SKILL.md"
    assert p.exists(), skill
    text = p.read_text(encoding="utf-8")
    assert text.startswith("---\n") and f"name: {skill}" in text and "description:" in text
    for m in re.finditer(r"scripts/[\w/]+\.py", text):
        assert (ROOT / m.group(0)).exists(), f"{skill} names a missing script {m.group(0)}"
    for m in re.finditer(r"\]\((reference/[\w.-]+)\)", text):
        assert (p.parent / m.group(1)).exists(), f"{skill} links a missing {m.group(1)}"


@pytest.mark.parametrize("script", SCRIPTS)
def test_validator_scripts_parse(script):
    ast.parse((ROOT / script).read_text(encoding="utf-8"))


def test_release_registry_points_at_real_scripts():
    spec = importlib.util.spec_from_file_location("validate_release", ROOT / "scripts" / "validate_release.py")
    vr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vr)
    names = [c["name"] for c in vr.CHECKS]
    assert len(names) == len(set(names))
    for c in vr.CHECKS:
        script = next((a for a in c["cmd"] if a.startswith("scripts/")), None)
        if script:
            assert (ROOT / script).exists(), c["name"]
            text = (ROOT / script).read_text(encoding="utf-8")
            if "--strict" in c["cmd"]:
                assert '"--strict"' in text, f"{c['name']}: {script} has no --strict flag"


def test_claude_md_documents_the_validators():
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    for needle in ("audit_cards_llm.py", "audit_source_freshness.py", "audit_geometry_vs_text.py", "validate_release.py", "diff_records.py"):
        assert needle in text, needle
