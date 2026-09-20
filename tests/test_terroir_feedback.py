"""Per-record review feedback (scripts/_lib/terroir_feedback.py,
scripts/build_terroir_feedback.py) and its wiring into the 21 stage-02d
scripts."""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

from _lib import terroir_feedback as tf

ROOT = Path(__file__).resolve().parents[1]


def _fb(**over):
    base = {
        "slug": "taurasi", "country": "it", "source_lang": "it",
        "graded_against": {"cahier_source_sha": "abc", "wiki_source_revision": "7"},
        "reviews": [{"id": "review-2026-09-12", "date": "2026-09-12"}],
        "do_not_claim": [
            {"claim_en": "Volcanic material imparts minerality to Taurasi.",
             "claim_src": "Il materiale piroclastico conferisce mineralità al Taurasi.",
             "mode": "unsupported-causal-link", "stage": "extraction",
             "why": "The source only records presence {of the material}."},
            {"claim_en": "Plots lie at 250–490 m.", "claim_src": "Parcelle tra 250 e 290 m.",
             "mode": "wrong-number-or-unit", "stage": "translation", "why": "490 is a translation slip."},
        ],
        "capture_if_present": [{"hint": "Aglianico's Greek origin is prominent in the source."}],
        "record_cautions": [{"kind": "sibling-text", "note": "Section b) describes the neighbouring DOC."}],
        "history": [],
    }
    base.update(over)
    return base


def test_block_is_empty_without_feedback():
    assert tf.feedback_prompt_block(None) == ""
    assert tf.feedback_prompt_block({"do_not_claim": [], "capture_if_present": [], "record_cautions": []}) == ""


def test_block_keeps_extraction_claims_and_drops_translation_ones():
    block = tf.feedback_prompt_block(_fb())
    assert "Do not assert «Volcanic material imparts minerality to Taurasi.»" in block
    assert "250–490" not in block
    assert "unless the source states it explicitly" in block
    assert "capture: Aglianico's Greek origin" in block
    assert "Caution (sibling-text)" in block
    assert "(2026-09-12)" in block


def test_translation_stage_selects_the_other_bucket():
    block = tf.feedback_prompt_block(_fb(), stage="translation")
    assert "250–490" in block and "Volcanic material" not in block


def test_block_never_carries_format_braces():
    block = tf.feedback_prompt_block(_fb())
    assert "{" not in block and "}" not in block
    assert "(of the material)" in block


def test_block_caps_the_number_of_claims():
    claims = [{"claim_en": f"claim {i}", "claim_src": f"src {i}", "stage": "extraction", "why": "w"} for i in range(9)]
    block = tf.feedback_prompt_block(_fb(do_not_claim=claims, capture_if_present=[], record_cautions=[]))
    assert block.count("Do not assert") == tf.MAX_CLAIMS
    assert "3 more claims" in block


def test_with_feedback_reads_the_sidecar(tmp_path, monkeypatch):
    monkeypatch.setattr(tf, "FEEDBACK_DIR", tmp_path)
    tf.clear_cache()
    assert tf.with_feedback("SYSTEM", "taurasi") == "SYSTEM"
    (tmp_path / "taurasi.json").write_text(json.dumps(_fb()), encoding="utf-8")
    tf.clear_cache()
    out = tf.with_feedback("SYSTEM\n", "taurasi")
    assert out.startswith("SYSTEM\n\nLessons from the previous review")
    assert tf.with_feedback("SYSTEM", "no-such-slug") == "SYSTEM"
    tf.clear_cache()


def test_recurrence_matches_the_source_bullet_not_translation_entries():
    facts = [
        {"bullet": "Il materiale piroclastico conferisce mineralità e struttura al Taurasi."},
        {"bullet": "Parcelle tra 250 e 290 m."},
    ]
    hits = tf.recurrence_findings(_fb(), facts)
    assert [h["index"] for h in hits] == [0]
    assert hits[0]["mode"] == "unsupported-causal-link"
    assert tf.recurrence_findings(_fb(), [{"bullet": "Clima mediterraneo con estati calde."}]) == []
    assert tf.recurrence_findings(None, facts) == []


def test_is_stale_tracks_the_graded_sources():
    fb = _fb()
    assert not tf.is_stale(fb, "abc", "7")
    assert tf.is_stale(fb, "def", "7")
    assert tf.is_stale(fb, "abc", "8")
    assert not tf.is_stale(fb, None, None)


def test_append_history_creates_and_extends(tmp_path, monkeypatch):
    monkeypatch.setattr(tf, "FEEDBACK_DIR", tmp_path)
    tf.clear_cache()
    tf.append_history("x", {"run": "02d-2026-10", "kind": "gate", "dropped": [3]})
    tf.append_history("x", {"run": "02d-2026-11", "kind": "gate", "dropped": []})
    fb = json.loads((tmp_path / "x.json").read_text(encoding="utf-8"))
    assert [h["run"] for h in fb["history"]] == ["02d-2026-10", "02d-2026-11"]
    assert all("at" in h for h in fb["history"])
    tf.clear_cache()


# ───────────────────────────────────────────── builder (merge semantics) ──


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_terroir_feedback", ROOT / "scripts" / "build_terroir_feedback.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_builder_collects_and_merges_without_duplicating(tmp_path):
    b = _load_builder()
    ev = tmp_path / "ev"
    ev.mkdir()
    (ev / "confirmed-misleading.json").write_text(json.dumps([
        {"slug": "x", "i": 2, "subsection": "interactions", "mode": "unsupported-causal-link",
         "where": "extraction", "en": "Soils give minerality.", "src": "I suoli danno mineralità.", "reason": "no link in source"},
    ]), encoding="utf-8")
    (ev / "merged.json").write_text(json.dumps({"record_notes": {"x": [
        ["fidelity", "MISSING", "The lake as climate regulator is absent."],
        ["language", "MISSING", "The lake, a climate regulator, is not captured."],
        ["fidelity", "OTHER", "Batch-wide: Rodopi should be Rhodopes."],
        ["fidelity", "WRONG_SOURCE", "The source text is the neighbouring DOC's disciplinare."],
    ]}}), encoding="utf-8")
    per = b.collect(ev, "review-t")
    assert set(per) == {"x"}
    assert len(per["x"]["do_not_claim"]) == 1
    assert len(per["x"]["capture_if_present"]) == 1          # two lenses, one observation
    assert [c["kind"] for c in per["x"]["record_cautions"]] == ["wrong-source"]  # batch-wide note skipped
    review = {"id": "review-t", "date": "t"}
    fb, added = b.merge_into(None, "x", per["x"], review)
    assert dict(added) == {"do_not_claim": 1, "capture_if_present": 1, "record_cautions": 1}
    fb2, added2 = b.merge_into(fb, "x", per["x"], review)   # re-running the same review adds nothing
    assert dict(added2) == {} and len(fb2["reviews"]) == 1 and fb2["history"] == []


# ─────────────────────────────────────────────── wiring lint (21 scripts) ──


STAGE_02D = [ROOT / "scripts" / "02d_extract_terroir_facts.py"] + sorted(ROOT.glob("scripts/*/02d_extract_terroir_facts.py"))


def test_all_02d_scripts_are_wired():
    assert len(STAGE_02D) == 21
    for path in STAGE_02D:
        src = path.read_text(encoding="utf-8")
        assert "from _lib.terroir_feedback import with_feedback" in src, path
        calls = len(re.findall(r"with_feedback\(", src))
        # live call after the system prompt, plus the emit-todo prompt (ES has no manual round-trip yet)
        expected = 1 if path.parent.name == "es" else 2
        assert calls >= expected, f"{path}: {calls} with_feedback calls, expected ≥ {expected}"
        assert re.search(r"^\s*system = with_feedback\(system, (record|job)\[\"slug\"\]\)", src, re.M), path


def test_recurrence_counts_a_meaningful_gate_rewrite_as_resolved():
    probe = "Il clima mediterraneo conferisce ai vini una spiccata mineralità."
    fb = {"do_not_claim": [{"claim_src": probe, "stage": "extraction", "mode": "causal"}]}
    rewritten = {"bullet": "Il clima è mediterraneo e i vini mostrano una spiccata mineralità.",
                 "support": {"verdict": "rewrite", "original_bullet": probe}}
    assert tf.recurrence_findings(fb, [rewritten]) == []
    # a cosmetic rewrite (punctuation only) is not a resolution
    cosmetic = {"bullet": probe.rstrip(".") + ",", "support": {"verdict": "rewrite", "original_bullet": probe}}
    assert len(tf.recurrence_findings(fb, [cosmetic])) == 1
    # the same claim re-extracted without a gate verdict recurs
    assert len(tf.recurrence_findings(fb, [{"bullet": probe}])) == 1
