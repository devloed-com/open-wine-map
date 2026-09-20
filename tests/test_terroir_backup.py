"""Per-run backups of the terroir-fact caches (scripts/_lib/terroir_backup.py),
the rollback (scripts/rollback_terroir_facts.py) and the wiring lint: every
02d / 02e script and post-pass writes the caches through the snapshotting
helpers, never through `cache.write_json` directly."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from _lib import terroir_backup as tb
from _lib import terroir_cache as tc

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    terroir = tmp_path / "terroir-facts"
    trans = tmp_path / "translations"
    backup = tmp_path / "backup"
    for mod in (tb, tc):
        monkeypatch.setattr(mod, "TERROIR", terroir)
        monkeypatch.setattr(mod, "TRANSLATIONS", trans)
    monkeypatch.setattr(tb, "BACKUP_ROOT", backup)
    monkeypatch.setattr(tb, "ROOT", tmp_path)
    monkeypatch.setenv(tb.RUN_ENV, "run-A")
    monkeypatch.setattr(tb, "_run_id", None)
    monkeypatch.setattr(tb, "_done", set())
    terroir.mkdir()
    (terroir / "chablis.json").write_text(json.dumps({"slug": "chablis", "facts": [{"bullet": "old"}]}), encoding="utf-8")
    (trans / "en").mkdir(parents=True)
    (trans / "en" / "chablis.json").write_text(json.dumps({"facts": [{"bullet": "old-en"}]}), encoding="utf-8")
    return tmp_path, terroir, trans, backup


def test_first_write_snapshots_source_and_translations_once(sandbox):
    tmp, terroir, trans, backup = sandbox
    tc.write_source_cache(terroir / "chablis.json", {"slug": "chablis", "facts": [{"bullet": "new"}]})
    tc.write_source_cache(terroir / "chablis.json", {"slug": "chablis", "facts": [{"bullet": "newer"}]})
    tc.write_translation_cache(trans / "en" / "chablis.json", {"facts": [{"bullet": "new-en"}]})
    tc.write_translation_cache(trans / "es" / "chablis.json", {"facts": [{"bullet": "new-es"}]})
    snap = json.loads((backup / "run-A" / "source" / "chablis.json").read_text(encoding="utf-8"))
    assert snap["facts"][0]["bullet"] == "old"                       # the pre-run state, not the intermediate
    assert json.loads((backup / "run-A" / "translations" / "en" / "chablis.json").read_text())["facts"][0]["bullet"] == "old-en"
    assert not (backup / "run-A" / "translations" / "es").exists()   # es did not exist before the run
    m = tb.load_manifest("run-A")
    assert m["slugs"]["chablis"] == {**m["slugs"]["chablis"], "source": True, "translations": ["en"]}
    assert json.loads((terroir / "chablis.json").read_text())["facts"][0]["bullet"] == "newer"


def test_new_slug_is_recorded_as_created(sandbox):
    tmp, terroir, trans, backup = sandbox
    tc.write_source_cache(terroir / "new-aoc.json", {"slug": "new-aoc", "facts": []})
    m = tb.load_manifest("run-A")
    assert m["slugs"]["new-aoc"]["source"] is False and m["slugs"]["new-aoc"]["translations"] == []
    assert not (backup / "run-A" / "source" / "new-aoc.json").exists()


def test_restore_puts_back_overwritten_and_deletes_created(sandbox):
    tmp, terroir, trans, backup = sandbox
    tc.write_source_cache(terroir / "chablis.json", {"slug": "chablis", "facts": [{"bullet": "new"}]})
    tc.write_translation_cache(trans / "es" / "chablis.json", {"facts": [{"bullet": "new-es"}]})
    tc.write_source_cache(terroir / "new-aoc.json", {"slug": "new-aoc", "facts": []})
    dry = tb.restore_slug("chablis", "run-A", dry_run=True)
    assert json.loads((terroir / "chablis.json").read_text())["facts"][0]["bullet"] == "new"
    assert any(p.endswith("terroir-facts/chablis.json") for p in dry["restored"])
    assert any(p.endswith("es/chablis.json") for p in dry["deleted"])
    r = tb.restore_slug("chablis", "run-A")
    assert json.loads((terroir / "chablis.json").read_text())["facts"][0]["bullet"] == "old"
    assert json.loads((trans / "en" / "chablis.json").read_text())["facts"][0]["bullet"] == "old-en"
    assert not (trans / "es" / "chablis.json").exists()
    assert r["missing"] is False
    r2 = tb.restore_slug("new-aoc", "run-A")
    assert not (terroir / "new-aoc.json").exists() and r2["deleted"]
    assert tb.restore_slug("never-touched", "run-A")["missing"] is True


def test_run_id_comes_from_the_environment(sandbox, monkeypatch):
    assert tb.run_id() == "run-A"
    monkeypatch.setattr(tb, "_run_id", None)
    monkeypatch.delenv(tb.RUN_ENV)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{6}", tb.run_id())


# ───────────────────────────────────────────────────────── wiring lint ──

STAGE_02D = [ROOT / "scripts" / "02d_extract_terroir_facts.py"] + sorted(ROOT.glob("scripts/*/02d_extract_terroir_facts.py"))
STAGE_02E = [ROOT / "scripts" / "02e_translate_terroir_facts.py"] + sorted(ROOT.glob("scripts/*/02e_translate_terroir_facts.py"))
POST_PASSES = [ROOT / "scripts" / n for n in (
    "dedupe_terroir_facts.py", "normalize_terroir_facts.py", "filter_terroir_boilerplate.py",
    "recompute_terroir_provenance.py", "02d_verify_terroir_facts.py", "02e_verify_terroir_facts.py",
)]
_DIRECT_SOURCE_WRITE = re.compile(r"cache\.write_json\(\s*(CACHE_DIR\s*/|cache_path\(slug\)|p,|paths\[)")
_DIRECT_TRANSLATION_WRITE = re.compile(r"cache\.write_json\(\s*(cache_path\(lang, slug\)|tp,)")


def test_every_02d_writes_through_the_backup_helper():
    assert len(STAGE_02D) == 21
    for path in STAGE_02D:
        src = path.read_text(encoding="utf-8")
        assert "write_source_cache" in src, path
        assert not _DIRECT_SOURCE_WRITE.search(src), f"{path}: writes the source cache directly"


def test_every_02e_writes_through_the_backup_helper():
    assert len(STAGE_02E) == 21
    for path in STAGE_02E:
        src = path.read_text(encoding="utf-8")
        assert "write_translation_cache" in src, path
        assert not _DIRECT_TRANSLATION_WRITE.search(src), f"{path}: writes the translation cache directly"


def test_post_passes_write_through_the_backup_helpers():
    for path in POST_PASSES:
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8")
        assert not _DIRECT_SOURCE_WRITE.search(src), f"{path}: writes the source cache directly"
        assert not _DIRECT_TRANSLATION_WRITE.search(src), f"{path}: writes a translation cache directly"
