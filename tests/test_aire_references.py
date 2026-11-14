"""`scripts/_lib/aire_references.json`: an appellation whose cahier defines
its area as another appellation's is bound to that aire by a cited pin, never
by a name that happens to contain it (the three Champagne spirits)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import aires  # noqa: E402
from _lib.grape_lexicon import slugify  # noqa: E402

EXTRACTED = ROOT / "raw" / "inao" / "cahier-extracted"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("’", "'")).strip()


def test_table_shape() -> None:
    pins = aires.load_aire_references()
    assert pins, "the table holds at least the Champagne spirits"
    for name, pin in pins.items():
        assert set(pin) == {"aire", "quote", "source", "verified"}, name
        assert pin["aire"].strip() and pin["quote"].strip(), name
        assert "https://" in pin["source"], name
        assert DATE_RE.match(pin["verified"]), name
        # a reference to itself would be no reference
        assert aires._normalize(pin["aire"]) != aires._normalize(name), name


def test_a_reference_binds_before_any_name_resemblance() -> None:
    index = {"champagne": {"1": {"51001", "10002"}}, "marcdechampagne": {"9": {"99999"}}}
    name = "Ratafia de Champagne ou Ratafia champenois"
    saved = (set(aires._SPIRIT_KEYS), set(aires._WINE_KEYS))
    try:
        # the spirit guard alone refuses the wine's aire …
        aires.register_product_names([name], ["Champagne"])
        aires._AIRE_REFERENCES = {}
        assert aires.lookup(index, name) is None
        # … the cited reference binds it
        aires._AIRE_REFERENCES = None
        assert aires.lookup(index, name) == {"51001", "10002"}
    finally:
        aires._AIRE_REFERENCES = None
        aires._SPIRIT_KEYS.clear()
        aires._SPIRIT_KEYS.update(saved[0])
        aires._WINE_KEYS.clear()
        aires._WINE_KEYS.update(saved[1])


def test_each_quote_is_in_the_records_own_area_section() -> None:
    if not EXTRACTED.exists():
        pytest.skip("raw/inao/cahier-extracted not built")
    checked = 0
    for name, pin in aires.load_aire_references().items():
        path = EXTRACTED / f"{slugify(name)}.json"
        if not path.exists():
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("kind") == "STUB":
            continue
        area = _fold((record.get("section_roles") or {}).get("aire") or "")
        assert _fold(pin["quote"]) in area, f"{name}: the quote is not in the cahier's area section"
        checked += 1
    if not checked:
        pytest.skip("no referenced record extracted")
