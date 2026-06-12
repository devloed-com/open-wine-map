"""Fixture-based regression tests for the Italy (IT) parsers.

Three parser modules, each with its own documented seam:

  - scripts/_lib/it/sottozona.py — sottozona detection.
      Pattern A: a "Sottozona NAME:" header at the start of a line
        followed by a commune body.
      Pattern B: a preamble ("...le seguenti sottozone:") + a comma-and-
        "e"-separated, often guillemet-wrapped and parent-name-prefixed
        list. Pattern B is the only shape any real IT document fires in
        the current corpus (Chianti 7, Valtellina 5, Bardolino 3); the
        prefix-header fixture is therefore `# synthetic`.

  - scripts/_lib/it/menzione.py — MGA/UGA harvesting.
      List shape is chosen BY YIELD, not marker count: parse the block
      both ways (numbered + comma) and keep whichever recovers more
      names. Chianti Classico's 11 UGAs are a numbered list; Barolo's
      181 MGAs are a long comma list carrying stray "del comune di X"
      prose + an "art. N" reference that must not divert it to the
      numbered parser.

  - scripts/_lib/it/masaf.py — MASAF disciplinare article carving +
      Article-2 grape candidate extraction (extract_articles,
      article2_candidate_phrases, parse_grapes_with).

Fixtures are short, redacted excerpts of public regulator documents
(MASAF consolidated disciplinari, EU-OJ documenti unici) under
tests/fixtures/it_*.txt — see tests/fixtures/README.md. Synthetic
fixtures carry a `# synthetic` first-line marker and exist only where no
cached raw/ document exercises the branch (Pattern A; the stray-art.-N
guard in isolation).

Assertions follow ACTUAL parser behaviour, not the regulator's intent.
test_menzione_numbered_list_keeps_name_with_lowercase_connector exercises
the widened _NAME_TOKEN_RE that keeps a UGA whose name carries a lowercase
Italian connector ("San Donato in Poggio") intact.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.grape_entity import match_variety  # noqa: E402
from _lib.it.masaf import (  # noqa: E402
    article2_candidate_phrases,
    extract_articles,
    find_article_offsets,
    parse_grapes_with,
)
from _lib.it.menzione import extract_menzioni  # noqa: E402
from _lib.it.sottozona import extract_sottozone  # noqa: E402


def _names(records: list[dict]) -> list[str]:
    return [r["name"] for r in records]


def _slugs(records: list[dict]) -> list[str]:
    return [r["slug"] for r in records]


def _patterns(records: list[dict]) -> set[str]:
    return {r["source_pattern"] for r in records}


# ==========================================================================
# sottozona — Pattern B (preamble + list)
# ==========================================================================

def test_sottozona_pattern_b_chianti_seven(fixture_text):
    text = fixture_text("it_sottozona_chianti_preamble_list.txt")
    out = extract_sottozone(text, "Chianti")

    # All 7 Chianti sottozone, parent prefix stripped, guillemets gone.
    assert _names(out) == [
        "Colli Aretini",
        "Colli Fiorentini",
        "Colli Senesi",
        "Colline Pisane",
        "Montalbano",
        "Montespertoli",
        "Rufina",
    ]
    # Slug derives from the bare (prefix-stripped) name.
    assert "colli-aretini" in _slugs(out)
    assert "rufina" in _slugs(out)
    # Single source pattern, the preamble-list branch.
    assert _patterns(out) == {"sottozona-preamble-list"}


def test_sottozona_pattern_b_strips_guillemets_and_parent_prefix(fixture_text):
    text = fixture_text("it_sottozona_chianti_preamble_list.txt")
    out = extract_sottozone(text, "Chianti")
    # No guillemet glyph survives in any name.
    for name in _names(out):
        assert "«" not in name and "»" not in name
    # The bare parent name "Chianti" never appears as a standalone
    # sottozona (it collapses to empty after prefix strip and is dropped),
    # and no name still carries the "Chianti " prefix.
    assert "Chianti" not in _names(out)
    for name in _names(out):
        assert not name.startswith("Chianti ")


def test_sottozona_pattern_b_final_e_conjunction(fixture_text):
    # The last item ("e «Chianti Rufina»") is separated by the Italian
    # final conjunction ` e `, not a comma — it must still be captured.
    text = fixture_text("it_sottozona_chianti_preamble_list.txt")
    out = extract_sottozone(text, "Chianti")
    assert "Rufina" in _names(out)


def test_sottozona_parent_name_excluded_from_yield():
    # The parent's own slug is pre-seeded into the seen set, so a list
    # that restates the parent does not emit a duplicate record for it.
    text = "comprende le seguenti sottozone: Chianti, Colli Aretini e Rufina."
    out = extract_sottozone(text, "Chianti")
    assert "Chianti" not in _names(out)
    assert "Colli Aretini" in _names(out)
    assert "Rufina" in _names(out)


# ==========================================================================
# sottozona — Pattern A (line-start "Sottozona NAME:" header) — synthetic
# ==========================================================================

def test_sottozona_pattern_a_prefix_header(fixture_text):
    text = fixture_text("it_sottozona_prefix_header.txt")
    out = extract_sottozone(text, "Irpinia")
    assert _names(out) == ["Campi Taurasini", "Serra"]
    assert _patterns(out) == {"sottozona-prefix"}
    # Pattern A captures a commune body alongside the name.
    campi = next(r for r in out if r["name"] == "Campi Taurasini")
    assert campi["communes"]
    assert "Taurasi" in campi["communes"][0]


def test_sottozona_pattern_a_requires_line_start():
    # The mid-sentence form Irpinia actually uses ("...con l'indicazione
    # della sottozona Campi Taurasini:") is NOT a line-start header, so
    # Pattern A deliberately does not fire — a parser quirk worth pinning.
    text = (
        "«Irpinia» con l'indicazione della sottozona Campi Taurasini: "
        "l'intero territorio amministrativo dei comuni di Taurasi e Lapio."
    )
    out = extract_sottozone(text, "Irpinia")
    assert out == []


def test_sottozona_pattern_b_only_when_pattern_a_absent(fixture_text):
    # Pattern B is evaluated only when Pattern A yields nothing — the
    # Chianti fixture has no line-start "Sottozona" header, so Pattern B
    # runs; assert it does not accidentally also classify under Pattern A.
    text = fixture_text("it_sottozona_chianti_preamble_list.txt")
    out = extract_sottozone(text, "Chianti")
    assert "sottozona-prefix" not in _patterns(out)


# ==========================================================================
# menzione — numbered vs comma list shape (chosen by yield)
# ==========================================================================

def test_menzione_numbered_list_chianti_classico(fixture_text):
    text = fixture_text("it_menzioni_chianti_classico_numbered.txt")
    out = extract_menzioni(text, "Chianti Classico")

    # All 11 UGAs, including "San Donato in Poggio" whose lowercase Italian
    # connector ("... in ...") the widened _NAME_TOKEN_RE now keeps — see
    # test_menzione_numbered_list_keeps_name_with_lowercase_connector.
    names = _names(out)
    assert names == [
        "Castellina",
        "Castelnuovo Berardenga",
        "Gaiole",
        "Greve",
        "Lamole",
        "Montefioralle",
        "Panzano",
        "Radda",
        "San Casciano",
        "San Donato in Poggio",
        "Vagliagli",
    ]
    assert _patterns(out) == {"numbered-list"}


def test_menzione_numbered_list_keeps_name_with_lowercase_connector():
    # _NAME_TOKEN_RE in menzione.py allows a lowercase Italian connector
    # ("in", "di", "del", …) *inside* a name, glued to a following
    # capitalised word, so the next-line numbered parser keeps a UGA like
    # "San Donato in Poggio" intact. (Previously the regex matched only
    # "San Donato" != the full line and dropped it; the widened token
    # regex fixed that.)
    block = "9.\nSan Casciano\n10.\nSan Donato in Poggio\n11.\nVagliagli"
    text = "Unità Geografiche Aggiuntive:\n" + block + "\nLink al disciplinare"
    out = extract_menzioni(text, "Chianti Classico")
    names = _names(out)
    assert "San Casciano" in names
    assert "Vagliagli" in names
    assert "San Donato in Poggio" in names  # connector name kept intact


def test_menzione_numbered_list_stops_at_terminator(fixture_text):
    # The "Link al disciplinare del prodotto" line + the ELI/ISSN furniture
    # after the list must NOT be harvested as menzioni — _LIST_END_RE bounds
    # the block at that terminator.
    text = fixture_text("it_menzioni_chianti_classico_numbered.txt")
    out = extract_menzioni(text, "Chianti Classico")
    for name in _names(out):
        assert "Link" not in name and "ELI" not in name and "http" not in name


def test_menzione_comma_list_barolo_shape_chosen_by_yield(fixture_text):
    text = fixture_text("it_menzioni_barolo_comma.txt")
    out = extract_menzioni(text, "Barolo")

    # The block has "comma 4" / "successivo comma" style numerics that
    # could lure a marker-count heuristic into the numbered parser (which
    # yields ~0); the comma parser must win because it recovers far more
    # names.
    assert _patterns(out) == {"comma-list"}
    names = _names(out)
    assert len(names) > 50
    for famous in ("Cannubi", "Brunate", "Bussia", "Cerequio", "Sarmassa"):
        assert famous in names


def test_menzione_comma_list_drops_prose_commune_entries(fixture_text):
    text = fixture_text("it_menzioni_barolo_comma.txt")
    out = extract_menzioni(text, "Barolo")
    # "del comune di Barolo" et al. start lowercase ("del") -> dropped.
    for name in _names(out):
        assert not name.lower().startswith("del comune")
        assert "comune di" not in name.lower()


def test_menzione_short_comma_with_stray_art_n(fixture_text):
    # Synthetic isolation of the "shape chosen by yield" guard: a short
    # comma list carrying a stray "all'art. 5 comma 2" reference must not
    # be mis-routed to the numbered parser.
    text = fixture_text("it_menzioni_comma_with_stray_artn.txt")
    out = extract_menzioni(text, "Chianti")
    assert _patterns(out) == {"comma-list"}
    assert _names(out) == ["Pian d'Albola", "Vistarenni", "Monteluco"]


def test_menzione_no_trigger_returns_empty():
    # No "unità/menzioni geografiche aggiuntive" trigger -> nothing.
    out = extract_menzioni(
        "La zona di produzione comprende i comuni di Greve e Radda.", "Chianti"
    )
    assert out == []


def test_menzione_trigger_without_colon_skipped():
    # A narrative trigger with no following colon introduces no list.
    text = (
        "Le menzioni geografiche aggiuntive sono definite nell'allegato 3 "
        "del disciplinare e non sono qui elencate."
    )
    assert extract_menzioni(text, "Chianti") == []


# ==========================================================================
# masaf — article carving + Article-2 grape extraction
# ==========================================================================

def test_masaf_extract_articles_carves_bodies(fixture_text):
    text = fixture_text("it_masaf_articles_barolo.txt")
    bodies = extract_articles(text)

    assert set(bodies) == {1, 2, 3}
    # Article 1 keeps its own body, not Article 2's.
    assert "Denominazione e vini" in bodies[1]
    assert "Base ampelografica" not in bodies[1]
    # Article 2 carries the vitigno prose.
    assert "Nebbiolo" in bodies[2]
    # Article 3 carries the commune list, and Article 2's prose stopped
    # at the Article-3 header.
    assert "provincia di Cuneo" in bodies[3]
    assert "Nebbiolo" not in bodies[3]


def test_masaf_find_article_offsets_ordered(fixture_text):
    text = fixture_text("it_masaf_articles_barolo.txt")
    offsets = find_article_offsets(text)
    nums = [n for n, _s, _e in offsets]
    assert nums == [1, 2, 3]
    # Offsets are sorted by document position.
    starts = [s for _n, s, _e in offsets]
    assert starts == sorted(starts)


def test_masaf_extract_articles_last_occurrence_wins():
    # A TOC line + a real body line share article number 2; the body
    # (later occurrence) must win, not the empty TOC entry.
    text = (
        "Articolo 2\n"
        "Base ampelografica\n"
        "\n"
        "Articolo 2\n"
        "Base ampelografica\n"
        "ottenuti dal vitigno Sangiovese.\n"
    )
    bodies = extract_articles(text)
    assert 2 in bodies
    assert "Sangiovese" in bodies[2]


def test_masaf_article2_vitigno_prose_yields_grape(fixture_text):
    text = fixture_text("it_masaf_articles_barolo.txt")
    bodies = extract_articles(text)
    phrases = article2_candidate_phrases(bodies[2])
    # The "vitigno Nebbiolo" prose scan surfaces the bare variety name.
    assert any(p == "Nebbiolo" for p in phrases)


def test_masaf_parse_grapes_barolo_nebbiolo(fixture_text):
    text = fixture_text("it_masaf_articles_barolo.txt")
    bodies = extract_articles(text)
    grapes = parse_grapes_with(match_variety, bodies[2], wine_name="Barolo")
    assert "nebbiolo" in grapes["principal"]
    # MASAF has no principal/accessory split — everything is principal.
    assert grapes["accessory"] == []
    detail = next(d for d in grapes["details"] if d["slug"] == "nebbiolo")
    assert detail["role"] == "principal"
    assert detail["source"] == "masaf-disciplinare"


def test_masaf_article2_candidate_strips_percent_and_index():
    # Numbered, percentage-bearing variety lines: the leading index and
    # the trailing share-range must both be stripped so the bare name
    # reaches the matcher.
    body = (
        "Base ampelografica\n"
        "1. Sangiovese: dal 70% al 100%;\n"
        "2. Canaiolo nero: da 0 a 30%;\n"
    )
    phrases = article2_candidate_phrases(body)
    assert "Sangiovese" in phrases
    assert "Canaiolo nero" in phrases
    # No phrase still carries a percent figure or a leading enumeration.
    for p in phrases:
        assert "%" not in p
        assert not p[:2].strip().rstrip(".").isdigit()
