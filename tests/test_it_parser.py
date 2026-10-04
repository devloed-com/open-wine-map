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

  - scripts/_lib/it/comune.py — geo-area comune-list parsing against the
      ISTAT registry (ITCommuneIndex). Fixture-free: a tiny ISTAT CSV is
      written per test and unit squares stand in for the GISCO polygons.

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
from _lib.it.comune import ITCommuneIndex  # noqa: E402
from _lib.it.masaf import (  # noqa: E402
    article2_candidate_phrases,
    cap_at_sentence,
    extract_articles,
    find_article_offsets,
    parse_grapes_with,
    pick_terroir_article,
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


def test_masaf_extract_article_runs_keeps_the_parent_and_lists_annexes():
    # A consolidated disciplinare: TOC, the parent's own articles, then one
    # sub-disciplinare per sottozona restarting at Art. 1. The parent's
    # Art. 1 / 3 / 9 must come from ITS run, never from the last annex
    # (review 2026-09-12: Montepulciano d'Abruzzo took San Martino's).
    from _lib.it.masaf import extract_article_runs
    body = "x" * 300
    text = (
        "Articolo 1 Denominazione\nArticolo 2 Base\nArticolo 3 Zona\nArticolo 9 Legame\n\n"
        f"Articolo 1\nDenominazione e vini\nLa DOC «Parent» {body}\n"
        f"Articolo 2\nBase ampelografica\nMontepulciano {body}\n"
        f"Articolo 3\nZona di produzione\nParent communes {body}\n"
        f"Articolo 9\nLegame con l'ambiente\nParent terroir {body}\n"
        "17\nALLEGATO 1\n“PARENT” SOTTOZONA “ALTO TIRINO”\n"
        f"Articolo 1\nDenominazione e vini\nLa sottozona Alto Tirino {body}\n"
        f"Articolo 3\nZona di produzione\nAlto Tirino communes {body}\n"
        f"Articolo 9\nLegame con l'ambiente\nAlto Tirino terroir {body}\n"
        "ALLEGATO 2\n“PARENT” SOTTOZONA “TEATE”\n"
        f"Articolo 1\nDenominazione e vini\nLa sottozona Teate {body}\n"
        f"Articolo 9\nLegame con l'ambiente\nTeate terroir {body}\n"
    )
    main, annexes = extract_article_runs(text)
    assert sorted(main) == [1, 2, 3, 9]
    assert "La DOC «Parent»" in main[1] and "Parent terroir" in main[9]
    assert "Alto Tirino" not in main[9] and "Teate" not in main[1]
    assert [a["title"] for a in annexes] == [
        "ALLEGATO 1 “PARENT” SOTTOZONA “ALTO TIRINO”", "ALLEGATO 2 “PARENT” SOTTOZONA “TEATE”",
    ]
    assert "Alto Tirino terroir" in annexes[0]["articles"][9]
    assert sorted(annexes[1]["articles"]) == [1, 9]
    assert extract_articles(text) == main


def test_masaf_terroir_uncapped_for_the_extractor_capped_for_the_panel():
    sentences = ["Il legame con l'ambiente geografico è antico e documentato."]
    sentences += [f"La frase numero {i} descrive i suoli e il clima della zona." for i in range(200)]
    body = "Legame con l'ambiente geografico\n" + " ".join(sentences)
    articles = {1: "Denominazione\nLa denominazione…", 9: body}

    n, full = pick_terroir_article(articles, max_chars=None)
    assert n == 9
    assert len(full) > 4000
    assert full.endswith("della zona.")

    n, brief = pick_terroir_article(articles)
    assert n == 9
    assert brief == cap_at_sentence(full, 4000)
    assert len(brief) <= 4000 and brief.endswith(".")
    assert full.startswith(brief[:-1])
    assert cap_at_sentence(full, None) == full


# ==========================================================================
# comune — ITCommuneIndex (geo-area comune list → ISTAT codes)
# ==========================================================================

# (code, name, regione, provincia) — the ISTAT rows the tests need. Codes
# and names are the registry's; the two Sant'Arcangelo are the national
# homonym pair that triage found on Bianco del Sillaro (2026-09-24).
_ISTAT_ROWS = [
    ("076080", "Sant'Arcangelo", "Basilicata", "Potenza"),
    ("099018", "Santarcangelo di Romagna", "Emilia-Romagna", "Rimini"),
    ("099003", "Coriano", "Emilia-Romagna", "Rimini"),
    ("099014", "Rimini", "Emilia-Romagna", "Rimini"),
    ("099020", "Verucchio", "Emilia-Romagna", "Rimini"),
    ("037016", "Castel Guelfo di Bologna", "Emilia-Romagna", "Bologna"),
    ("037046", "Ozzano dell'Emilia", "Emilia-Romagna", "Bologna"),
    ("040005", "Castrocaro Terme e Terra del Sole", "Emilia-Romagna", "Forlì-Cesena"),
    ("040007", "Cesena", "Emilia-Romagna", "Forlì-Cesena"),
    ("018087", "Marzano", "Lombardia", "Pavia"),
    ("064047", "Marzano di Nola", "Campania", "Avellino"),
    ("073025", "San Marzano di San Giuseppe", "Puglia", "Taranto"),
    ("073026", "Sava", "Puglia", "Taranto"),
    ("016065", "Castro", "Lombardia", "Bergamo"),
    ("075096", "Castro", "Puglia", "Lecce"),
    # Comuni whose name, plus a connector, starts a longer name elsewhere
    # (Lizzano + "in" → Lizzano in Belvedere, BO; Ponte + "in" → Ponte in
    # Valtellina; Lugo + "di" → Lugo di Vicenza).
    ("073005", "Faggiano", "Puglia", "Taranto"),
    ("073023", "Roccaforzata", "Puglia", "Taranto"),
    ("073011", "Lizzano", "Puglia", "Taranto"),
    ("037033", "Lizzano in Belvedere", "Emilia-Romagna", "Bologna"),
    ("073027", "Taranto", "Puglia", "Taranto"),
    ("062049", "Paupisi", "Campania", "Benevento"),
    ("062053", "Ponte", "Campania", "Benevento"),
    ("014052", "Ponte in Valtellina", "Lombardia", "Sondrio"),
    ("062008", "Benevento", "Campania", "Benevento"),
    ("039002", "Bagnacavallo", "Emilia-Romagna", "Ravenna"),
    ("039012", "Lugo", "Emilia-Romagna", "Ravenna"),
    ("039009", "Cotignola", "Emilia-Romagna", "Ravenna"),
    ("024053", "Lugo di Vicenza", "Veneto", "Vicenza"),
    # Alto Livenza (Veneto) crosses into Friuli-Venezia Giulia.
    ("026049", "Motta di Livenza", "Veneto", "Treviso"),
    ("093007", "Brugnera", "Friuli-Venezia Giulia", "Pordenone"),
    ("093037", "Sacile", "Friuli-Venezia Giulia", "Pordenone"),
    ("001219", "Rivoli", "Piemonte", "Torino"),
    # Rubicone IGT (it-A, 2026-09-24): three whole provinces + ten Bologna
    # comuni. Province seats and the comuni the record names, per ISTAT.
    ("040012", "Forlì", "Emilia-Romagna", "Forlì-Cesena"),
    ("039010", "Faenza", "Emilia-Romagna", "Ravenna"),
    ("039014", "Ravenna", "Emilia-Romagna", "Ravenna"),
    ("037007", "Borgo Tossignano", "Emilia-Romagna", "Bologna"),
    ("037012", "Casalfiumanese", "Emilia-Romagna", "Bologna"),
    ("037020", "Castel San Pietro Terme", "Emilia-Romagna", "Bologna"),
    ("037025", "Dozza", "Emilia-Romagna", "Bologna"),
    ("037026", "Fontanelice", "Emilia-Romagna", "Bologna"),
    ("037032", "Imola", "Emilia-Romagna", "Bologna"),
    ("037037", "Medicina", "Emilia-Romagna", "Bologna"),
    ("037045", "Mordano", "Emilia-Romagna", "Bologna"),
]


def _comune_index(tmp_path):
    from shapely.geometry import box

    header = ";".join(f"c{i}" for i in range(12))
    lines = [header]
    for code, name, regione, prov in _ISTAT_ROWS:
        row = [""] * 12
        row[4], row[6], row[10], row[11] = code, name, regione, prov
        lines.append(";".join(row))
    csv_path = tmp_path / "istat.csv"
    csv_path.write_text("\n".join(lines) + "\n", encoding="cp1252")
    idx = ITCommuneIndex(istat_csv=csv_path, gisco_lau_zip=tmp_path / "missing.zip")
    # One unit square per comune, at x = its code (so a union's bounds
    # tell which codes went in).
    for code, *_ in _ISTAT_ROWS:
        idx._geom_by_code[code] = box(int(code), 0, int(code) + 1, 1)
    return idx


def test_comune_fused_hagionym_matches_the_split_spelling(tmp_path):
    # ISTAT fuses "Santarcangelo"; the disciplinare writes "S. Arcangelo di
    # Romagna". The 4-word name must win over the 2-word prefix that is
    # Sant'Arcangelo (PZ) — a different comune 400 km away.
    idx = _comune_index(tmp_path)
    parsed = idx.parse_geo_area(
        "dei comuni di: Coriano, Rimini, S. Arcangelo di Romagna e Verucchio, "
        "in provincia di Rimini."
    )
    assert parsed["comuni"] == ["coriano", "rimini", "sanarcangelodiromagna", "verucchio"]


def test_comune_regione_filter_drops_the_homonym(tmp_path):
    idx = _comune_index(tmp_path)
    text = "comuni di Castro e Sava"
    # Without a regione the homonym is ambiguous and both Castro go in.
    geom, source, stats = idx.resolve(text)
    assert source == "gisco-comune-union" and stats["matched"] == 3
    assert geom.bounds[0] == 16065
    geom, source, stats = idx.resolve(text, regione="Puglia")
    assert stats["matched"] == 2
    assert geom.bounds[0] == 73026 and geom.bounds[2] == 75097  # Sava + Castro (LE)
    # An unknown regione (a record with none derived) filters nothing.
    assert idx.resolve(text, regione="Italia")[2]["matched"] == 3


def test_comune_connector_guard_rejects_a_truncated_name(tmp_path):
    # "S. Arcangelo di Romagn…" (typo) fails the full name; the 2-word
    # prefix is another comune. The text runs on through "di" into a name
    # the index knows, so the prefix is a miss — never Sant'Arcangelo (PZ).
    idx = _comune_index(tmp_path)
    parsed = idx.parse_geo_area("comuni di: Rimini, S. Arcangelo di Romagn e Verucchio")
    assert parsed["comuni"] == ["rimini", "verucchio"]
    # A connector that no indexed name continues through is plain prose.
    parsed = idx.parse_geo_area("comuni di: Rimini, Verucchio di cui la frazione")
    assert parsed["comuni"] == ["rimini", "verucchio"]


def test_comune_disciplinare_spellings_and_glued_commas(tmp_path):
    idx = _comune_index(tmp_path)
    # Bianco del Sillaro Art. 3: a dropped disambiguator, a dropped article,
    # a source typo — the Castrocaro miss used to exhaust the miss budget
    # and silently drop the rest of the Forlì-Cesena list.
    parsed = idx.parse_geo_area(
        "comuni di: Castelguelfo, Ozzano Emilia, in provincia di Bologna; "
        "dei comuni di: Castrocaro Terme e Terre del Sole, Cesena, in provincia di Forlì-Cesena"
    )
    assert parsed["comuni"] == [
        "castelguelfo", "ozzanoemilia", "castrocarotermeeterredelsole", "cesena",
    ]
    # Primitivo di Manduria: pdftotext glued "Jonico,San" — the comma still
    # separates two names, so "San Marzano di San Giuseppe" matches whole
    # instead of a bare "Marzano" (PV) and the list survives.
    parsed = idx.parse_geo_area(
        "comuni di Sava, San Giorgio Jonico,San Marzano di San Giuseppe, in provincia di Taranto"
    )
    assert parsed["comuni"] == ["sava", "sanmarzanodisangiuseppe"]


def test_comune_connector_guard_keeps_a_whole_name_before_list_prose(tmp_path):
    # "Lizzano in …" starts Lizzano in Belvedere (BO), but here "in" opens
    # the list's province trailer: Lizzano (TA) stays, and the "provincia"
    # keyword is not swallowed — so Taranto is the province, not a comune.
    idx = _comune_index(tmp_path)
    text = "comprende i comuni di Faggiano, Roccaforzata e Lizzano in provincia di Taranto"
    assert idx.parse_geo_area(text)["comuni"] == ["faggiano", "roccaforzata", "lizzano"]
    geom, source, stats = idx.resolve(text, regione="Puglia")
    assert source == "gisco-comune-union" and stats["matched"] == 3
    assert geom.bounds[2] == 73024  # Faggiano + Lizzano + Roccaforzata; Taranto (73027) out
    # A comma closes the name whatever follows it.
    parsed = idx.parse_geo_area("comuni di Faggiano, Lizzano, in provincia di Taranto")
    assert parsed["comuni"] == ["faggiano", "lizzano"]
    parsed = idx.parse_geo_area("comuni di Paupisi e Ponte in provincia di Benevento")
    assert parsed["comuni"] == ["paupisi", "ponte"]
    # "Lugo di Romagna" is Lugo (RA) with its regional qualifier: the list
    # around it is in Ravenna, so it is not a Lugo di Vicenza misspelt.
    parsed = idx.parse_geo_area("comuni di Bagnacavallo, Lugo di Romagna, Cotignola")
    assert parsed["comuni"] == ["bagnacavallo", "lugo", "cotignola"]


def test_comune_regione_keeps_a_second_regione_list(tmp_path):
    # Alto Livenza (regione Veneto) names Treviso comuni and a group in the
    # province of Pordenone (FVG): the second regione's comuni stay.
    idx = _comune_index(tmp_path)
    text = (
        "l'intero territorio amministrativo dei comuni di: Motta di Livenza in provincia di "
        "Treviso e dei comuni di: Brugnera e Sacile, in provincia di Pordenone."
    )
    geom, source, stats = idx.resolve(text, regione="Veneto")
    assert stats["matched"] == 3
    assert geom.bounds[0] == 26049 and geom.bounds[2] == 93038
    # A lone name outside the regione is a homonym (Garda writes "Rivoli"
    # for Rivoli Veronese; ISTAT's only Rivoli is in Torino).
    geom, source, stats = idx.resolve("comuni di Motta di Livenza, Rivoli", regione="Veneto")
    assert stats["matched"] == 1 and geom.bounds[0] == 26049


# The area text of raw/it/disciplinari-extracted/rubicone.json (EU-OJ
# documento unico, section 6), verbatim: the register's spellings
# "Castelguelfo" / "Ozzano Emilia" and the pdftotext-split "Casal Fiumanese".
_RUBICONE_AREA = (
    "La zona di produzione delle uve per l’ottenimento dei vini e dei mosti di uve "
    "parzialmente fermentati designati con la Indicazione Geografica Protetta« “Rubicone” "
    "»comprende l’intero territorio amministrativo delle province di Forlì-Cesena, Ravenna e "
    "Rimini e dei comuni di Borgo Tossignano, Casal Fiumanese, Castelguelfo, Castel San Pietro "
    "Terme, Dozza, Fontanelice, Imola, Medicina, Mordano e Ozzano Emilia della provincia di "
    "Bologna."
)


def test_comune_whole_territory_province_is_a_member_beside_comuni(tmp_path):
    # it-A: "l'intero territorio amministrativo delle province di …" names
    # the provinces as members of the area, not as the location of the
    # comune list that follows — Rubicone used to be drawn from its ten
    # Bologna comuni alone, the three whole provinces dropped.
    from shapely.geometry import Point

    idx = _comune_index(tmp_path)
    parsed = idx.parse_geo_area(_RUBICONE_AREA)
    assert parsed["province"] == ["forlicesena", "ravenna", "rimini"]
    assert len(parsed["comuni"]) == 10
    assert "casalfiumanese" in parsed["comuni"] and "ozzanoemilia" in parsed["comuni"]

    geom, source, stats = idx.resolve(_RUBICONE_AREA, regione="Emilia-Romagna")
    assert source == "gisco-comune-provincia-union"
    # 3 FC + 5 RA + 4 RN fixture comuni through the provinces, 10 named BO comuni.
    assert stats["matched"] == 22 and stats["n_units"] == 13
    assert geom.area == 22
    assert geom.bounds[0] == 37007 and geom.bounds[2] == 99021
    # Bologna itself is only a qualifier ("della provincia di Bologna"):
    # its unlisted comune Lizzano in Belvedere stays out.
    assert not geom.contains(Point(37033.5, 0.5))


def test_comune_qualifier_province_still_dropped_beside_comuni(tmp_path):
    # The rule that dropped Rubicone's provinces is kept for locational
    # qualifiers: no quantifier, or the quantifier belongs to the comuni.
    idx = _comune_index(tmp_path)
    # Rimini DOC: "il territorio della provincia" + an exclusion list — the
    # province (a qualifier, no quantifier) is the area and the excluded
    # comuni leave it; before 2026-09-25 the excluded comuni WERE the area.
    text = ("prodotte nell’ambito del territorio amministrativo della provincia di Rimini "
            "ad esclusione dei comuni di Coriano e Verucchio")
    parsed = idx.parse_geo_area(text)
    assert parsed["comuni"] == [] and parsed["province"] == ["rimini"]
    assert parsed["excluded_comuni"] == ["coriano", "verucchio"]
    geom, source, stats = idx.resolve(text)
    assert source == "gisco-provincia-union" and stats["excluded"] == 2
    # Rimini (099014) + Santarcangelo (099018) stay; Coriano (099003) and
    # Verucchio (099020) leave the union.
    assert stats["matched"] == 2 and geom.bounds[0] == 99014 and geom.bounds[2] == 99019
    for text in (
        # A "provincia di X:" header over a comune list.
        "comprende i territori della provincia di Bologna: i comuni di Imola e Dozza",
        # The quantifier is the comuni's ("l'intero territorio dei comuni … in provincia di").
        "comprende l’intero territorio amministrativo dei comuni di Coriano e Verucchio in "
        "provincia di Rimini",
        "comprende i comuni di Faggiano, Roccaforzata e Lizzano in provincia di Taranto",
    ):
        parsed = idx.parse_geo_area(text)
        assert parsed["comuni"] and parsed["province"] == [], text
        assert idx.resolve(text)[1] == "gisco-comune-union", text
    # Without comuni every province is used, as before.
    parsed = idx.parse_geo_area("comprende l’intero territorio della provincia di Rimini.")
    assert parsed["province"] == ["rimini"]
    assert idx.resolve("comprende il territorio della provincia di Rimini.")[1] \
        == "gisco-provincia-union"


def test_comune_whole_territory_quantifier_variants(tmp_path):
    idx = _comune_index(tmp_path)
    # "tutto il territorio della provincia" (Venezia IGT's wording).
    parsed = idx.parse_geo_area(
        "comprende tutto il territorio amministrativo della provincia di Rimini e il comune "
        "di Imola."
    )
    assert parsed["province"] == ["rimini"] and parsed["comuni"] == ["imola"]
    # Costa Toscana: the quantifier follows the name — "Provincia di X:
    # comuni costituenti l'intero territorio provinciale" — and marks that
    # province only; the next header is a qualifier again.
    parsed = idx.parse_geo_area(
        "Provincia di Rimini: comuni costituenti l’intero territorio provinciale; "
        "provincia di Bologna: i comuni di Imola e Dozza."
    )
    assert parsed["province"] == ["rimini"] and parsed["comuni"] == ["imola", "dozza"]
    # "strada provinciale" / "confine provinciale" never promote anything.
    parsed = idx.parse_geo_area(
        "dei comuni di Imola e Dozza, in provincia di Bologna, lungo la strada provinciale "
        "fino al confine provinciale"
    )
    assert parsed["province"] == []
    # Grignolino del Monferrato Casalese: the whole province is where the
    # wine may be MADE, in the sentence after the grape area — not a member.
    parsed = idx.parse_geo_area(
        "ricade nei territori comunali della provincia di Bologna: Imola, Dozza. Inoltre, le "
        "operazioni di vinificazione, elaborazione ed imbottigliamento devono essere effettuate "
        "nell’intero territorio della provincia di Rimini e nei comuni di Faenza."
    )
    assert parsed["province"] == [] and "faenza" in parsed["comuni"]


# --------------------------------------------------------------------------
# 2026-09-25 — exclusion clauses, bare province headers, unresolved names
# --------------------------------------------------------------------------


def test_comune_esclusivamente_is_not_an_exclusion(tmp_path):
    # Torgiano: "devono essere prodotte esclusivamente nel territorio … del
    # Comune di Torgiano" — the adverb includes, it does not exclude.
    idx = _comune_index(tmp_path)
    parsed = idx.parse_geo_area(
        "devono essere prodotte esclusivamente nel territorio amministrativo del Comune di "
        "Imola in provincia di Bologna."
    )
    assert parsed["comuni"] == ["imola"] and parsed["excluded_comuni"] == []


def test_comune_partial_exclusion_keeps_the_comune(tmp_path):
    idx = _comune_index(tmp_path)
    # Aglianico del Vulture: three administrative islands of Atella, not Atella.
    parsed = idx.parse_geo_area(
        "comprende i comuni di Imola, Dozza, Faenza e Lugo, escluse le tre isole amministrative "
        "di Sant'Ilario e Macchia del comune di Lugo."
    )
    assert parsed["comuni"] == ["imola", "dozza", "faenza", "lugo"]
    assert parsed["excluded_comuni"] == []
    # Grignolino del Monferrato Casalese: a bracketed part, the list goes on.
    parsed = idx.parse_geo_area(
        "i comuni di Imola (esclusa la parte sulla riva sinistra del Po), Dozza, Faenza e Lugo."
    )
    assert parsed["comuni"] == ["imola", "dozza", "faenza", "lugo"]
    # Rimini: a partial exclusion, then "dell'intero comune di" reopens a whole one.
    parsed = idx.parse_geo_area(
        "comprende il territorio della provincia di Rimini ad esclusione dei territori posti a "
        "valle della strada statale, e dell'intero comune di Coriano."
    )
    assert parsed["province"] == ["rimini"] and parsed["excluded_comuni"] == ["coriano"]


def test_comune_whole_exclusion_leaves_the_union(tmp_path):
    idx = _comune_index(tmp_path)
    # Marsala's shape: a list, then "esclusi i comuni di …".
    text = "comprende i comuni di Imola, Dozza, Faenza e Lugo, esclusi i comuni di Faenza e Lugo."
    parsed = idx.parse_geo_area(text)
    assert parsed["excluded_comuni"] == ["faenza", "lugo"]
    assert idx.resolve(text)[2]["matched"] == 2  # the parse lists all four, the union drops two
    # Freisa d'Asti's shape: a province, then "con l'esclusione dei territori comunali di …".
    text = ("all'interno del territorio collinare della provincia di Rimini con l'esclusione dei "
            "territori comunali di Coriano e di Verucchio.")
    parsed = idx.parse_geo_area(text)
    assert parsed["province"] == ["rimini"] and parsed["excluded_comuni"] == ["coriano", "verucchio"]
    geom, source, stats = idx.resolve(text)
    assert source == "gisco-provincia-union" and stats["matched"] == 2 and stats["excluded"] == 2
    # A whole province excluded from a whole-province area.
    parsed = idx.parse_geo_area(
        "comprende l'intero territorio della provincia di Bologna, ad eccezione dell'intero "
        "territorio della provincia di Ravenna."
    )
    assert parsed["province"] == ["bologna"] and parsed["excluded_province"] == ["ravenna"]


def test_comune_bare_province_header_opens_the_list(tmp_path):
    # Costa Toscana / Carso / Asolo: "Provincia di X: A, B, C" without "comuni".
    idx = _comune_index(tmp_path)
    parsed = idx.parse_geo_area(
        "Provincia di Bologna: Imola, Dozza; provincia di Ravenna: Faenza e Lugo."
    )
    assert parsed["comuni"] == ["imola", "dozza", "faenza", "lugo"] and parsed["province"] == []
    assert idx.resolve(parsed and "Provincia di Bologna: Imola, Dozza; provincia di Ravenna: "
                       "Faenza e Lugo.")[1] == "gisco-comune-union"


def test_comune_unresolved_name_is_one_miss_and_a_list_resumes_after_a_province(tmp_path):
    # Valle Belice: "Santa Margherita Belice" (ISTAT: "… di Belice") burnt four
    # misses and closed the bucket, so four comuni became two whole provinces;
    # and the list resumes after "in provincia di Agrigento e".
    idx = _comune_index(tmp_path)
    text = ("comprende l'intero territorio amministrativo dei comuni di Santa Margherita Belice, "
            "Montevago, Imola, in provincia di Bologna e Dozza in provincia di Ravenna.")
    parsed = idx.parse_geo_area(text)
    assert parsed["comuni"] == ["imola", "dozza"] and parsed["province"] == []
    assert idx.resolve(text)[1] == "gisco-comune-union"


def test_comune_connector_less_spelling_matches(tmp_path):
    # "Santa Margherita Belice" for ISTAT "Santa Margherita di Belice".
    idx = _comune_index(tmp_path)
    assert idx.parse_geo_area("i comuni di Santarcangelo Romagna e Imola")["comuni"] == [
        "santarcangeloromagna", "imola",  # the bare alias key; it resolves to 099018
    ]
    assert idx.resolve("i comuni di Santarcangelo Romagna e Imola")[2]["matched"] == 2
    # "Jonica" / ISTAT "Ionica", and an elided d' — both folded.
    assert idx.parse_geo_area("i comuni di Lugo di Vicenza e Motta Livenza")["comuni"] == [
        "lugodivicenza", "mottalivenza",
    ]


def test_comune_abbreviation_does_not_end_the_winemaking_lookback(tmp_path):
    idx = _comune_index(tmp_path)
    for text in (
        "ricade nei comuni di Imola, Dozza. Le operazioni di vinificazione di cui all'art. 5 "
        "devono essere effettuate nell'intero territorio della provincia di Rimini.",
        # the "territorio provinciale" form, also inside a winemaking clause
        "ricade nei comuni di Imola, Dozza. Le operazioni di vinificazione di cui all'art. 5 "
        "possono essere effettuate nella provincia di Rimini, comuni costituenti l'intero "
        "territorio provinciale.",
    ):
        parsed = idx.parse_geo_area(text)
        assert parsed["comuni"] == ["imola", "dozza"] and parsed["province"] == [], text


# ---------------------------------------------------------------------------
# masaf — the in-PDF variety annex ("Allegato 1 – Elenco vitigni …")
# ---------------------------------------------------------------------------

def test_masaf_annex_complement_merges_as_accessory(fixture_text):
    # Bolgheri Sassicaia: article 2 names Cabernet Sauvignon (>= 80 %) and
    # hands the complement to "allegato 1" — a numbered list at the end of
    # the PDF. Visitor flag 2026-10-03: the card showed no Cabernet Franc.
    from _lib.it.masaf import grapes_with_annex
    text = fixture_text("it_masaf_allegato_sassicaia.txt")
    bodies = extract_articles(text)
    grapes = grapes_with_annex(match_variety, bodies[2], text, "Bolgheri Sassicaia")
    assert grapes["principal"] == ["cabernet-sauvignon"]
    assert "cabernet-franc" in grapes["accessory"]
    assert "merlot" in grapes["accessory"]
    # The name as written resolves before the wine-type stripper takes
    # its "rosso" away.
    assert "refosco-dal-peduncolo-rosso" in grapes["accessory"]
    assert "cabernet-sauvignon" not in grapes["accessory"]
    franc = next(d for d in grapes["details"] if d["slug"] == "cabernet-franc")
    assert franc["role"] == "accessory"
    assert franc["source"] == "masaf-disciplinare-allegato"


def test_masaf_annex_register_table_cells_bounded_at_next_allegato(fixture_text):
    # A register-table annex: code column, two variety columns, a synonym
    # cell, a bracketed colour, header rows and a page number. The list
    # ends at "ALLEGATO 2", whose own numbered items are not varieties.
    from _lib.it.masaf import grapes_with_annex, parse_annex_grapes_with
    text = fixture_text("it_masaf_allegato_register_table.txt")
    bodies = extract_articles(text)
    grapes = grapes_with_annex(match_variety, bodies[2], text, "Esempio")
    assert grapes["principal"] == ["arneis"]
    for slug in ("uva-rara", "aleatico", "vespolina", "ancellotta", "cabernet-franc"):
        assert slug in grapes["accessory"], slug
    # Article 2's own variety is never repeated as accessory.
    assert "arneis" not in grapes["accessory"]
    # Past the next "ALLEGATO" heading nothing is read.
    assert "merlot" not in grapes["accessory"]
    # With no article-2 variety the same annex is the whole roster.
    roster = parse_annex_grapes_with(match_variety, text)
    assert "uva-rara" in roster["principal"]
    assert roster["accessory"] == []
    assert "merlot" not in roster["principal"]


def test_masaf_annex_ignored_when_article2_does_not_refer_to_it(fixture_text):
    # Article 2 names its varieties and never says "allegato": an annex
    # elsewhere in the PDF (a region-wide register) is not the complement.
    from _lib.it.masaf import grapes_with_annex
    text = fixture_text("it_masaf_allegato_register_table.txt")
    art2 = "2.1 «Esempio» è riservata al vino ottenuto dal vitigno Nebbiolo al 100%."
    grapes = grapes_with_annex(match_variety, art2, text, "Esempio")
    assert grapes["principal"] == ["nebbiolo"]
    assert grapes["accessory"] == []


def test_masaf_annex_is_the_roster_for_a_one_or_more_varieties_igt(fixture_text):
    # A regional IGT: "da uno o più vitigni idonei … riportati nell'allegato
    # 1". The annex is the roster, so it merges as principal beside the
    # names article 2 singles out for labelling, never as a complement.
    from _lib.it.masaf import grapes_with_annex
    text = fixture_text("it_masaf_allegato_register_table.txt")
    art2 = (
        "1. I vini a indicazione geografica tipica «Esempio» devono essere ottenuti da "
        "uve provenienti da vigneti composti da uno o più vitigni idonei alla "
        "coltivazione nella Regione, riportati nell’allegato 1 del presente "
        "disciplinare. 2. La specificazione di uno dei vitigni, ad esclusione del "
        "vitigno Nebbiolo, è riservata ai vini ottenuti per almeno l'85%."
    )
    grapes = grapes_with_annex(match_variety, art2, text, "Esempio")
    assert "nebbiolo" in grapes["principal"]
    assert "uva-rara" in grapes["principal"]
    assert grapes["accessory"] == []
