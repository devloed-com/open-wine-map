"""The per-record style additions of scripts/_lib/style_overrides.py: a
curator's cited reading where the country's reader has no rule yet (Porto's
sweetness table, Madeira's type list, a French mistelle's method). Pins the
table (every quote is in the record's own text, a `method` entry discloses
itself in four languages), that an entry retires once its reader states the
style, the inheritance by sub-denominations, and the wiring of stage 04 and
the two card renderers."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import style_overrides as so  # noqa: E402
from _lib.style_taxonomy import simple_buckets  # noqa: E402

TABLE = so.load_style_overrides()
BUILD_CONTEXT = ROOT / "wiki" / "data" / "mcp" / "en.json"


def _fold(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _entry(**kw) -> dict:
    base = {
        "country": "pt", "add": ["sweet"], "basis": "stated", "reason": "r", "source": "s",
        "verified": "2026-11-14", "evidence": [{"file": "f.json", "field": "a.b", "quote": "q"}],
    }
    return {**base, **kw}


def _load(tmp_path: Path, table: dict) -> dict:
    path = tmp_path / "style_overrides.json"
    path.write_text(json.dumps(table), encoding="utf-8")
    return so.load_style_overrides(path)


def test_table_is_not_empty_and_adds_what_puts_the_record_under_sweet() -> None:
    assert {"porto", "madeira", "pineau-des-charentes"} <= set(TABLE)
    for slug, ent in TABLE.items():
        buckets = {b for s in ent["add"] for b in simple_buckets(s)}
        assert "sweet" in buckets, f"{slug}: {ent['add']} files nothing under Sweet"
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", ent["verified"]), slug


def test_a_method_entry_discloses_itself_and_a_stated_one_does_not() -> None:
    for slug, ent in TABLE.items():
        if ent["basis"] == "method":
            assert set(ent["disclose"]) == set(so.LOCALES), slug
            assert all(len(t) > 40 for t in ent["disclose"].values()), slug
        else:
            assert "disclose" not in ent, slug


@pytest.mark.parametrize("slug", sorted(TABLE))
def test_every_quote_is_in_the_record(slug: str) -> None:
    for ev in TABLE[slug]["evidence"]:
        path = ROOT / ev["file"]
        if not path.exists():
            pytest.skip(f"{ev['file']} not on disk (raw/ is not checked in)")
        node = json.loads(path.read_text(encoding="utf-8"))
        for key in ev["field"].split("."):
            node = (node or {}).get(key)
        assert _fold(ev["quote"]) in _fold(node or ""), f"{slug}: {ev['quote']!r} not in {ev['file']} {ev['field']}"


@pytest.mark.parametrize("slug", sorted(TABLE))
def test_an_entry_retires_when_its_reader_states_the_style(slug: str) -> None:
    """STALE: the extracted record already carries every style the entry
    adds, so the reader reads the sentence now and the pin must go."""
    path = ROOT / TABLE[slug]["evidence"][0]["file"]
    if not path.exists():
        pytest.skip(f"{path.name} not on disk (raw/ is not checked in)")
    carried = set(json.loads(path.read_text(encoding="utf-8")).get("styles") or [])
    assert not set(TABLE[slug]["add"]) <= carried, (
        f"{slug}: the reader states {TABLE[slug]['add']} now — drop the entry"
    )


def test_additions_own_entry_parent_entry_and_nothing_to_add(capsys) -> None:
    table = {"porto": _entry(add=["semi-dry", "sweet"])}
    assert so.style_additions(table, "porto", "", {"red", "vin-de-liqueur"}) == ("porto", ["semi-dry", "sweet"])
    # only what the record lacks
    assert so.style_additions(table, "porto", "", {"sweet"}) == ("porto", ["semi-dry"])
    # a sub-denomination takes its parent's entry
    assert so.style_additions(table, "porto-baixo-corgo", "porto", {"red"}) == ("porto", ["semi-dry", "sweet"])
    assert so.style_additions(table, "douro", "", {"red"}) == ("", [])
    assert capsys.readouterr().err == ""
    # the reader states it all: nothing added, and the record's own entry says STALE
    assert so.style_additions(table, "porto", "", {"semi-dry", "sweet"}) == ("", [])
    assert "STALE porto" in capsys.readouterr().err
    # an inheriting sub-denomination is not the stale one
    assert so.style_additions(table, "porto-baixo-corgo", "porto", {"semi-dry", "sweet"}) == ("", [])
    assert capsys.readouterr().err == ""


def test_own_entry_wins_over_the_parents() -> None:
    table = {"parent": _entry(add=["sweet"]), "child": _entry(add=["semi-sweet"])}
    assert so.style_additions(table, "child", "parent", set()) == ("child", ["semi-sweet"])


def test_disclosure_only_for_a_method_entry() -> None:
    disclose = {loc: f"text {loc} — long enough to be a sentence" for loc in so.LOCALES}
    table = {"a": _entry(), "b": _entry(basis="method", disclose=disclose)}
    assert so.disclosure(table, "a") is None
    assert so.disclosure(table, "b") == disclose
    assert so.disclosure(table, "") is None


@pytest.mark.parametrize(
    "bad",
    [
        _entry(add=[]),
        _entry(add=["sucré"]),
        _entry(basis="guess"),
        _entry(evidence=[]),
        _entry(evidence=[{"file": "f.json", "field": "a", "quote": ""}]),
        _entry(source=""),
        _entry(basis="method"),
        _entry(basis="method", disclose={"en": "only english"}),
        _entry(disclose={loc: "x" for loc in so.LOCALES}),
    ],
)
def test_the_loader_refuses_an_incomplete_entry(tmp_path: Path, bad: dict) -> None:
    with pytest.raises(ValueError):
        _load(tmp_path, {"x": bad})


def test_the_loader_skips_the_doc_key(tmp_path: Path) -> None:
    assert _load(tmp_path, {"__doc__": "text", "x": _entry()}) == {"x": _entry()}


def test_stage_04_and_both_renderers_are_wired() -> None:
    stage04 = (ROOT / "scripts" / "04_build_maps.py").read_text(encoding="utf-8")
    assert "style_additions(" in stage04 and '"styles_override"' in stage04 and '"styles_note"' in stage04
    ssr = (ROOT / "scripts" / "_lib" / "content_block.py").read_text(encoding="utf-8")
    app = (ROOT / "scripts" / "_lib" / "assets" / "app.js").read_text(encoding="utf-8")
    assert 'class="approx-line styles-note"' in ssr and 'class="approx-line styles-note"' in app
    assert "r.styles_note" in app


def test_the_card_prints_the_disclosure_under_the_style_pills() -> None:
    ssr = (ROOT / "scripts" / "_lib" / "content_block.py").read_text(encoding="utf-8")
    # the line sits right under the style pills, after the inferred-colour line
    assert ssr.index('f"{inferred_line}"') < ssr.index('f"{styles_note_line}"') < ssr.index(
        "f\"{_section(lab['facet_principal_h'], principal)}\""
    )


@pytest.mark.parametrize("slug", sorted(TABLE))
def test_the_build_files_the_record_under_sweet(slug: str) -> None:
    if not BUILD_CONTEXT.exists() or BUILD_CONTEXT.stat().st_mtime < so.OVERRIDES_PATH.stat().st_mtime:
        pytest.skip("no build on disk newer than the table")
    aocs = json.loads(BUILD_CONTEXT.read_text(encoding="utf-8"))["aocs"]
    rec = aocs[slug]
    assert set(TABLE[slug]["add"]) <= set(rec["styles"]), f"{slug}: the build did not apply the entry"
    assert "sweet" in rec["styles_simple"] and "fortified" in rec["styles_simple"], slug
    for child, crec in aocs.items():
        if crec.get("parent_slug") == slug and child not in TABLE:
            assert set(TABLE[slug]["add"]) <= set(crec["styles"]), f"{child} did not inherit {slug}'s entry"
