"""The whole-card judge's guards: reply parsing, evidence grounding, the
report rows (scripts/audit_cards_llm.py)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

spec = importlib.util.spec_from_file_location("audit_cards_llm", ROOT / "scripts" / "audit_cards_llm.py")
acl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acl)


def test_parse_reply_keeps_only_valid_findings_and_derives_verdict():
    raw = json.dumps({"verdict": "nonsense", "summary": "ok", "findings": [
        {"section": "grapes", "kind": "omission", "severity": "misleads", "tag": "missing-grape", "claim": "x", "evidence": "y", "document": "0", "fix": "z"},
        {"section": "weird", "kind": "error", "severity": "defective", "tag": "not-a-tag", "claim": "a"},
        {"section": "styles", "kind": "guess", "severity": "misleads"},
        "junk",
    ]})
    out = acl.parse_reply("```json\n" + raw + "\n```")
    assert out["verdict"] == "caution"
    assert len(out["findings"]) == 2
    assert out["findings"][0]["document"] == 0 and out["findings"][0]["tag"] == "missing-grape"
    assert out["findings"][1]["section"] == "other" and out["findings"][1]["tag"] == "other"
    assert acl.parse_reply("no json here") is None
    assert acl.parse_reply(json.dumps({"findings": "nope"})) is None


def test_ground_marks_quotes_absent_from_the_documents_unverified():
    docs = [{"text": "La récolte des raisins est assurée sur le territoire de la commune de Pauillac."},
            {"text": "Les vins sont issus des cépages cabernet franc N, merlot N et petit verdot N."}]
    findings = [
        {"kind": "error", "evidence": "sur le territoire de la commune de Pauillac", "document": 0},
        {"kind": "error", "evidence": "merlot N et petit verdot N", "document": 0},   # right text, wrong document → all docs
        {"kind": "error", "evidence": "the moon is made of cheese and the vines grow there", "document": 1},
        {"kind": "unsupported", "evidence": "", "document": None},
    ]
    acl.ground(findings, docs)
    assert findings[0]["verified"] and findings[1]["verified"]
    assert not findings[2]["verified"]
    assert findings[3]["verified"] and findings[3]["grounding"] is None


def test_summary_and_curator_rows():
    rows = [
        {"slug": "a", "country": "es", "status": "ok", "name": "A", "verdict": "caution", "summary": "", "n_findings": 2, "n_misleads": 1, "n_unverified": 0,
         "findings": [
             {"section": "grapes", "kind": "omission", "severity": "misleads", "tag": "missing-grape", "claim": "c", "evidence": "e", "fix": "f", "verified": True},
             {"section": "terroir_facts", "kind": "error", "severity": "misleads", "tag": "sibling-leak", "claim": "c2", "evidence": "e2", "fix": "f2", "verified": True}]},
        {"slug": "b", "country": "fr", "status": "ok", "name": "B", "verdict": "trust", "summary": "", "n_findings": 0, "n_misleads": 0, "n_unverified": 0, "findings": []},
        {"slug": "c", "country": "fr", "status": "error", "error": "boom"},
    ]
    s = acl.summarize(rows)
    assert s["records"] == 2 and s["records_failed"] == 1 and s["records_with_misleads"] == 1
    assert s["by_section"] == {"grapes": 1, "terroir_facts": 1}
    cur = acl.curator_rows(rows)
    assert "### ES" in cur and "`a`" in cur and "missing-grape" in cur
    assert "sibling-leak" not in cur  # fact findings go to the feedback sidecars, not CURATOR_TODO
    md = acl.markdown_report(s, rows, title="t")
    assert "do-not-trust" not in md and "| grapes | 1 |" in md


def test_stratified_sample_spreads_over_countries():
    cands = [(f"fr{i}", {"country": "fr", "geom_source": "parcellaire"}) for i in range(50)]
    cands += [(f"es{i}", {"country": "es", "geom_source": "mapa-zone"}) for i in range(5)]
    picked = acl.stratified_sample(cands, 10, seed=1)
    assert len(picked) == 10 and sum(1 for p in picked if p.startswith("es")) == 5


def test_system_prompt_mentions_tags_and_section_restriction():
    s = acl.system_prompt(None)
    assert "sibling-leak" in s and "{tags}" not in s
    assert 'ONLY the card section "grapes"' in acl.system_prompt("grapes")
