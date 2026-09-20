"""Tests for the ES national traditional-term roster
(`scripts/_lib/es/national_term.py`).

The fixture is a redacted `pdftotext -layout` excerpt of MAPA's listado —
header lines, region banners, "Total DOPs/IGPs" subtotals, a page-footer
line and the footnote block are all present so the row regex is proven to
skip everything that is not a GI row.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.es import national_term as nt  # noqa: E402

PLIEGOS_DIR = nt.ROOT / "raw" / "es" / "pliegos-extracted"


@pytest.fixture
def listado_rows(fixture_text):
    return nt.parse_listado_text(fixture_text("es_mapa_listado_excerpt.txt"))


@pytest.fixture
def roster(monkeypatch, listado_rows):
    display = {fn: nt.TERM_DISPLAY[t] for fn, t in listado_rows.items()}
    monkeypatch.setattr(nt, "_TERMS_CACHE", display)
    return display


def test_parse_rows_only(listado_rows):
    assert listado_rows == {
        "PDO-ES-A0735": "DO",
        "PDO-ES-A0117": "DOCa",
        "PGI-ES-A0083": "VT",
        "PDO-ES-A1522": "VP",
        "PDO-ES-02585": "DO",
        "PGI-ES-A1362": "VT",
        "PDO-ES-A1478": "VC",
        "PDO-ES-A1483": "DO",
        "PDO-ES-A1560": "DOCa",
        "PDO-ES-02481": "VP",
        "PDO-ES-N1634": "VP",
        "PDO-ES-02086": "VP",
        "PGI-ES-A1173": "VT",
    }


def test_multi_alias_name_does_not_shift_columns(listado_rows):
    assert listado_rows["PDO-ES-A1483"] == "DO"


def test_conflicting_term_for_one_file_number_raises():
    text = (
        "   DOP Foo            DO      PDO-ES-A9999\n"
        "   DOP Foo            VP      PDO-ES-A9999\n"
    )
    with pytest.raises(ValueError):
        nt.parse_listado_text(text)


def test_term_display_is_bottle_wording():
    assert nt.TERM_DISPLAY["VP"] == "Vino de Pago"
    assert nt.TERM_DISPLAY["VT"] == "Vino de la Tierra"
    assert nt.TERM_DISPLAY["DOCa"] == "DOCa"


def test_exact_file_number(roster):
    assert nt.es_term_for({"slug": "rioja", "file_number": "PDO-ES-A0117"}, "DOP") == "DOCa"
    assert (
        nt.es_term_for({"slug": "ribera-del-queiles", "file_number": "PGI-ES-A0083"}, "IGP")
        == "Vino de la Tierra"
    )


def test_numeric_tail_bridge(roster):
    assert nt.es_term_for({"slug": "x", "file_number": "PDO-ES-1522"}, "DOP") == "Vino de Pago"
    assert nt.es_term_for({"slug": "x", "file_number": "PGI-ES-1522"}, "IGP") == ""


def test_unknown_file_number_is_empty_not_kind_default(roster):
    assert nt.es_term_for({"slug": "x", "file_number": "PDO-ES-A0000"}, "DOP") == ""
    assert nt.es_term_for({"slug": "x", "file_number": "PGI-ES-A0000"}, "IGP") == ""
    assert nt.es_term_for({"slug": "x"}, "IGP") == ""


def test_pgi_never_gets_pdo_term(roster):
    with pytest.raises(AssertionError):
        nt.es_term_for({"slug": "x", "file_number": "PDO-ES-A0117"}, "IGP")
    with pytest.raises(AssertionError):
        nt.es_term_for({"slug": "x", "file_number": "PGI-ES-A0083"}, "DOP")


def test_overrides_are_cited_and_win(roster):
    overrides = nt.load_es_term_overrides()
    for slug, entry in overrides.items():
        assert entry["sources"], slug
        assert all(s["url"].startswith("https://") for s in entry["sources"]), slug
    assert nt.es_term_for({"slug": "priorat", "file_number": "PDO-ES-A1560"}, "DOP") == "DOQ"
    assert overrides["priorat"]["castilian_form"] == "DOCa"
    assert (
        nt.es_term_for({"slug": "tharsys", "file_number": "PDO-ES-02980"}, "DOP")
        == "Vino de Pago"
    )
    assert (
        nt.es_term_for({"slug": "urbezo", "file_number": "PDO-ES-02585"}, "DOP")
        == "Vino de Pago"
    )


def test_missing_pdf_warns_and_returns_empty(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(nt, "_TERMS_CACHE", None)
    monkeypatch.setattr(nt, "LISTADO_DIR", tmp_path)
    assert nt.load_es_terms() == {}
    assert "missing" in capsys.readouterr().err


def test_sub_denominations_follow_parent(roster):
    records = [
        {"slug": "rioja", "file_number": "PDO-ES-A0117", "kind": "DOP"},
        {"slug": "rioja-rioja-alta", "file_number": "PDO-ES-A0117", "kind": "DOP",
         "is_sub_denomination": True, "parent_slug": "rioja"},
    ]
    assert nt.check_sub_denomination_terms(records) == []
    records[1]["file_number"] = "PDO-ES-A0735"
    assert nt.check_sub_denomination_terms(records) == [
        "rioja-rioja-alta: 'DO' != parent rioja 'DOCa'"
    ]


@pytest.mark.skipif(
    not (PLIEGOS_DIR.exists() and (nt.LISTADO_DIR / nt.LISTADO_FILE).exists()),
    reason="raw/ corpus + MAPA listado not present",
)
def test_live_corpus_joins_and_subzonas_agree(monkeypatch):
    monkeypatch.setattr(nt, "_TERMS_CACHE", None)
    records = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(PLIEGOS_DIR.glob("*.json")) if p.name != "_index.json"
    ]
    parents = [r for r in records if not r.get("is_sub_denomination")]
    unresolved = [r["slug"] for r in parents if not nt.es_term_for(r, r["kind"])]
    assert unresolved == []
    assert nt.check_sub_denomination_terms(records) == []
    assert nt.es_term_for(next(r for r in parents if r["slug"] == "rioja"), "DOP") == "DOCa"
