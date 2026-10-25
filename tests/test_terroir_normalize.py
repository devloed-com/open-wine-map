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
        ("Des composés aromatiques comme l'α-terpinéol.", "Des composés aromatiques comme l'α-terpinéol."),
        ("Amphorae stamped with the word ΘΑΣΙΩΝ, guaranteeing capacity.", "Amphorae stamped with the word THASION, guaranteeing capacity."),
        ("Strabo called Ankón «σφόδρα δ'εὔοινος», a producer of good wine.", "Strabo called Ankón «sphodra d'euoinos», a producer of good wine."),
        ("Wooden vessels called tines (τίνες) rested on scaffolds.", "Wooden vessels called tines rested on scaffolds."),
        ("Terraces called xerolithies (ξερολιθιές) in the local dialect.", "Terraces called xerolithies in the local dialect."),
        ("The level called « sans mesure » (άμετρος) by the islanders.", "The level called « sans mesure » (ametros) by the islanders."),
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


@pytest.mark.parametrize(
    "src,lang,expected",
    [
        # the four records of 2026-10-25 and their translations
        ("Según el pliego, se cree que las primeras cepas se plantaron en la isla de La Palma en 1505.", "",
         "Se cree que las primeras cepas se plantaron en la isla de La Palma en 1505."),
        ("According to the specification, the first vines are believed to have been planted in 1505.", "en",
         "The first vines are believed to have been planted in 1505."),
        ("Selon le cahier des charges, on pense que les premiers ceps furent plantés en 1505.", "fr",
         "On pense que les premiers ceps furent plantés en 1505."),
        ("Según el pliego de condiciones, las elevadas temperaturas estivales permiten que las uvas maduren.", "es",
         "Las elevadas temperaturas estivales permiten que las uvas maduren."),
        ("Secondo il disciplinare, le temperature estive elevate consentono alle uve di maturare.", "",
         "Le temperature estive elevate consentono alle uve di maturare."),
        ("According to the production specification, the high summer temperatures let the grapes ripen.", "en",
         "The high summer temperatures let the grapes ripen."),
        # the document as the subject of a reporting verb
        ("Il disciplinare afferma che tutti i vini presentano caratteristiche equilibrate.", "",
         "Tutti i vini presentano caratteristiche equilibrate."),
        ("The production regulations state that all wines display balanced characteristics.", "en",
         "All wines display balanced characteristics."),
        ("The Bardolino production rules record that as early as 1800 appraisers distinguished three sub-zones.", "en",
         "As early as 1800 appraisers distinguished three sub-zones."),
        ("Le cahier des charges indique que tous les vins rouges présentent des caractéristiques équilibrées.", "fr",
         "Tous les vins rouges présentent des caractéristiques équilibrées."),
        ("El pliego de condiciones señala que el clima de la zona permite una maduración lenta.", "es",
         "El clima de la zona permite una maduración lenta."),
        ("O caderno de especificações refere que os solos são graníticos.", "",
         "Os solos são graníticos."),
        ("A Wikipedia szerint a talaj főként löszön kialakult barna erdőtalaj.", "",
         "A talaj főként löszön kialakult barna erdőtalaj."),
        # trailing and bracketed
        ("Los suelos son calizos y pobres, según el pliego.", "", "Los suelos son calizos y pobres."),
        ("The soils are calcareous and poor, as the specification states.", "en", "The soils are calcareous and poor."),
        ("Les parcelles sont exposées au levant selon Wikipédia.", "", "Les parcelles sont exposées au levant."),
        ("Los suelos (según el pliego) son calizos y pobres.", "", "Los suelos son calizos y pobres."),
        ("De bodems zijn kalkrijk, zoals het productiereglement bevestigt.", "nl", "De bodems zijn kalkrijk."),
        ("De bodems (volgens het productdossier) zijn kalkrijk.", "nl", "De bodems zijn kalkrijk."),
    ],
)
def test_document_reference_is_cut_and_the_claim_kept(src, lang, expected):
    from _lib.terroir_normalize import document_reference
    assert document_reference(src) in {"lead", "subject", "trailing", "paren"}
    assert normalize_bullet(src, lang) == expected
    assert document_reference(normalize_bullet(src, lang)) is None


@pytest.mark.parametrize(
    "src",
    [
        "Σύμφωνα με τον μύθο, ο Διόνυσος δίδαξε την αμπελουργία στους κατοίκους.",
        "According to Strabo, the island produced a much-praised wine.",
        "Según el estudio de Hidalgo, los suelos de albariza retienen la humedad.",
        "Selon la légende, le prince planta les premières vignes.",
        "Volgens de mythe plantte Kefalos de eerste wijnstok.",
        "Il disciplinare di produzione fu approvato con DPR del 21 luglio 1967.",
        "Il primo disciplinare di produzione del vino Valpolicella fu approvato nel 1968.",
        "Según el Reglamento (CE) n.º 607/2009, la mención es facultativa.",
        "C'est à cette époque que le règlement intérieur de l'appellation impose la vendange manuelle.",
    ],
)
def test_a_source_attribution_or_the_document_as_history_is_no_reference(src):
    from _lib.terroir_normalize import document_reference
    assert document_reference(src) is None
    assert normalize_bullet(src) == ensure_terminal_period(src)


@pytest.mark.parametrize(
    "src,kind",
    [
        # Dutch / German: dropping the fronted adverbial would put the verb first
        ("Volgens het productdossier zijn de eerste wijnstokken in 1505 geplant.", "lead"),
        ("Volgens Wikipedia bevat de bodem daarnaast veel ijzeroxiden.", "lead"),
        ("Het productiereglement stelt dat alle wijnen evenwichtige kenmerken vertonen.", "subject"),
        ("Laut Produktspezifikation sind die Böden schiefrig.", "lead"),
        # a subjunctive complement is no main clause
        ("Il disciplinare stabilisce che le uve provengano da vigneti collinari.", "subject"),
        ("The specification establishes that the grapes be harvested by hand.", "subject"),
    ],
)
def test_a_reference_the_cut_cannot_reach_is_reported_and_left(src, kind):
    from _lib.terroir_normalize import document_reference
    assert document_reference(src) == kind
    assert normalize_bullet(src, "nl") == src


@pytest.mark.parametrize(
    "src",
    [
        "El color es amarillo pajizo con una transparencia que, según el pliego, realza la frescura.",
        "Il disciplinare descrive i vini rossi come tranquilli ma strutturati.",
        "Wikipedia décrit des sols calcaires et graveleux d'origine bathonienne.",
        "Las precipitaciones son de 300 mm según el pliego, frente a los 350 mm que indica Wikipedia.",
        "The vineyards lie at 600-1100 m, while most lie at 700-900 m according to Wikipedia.",
        "Il vino presenta caratteristiche comuni a tutte le tipologie previste dal disciplinare.",
        "Le forme di allevamento contengono le rese entro i limiti del disciplinare.",
        "Základom je andezitový substrát, na ktorom sa podľa Wikipédie vytvorili úrodné andozeme.",
        "Cada sub-região tem tipos de solo próprios definidos no caderno de especificações.",
        "Les vendanges dépassent de 5 degrés Oechslé les minima prévus par le règlement.",
    ],
)
def test_a_reference_needing_rewording_is_mid_and_left(src):
    from _lib.terroir_normalize import document_reference
    assert document_reference(src) == "mid"
    assert normalize_bullet(src) == src


def test_a_chemical_prefix_is_no_residual_script_for_the_three_tools():
    """The normaliser, the audit and the untranslated detector agree that
    "α-terpineol" — after an elided article too — is chemistry (La Palma's
    tea-barrel bullet, 2026-10-25)."""
    import importlib.util
    from pathlib import Path

    import audit_terroir_facts as audit
    path = Path(__file__).resolve().parents[1] / "scripts" / "detect_untranslated_terroir_facts.py"
    spec = importlib.util.spec_from_file_location("detect_untranslated", path)
    det = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(det)
    det._GI_FORMS = frozenset()
    for bullet, lang in [("Aromatic compounds such as α-terpineol.", "en"),
                         ("Des composés aromatiques comme l'α-terpinéol.", "fr")]:
        assert latinize_residual_script(bullet) == bullet
        assert not audit.has_non_latin(bullet)
        assert det._reasons(bullet, lang, raw=False) == []
    assert det._reasons("Terraces called xerolithies (ξερολιθιές).", "en", raw=False) == ["non-latin:ξ"]
