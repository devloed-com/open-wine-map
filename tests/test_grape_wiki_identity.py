"""A grape pill's Wikipedia article must be its own (2026-11-14, the Palomino
question): an article found through a VIVC passport the slug no longer has is
withheld, and the bare Palomino pill carries a note instead of the Palomino
Fino article."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import map_template as mt  # noqa: E402
from _lib.grape_wiki_identity import passport_match_is_stale  # noqa: E402

CURRENT = {"picardan": 527, "montepulciano": 7949, "palomino-fino": 8888}
WITHDRAWN = frozenset({"pugnitello", "palomino"})


def _stale(record: dict, slug: str) -> bool:
    return passport_match_is_stale(record, slug, current=CURRENT, withdrawn=WITHDRAWN)


def test_a_match_through_a_withdrawn_passport_is_stale():
    rec = {"matched_via": "shared-vivc:7949:montepulciano", "vivc_consulted": {"vivc_id": 7949}}
    assert _stale(rec, "pugnitello")


def test_a_match_through_another_number_is_stale():
    rec = {"matched_via": "shared-vivc:1612:bourboulenc", "vivc_consulted": {"vivc_id": 1612}}
    assert _stale(rec, "picardan")
    assert _stale({"matched_via": "vivc-synonym:X", "vivc_consulted": {"vivc_id": 1612}}, "picardan")
    assert _stale({"matched_via": "vivc-prime", "vivc_consulted": {"vivc_id": 1612}}, "picardan")


def test_the_current_passport_stands():
    rec = {"matched_via": "shared-vivc:8888:palomino", "vivc_consulted": {"vivc_id": 8888}}
    assert not _stale(rec, "palomino-fino")


def test_a_title_match_or_a_curator_pin_is_never_stale_by_passport():
    for via in ("primary", "primary-disambig", "override", None):
        rec = {"matched_via": via, "vivc_consulted": {"vivc_id": 8888}}
        assert not _stale(rec, "palomino")


def test_an_unresolved_slug_keeps_its_entry():
    # no resolution yet and no withdrawn pin: a gap, not a decision
    rec = {"matched_via": "vivc-prime", "vivc_consulted": {"vivc_id": 2863}}
    assert not _stale(rec, "corvina")


def test_the_palomino_note_replaces_the_borrowed_article():
    labels = {"bianchello_note": "B", "palomino_note": "P"}
    info = {
        "palomino": {"name": "palomino", "extract": "Palomino Fino is a white grape …",
                     "page_url": "https://en.wikipedia.org/wiki/Palomino_(grape)",
                     "thumbnail": "x.jpg", "wikipedia_title": "Palomino", "revision_id": "1"},
        "palomino-fino": {"name": "palomino fino", "extract": "Palomino Fino is a white grape …",
                          "page_url": "https://en.wikipedia.org/wiki/Palomino_(grape)",
                          "vivc_id": 8888},
        "bianchello": {"name": "bianchello", "extract": "Bianchello is …"},
    }
    mt.apply_grape_notes(info, labels)
    bare = info["palomino"]
    assert bare["note"] == "P" and bare["name"] == "palomino"
    assert not {"extract", "page_url", "thumbnail", "wikipedia_title"} & set(bare)
    assert [s["label"] for s in bare["sources"]] == ["VIVC #8888", "VIVC #8887"]
    # the article stays on the pill it describes, and a plain note keeps its article
    assert info["palomino-fino"]["extract"].startswith("Palomino Fino")
    assert info["bianchello"]["note"] == "B" and info["bianchello"]["extract"]


def test_every_grape_note_has_its_label():
    labels = mt.build_labels(lambda s: s)
    for slug, (key, _replaces, sources) in mt._GRAPE_NOTES.items():
        assert labels.get(key), slug
        for label, url in sources:
            assert label and url.startswith("https://"), slug


def test_a_null_pin_takes_effect_on_a_cached_article():
    import importlib.util
    spec = importlib.util.spec_from_file_location("fetch02b", ROOT / "scripts" / "02b_fetch_grape_lexicon.py")
    fetch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fetch)
    saved = fetch.LANG_OVERRIDES
    try:
        fetch.LANG_OVERRIDES = {"en": {"chenanson": None, "airen": "Airén"}}
        cached = {"wikipedia_title": "Chenin blanc", "extract": "…", "matched_via": "vivc-synonym:VAALBLAAR STEIN"}
        assert fetch._null_pin_unapplied("en", "chenanson", cached)
        assert not fetch._null_pin_unapplied("en", "chenanson", {"missing": True, "matched_via": "override-absent"})
        assert not fetch._null_pin_unapplied("fr", "chenanson", cached)      # pinned for English only
        assert not fetch._null_pin_unapplied("en", "airen", cached)          # a title pin is not a null pin
    finally:
        fetch.LANG_OVERRIDES = saved
