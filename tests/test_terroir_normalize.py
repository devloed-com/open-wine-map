"""Deterministic bullet clean-up (scripts/_lib/terroir_normalize.py)."""
from __future__ import annotations

import pytest
from _lib.terroir_normalize import (
    ensure_terminal_period,
    expand_mentions,
    latinize_residual_script,
    normalize_bullet,
    normalize_facts,
    strip_colour_codes,
)


@pytest.mark.parametrize(
    "src,expected",
    [
        ("Cépages : pinot noir N, chardonnay B et pinot gris G.", "Cépages : pinot noir, chardonnay et pinot gris."),
        ("Riesling B, gewurztraminer Rs, pinot gris G et sylvaner B.", "Riesling, gewurztraminer, pinot gris et sylvaner."),
        ("Seul grand cru à inclure le sylvaner B parmi ses cépages.", "Seul grand cru à inclure le sylvaner parmi ses cépages."),
        ("Grenache G (Rg) et muscat à petits grains B dominent.", "Grenache et muscat à petits grains dominent."),
        ("Vignoble de Colmar N exposé au sud.", "Vignoble de Colmar N exposé au sud."),
        ("Classé en 1936 en catégorie B du référentiel.", "Classé en 1936 en catégorie B du référentiel."),
    ],
)
def test_colour_codes_are_stripped_only_after_grape_names(src, expected):
    assert strip_colour_codes(src) == expected


def test_vt_sgn_are_expanded():
    assert expand_mentions("VT : arômes exotiques ; SGN plus concentrés.") == (
        "Vendanges Tardives : arômes exotiques ; Sélection de Grains Nobles plus concentrés."
    )
    assert expand_mentions("Mentions VT/SGN exigent 18 mois.") == (
        "Mentions Vendanges Tardives / Sélection de Grains Nobles exigent 18 mois."
    )
    assert expand_mentions("La SGNV n'existe pas.") == "La SGNV n'existe pas."


@pytest.mark.parametrize(
    "src,expected",
    [
        ("Sols argilo-calcaires", "Sols argilo-calcaires."),
        ("Sols argilo-calcaires.", "Sols argilo-calcaires."),
        ("AOC reconnue en 1936 (JORF)", "AOC reconnue en 1936 (JORF)."),
        ("Renommée « Montlouis-sur-Loire »", "Renommée « Montlouis-sur-Loire »."),
        ("Trailing space   ", "Trailing space."),
        ("Déjà ponctué ?", "Déjà ponctué ?"),
        ("", ""),
    ],
)
def test_terminal_period(src, expected):
    assert ensure_terminal_period(src) == expected


def test_normalize_facts_counts_changes_and_edits_in_place():
    facts = [{"bullet": "Pinot noir N dominant"}, {"bullet": "Déjà propre."}]
    assert normalize_facts(facts) == 1
    assert facts[0]["bullet"] == "Pinot noir dominant."
    assert normalize_bullet("") == ""


@pytest.mark.parametrize(
    "src,expected",
    [
        ("Thermoheliоhydric index 4,596–4,765.", "Thermoheliohydric index 4,596–4,765."),
        ("Dr. Nik. Piniatorοs founded a company.", "Dr. Nik. Piniatoros founded a company."),
        ("Terraces with dry-stone walls (ξερολιθιές) of 1–2 m.", "Terraces with dry-stone walls (xerolithies) of 1–2 m."),
        ("Vertisols (смолници) and brown forest soils.", "Vertisols (smolnitsi) and brown forest soils."),
        ("Bяло Мискет врачански: fine misket aroma.", "Bialo Misket vrachanski: fine misket aroma."),
        ("A bitter, resinous note of α-terpineol.", "A bitter, resinous note of α-terpineol."),
        ("Οι θερινοί άνεμοι αποτελούν παράγοντα μοναδικότητας των οίνων.", "Οι θερινοί άνεμοι αποτελούν παράγοντα μοναδικότητας των οίνων."),
    ],
)
def test_residual_script_is_latinised_only_in_mostly_latin_bullets(src, expected):
    assert latinize_residual_script(src) == expected


def test_latinisation_applies_to_target_locales_only():
    src = "Wijngaarden op terrassen met droogstenen muren (πεζούλες), tot 900 m hoogte."
    assert normalize_bullet(src, "nl") == "Wijngaarden op terrassen met droogstenen muren (pezoules), tot 900 m hoogte."
    assert normalize_bullet(src, "") == src


def test_trailing_meta_clause_is_dropped_and_the_fact_kept():
    from _lib.terroir_normalize import normalize_bullet, strip_trailing_meta
    assert normalize_bullet("Un'epoca iniziata 70 milioni di anni fa secondo il disciplinare.") == "Un'epoca iniziata 70 milioni di anni fa."
    assert normalize_bullet("Les sols sont argilo-calcaires, selon le cahier des charges.") == "Les sols sont argilo-calcaires."
    assert normalize_bullet("Die Böden sind Schiefer laut Produktspezifikation") == "Die Böden sind Schiefer."
    assert normalize_bullet("A period that began 70 million years ago according to the production specification.", "en") == "A period that began 70 million years ago."
    # mid-sentence citations are left to the audit's meta_text check
    assert strip_trailing_meta("Il disciplinare prevede una resa massima di 80 q/ha.") == "Il disciplinare prevede una resa massima di 80 q/ha."


def test_dutch_common_noun_appellatie_keeps_the_registered_french_term():
    from _lib.terroir_normalize import normalize_bullet
    assert normalize_bullet("De appellation is gelegen in de streek Revermont.", "nl") == "De appellatie is gelegen in de streek Revermont."
    assert normalize_bullet("In 2009 coëxisteerden de appellations Limoux en Crémant de Limoux.", "nl") == "In 2009 coëxisteerden de appellaties Limoux en Crémant de Limoux."
    assert normalize_bullet("Appellation Alsace grand cru werd erkend in 1975.", "nl") == "Appellatie Alsace grand cru werd erkend in 1975."
    kept = "De appellation d'origine contrôlée Alsace grand cru Muenchberg werd erkend in 1992."
    assert normalize_bullet(kept, "nl") == kept
    assert normalize_bullet("De appellation d’origine protégée omvat 12 gemeenten.", "nl") == "De appellation d’origine protégée omvat 12 gemeenten."
    # other locales untouched
    assert normalize_bullet("The appellation lies in the Revermont.", "en") == "The appellation lies in the Revermont."
