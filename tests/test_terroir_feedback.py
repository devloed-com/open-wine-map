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
    assert "unless the source states it explicitly (then state it plainly, without naming the source)" in block
    assert "Reviewer hint: the source describes this and no bullet captured it." in block
    assert "takes a slot ahead of any unhinted fact of the same sub-section (the maximum still holds): "\
           "Aglianico's Greek origin" in block
    assert "Caution (sibling-text)" in block
    assert "(2026-09-12)" in block


def test_a_claim_a_source_does_state_gets_no_source_escape():
    """An outdated Wikipedia statement (source-vintage) or another tier's
    statement (sibling-or-subzone-confusion) is stated by a source, so the
    default "unless the source states it" escape would let it through — in
    the 02d block and in the gate's constraints alike."""
    from _lib.terroir_gate import _constraints_block
    claims = [
        {"claim_en": "The zone has two subzones.", "claim_src": "La zona tiene dos subzonas.",
         "mode": "source-vintage", "stage": "extraction", "why": "eight subzonas now"},
        {"claim_en": "Wines carry the DOK designation.", "claim_src": "",
         "mode": "sibling-or-subzone-confusion", "stage": "extraction", "why": "DOK is the PDO tier"},
    ]
    fb = _fb(do_not_claim=claims, capture_if_present=[], record_cautions=[])
    block = tf.feedback_prompt_block(fb)
    assert "«The zone has two subzones.»: a source may state it, but that statement is outdated" in block
    assert "never from the Wikipedia article alone (then state it plainly, without naming the source)" in block
    assert "«Wines carry the DOK designation.» unless the source states it of this appellation itself" in block
    assert "another appellation, sub-zone or tier (then state it plainly, without naming the source)" in block
    assert "states it explicitly" not in block
    gate = _constraints_block(fb)
    assert "a Wikipedia hint stating it does not support this claim" in gate
    assert "only where the source says it of this record" in gate


def test_a_restated_claim_is_kept_to_its_own_subsection():
    """Wachau, 2026-11-08: the medieval laying-out of the terraces, stated once
    by the source, sat in the natural-factors bullet beside the human-factors
    bullet that owns it. The source states it, so the default escape would let
    it through; the mode tells 02d to give it in one sub-section only and the
    gate to rewrite the restating bullet to its own fact (or drop it)."""
    from _lib.terroir_gate import _constraints_block
    claims = [{"claim_en": "The terraces were laid out in the Middle Ages.",
               "claim_src": "Die Terrassen wurden im Mittelalter angelegt.",
               "mode": "restated-across-subsections", "stage": "extraction",
               "why": "the human-factors bullet carries it"}]
    fb = _fb(do_not_claim=claims, capture_if_present=[], record_cautions=[])
    block = tf.feedback_prompt_block(fb)
    assert ("«The terraces were laid out in the Middle Ages.»: the source states it, but it belongs "
            "to one sub-section only") in block
    assert "states it explicitly" not in block
    gate = _constraints_block(fb)
    assert "another bullet of this record already gives it in its own sub-section" in gate
    assert "rewrite this bullet to the fact it states on its own" in gate


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


def test_card_evidence_is_filed_under_the_facts_owner(tmp_path, monkeypatch):
    """A card-level finding (audit_cards_llm --emit-feedback: no `src`, the
    card slug) on a sub-denomination whose bullets are its parent's lands in
    the parent's sidecar — the one 02d reads — with the parent's index and
    source-language bullet recovered from the EN translation cache."""
    b = _load_builder()
    facts_dir, tr_dir, rec_dir = tmp_path / "tf", tmp_path / "tr", tmp_path / "rec"
    (tr_dir / "en").mkdir(parents=True)
    facts_dir.mkdir()
    rec_dir.mkdir()
    (facts_dir / "parent.json").write_text(json.dumps({"source_lang": "es", "facts": [
        {"bullet": "Los suelos son calizos."}, {"bullet": "La zona se divide en dos subzonas."}]}), encoding="utf-8")
    (tr_dir / "en" / "parent.json").write_text(json.dumps({"facts": [
        {"bullet": "The soils are calcareous."}, {"bullet": "The zone is divided into two sub-zones."}]}), encoding="utf-8")
    (rec_dir / "parent-child.json").write_text(json.dumps({"parent_slug": "parent"}), encoding="utf-8")
    monkeypatch.setattr(b, "TERROIR_FACTS", facts_dir)
    monkeypatch.setattr(b, "TRANSLATIONS", tr_dir)
    monkeypatch.setattr(b, "record_path", lambda cc, slug: rec_dir / f"{slug}.json" if (rec_dir / f"{slug}.json").exists() else None)
    ev = tmp_path / "ev"
    ev.mkdir()
    (ev / "confirmed-misleading.json").write_text(json.dumps([
        {"slug": "parent-child", "i": 0, "country": "es", "mode": "source-vintage", "where": "extraction",
         "en": "The zone is divided into two sub-zones", "src": "", "reason": "eight subzonas now"},
    ]), encoding="utf-8")
    (ev / "merged.json").write_text(json.dumps({"record_notes": {}}), encoding="utf-8")
    per = b.collect(ev, "cards-t")
    assert set(per) == {"parent"}
    entry = per["parent"]["do_not_claim"][0]
    assert entry["fact_index"] == 1 and entry["graded_on"] == "parent-child"
    assert entry["claim_src"] == "La zona se divide en dos subzonas."
    assert entry["claim_en"] == "The zone is divided into two sub-zones."
    # an explicit owner (the emitter's `owner`) wins; a record written in the
    # card's locale is matched against its own bullets
    (facts_dir / "mt.json").write_text(json.dumps({"source_lang": "en", "facts": [
        {"bullet": "Wines can carry the DOK designation."}]}), encoding="utf-8")
    owner, entry = b.claim_entry({"slug": "card", "owner": "mt", "locale": "en", "i": 3,
                                  "en": "Wines can carry the DOK designation", "src": ""}, "cards-t")
    assert owner == "mt" and entry["fact_index"] == 0 and entry["claim_src"] == "Wines can carry the DOK designation."


# ─────────────────────────────────────────────── wiring lint (21 scripts) ──


STAGE_02D = [ROOT / "scripts" / "02d_extract_terroir_facts.py"] + sorted(ROOT.glob("scripts/*/02d_extract_terroir_facts.py"))


def test_all_02d_scripts_are_wired():
    assert len(STAGE_02D) == 22
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
