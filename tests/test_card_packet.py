"""The validator packet: the card as text, the source documents behind it,
and the shape the judge is given (scripts/_lib/card_packet.py)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import card_packet as cp  # noqa: E402


def test_html_to_text_keeps_blocks_and_separates_pills():
    html = ('<h1>Pauillac</h1><p>🇫🇷 France · <abbr title="x">AOC</abbr></p>'
            '<div class="pills"><a class="pill grape">Merlot</a><a class="pill grape">Cot</a></div>'
            '<ul><li>one</li><li>two</li></ul><script>var x=1</script>')
    text = cp.html_to_text(html)
    assert "Pauillac\n" in text
    assert "Merlot · Cot" in text.replace(" ·  · ", " · ") or "· Merlot" in text
    assert "• one" in text and "• two" in text
    assert "var x" not in text


def test_section_order_roman_then_dotted_numbers():
    keys = ["7.1", "X", "2", "I", "10", "7", "a"]
    assert sorted(keys, key=cp._section_order) == ["I", "X", "2", "7", "7.1", "10", "a"]


def test_text_blocks_reads_sections_once_and_the_roster():
    rec = {
        "sections": {"II": "Dénomination géographique complémentaire text here", "I": "Nom de l'appellation …… long enough"},
        "section_titles": {"I": "Nom", "II": "DGC"},
        "section_roles": {"aire": "ignored when sections exist ……………"},
        "link_to_terroir": "the lien text that is long enough to count",
        "link_to_terroir_full": "the lien text that is long enough to count",
        "grapes": {"details": [{"name": "merlot N", "slug": "merlot", "role": "principal", "colour": "noir"},
                               {"name": "merlot N", "slug": "merlot", "role": "principal"}]},
    }
    blocks = cp.text_blocks(rec, label="R")
    headings = [h for h, _ in blocks]
    assert headings[0].startswith("R — section I") and headings[1].startswith("R — section II")
    assert sum(1 for h in headings if "link_to_terroir" in h) == 1
    assert not any("aire" in h for h in headings)
    roster = dict(blocks)["R — variety roster (parsed)"]
    assert roster.splitlines() == ["merlot N [merlot] — principal (noir)"]


def test_roster_text_falls_back_to_slug_lists():
    assert cp.roster_text({"principal": ["a"], "accessory": ["b"], "details": []}) == "a — principal\nb — accessory"
    assert cp.roster_text(None) == ""


def test_source_documents_prefers_regulator_then_sidecars_then_wikipedia(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    (raw / "xx" / "ext").mkdir(parents=True)
    (raw / "xx" / "side").mkdir(parents=True)
    (raw / "wikipedia" / "aocs" / "xx").mkdir(parents=True)
    import json
    (raw / "xx" / "ext" / "foo.json").write_text(json.dumps({
        "sections": {"1": "The regulator says the area is the commune of Foo and nothing else at all."},
        "section_titles": {"1": "Area"}, "source": {"source_url": "https://reg.example/foo.pdf"}}))
    (raw / "xx" / "side" / "foo.json").write_text(json.dumps({"link_to_terroir": "A national spec paragraph about soils and climate.", "source": {"url": "https://nat.example/foo.pdf"}}))
    (raw / "wikipedia" / "aocs" / "xx" / "foo.json").write_text(json.dumps({"lang": "xx", "page_title": "Foo", "page_url": "https://xx.wikipedia.org/wiki/Foo", "full_text": "Wikipedia text " * 50}))
    monkeypatch.setattr(cp, "RAW", raw)
    monkeypatch.setattr(cp, "EXTRACTED_DIRS", {"xx": (raw / "xx" / "ext",)})
    monkeypatch.setattr(cp, "SIDECAR_DIRS", {"xx": (("national-spec", "Spec", raw / "xx" / "side"),)})
    monkeypatch.setitem(cp.WIKI_LANG_BY_COUNTRY, "xx", "xx")
    docs = cp.source_documents("xx", "foo")
    assert [d["kind"] for d in docs] == ["regulator", "national-spec", "wikipedia"]
    assert docs[0]["url"] == "https://reg.example/foo.pdf" and "commune of Foo" in docs[0]["text"]
    assert docs[1]["url"] == "https://nat.example/foo.pdf"
    # the budget cuts the tail, never the regulator record
    docs2 = cp.source_documents("xx", "foo", max_chars=120)
    assert docs2 and docs2[0]["kind"] == "regulator"


@pytest.mark.skipif(not (ROOT / "wiki" / "data").exists() or not list((ROOT / "wiki" / "data").glob("aocs.en.*.js")),
                    reason="no built site")
def test_packet_on_the_built_site_has_card_and_documents():
    aocs, _ = cp.load_startup("en")
    slug = next((s for s in ("pauillac", "rioja", "barolo") if s in aocs), next(iter(aocs)))
    p = cp.build_packet("en", slug)
    assert p and p["card_text"] and p["documents"]
    assert p["card"]["name"] == aocs[slug]["name"]
    msg = cp.packet_user_message(p)
    assert "CARD AS RENDERED" in msg and "SOURCE DOCUMENTS" in msg


def test_card_fields_exposes_the_summary_only_when_the_card_renders_it(monkeypatch):
    monkeypatch.setattr(cp, "load_startup", lambda locale: ({}, {}))
    base = {"name": "X", "summary": "Section-1 paste the card never shows", "summary_translation": True,
            "grapes_principal": [], "grapes_accessory": []}
    with_facts = dict(base, terroir_facts={"facts": [{"bullet": "a fact", "subsection": "produit", "provenance": "cahier"}]})
    f = cp.card_fields("en", "x", with_facts)
    assert f["summary"] == "" and f["summary_translation"] is False
    assert f["terroir_facts"][0]["bullet"] == "a fact"
    g = cp.card_fields("en", "x", dict(base, terroir_facts={"facts": []}))
    assert g["summary"] == "Section-1 paste the card never shows" and g["summary_translation"] is True
