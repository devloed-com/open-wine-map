"""Geographic exonym detection for translated bullets (scripts/_lib/exonyms.py)."""
from __future__ import annotations

from _lib.exonyms import EXONYMS, exonym_hits, gi_forms_from_names

GI = gi_forms_from_names(["Toscana", "Bourgogne", "Alsace grand cru Rangen", "Wien", "Côtes du Rhône"])


def test_forms_used_in_gi_names_are_detected():
    assert {"Toscana", "Bourgogne", "Alsace", "Wien", "Rhône"} <= set(GI)
    assert "Vosges" not in GI


def test_plain_geographic_name_is_flagged_in_its_target_locale():
    assert exonym_hits("De Vosges vormen een scherm tegen oceanische invloeden.", "nl") == ["Vosges"]
    assert exonym_hits("The Vosges shelter the vineyard.", "en") == []  # Vosges is the English form


def test_gi_homonym_is_flagged_only_as_a_place():
    assert exonym_hits("Hilly terrain in central Toscana, close to the Apennines.", "en", gi_forms=GI) == ["Toscana"]
    assert exonym_hits("Reconnu en Toscana IGT en 1995.", "en", gi_forms=GI) == []
    assert exonym_hits("The Melon de Bourgogne variety spread in the sixteenth century.", "en", gi_forms=GI) == []
    assert exonym_hits("Recognised in 2003 by the Junta de Andalucía.", "en") == []


def test_every_table_entry_has_a_valid_locale():
    assert all(set(t) <= {"en", "fr", "es", "nl"} for t in EXONYMS.values())


def test_a_form_that_is_already_the_target_form_is_never_flagged():
    # 2026-10-25: "mar Egeo" is the Spanish name, "Karpaten" the Dutch one
    assert exonym_hits("En el mar Egeo, la insolación es alta.", "es") == []
    assert exonym_hits("De beken uit de Kleine Karpaten.", "nl") == []
    assert exonym_hits("The Egeo islands.", "en") == ["Egeo"]


def test_a_form_inside_a_proper_name_or_quotes_is_the_name():
    gi = frozenset({"Toscana"})
    assert exonym_hits("part of Manciano, Magliano in Toscana, Grosseto", "en", gi_forms=gi) == []
    assert exonym_hits('the dithyramb "Bacco in Toscana" praised it', "en", gi_forms=gi) == []
    assert exonym_hits("the vineyards of Alto Piemonte", "en", gi_forms=frozenset({"Piemonte"})) == []
    assert exonym_hits("the vineyards of Toscana are warm", "en", gi_forms=gi) == ["Toscana"]


def test_a_form_inside_the_records_own_longer_name_is_the_label():
    own = ("Cannonau di Sardegna",)
    assert exonym_hits("The zone of Cannonau di Sardegna covers Sardinia.", "en",
                       gi_forms=frozenset({"Sardegna"}), own_names=own) == []
    # a record named after the region alone keeps the place reading
    assert exonym_hits("Upper Kärnten is alpine.", "en", own_names=("Kärnten",)) == ["Kärnten"]


def test_a_form_inside_the_records_own_name_is_the_label_whatever_the_apostrophe_or_case():
    """The record is « Kirsch d’Alsace » (typographic apostrophe); a
    translation writes "Kirsch d'Alsace", and "de marc d'Alsace
    Gewurztraminer" opens lower-case. Both are the GI's name, not the region."""
    assert exonym_hits("El Kirsch d'Alsace es un aguardiente blanco.", "es",
                       own_names=("Kirsch d’Alsace",)) == []
    assert exonym_hits("De reputatie van de marc d'Alsace Gewurztraminer werd erkend.", "nl",
                       own_names=("Marc d'Alsace Gewurztraminer",)) == []
    # the region on its own is still read as a place
    assert exonym_hits("Los viñedos de Alsace se extienden al pie de los Vosgos.", "es",
                       own_names=("Kirsch d’Alsace",)) == ["Alsace"]


def test_a_source_form_glossed_after_its_exonym_is_not_flagged():
    # Franken, 2026-11-24: the exonym is there, the source name glossed.
    assert exonym_hits("dans le nord de la Bavière (Bayern) et", "fr") == []
    assert exonym_hits("en el norte de Baviera (Bayern) y", "es") == []
    # the source form alone, or in brackets after something else, still is
    assert exonym_hits("dans le nord de la Bayern", "fr") == ["Bayern"]
    assert exonym_hits("dans le nord (Bayern) et", "fr") == ["Bayern"]
