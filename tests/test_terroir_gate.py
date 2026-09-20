"""The claim-support gate (scripts/_lib/terroir_gate.py): verdict parsing,
rewrite guards and the deterministic application of verdicts."""
from __future__ import annotations

from _lib import terroir_gate as tg

FACTS = [
    {"bullet": "I suoli vulcanici conferiscono mineralità e struttura al vino.", "subsection": "interactions",
     "provenance": "cahier", "cahier_quote": "suoli di origine vulcanica"},
    {"bullet": "Il clima è mediterraneo con estati calde e secche.", "subsection": "facteurs_humains",
     "provenance": "cahier", "cahier_quote": "clima mediterraneo con estati calde e secche"},
    {"bullet": "La vendemmia avviene esclusivamente a mano.", "subsection": "facteurs_humains",
     "provenance": "cahier", "cahier_quote": "la vendemmia è di norma manuale"},
    {"bullet": "Le estati sono calde e secche, con clima mediterraneo.", "subsection": "produit",
     "provenance": "cahier", "cahier_quote": "clima mediterraneo con estati calde e secche"},
]
SOURCE = "I suoli sono di origine vulcanica. Il clima è mediterraneo con estati calde e secche. La vendemmia è di norma manuale."


def test_parse_verdicts_is_tolerant_and_aligned():
    raw = '```json\n{"facts": [{"i": 0, "verdict": "drop", "note": "n0"}, {"i": 2, "verdict": "REWRITE", "rewrite": "x", "restates": "", "subsection": "produit"}, {"i": 9, "verdict": "drop"}, "junk"]}\n```'
    rows, err = tg.parse_verdicts(raw, 3)
    assert err is None and len(rows) == 3
    assert rows[0]["verdict"] == "drop" and rows[1]["verdict"] == "supported"
    assert rows[2]["verdict"] == "rewrite" and rows[2]["subsection"] == "produit" and rows[2]["restates"] is None
    assert tg.parse_verdicts("no json here", 2) == (None, "no JSON object in reply")
    assert tg.parse_verdicts('{"facts": []}', 2)[1] == "reply graded none of the bullets"


def test_rewrite_guards():
    assert tg.rewrite_ok("Piove 600 mm all'anno.", "Piove 600 mm all'anno sulla costa.", "600 mm sulla costa") is None
    assert tg.rewrite_ok("Piove 600 mm.", "Piove 600 mm.", "") == "unchanged"
    assert tg.rewrite_ok("Piove 600 mm.", "", "") == "empty"
    assert tg.rewrite_ok("Piove molto.", "Piove 800 mm all'anno in collina.", "piove molto") == "new numbers ['800']"
    assert tg.rewrite_ok("Piove molto.", "Suolo → vino.", "") == "arrow"


def test_apply_verdicts_drops_rewrites_moves_and_records_support():
    verdicts = [
        {"verdict": "rewrite", "note": "presence only", "rewrite": "I suoli sono di origine vulcanica", "restates": None, "subsection": "facteurs_naturels"},
        {"verdict": "supported", "note": "", "rewrite": "", "restates": None, "subsection": "facteurs_naturels"},
        {"verdict": "rewrite", "note": "hedge dropped", "rewrite": "La vendemmia è di norma manuale.", "restates": None, "subsection": None},
        {"verdict": "drop", "note": "restates #1", "rewrite": "", "restates": 1, "subsection": None},
    ]
    res = tg.apply_verdicts(FACTS, verdicts, source=SOURCE, source_lang="it", run="r1", model="m")
    assert [f["bullet"] for f in res["facts"]] == [
        "I suoli sono di origine vulcanica.", "Il clima è mediterraneo con estati calde e secche.", "La vendemmia è di norma manuale.",
    ]
    assert res["kept_indices"] == [0, 1, 2]
    assert [f["subsection"] for f in res["facts"]] == ["facteurs_naturels", "facteurs_naturels", "facteurs_humains"]
    assert res["facts"][0]["support"]["original_bullet"].startswith("I suoli vulcanici")
    assert res["facts"][0]["support"]["moved_from"] == "interactions"
    assert res["facts"][1]["support"] == {**res["facts"][1]["support"], "verdict": "supported", "moved_from": "facteurs_humains"}
    assert [d["index"] for d in res["dropped"]] == [3] and res["dropped"][0]["restates"] == 1
    assert res["text_changed"] and len(res["rewritten"]) == 2 and len(res["moved"]) == 2


def test_apply_verdicts_keeps_a_bullet_whose_twin_was_dropped_and_rejects_bad_rewrites():
    verdicts = [
        {"verdict": "drop", "note": "unsupported", "rewrite": "", "restates": None, "subsection": None},
        {"verdict": "drop", "note": "restates #0", "rewrite": "", "restates": 0, "subsection": None},
        {"verdict": "rewrite", "note": "x", "rewrite": "Vendemmia a mano su 1.200 ettari.", "restates": None, "subsection": None},
        {"verdict": "supported", "note": "", "rewrite": "", "restates": None, "subsection": None},
    ]
    res = tg.apply_verdicts(FACTS, verdicts, source=SOURCE, source_lang="it", run="r1", model="m")
    kept = {f["bullet"]: f["support"] for f in res["facts"]}
    assert "Il clima è mediterraneo con estati calde e secche." in kept
    assert kept["Il clima è mediterraneo con estati calde e secche."]["verdict"] == "supported"
    assert kept["La vendemmia avviene esclusivamente a mano."]["verdict"] == "rewrite-rejected"
    assert kept["La vendemmia avviene esclusivamente a mano."]["rejected_reason"].startswith("new numbers")
    # #3 restates #1 (same quote, near-identical bullet): the lexical dedupe
    # after the gate collapses it even though the model kept it.
    assert [(d["index"], d["note"][:9]) for d in res["dropped"]] == [(0, "unsupport"), (3, "duplicate")]
    assert res["kept_indices"] == [1, 2]
    assert not res["text_changed"]


def test_user_message_carries_constraints_and_no_braces():
    fb = {"do_not_claim": [{"claim_src": "I suoli danno {mineralità}", "why": "presence only", "stage": "extraction"},
                           {"claim_src": "x", "why": "y", "stage": "translation"}],
          "record_cautions": [{"kind": "wrong-source", "note": "section b describes the neighbour"}]}
    msg = tg.build_user_message(name="Taurasi", country="it", source_lang="it", cahier="testo", hints={"produit": "vino rosso"},
                                facts=FACTS[:1], feedback=fb)
    assert "Verified misleading before: «I suoli danno (mineralità)»" in msg
    assert msg.count("Verified misleading before") == 1
    assert "Caution (wrong-source)" in msg and "[produit]\nvino rosso" in msg and "#0 [interactions · cahier]" in msg
    assert "{" not in msg and "}" not in msg


def test_parse_verdicts_recovers_rows_with_unescaped_quotes_in_notes():
    raw = '''```json
{"facts": [
  {"i": 0, "verdict": "supported", "note": "Source states «la "montille" est calcaire», confirmed.", "rewrite": "", "restates": null, "subsection": null},
  {"i": 1, "verdict": "drop", "note": "Says "chiaretto" twice; restates #0.", "rewrite": "", "restates": 0, "subsection": null},
  {"i": 2, "verdict": "rewrite", "note": "ok", "rewrite": "Il suolo è "calcareo" e marnoso.", "restates": null, "subsection": "facteurs_naturels"}
]}
```'''
    rows, err = tg.parse_verdicts(raw, 3)
    assert err is None
    assert [r["verdict"] for r in rows] == ["supported", "drop", "rewrite"]
    assert rows[1]["restates"] == 0 and 'Says "chiaretto"' in rows[1]["note"]
    assert rows[2]["rewrite"] == 'Il suolo è "calcareo" e marnoso.' and rows[2]["subsection"] == "facteurs_naturels"


# ───────────────────────────────────────────── 02e back-check (R6) ──

from _lib import terroir_backcheck as tb  # noqa: E402


def test_backcheck_parse_and_apply_fixes_with_guards():
    raw = '{"facts": [{"i": 0, "verdict": "fix", "issue": "generoso is fortified", "fix": "Fortified wines (generoso) are aged under flor."}, {"i": 1, "verdict": "fix", "issue": "number", "fix": "Plots lie at 250–490 m."}, {"i": 2, "verdict": "ok", "issue": "", "fix": ""}]}'
    checks, err = tb.parse_checks(raw, 3)
    assert err is None and [c["verdict"] for c in checks] == ["fix", "fix", "ok"]
    source = [{"bullet": "Los vinos generosos se crían bajo velo de flor."}, {"bullet": "Las parcelas están entre 250 y 290 m."}, {"bullet": "x"}]
    translated = [{"bullet": "Generous wines are aged under flor.", "subsection": "produit"},
                  {"bullet": "Plots lie at 250–290 m.", "subsection": "facteurs_naturels"}, {"bullet": "x", "subsection": "produit"}]
    res = tb.apply_fixes(translated, source, checks, lang="en", run="r", model="m")
    assert res["facts"][0]["bullet"] == "Fortified wines (generoso) are aged under flor."
    assert res["facts"][0]["check"]["original"] == "Generous wines are aged under flor."
    assert res["facts"][1]["bullet"] == "Plots lie at 250–290 m."          # 490 is in neither source nor translation
    assert res["facts"][1]["check"]["verdict"] == "fix-rejected" and res["facts"][1]["check"]["rejected_reason"].startswith("new numbers")
    assert res["facts"][2]["check"]["verdict"] == "ok" and res["facts"][2]["subsection"] == "produit"
    assert [f["index"] for f in res["fixed"]] == [0] and [r["index"] for r in res["rejected"]] == [1]


def test_backcheck_user_message_flags_exonyms_and_translation_feedback():
    fb = {"do_not_claim": [{"claim_en": "Plots lie at 250–490 m.", "why": "490 is a slip", "stage": "translation"},
                           {"claim_en": "x", "why": "y", "stage": "extraction"}]}
    msg = tb.build_user_message(name="Rueda", source_lang="es", target_lang="en",
                                source_facts=[{"bullet": "Al pie de los Pirineos.", "subsection": "facteurs_naturels"}],
                                translated=[{"bullet": "At the foot of the Pirineos."}], feedback=fb)
    assert "DETECTOR: source-form place name(s) still present: Pirineos" in msg
    assert "250–490" in msg and msg.count("previous review verified") == 1
    assert "Spanish → English" in msg and "{" not in msg
    assert "generoso" in tb.system_prompt() and "{watch_list}" not in tb.system_prompt()
