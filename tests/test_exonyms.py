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
