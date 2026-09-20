"""Pure checks of scripts/audit_terroir_facts.py on synthetic input — no raw/ access."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import audit_terroir_facts as audit  # noqa: E402

# ───────────────────────────────────────────────── name guard (W2b) ──


def test_name_tokens_drop_stop_words_and_short_tokens():
    assert audit.name_tokens("Côtes du Rhône Villages") == ["rhone"]
    assert audit.name_tokens("Saint-Pourçain") == ["pourcain"]
    assert audit.name_tokens("L'Étoile") == ["etoile"]
    assert audit.name_tokens("Grands-Echezeaux") == ["echezeaux"]
    assert audit.name_tokens("Alsace grand cru Zotzenberg") == ["alsace", "zotzenberg"]
    assert audit.name_tokens("Grand Cru") == []


def _lien(sentence: str) -> str:
    lien = (sentence + " ") * 30
    assert len(lien) >= audit.NAME_GUARD_MIN_LIEN
    return lien


def test_name_guard_passes_when_the_lien_names_the_appellation():
    lien = _lien("Le vignoble de Pierrevert s'étend sur les collines de Haute-Provence.")
    assert audit.lien_names_record(lien, "Pierrevert") is True
    assert audit.name_guard_finding(lien, "Pierrevert", "pierrevert") is False


def test_name_guard_fires_when_the_lien_never_names_it():
    lien = _lien("Le vignoble de Saint-Pourçain s'étend sur les coteaux de l'Allier.")
    assert audit.lien_names_record(lien, "Pierrevert") is False
    assert audit.name_guard_finding(lien, "Pierrevert", "pierrevert") is True


def test_name_guard_folds_accents_and_case():
    lien = _lien("LE VIGNOBLE DE L'ETOILE DOMINE LA PLAINE DE LONS-LE-SAUNIER.")
    assert audit.name_guard_finding(lien, "L'Étoile", "l-etoile") is False


def test_name_guard_respects_whitelist_short_lien_and_untestable_names():
    lien = _lien("Le vignoble bourguignon s'étend sur des coteaux calcaires exposés à l'est.")
    assert audit.name_guard_finding(lien, "Saône-et-Loire", "saone-et-loire") is False
    assert audit.name_guard_finding(lien, "Saône-et-Loire", "other-slug") is True
    assert audit.name_guard_finding(lien[:400], "Pierrevert", "pierrevert") is False
    assert audit.lien_names_record(lien, "Grand Cru") is None
    assert audit.name_guard_finding(lien, "Grand Cru", "grand-cru") is False


# ────────────────────────────────────────────────── style checks (W5) ──


@pytest.mark.parametrize(
    "bullet,expected",
    [
        ("Cépages : pinot noir N et chardonnay B.", True),
        ("Riesling B, gewurztraminer Rs et pinot gris G dominent.", True),
        ("Pinot Noir N is the only red variety.", True),
        ("Vignoble de Colmar N exposé au sud.", False),
        ("Classé en 1936 en catégorie B du référentiel.", False),
        ("Sols argilo-calcaires sur marnes du Kimméridgien.", False),
    ],
)
def test_colour_code_needs_a_grape_name(bullet, expected):
    assert audit.has_colour_code(bullet) is expected


def test_label_prefix_is_a_short_non_numeric_lead():
    assert audit.has_label_prefix("Rioja Oriental: climat méditerranéen plus chaud.")
    assert audit.has_label_prefix("  Sols: marnes et calcaires.")
    assert not audit.has_label_prefix("En 1936: premier classement.")
    assert not audit.has_label_prefix("Sols argilo-calcaires sur marnes.")
    assert not audit.has_label_prefix(
        "Un très long préambule de plus de trente caractères ici: puis le fait."
    )


@pytest.mark.parametrize(
    "bullet,expected",
    [
        ("Sols argilo-calcaires", True),
        ("Sols argilo-calcaires.", False),
        ("Sols argilo-calcaires…  ", False),
        ("Vraiment ?", False),
        ("Oui !", False),
        ("Cité « Marnes »", True),
        ("", True),
    ],
)
def test_missing_terminal_punctuation(bullet, expected):
    assert audit.missing_terminal_punct(bullet) is expected


def test_arrow_and_meta_text():
    assert audit.has_arrow("Marnes → vins puissants.")
    assert not audit.has_arrow("Marnes, donc vins puissants.")
    assert audit.has_meta_text("Slate soils, confirmed by Wikipedia.")
    assert audit.has_meta_text("The disciplinare states that yields are capped.")
    assert audit.has_meta_text("According to the specification, the area is 5 ha.")
    assert not audit.has_meta_text("Slate soils on south-facing slopes.")
    # source-language forms
    assert audit.has_meta_text("Un'epoca iniziata 70 milioni di anni fa secondo il disciplinare.")
    assert audit.has_meta_text("Les sols sont calcaires, selon le cahier des charges.")
    assert audit.has_meta_text("Laut Produktspezifikation dominieren Schieferböden.")
    assert not audit.has_meta_text("Il disciplinare del 1966 fu il primo in Italia.")   # a dated fact about the rules, not a citation


def test_style_findings_lists_every_defect_in_order():
    assert audit.style_findings(
        "Rioja Oriental: pinot noir N → vins, confirmed by Wikipedia"
    ) == ["colour_code", "arrow", "label_prefix", "no_terminal_punct", "meta_text"]
    assert audit.style_findings("Sols argilo-calcaires sur marnes.") == []


# ─────────────────────────────────────────────────── non-Latin (W1) ──


@pytest.mark.parametrize(
    "bullet,expected",
    [
        ("Soils of чернозем dominate the plain.", True),
        ("Vines on ασβεστόλιθος bedrock.", True),
        ("Sols argilo-calcaires à Chablis, Kimméridgien.", False),
        ("Ġellewża and Girgentina; Furmint, Hárslevelű, Žametovka.", False),
        ("", False),
    ],
)
def test_non_latin_detection(bullet, expected):
    assert audit.has_non_latin(bullet) is expected


# ─────────────────────────────────────────────────── duplicates (W3) ──


def fact(bullet, *, cq="", wq="", prov="cahier", sub="facteurs_naturels"):
    return {"bullet": bullet, "cahier_quote": cq, "wiki_quote": wq, "provenance": prov, "subsection": sub}


def test_intra_record_duplicates_reports_each_pair():
    facts = [
        fact("Marne calcaree argillose favoriscono potenza e longevità; macigno toscano apporta serbevolezza."),
        fact("Marne calcaree danno potenza e longevità; macigno toscano conferisce serbevolezza.", sub="produit"),
        fact("Clima mediterraneo con estati calde e inverni miti."),
    ]
    assert audit.intra_record_duplicates(facts) == [{"i": 0, "j": 1, "reason": "similar-bullet"}]
    assert audit.intra_record_duplicates(facts[1:]) == []


# ──────────────────────────────────────────── own chapter (W2a) & W4 ──


def chapter(name: str, body: str) -> str:
    return (
        f"                 « Alsace grand cru {name} »\n\n"
        f"1°– Informations sur la zone géographique\n\na) - Description des facteurs naturels\n\n{body}\n\n"
        f"2°– Informations sur la qualité et les caractéristiques des produits\n\nVins blancs.\n\n"
        f"3°– Interactions causales\n\nLe lien.\n\n"
    )


SHARED_LIEN = (
    chapter("Altenberg de Bergheim", "Marnes et calcaires du Keuper sur une pente forte exposée au sud.")
    + chapter("Kastelberg", "Schistes de Steige, sombres et friables, sur un coteau escarpé.")
    + chapter("Zotzenberg", "Marnes très denses sur socle calcaire, vignoble en amphithéâtre.")
)


def test_own_chapter_findings_flag_quotes_taken_from_another_cru():
    facts = [
        fact("Schistes de Steige.", cq="Schistes de Steige, sombres et friables"),
        fact("Marnes denses.", cq="Marnes très denses sur socle calcaire, vignoble en amphithéâtre"),
        fact("Vins blancs.", cq=""),
    ]
    rows = audit.own_chapter_findings(SHARED_LIEN, "Alsace grand cru Kastelberg", facts)
    assert [(r["check"], r["index"]) for r in rows] == [("quote_outside_own_chapter", 1)]
    assert rows[0]["coverage"] < audit.FUZZY_THRESHOLD
    assert audit.own_chapter_findings(SHARED_LIEN, "Kastelberg", facts) == rows


def test_own_chapter_findings_when_the_record_has_no_chapter_or_the_lien_is_not_shared():
    facts = [fact("x", cq="Schistes de Steige")]
    assert audit.own_chapter_findings(SHARED_LIEN, "Alsace grand cru Rangen", facts) == [
        {"check": "no_own_chapter"}
    ]
    assert audit.own_chapter_findings(chapter("Rangen", "Roches volcaniques."), "Chablis", facts) == []


def test_wiki_provenance_with_a_cahier_quote():
    facts = [
        fact("a", cq="quote", prov="wiki"),
        fact("b", cq="", prov="wiki"),
        fact("c", cq="quote", prov="both"),
        fact("d", cq="  ", prov="wiki"),
    ]
    assert audit.wiki_with_cahier_quote(facts) == [0]


def test_shared_quote_groups_need_three_records_and_sixty_chars():
    long_quote = "Les sols argilo-calcaires du Kimméridgien confèrent minéralité et tension aux vins"
    short_quote = "Sols argilo-calcaires du Kimméridgien"
    by_slug = {
        "a": [fact("x", cq=long_quote), fact("y", cq=short_quote)],
        "b": [fact("x", cq="  " + long_quote.upper() + " ")],
        "c": [fact("x", cq=long_quote), fact("z", cq=long_quote)],
        "d": [fact("x", cq=short_quote)],
        "e": [fact("x", cq=short_quote)],
    }
    groups = audit.shared_quote_groups(by_slug)
    assert groups == [{"quote": long_quote.lower(), "count": 3, "slugs": ["a", "b", "c"]}]
    assert audit.shared_quote_groups({"a": by_slug["a"], "b": by_slug["b"]}) == []


def test_own_chapter_check_skips_wiki_grounded_facts():
    lien = (
        "                 « Alsace grand cru Rangen »\n\n1°– Zone\n\nSols volcaniques du Rangen." + " x" * 40 + "\n\n"
        "                 « Alsace grand cru Zotzenberg »\n\n1°– Zone\n\nMarnes denses du Zotzenberg." + " y" * 40 + "\n\n"
    )
    facts = [
        {"cahier_quote": "Marnes denses du Zotzenberg", "provenance": "cahier"},
        {"cahier_quote": "Marnes denses du Zotzenberg", "provenance": "wiki"},
        {"cahier_quote": "Sols volcaniques du Rangen", "provenance": "both"},
    ]
    rows = audit.own_chapter_findings(lien, "Alsace grand cru Rangen", facts)
    assert [r["index"] for r in rows] == [0]


def test_greek_chemical_prefix_is_not_non_latin():
    assert not audit.has_non_latin("A bitter, resinous note of α-terpineol.")
    assert audit.has_non_latin("Terraces (πεζούλες) up to 900 m.")


# ───────────────────────────────────────── review 2026-09-12 additions (R9) ──


def test_name_guard_requires_the_whole_name_or_a_long_token():
    from audit_terroir_facts import lien_names_record
    beaujolais = "Le vignoble du Beaujolais s'étend sur tout le territoire; les grains sont petits. " * 20
    assert lien_names_record(beaujolais, "Bourgogne Passe-tout-grains") is False   # "tout" / "grains" no longer enough
    assert lien_names_record("… l'appellation Bourgogne Passe-tout-grains … " * 5, "Bourgogne Passe-tout-grains") is True
    assert lien_names_record("… les vins de Bourgogne … " * 5, "Bourgogne Passe-tout-grains") is True  # longest token ≥ 6
    assert lien_names_record("… le cru de Volnay … " * 5, "Volnay") is True
    assert lien_names_record("… " * 50, "Volnay") is False
    assert lien_names_record("x", "AOC de la") is None


def test_foreign_name_guard_flags_a_pasted_or_mis_bound_text():
    from audit_terroir_facts import foreign_names
    text = ("Η ζώνη ΠΓΕ Παρνασσός καλύπτει τους δήμους … Παρνασσός … Παρνασσός … Παρνασσός … Παρνασσός … " + "λοιπά " * 300)
    from audit_terroir_facts import name_tokens
    others = {s: " ".join(name_tokens(n)) for s, n in
              (("parnassos", "Παρνασσός"), ("fthiotida", "Φθιώτιδα"), ("attiki", "Αττική"))}
    hits = foreign_names(text, "Φθιώτιδα", others)
    assert [h["other"] for h in hits] == ["parnassos"] and hits[0]["hits"] >= 5
    assert foreign_names("Η ζώνη Φθιώτιδα … " + "Παρνασσός " * 6 + "x " * 500, "Φθιώτιδα", others) == []
    # a name contained in the record's own name is not foreign (Chianti in Chianti Classico)
    assert foreign_names("Chianti Chianti Chianti " + "x " * 500, "Chianti Classico", {"chianti": "chianti"}) == []


def test_multi_sentence_check():
    from audit_terroir_facts import has_multiple_sentences
    assert has_multiple_sentences("The soils are clay. The climate is dry.")
    assert not has_multiple_sentences("The wine reaches 13.5 % vol. in warm years.")
    assert not has_multiple_sentences("Yields are capped at 60 hl/ha.")


def test_identical_en_groups():
    from audit_terroir_facts import identical_en_groups
    groups = identical_en_groups({
        "a": ["Grand cru wines are aged for eighteen months in oak.", "unique"],
        "b": ["Grand cru wines are aged for eighteen months in oak."],
        "c": ["Short."],
    })
    assert len(groups) == 1 and groups[0]["slugs"] == ["a", "b"]


def test_wiki_binding_check_reads_the_cached_article(tmp_path, monkeypatch):
    import audit_terroir_facts as a
    monkeypatch.setattr(a, "WIKI_AOCS", tmp_path)
    (tmp_path / "de").mkdir()
    (tmp_path / "de" / "tirol.json").write_text(json.dumps({"page_url": "https://de.wikipedia.org/wiki/Toro_(Weinbaugebiet)", "revision": "1"}), encoding="utf-8")
    (tmp_path / "de" / "wachau.json").write_text(json.dumps({"page_url": "https://de.wikipedia.org/wiki/Wachau_(Weinbaugebiet)", "revision": "1"}), encoding="utf-8")
    (tmp_path / "de" / "pinned.json").write_text(json.dumps({"page_url": "https://de.wikipedia.org/wiki/Anything", "override_source": "curator"}), encoding="utf-8")
    (tmp_path / "el").mkdir()
    (tmp_path / "el" / "samos.json").write_text(json.dumps({"page_url": "https://el.wikipedia.org/wiki/%CE%A3%CE%AC%CE%BC%CE%BF%CF%82", "revision": "1"}), encoding="utf-8")
    assert a.wiki_binding_finding("at", "de", "tirol", "Tirol") == {"title": "Toro (Weinbaugebiet)", "lang": "de"}
    assert a.wiki_binding_finding("at", "de", "wachau", "Wachau") is None
    assert a.wiki_binding_finding("at", "de", "pinned", "Whatever") is None          # curator pins are trusted
    assert a.wiki_binding_finding("gr", "el", "samos", "Σάμος") is None             # percent-encoded Greek title
    assert a.wiki_binding_finding("gr", "el", "missing-file", "X") is None


def test_coverage_is_block_aware_across_a_pdftotext_artefact():
    from _lib.terroir_coverage import fuzzy_coverage
    source = ("L'indice termico di Winkler, ossia la temperatura media attiva nel periodo aprile-ottobre, è compreso\n"
              "tra 1.800 e 2.200 gradi- giorno, condizioni che garantiscono la maturazione ottimale del vitigno\nMontepulciano.")
    quote = ("L'indice termico di Winkler, ossia la temperatura media attiva nel periodo aprile-ottobre, è compreso "
             "tra 1.800 e 2.200 gradi-giorno, condizioni che garantiscono la maturazione ottimale del vitigno Montepulciano")
    assert fuzzy_coverage(quote, source) >= 0.95            # one artefact ("gradi- giorno") no longer halves it
    assert fuzzy_coverage("temperatura media attiva nel periodo aprile-ottobre", source) == 1.0
    assert fuzzy_coverage("clima temperato, suoli argillosi profondi, vigneti a 300 m", source) < 0.3   # scattered
    assert fuzzy_coverage("Bordeaux gravel terraces beside the Gironde estuary", source) < 0.3      # foreign


def test_translation_stale_flags_an_outdated_key_but_not_pending(tmp_path, monkeypatch):
    from _lib.terroir_dedupe import facts_sha
    monkeypatch.setattr(audit, "TRANSLATIONS", tmp_path)
    src = [{"bullet": "Les sols sont calcaires."}]
    for lang, key in (("en", facts_sha(src)), ("es", "0" * 64), ("nl", "pending:" + "0" * 64)):
        (tmp_path / lang).mkdir()
        (tmp_path / lang / "x.json").write_text(json.dumps({"source_facts_sha": key, "facts": [{"bullet": "Soils are limestone."}]}))
    _, rows, _ = audit.audit_translations("x", src)
    assert [(r["lang"]) for r in rows if r["check"] == "translation_stale"] == ["es"]
