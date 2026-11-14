"""The Austrian BML Produktspezifikation layer (2026-11-08): the parser
(scripts/_lib/at/produktspezifikation.py) on redacted excerpts of the
specifications, the stage-02f role rule, the stage-01c page reader, the
stage-04 augmenter and the wiring every hook needs.

Fixtures are trimmed `pdftotext -layout` output of the public BML PDFs
(tests/fixtures/at_bml_*.txt): the DAC shape with the Hauptsorten sentence
and tier lists (Wachau), the national roster in numbered colour blocks
(Niederösterreich), a title pdftotext glued to the roster's last line
(Kärnten), the 2025 template's unlettered terroir title (Kamptal), the
Steiermark trap words (Vulkanland Steiermark) and a broken quote (Leithaberg).
"""
from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.at import produktspezifikation as ps  # noqa: E402
from _lib.augment import at as aug  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
f02 = importlib.import_module("at.02f_extract_produktspezifikationen")
f01c = importlib.import_module("at.01c_fetch_produktspezifikationen")


def _parse(fixture_text, name: str) -> tuple[dict, dict, dict]:
    sections, letters = ps.slice_sections(fixture_text(name))
    return sections, letters, ps.parse_grapes(sections.get("grapes", ""))


# ---------------------------------------------------------------- slicer ----

def test_sections_are_found_by_title_with_the_letter_where_printed(fixture_text):
    sections, letters, _ = _parse(fixture_text, "at_bml_dac_wachau.txt")
    assert {"yield", "grapes", "link", "requirements"} <= set(sections)
    assert letters == {"yield": "e", "grapes": "f", "link": "g", "requirements": "h"}
    # the body starts after the title's last line (the one ending with a colon)
    assert sections["grapes"].lstrip().startswith("Die Hauptsorten der Wachau")
    assert sections["link"].lstrip().startswith("-   Angaben zum geografischen Gebiet")


def test_a_title_glued_to_the_roster_is_still_a_section(fixture_text):
    """Kärnten: pdftotext ran "Rotburger)." straight into the g) title and lost
    the letter — the title words cut the section, the roster keeps its last name."""
    sections, letters, grapes = _parse(fixture_text, "at_bml_glued_title_kaernten.txt")
    assert "link" in sections and "link" not in letters
    assert sections["link"].lstrip().startswith("-   Angaben zum geografischen Gebiet")
    assert "zweigelt" in [g["slug"] for g in grapes["roster"]]
    assert grapes["unmatched"] == []


def test_the_2025_template_terroir_title_without_a_letter(fixture_text):
    sections, letters, grapes = _parse(fixture_text, "at_bml_2025_kamptal.txt")
    assert "link" in sections and "link" not in letters
    assert letters["grapes"] == "f" and letters["requirements"] == "g"
    assert "Der Boden im Kamptal" in sections["link"]
    assert [g["slug"] for g in grapes["roster"]] == [
        "gruner-veltliner", "riesling", "chardonnay", "pinot-blanc", "pinot-gris",
    ]
    assert grapes["roster_kind"] == "exclusive-list"
    assert grapes["open_roster_clauses"] == ["anderen Qualitätsweinrebsorten"]


# ----------------------------------------------------------------- roster ----

def test_dac_hauptsorten_tiers_and_the_field_blend(fixture_text):
    _, _, grapes = _parse(fixture_text, "at_bml_dac_wachau.txt")
    assert grapes["hauptsorten"] == ["gruner-veltliner", "riesling"]
    slugs = [g["slug"] for g in grapes["roster"]]
    assert len(slugs) == 16 and "pinot-blanc" in slugs and "sankt-laurent" in slugs
    assert not any("gemischt" in g["name"].lower() for g in grapes["roster"])  # a field blend, no variety
    assert len(grapes["tiers"]["gebietswein"]) == 16
    assert len(grapes["tiers"]["ortswein"]) == 9  # the list a page break had cut after two names
    assert grapes["tiers"]["riedenwein"] == ["gruner-veltliner", "riesling"]
    # a quoted name without a colour block takes the national roster's colour
    assert next(g for g in grapes["roster"] if g["slug"] == "riesling")["colour"] == "blanc"
    assert grapes["unmatched"] == []


def test_national_roster_blocks_hyphens_brackets_and_the_hauptsorten_sentence(fixture_text):
    _, _, grapes = _parse(fixture_text, "at_bml_roster_niederoesterreich.txt")
    by_slug = {g["slug"]: g for g in grapes["roster"]}
    assert len(by_slug) == 35 and grapes["roster_kind"] == "national-roster"
    assert "goldburger" in by_slug and "jubilaeumsrebe" in by_slug  # "Goldbur-\nger", "Jubilä-\numsrebe"
    assert by_slug["bouvier"]["colour"] == "blanc" and by_slug["zweigelt"]["colour"] == "noir"
    # bracket synonyms are the regulator's own and never bind: "(Morillon)" adds no Pinot noir
    assert by_slug["pinot-noir"]["name"] == "Blauer Burgunder"
    assert by_slug["chardonnay"]["name"] == "Chardonnay"
    assert grapes["hauptsorten"] == ["gruner-veltliner", "zweigelt"]  # "… bei den Weißweinen, und … bei den Rotweinen"
    assert grapes["unmatched"] == []


def test_place_words_never_bind_and_morillon_is_chardonnay(fixture_text):
    _, _, grapes = _parse(fixture_text, "at_bml_leitsorten_vulkanland.txt")
    slugs = [g["slug"] for g in grapes["roster"]]
    assert "furmint" not in slugs  # "Steiermark" is a VIVC synonym of Furmint
    assert next(g for g in grapes["roster"] if g["slug"] == "chardonnay")["name"] == "Morillon"
    assert len(slugs) == 8 and grapes["roster_kind"] == "exclusive-list"
    assert grapes["unmatched"] == []  # the Gemeinde labels of the Leitsorten lines are not names


def test_colour_from_the_rule_sentence_and_a_broken_quote(fixture_text):
    _, _, grapes = _parse(fixture_text, "at_bml_quotes_leithaberg.txt")
    by_slug = {g["slug"]: g for g in grapes["roster"]}
    assert set(by_slug) == {"blaufrankisch", "pinot-blanc", "chardonnay", "neuburger", "gruner-veltliner"}
    assert by_slug["blaufrankisch"]["colour"] == "noir"  # "Rotwein muss aus …"
    assert by_slug["pinot-blanc"]["colour"] == "blanc"  # "Weißwein muss aus …"
    assert grapes["unmatched"] == []  # „Weißer Burgunder“ is the Pinot Blanc already read


def test_an_open_reference_alone_is_no_roster():
    body = ("Alle weißen Qualitätsweinrebsorten sind für die Erzeugung von Ruster\n"
            "Ausbruch zulässig.")
    grapes = ps.parse_grapes(body)
    assert grapes["roster"] == [] and grapes["roster_kind"] == "open"
    assert grapes["open_roster_clauses"] == ["Alle weißen Qualitätsweinrebsorten"]


def test_bare_family_words_and_blends_resolve_to_nothing():
    assert ps.resolve_variety("Burgunder") is None  # VIVC files BURGUNDER under Blaufränkisch
    assert ps.resolve_variety("Veltliner") is None
    assert ps.resolve_variety("Gemischter Satz") is None
    assert ps.resolve_variety("Steiermark") is None
    assert ps.resolve_variety("Grüner Veltliner").slug == "gruner-veltliner"
    assert ps.resolve_variety("Morillon").slug == "chardonnay"


def test_stated_colours_come_from_the_prose_with_a_wine_word():
    styles = ps.stated_colour_styles(
        "Rund 2/3 der Anbaufläche sind mit Weißwein bepflanzt, ein Drittel mit Rotwein.",
        "Rot- und Roséweine spielen eine sehr untergeordnete Rolle. 2. Rotweinrebsorten: Zweigelt.",
    )
    assert set(styles) == {"blanc", "noir", "rose"}
    assert styles["rose"].startswith("Rot- und Roséweine")
    assert ps.stated_colour_styles("Für die Gewinnung der Weine sind folgende Keltertraubensorten erlaubt") == {}


def test_augmenter_completes_a_stated_colour_list_but_never_starts_one(tmp_path, monkeypatch):
    """Oberösterreich: the EU text states white, the specification's § g states
    red — Red joins. A record whose EU text states no colour keeps the berry
    floor (a stated Red alone would switch it off and lose the White)."""
    monkeypatch.setattr(aug, "PRODUKTSPEZIFIKATION_AT", _sidecar(
        tmp_path, styles_stated=["blanc", "noir"],
        styles_evidence={"noir": "Die Rotweine werden aus den Sorten Blauer Burgunder, Zweigelt bereitet."}))
    rec = _eu_record()
    rec["styles"] = ["blanc", "sparkling"]
    aug.augment_at_records_with_produktspezifikation([rec])
    assert rec["styles"] == ["blanc", "sparkling", "noir"]
    assert rec["produktspezifikation"]["styles_added"] == ["noir"]
    assert rec["produktspezifikation"]["styles_evidence"]["noir"].startswith("Die Rotweine")
    rec = _eu_record()
    rec["styles"] = ["sparkling"]
    aug.augment_at_records_with_produktspezifikation([rec])
    assert rec["styles"] == ["sparkling"] and rec["produktspezifikation"]["styles_added"] == []


# --------------------------------------------------------------- 02f roles ----

def _roster(*slugs):
    return [{"slug": s, "name": s, "colour": ""} for s in slugs]


def test_role_rule_hauptsorten_national_roster_exclusive_list_open():
    grapes, rule = f02.assign_roles({"roster": _roster("gruner-veltliner", "riesling", "pinot-blanc"),
                                     "hauptsorten": ["gruner-veltliner", "riesling"], "roster_kind": "exclusive-list"})
    assert rule == "hauptsorten"
    assert [(g["slug"], g["role"]) for g in grapes] == [
        ("gruner-veltliner", "principal"), ("riesling", "principal"), ("pinot-blanc", "accessory")]
    grapes, rule = f02.assign_roles({"roster": _roster(*[f"v{i}" for i in range(25)]), "hauptsorten": [],
                                     "roster_kind": "national-roster"})
    assert rule == "national-roster" and {g["role"] for g in grapes} == {"accessory"}
    grapes, rule = f02.assign_roles({"roster": _roster("blaufrankisch", "zweigelt"), "hauptsorten": [],
                                     "roster_kind": "exclusive-list"})
    assert rule == "exclusive-list" and {g["role"] for g in grapes} == {"principal"}
    assert grapes[0]["colour"] == "noir"  # the national roster's colour where the text gives none
    assert f02.assign_roles({"roster": [], "hauptsorten": [], "roster_kind": "open"}) == ([], "open")


# --------------------------------------------------------------- 01c page ----

def test_page_links_display_names_slugs_and_the_duplicate_pin():
    html = ('<a href="/dam/jcr:e3bf-1/Wachau%20Produktspezifikation.pdf">x</a>'
            '<a href="/dam/jcr:9bcf-2/Vulkanland%20Steiermark_Produktspezifikation.pdf">x</a>'
            '<a href="/dam/jcr:9356-3/Produktspezifikation_Eisenberg.pdf">x</a>'
            '<a href="/dam/jcr:9559-4/Eisenberg%20Produktspezifikation.pdf">x</a>'
            '<a href="/dam/jcr:c93a-5/K%C3%A4rnten%20Produktspezifikation.pdf">x</a>')
    links = f01c.page_links(html)
    assert [(lk["display"], lk["slug"]) for lk in links] == [
        ("Wachau", "wachau"), ("Vulkanland Steiermark", "vulkanland-steiermark"),
        ("Eisenberg", "eisenberg"), ("Eisenberg", "eisenberg"), ("Kärnten", "karnten")]
    assert links[0]["url"] == "https://www.bmluk.gv.at/dam/jcr:e3bf-1/Wachau%20Produktspezifikation.pdf"
    eis = [lk for lk in links if lk["slug"] == "eisenberg"]
    chosen, how = f01c.choose(eis, None)
    assert chosen is None and how.startswith("ambiguous")
    pins = json.loads((ROOT / "scripts/_lib/at/produktspezifikation_pins.json").read_text(encoding="utf-8"))
    chosen, how = f01c.choose(eis, pins["eisenberg"])
    assert how == "pinned" and chosen["filename"] == "Produktspezifikation_Eisenberg.pdf"
    assert f01c.choose(eis[:1], None) == (eis[0], "single")


# -------------------------------------------------------------- augmenter ----

def _eu_record(link_chars: int = 1800) -> dict:
    return {
        "country": "at", "slug": "wachau", "name": "Wachau",
        "grapes": {"principal": ["gruner-veltliner", "riesling"], "accessory": [], "observation": [],
                   "details": [{"slug": "gruner-veltliner", "name": "Grüner Veltliner", "role": "principal", "colour": "blanc"},
                               {"slug": "riesling", "name": "Weißer Riesling", "role": "principal", "colour": ""}]},
        "link_to_terroir": "x" * link_chars,
        "section_roles": {"link_to_terroir": "x" * link_chars},
        "source": {"final_url": "https://eur-lex.europa.eu/x"},
    }


def _sidecar(tmp_path: Path, slug: str = "wachau", **over) -> Path:
    side = {
        "slug": slug, "parser_template": "bml-produktspezifikation-v1", "role_rule": "hauptsorten",
        "grapes": [{"slug": "gruner-veltliner", "name": "Grüner Veltliner", "colour": "blanc", "role": "principal"},
                   {"slug": "riesling", "name": "Riesling", "colour": "blanc", "role": "principal"},
                   {"slug": "pinot-blanc", "name": "Weißer Burgunder", "colour": "blanc", "role": "accessory"},
                   {"slug": "zweigelt", "name": "Zweigelt", "colour": "noir", "role": "accessory"}],
        "hauptsorten": ["gruner-veltliner", "riesling"], "open_roster_clauses": ["anderen Qualitätsweinrebsorten"],
        "zusammenhang_text": "g" * 1000,
        "source": {"url": "https://www.bmluk.gv.at/dam/jcr:x/Wachau.pdf", "sha256": "abc", "bytes": 1,
                   "fetched_at": "2026-11-08T10:00:00+00:00", "source_org": "BML", "license": "§ 7 UrhG"},
    }
    side.update(over)
    (tmp_path / f"{slug}.json").write_text(json.dumps(side), encoding="utf-8")
    return tmp_path


def test_augmenter_adds_the_specification_varieties_and_keeps_the_eu_roster(tmp_path, monkeypatch):
    monkeypatch.setattr(aug, "PRODUKTSPEZIFIKATION_AT", _sidecar(tmp_path))
    rec = _eu_record()
    assert aug.augment_at_records_with_produktspezifikation([rec, {"country": "de", "slug": "mosel"}]) == 1
    g = rec["grapes"]
    assert g["principal"] == ["gruner-veltliner", "riesling"] and g["accessory"] == ["pinot-blanc", "zweigelt"]
    assert g["details"][1]["name"] == "Weißer Riesling"  # the EU document's own spelling stays
    assert g["details"][2] == {"slug": "pinot-blanc", "name": "Weißer Burgunder", "role": "accessory",
                               "colour": "blanc", "source": "bml-produktspezifikation"}
    prov = rec["produktspezifikation"]
    assert prov["added_slugs"] == ["pinot-blanc", "zweigelt"] and prov["n_added"] == 2
    assert prov["role_rule"] == "hauptsorten" and prov["url"].endswith("Wachau.pdf")
    assert aug._AT_PRODUKTSPEZIFIKATION_BY_SLUG["wachau"] is prov
    assert "terroir_backfilled" not in prov and rec["link_to_terroir"] == "x" * 1800  # the EU text is long enough


def test_augmenter_backfills_a_short_eu_link_from_section_g(tmp_path, monkeypatch):
    monkeypatch.setattr(aug, "PRODUKTSPEZIFIKATION_AT", _sidecar(tmp_path))
    rec = _eu_record(link_chars=347)
    aug.augment_at_records_with_produktspezifikation([rec])
    assert rec["link_to_terroir"] == "g" * 1000 and rec["section_roles"]["link_to_terroir"] == "g" * 1000
    assert rec["source"]["terroir_source_org"] == "BML"
    assert rec["produktspezifikation"]["terroir_backfilled"] is True


def test_augmenter_promotes_a_hauptsorte_the_eu_document_lacks_and_skips_subdenominations(tmp_path, monkeypatch):
    monkeypatch.setattr(aug, "PRODUKTSPEZIFIKATION_AT", _sidecar(
        tmp_path, grapes=[{"slug": "welschriesling", "name": "Welschriesling", "colour": "blanc", "role": "principal"},
                          {"slug": "gruner-veltliner", "name": "Grüner Veltliner", "colour": "blanc", "role": "principal"}],
        hauptsorten=["welschriesling", "gruner-veltliner"]))
    rec = _eu_record()
    aug.augment_at_records_with_produktspezifikation([rec])
    assert rec["grapes"]["principal"] == ["gruner-veltliner", "riesling", "welschriesling"]
    assert rec["grapes"]["accessory"] == []
    sub = _eu_record()
    sub["is_sub_denomination"] = True
    assert aug.augment_at_records_with_produktspezifikation([sub]) == 0
    assert "produktspezifikation" not in sub


# ------------------------------------------------------------------ wiring ----

def test_stage04_and_the_card_are_wired():
    stage04 = (ROOT / "scripts/04_build_maps.py").read_text(encoding="utf-8")
    for needle in (
        "from _lib.augment.at import augment_at_records_with_produktspezifikation",
        "n_aug_at = augment_at_records_with_produktspezifikation(extracted_records)",
        '"bml_produktspezifikation_url": at_spec.get("url", "")',
        '"bml_produktspezifikation_added_slugs"',
        'or (country == "at" and slug in _AT_PRODUKTSPEZIFIKATION_BY_SLUG)',
        '"_AT_PRODUKTSPEZIFIKATION_BY_SLUG": _AT_PRODUKTSPEZIFIKATION_BY_SLUG,',
    ):
        assert needle in stage04, needle
    assert 'sources.get("bml_produktspezifikation_url")' in (ROOT / "scripts/_lib/content_block.py").read_text(encoding="utf-8")
    assert "sources.bml_produktspezifikation_url" in (ROOT / "scripts/_lib/assets/app.js").read_text(encoding="utf-8")
    tmpl = (ROOT / "scripts/_lib/map_template.py").read_text(encoding="utf-8")
    assert '"src_bml_produktspezifikation": _(' in tmpl and '"bml_produktspezifikation_url"' in tmpl
    d02 = (ROOT / "scripts/at/02d_extract_terroir_facts.py").read_text(encoding="utf-8")
    assert 'produktspezifikationen-extracted' in d02 and '"bml-produktspezifikation"' in d02
    for lang in ("en", "fr", "es", "nl"):
        po = (ROOT / f"locale/{lang}/LC_MESSAGES/messages.po").read_text(encoding="utf-8")
        m = re.search(r'msgid "Cahier des charges national \(BML, PDF\)"\nmsgstr "([^"]+)"', po)
        assert m and m.group(1), lang
