"""Intra-record fact de-duplication (scripts/_lib/terroir_dedupe.py)."""
from __future__ import annotations

from _lib.terroir_dedupe import dedupe_facts, duplicate_reason, facts_sha

QUOTE = "I terreni argillosi delle marne calcaree producono vini di potenza e longevità, mentre il macigno"


def fact(bullet, *, cq="", wq="", prov="cahier", sub="facteurs_naturels"):
    return {
        "bullet": bullet, "cahier_quote": cq, "wiki_quote": wq,
        "provenance": prov, "subsection": sub,
    }


def test_near_identical_bullets_collapse_to_the_earlier_one():
    facts = [
        fact("Marne calcaree argillose favoriscono potenza e longevità; macigno toscano apporta serbevolezza."),
        fact("Marne calcaree danno potenza e longevità; macigno toscano conferisce serbevolezza.", sub="produit"),
    ]
    res = dedupe_facts(facts)
    assert res.kept_indices == [0]
    assert res.drops[0]["reason"] == "similar-bullet"
    assert res.drops[0]["dropped_index"] == 1 and res.drops[0]["kept_index"] == 0


def test_same_quote_with_substantial_bullet_overlap_is_a_duplicate():
    facts = [
        fact("Hlinitá až ílovito-hlinitá pôda dodáva vínam vyššiu mineralitu; priemerný bezcukorný extrakt dosahuje až 19,0 g/l.", cq=QUOTE),
        fact("Černozemné ílovito-hlinité pôdy zvyšujú mineralitu vína; bezcukorný extrakt dosahuje až 19,0 g/l.", cq=QUOTE, sub="interactions"),
    ]
    res = dedupe_facts(facts)
    assert res.kept_indices == [0]
    assert res.drops[0]["reason"] == "same-quote"


def test_same_quote_but_different_facts_are_both_kept():
    facts = [
        fact("Origine geologica alluvionale: suoli di medio impasto tendenti all'argilloso.", cq=QUOTE),
        fact("Disponibilità idrica garantita dal fiume Panaro e da acqua di falda nel sottosuolo.", cq=QUOTE),
    ]
    assert dedupe_facts(facts).kept_indices == [0, 1]


def test_bullets_with_different_numbers_are_never_merged():
    a = fact("Rendement maximal fixé à 50 hl/ha pour les vins rouges de l'appellation.", cq=QUOTE)
    b = fact("Rendement maximal fixé à 60 hl/ha pour les vins rouges de l'appellation.", cq=QUOTE)
    assert duplicate_reason(a, b) is None
    assert dedupe_facts([a, b]).kept_indices == [0, 1]


def test_more_informative_superset_wins_and_takes_the_earlier_slot():
    a = fact("As condições climáticas favorecem a síntese de açúcares e a concentração de matérias corantes.")
    b = fact("As 3000 horas de sol anuais favorecem a síntese de açúcares e a concentração de matérias corantes.", sub="interactions")
    res = dedupe_facts([a, b])
    assert res.kept == [b]
    assert res.kept_indices == [1]
    assert res.drops[0]["dropped_index"] == 0 and res.drops[0]["kept_index"] == 1


def test_both_provenance_beats_cahier_only():
    a = fact("Vulkanische Böden bedingen mineralischen Geruch der Weine, beschrieben als Geruch nach nassem Stein.", cq=QUOTE)
    b = fact("Vulkanböden prägen mineralischen Geruch der Weine, beschrieben als Geruch nach nassem Stein.", cq=QUOTE, wq="x" * 40, prov="both")
    res = dedupe_facts([a, b])
    assert res.kept == [b]


def test_short_quotes_do_not_count_as_shared():
    a = fact("Suoli vulcanici di origine piroclastica nell'area del Vulture con elevata fertilità.", cq="short quote")
    b = fact("Suoli vulcanici piroclastici al Vulture conferiscono fertilità mentre le argille danno struttura.", cq="short quote")
    assert dedupe_facts([a, b]).kept_indices == [0, 1]


def test_unchanged_record_reports_no_drops():
    facts = [fact("Un fait."), fact("Un autre fait, sans rapport avec le premier.")]
    res = dedupe_facts(facts)
    assert not res.changed and res.kept == facts and res.kept_indices == [0, 1]


def test_facts_sha_hashes_bullets_only():
    a = [fact("x", cq="q1"), fact("y", cq="q2")]
    b = [fact("x", cq="other"), fact("y", wq="w")]
    assert facts_sha(a) == facts_sha(b)
    assert facts_sha(a) != facts_sha(a[:1])
