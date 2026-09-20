"""Two naming axes (scripts/_lib/gi_terms.py): scheme derivation, the single
label composer, the facet key, the facet tree, and the SSR meta-line tokens.

The ruling table (traditional_terms.json) is exercised only through the pure
helpers here; roster joins (MASAF / MAPA) have their own fixture tests."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib import gi_terms as g  # noqa: E402
from _lib.content_block import RenderCtx, classification_html  # noqa: E402

LABELS = {"scheme_pdo": "PDO", "scheme_pgi": "PGI", "scheme_spirit_gi": "spirit-drink GI"}
LABELS_FR = {"scheme_pdo": "AOP", "scheme_pgi": "IGP", "scheme_spirit_gi": "IG spiritueux"}


def test_scheme_from_siqo_signe_ue_for_france() -> None:
    assert g.derive_eu_scheme({"country": "fr", "signe_ue": "AOP"}, "AOC") == "pdo"
    assert g.derive_eu_scheme({"country": "fr", "signe_ue": "IGP"}, "IGP") == "pgi"
    assert g.derive_eu_scheme({"country": "fr", "signe_ue": "IG"}, "EDV") == "spirit-gi"


def test_scheme_falls_back_on_the_derived_kind_when_signe_is_empty() -> None:
    assert g.derive_eu_scheme({"country": "fr", "slug": "cote-roannaise"}, "AOC") == "pdo"
    assert g.derive_eu_scheme({"country": "fr", "slug": "x"}, "EDV") == "spirit-gi"


def test_switzerland_has_no_scheme_and_uk_is_its_own_register() -> None:
    assert g.derive_eu_scheme({"country": "ch"}, "AOC") == "none"
    assert g.derive_eu_scheme({"country": "gb"}, "DOP") == "uk-pdo"
    assert g.derive_eu_scheme({"country": "gb"}, "IGP") == "uk-pgi"
    assert g.derive_eu_scheme({"country": "it"}, "DOP") == "pdo"
    assert g.derive_eu_scheme({"country": "it"}, "IGP") == "pgi"


def test_label_is_term_then_localised_scheme_in_brackets() -> None:
    assert g.classification_label("DOQ", "pdo", LABELS) == "DOQ (PDO)"
    assert g.classification_label("DOCG", "pdo", LABELS_FR) == "DOCG (AOP)"
    assert g.classification_label("AOC", "spirit-gi", LABELS) == "AOC (spirit-drink GI)"


def test_label_degrades_to_one_token_never_two_equal_ones() -> None:
    assert g.classification_label("AOC", "none", LABELS) == "AOC"
    assert g.classification_label("", "pgi", LABELS) == "PGI"
    assert g.classification_label("", "uk-pdo", LABELS) == "PDO"
    assert g.classification_label("IGP", "pgi", LABELS_FR) == "IGP"
    assert g.classification_label("", "none", LABELS) == ""


def test_class_key_is_padded_scheme_then_slugified_term() -> None:
    assert g.class_key("pdo", "it", "DOCG") == ";pdo;it:docg;"
    assert g.class_key("pgi", "es", "Vino de la Tierra") == ";pgi;es:vino-de-la-tierra;"
    assert g.class_key("none", "ch", "AOC") == ";none;ch:aoc;"
    assert g.class_key("pdo", "de", "") == ";pdo;"
    assert g.term_key("mt", "IĠT") == "mt:igt"


def test_term_tree_orders_schemes_then_terms_by_count() -> None:
    tree, desc = g.build_term_tree({
        ";pdo;it:docg;": 79, ";pdo;it:doc;": 332, ";pdo;": 12, ";pgi;it:igt;": 112,
        ";none;ch:aoc;": 30, ";spirit-gi;fr:aoc;": 28,
    })
    assert [n["slug"] for n in tree if n["depth"] == 0] == ["pdo", "pgi", "spirit-gi", "none"]
    pdo = next(n for n in tree if n["slug"] == "pdo")
    assert pdo["count"] == 79 + 332 + 12
    kids = [n["slug"] for n in tree if n["parent"] == "pdo"]
    assert kids == ["it:doc", "it:docg"]
    assert desc["pdo"] == ["pdo", "it:doc", "it:docg"]
    assert desc["it:docg"] == ["it:docg"]


def _ctx(terms_info: dict) -> RenderCtx:
    return RenderCtx(
        locale="en", labels={}, region_labels={}, country_labels={}, country_flag_emoji={},
        grapes_info={}, styles_info={}, style_labels={}, github_new_issue_url="",
        terms_info=terms_info,
    )


def test_ssr_meta_line_splits_term_and_scheme_into_two_spans() -> None:
    info = {"it:docg": {"full": "Denominazione di origine controllata e garantita", "note": "top tier"},
            "pdo": {"full": "Protected Designation of Origin", "note": "EU scheme"}}
    rec = {"class_label": "DOCG (PDO)", "national_term": "DOCG", "eu_scheme": "pdo",
           "class_key": ";pdo;it:docg;", "country": "it"}
    html = classification_html(rec, _ctx(info))
    assert '<span class="gi-term has-info" tabindex="0" data-key="it:docg">' in html
    assert '<span class="gi-scheme has-info" tabindex="0" data-key="pdo">' in html
    assert "<abbr title=\"Denominazione di origine controllata e garantita — top tier\">DOCG</abbr>" in html
    assert html.endswith("(PDO)</abbr></span>")


def test_ssr_meta_line_without_definitions_is_plain_text() -> None:
    rec = {"class_label": "AOC", "national_term": "AOC", "eu_scheme": "none",
           "class_key": ";none;ch:aoc;", "country": "ch"}
    assert classification_html(rec, _ctx({})) == '<span class="gi-term" data-key="ch:aoc">AOC</span>'
    rec = {"class_label": "PDO", "national_term": "", "eu_scheme": "uk-pdo", "country": "gb"}
    assert classification_html(rec, _ctx({})) == '<span class="gi-scheme" data-key="uk-pdo">PDO</span>'
    assert classification_html({"class_label": ""}, _ctx({})) == ""


def test_table_refuses_a_scheme_abbreviation_in_a_term_slot(tmp_path: Path) -> None:
    import json

    import pytest

    bad = tmp_path / "t.json"
    bad.write_text(json.dumps({"constants": {"hu": {"DOP": "OEM"}}}), encoding="utf-8")
    with pytest.raises(ValueError, match="OEM"):
        g.load_terms_table_from(bad)
    bad.write_text(json.dumps({"terms": {"si:ZOP": {"scheme": "pdo"}}}), encoding="utf-8")
    with pytest.raises(ValueError, match="ZOP"):
        g.load_terms_table_from(bad)
    ok = tmp_path / "ok.json"
    ok.write_text(json.dumps({"constants": {"pt": {"DOP": "DOC", "IGP": "Vinho Regional"}},
                              "terms": {"pt:DOC": {"scheme": "pdo"}}}), encoding="utf-8")
    assert g.load_terms_table_from(ok)["constants"]["pt"]["DOP"] == "DOC"


def test_all_four_axis_fields_ship_in_the_startup_blob() -> None:
    from _lib.map_template import STARTUP_AOCS_FIELDS

    assert {"eu_scheme", "national_term", "class_key", "class_label"} <= STARTUP_AOCS_FIELDS
