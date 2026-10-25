"""The `shared` list of scripts/audit_grape_identity.py: two slugs VIVC files
under one number on one card, read from the build, with the reason table
scripts/_lib/vivc_shared_pills.json (2026-10-25, the phase H class)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

_spec = importlib.util.spec_from_file_location("agi", ROOT / "scripts" / "audit_grape_identity.py")
agi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(agi)


def _build(tmp: Path) -> Path:
    data = tmp / "data"
    (data / "d" / "en").mkdir(parents=True)
    aocs = {
        "chianti": {"country": "it", "grapes_principal": ["sangiovese"], "grapes_accessory": ["prugnolo"]},
        "duriense": {"country": "pt", "grapes_principal": ["marufo", "mourisco"]},
        "chianti-rufina": {"country": "it", "parent_slug": "chianti",
                           "grapes_principal": ["sangiovese", "prugnolo"]},
    }
    (data / "aocs.en.0000.js").write_text("window.__OWM_DATA=" + json.dumps({"aocs": aocs}) + ";")
    (data / "d" / "en" / "chianti.json").write_text(json.dumps(
        {"grape_names": {"sangiovese": "Sangiovese", "prugnolo": "Prugnolo gentile"}}))
    return data


def test_pairs_are_grouped_per_card_and_ruled_by_the_table(tmp_path):
    data = _build(tmp_path)
    vids = {"sangiovese": 10680, "prugnolo": 10680, "marufo": 8086, "mourisco": 8086}
    table = {"countries": {"pt": {"decision": "keep", "reason": "the caderno lists both"}}}
    out = agi.shared_vivc_pills(data, vids=vids, table=table)
    by_pair = {"+".join(e["pair"]): e for e in out}
    assert set(by_pair) == {"prugnolo+sangiovese", "marufo+mourisco"}
    # the sub-denomination repeats its parent's roster and is not counted
    assert by_pair["prugnolo+sangiovese"]["cards"] == ["chianti"]
    assert by_pair["prugnolo+sangiovese"]["class"] == "review"
    assert by_pair["prugnolo+sangiovese"]["spellings"] == ["Prugnolo gentile / Sangiovese"]
    assert by_pair["marufo+mourisco"]["class"] == "keep"
    assert out[0]["class"] == "review"


def test_a_pair_entry_beats_a_country_rule_and_a_country_rule_needs_every_card():
    table = {"pairs": {"a+b": {"decision": "keep", "reason": "x"}},
             "countries": {"pt": {"decision": "keep", "reason": "y"}}}
    assert agi.shared_decision(("a", "b"), {"es"}, table)["reason"] == "x"
    assert agi.shared_decision(("c", "d"), {"pt"}, table)["reason"] == "y"
    assert agi.shared_decision(("c", "d"), {"pt", "es"}, table) is None


def test_the_checked_in_table_is_well_formed():
    table = agi.load_shared_table()
    for key, e in (table.get("pairs") or {}).items():
        assert key == "+".join(sorted(key.split("+"))), key
        assert e["decision"] == "keep" and e["reason"] and e["source"] and e["verified"], key
    for cc, e in (table.get("countries") or {}).items():
        assert e["decision"] == "keep" and e["reason"] and e["verified"], cc
