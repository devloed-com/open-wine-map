"""The ΥΠΑΑΤ national spec's link section ends at the template's trailing
sections (scripts/_lib/gr/specifikacija.py, POST_LINK_ROLE, 2026-10-24)."""
from __future__ import annotations

from _lib.gr.specifikacija import (
    _TERROIR_END_ANCHORS,
    POST_LINK_ROLE,
    _fold_keep_len,
    _terroir_window,
    extract_sections,
    parse_styles,
)

FIXTURE = """1. ΟΝΟΜΑΣΙΑ
ΠΓΕ Δοκιμή
7. ΔΕΣΜΟΣ ΜΕ ΤΗ ΓΕΩΓΡΑΦΙΚΗ ΠΕΡΙΟΧΗ
Το κλίμα είναι μεσογειακό και τα εδάφη ασβεστολιθικά.
Τα δικαιολογητικά της ποιότητας είναι οι βραβεύσεις των οίνων.
ΣΤΑΦΥΛΙΑ
Οι αμπελώνες ωριμάζουν αργά στις πλαγιές.
8. ΆΛΛΕΣ ΠΡΟΫΠΟΘΈΣΕΙΣ
Επιτρέπεται η ένδειξη αφρώδης οίνος στην επισήμανση.
9. ΕΦΑΡΜΟΣΤΕΕΣ ΑΠΑΙΤΗΣΕΙΣ
Κ.Υ.Α. 5833/155045/2013.
4. ΓΛΏΣΣΑ ΑΊΤΗΣΗΣ:
Ελληνική
3. ΔΕΣΜΌΣ ΜΕ ΤΙΣ ΠΡΟΔΙΑΓΡΑΦΈΣ ΤΟΥ ΠΡΟΪΌΝΤΟΣ
Δεσμός:                http://www.minagric.gr/greek/3.6.OINOY_LIS
                       TA%20PGE.html
5. ΣΎΝΔΕΣΜΟΣ ΜΕ ΤΗΝ E-BACCHUS
Δοκιμή
"""


def test_link_ends_at_the_first_trailing_header_in_both_passes():
    for strict in (False, True):
        sections, titles = extract_sections(FIXTURE, strict=strict)
        link = sections["link_to_terroir"]
        assert link.endswith("στις πλαγιές."), (strict, link)
        # a narrative sentence naming "δικαιολογητικά" and the narrative's own
        # capitalised sub-heading do not end the link
        assert "δικαιολογητικά της ποιότητας" in link and "ΣΤΑΦΥΛΙΑ" in link
        assert "ΠΡΟΫΠΟΘΈΣΕΙΣ" not in link and "αφρώδης" not in link and "Ελληνική" not in link
        assert titles[POST_LINK_ROLE] == "ΆΛΛΕΣ ΠΡΟΫΠΟΘΈΣΕΙΣ"
        assert "Ελληνική" in sections[POST_LINK_ROLE] and "αφρώδης" in sections[POST_LINK_ROLE]
        # the form's "Δεσμός: http://…" and "ΣΥΝΔΕΣΜΟΣ ΜΕ ΤΗΝ E-BACCHUS" carry the
        # bare link keyword: once the trailing sections have opened nothing re-opens
        assert "TA%20PGE.html" not in link and "Δοκιμή" not in link
        assert "TA%20PGE.html" in sections[POST_LINK_ROLE] and "Δοκιμή" in sections[POST_LINK_ROLE]
        assert "additional_conditions" not in sections


def test_trailing_text_feeds_no_style():
    sections, _ = extract_sections(FIXTURE, strict=True)
    tail = sections[POST_LINK_ROLE]
    # the control: routed to additional_conditions the labelling rule would add a style
    assert parse_styles({"additional_conditions": tail}), "fixture must carry a style word"
    assert parse_styles(sections) == []


def test_a_trailing_header_before_the_link_is_not_a_role():
    text = "ΔΙΚΑΙΟΛΟΓΗΤΙΚΑ\nκατάλογος.\n7. ΔΕΣΜΟΣ ΜΕ ΤΗ ΓΕΩΓΡΑΦΙΚΗ ΠΕΡΙΟΧΗ\nλόγος δεσμού.\n"
    sections, _ = extract_sections(text, strict=True)
    assert POST_LINK_ROLE not in sections and sections["link_to_terroir"] == "λόγος δεσμού."


def test_eu_template_other_conditions_keeps_its_role():
    text = "ΔΕΣΜΟΣ\nκείμενο δεσμού.\nΆλλες ουσιώδεις προϋποθέσεις\nκανόνες επισήμανσης.\n"
    sections, _ = extract_sections(text, strict=True)
    assert "additional_conditions" in sections and POST_LINK_ROLE not in sections


def test_window_fallback_stops_at_the_trailing_anchors():
    for a in _TERROIR_END_ANCHORS:
        assert a == _fold_keep_len(a), a  # written as the text is folded, else it never matches
    text = "ΔΕΣΜΟΣ ΜΕ ΤΗ ΓΕΩΓΡΑΦΙΚΗ ΠΕΡΙΟΧΗ " + "ο λόγος του δεσμού " * 5 + "ΕΦΑΡΜΟΣΤΕΕΣ ΑΠΑΙΤΗΣΕΙΣ νόμος"
    assert "ΕΦΑΡΜΟΣΤΕΕΣ" not in _terroir_window(text)
    text = "ΔΕΣΜΟΣ ΜΕ ΤΗ ΓΕΩΓΡΑΦΙΚΗ ΠΕΡΙΟΧΗ " + "ο λόγος του δεσμού " * 5 + "ΑΛΛΕΣ ΠΡΟΫΠΟΘΕΣΕΙΣ επισήμανση"
    assert "ΑΛΛΕΣ" not in _terroir_window(text)
