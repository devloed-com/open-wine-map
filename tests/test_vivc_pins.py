"""Curator VIVC pins must land on the passport they describe.

A pin's `_prime` annotation has to be the fetched passport's prime name or
one of its synonyms; otherwise the id points at an unrelated variety and
every grape pill carrying the slug renders that variety's name in brackets
(2026-09-20: `oneca` → 4359 GALVANI on the Navarra card). Runs only when
the raw VIVC caches are present."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_audit():
    spec = importlib.util.spec_from_file_location(
        "audit_vivc_coverage", ROOT / "scripts" / "audit_vivc_coverage.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_check_pins_flags_unrelated_passport(tmp_path: Path):
    audit = _load_audit()
    overrides = tmp_path / "slug_overrides.json"
    overrides.write_text(json.dumps({"entries": {
        "oneca": {"vivc_id": 4359, "_prime": "ONECA"},
        "jaen-blanca": {"vivc_id": 5648, "_prime": "JAEN BLANCO"},
        "terret": {"vivc_id": 12384, "_prime": "TERRET NOIR"},
        "pirene": {"vivc_id": False},
        "schiava": {"vivc_id": False},
        "torrontes": {"vivc_id": 12631, "_prime": "TORRONTES RIOJANO"},
    }}), encoding="utf-8")
    records = [
        {"slug": "oneca", "vivc_id": 4359, "prime_name": "GALVANI", "country": "ITALY",
         "synonyms": [{"name": "86 PIROVANO"}]},
        {"slug": "jaen-blanca", "vivc_id": 5648, "prime_name": "CAYETANA BLANCA",
         "synonyms": [{"name": "JAEN BLANCO"}]},
        {"slug": "terret", "vivc_id": 12397, "prime_name": "TERZI 97- 41", "synonyms": []},
        {"slug": "pirene", "vivc_id": 19884, "prime_name": "CASTEL 13316", "synonyms": []},
        {"slug": "schiava", "vivc_id": None, "prime_name": None, "synonyms": []},
        {"slug": "torrontes", "vivc_id": 12631, "prime_name": "", "synonyms": []},
    ]
    kinds = {f["slug"]: f["kind"] for f in audit.check_pins(records, overrides)}
    assert kinds == {
        "oneca": "mismatch", "terret": "stale", "pirene": "skip-stale",
        "torrontes": "empty-passport",
    }


def test_live_pins_consistent():
    audit = _load_audit()
    if not audit.BY_SLUG.exists() or not audit.OVERRIDES.exists():
        pytest.skip("raw/vivc caches not present")
    findings = audit.check_pins(audit._load_records())
    assert findings == [], [
        f"{f['slug']}: {f['kind']} pin={f['pin']} passport={f.get('prime')!r}" for f in findings
    ]
