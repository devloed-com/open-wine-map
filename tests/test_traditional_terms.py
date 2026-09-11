"""Shape guard for scripts/_lib/traditional_terms.json.

The loader (scripts/_lib/gi_terms.py) is written against this exact schema; a
drift here silently drops a country's term from every panel, so the file is
validated structurally rather than trusted.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "scripts" / "_lib" / "traditional_terms.json"
LOCALES = {"en", "fr", "es", "nl"}
SCHEME_IDS = {"pdo", "pgi", "spirit-gi", "uk-pdo", "uk-pgi", "none"}
COUNTRIES = {
    "fr",
    "ch",
    "it",
    "es",
    "pt",
    "ro",
    "at",
    "de",
    "mt",
    "gb",
    "lu",
    "be",
    "nl",
    "si",
    "hr",
    "hu",
    "bg",
    "gr",
    "cz",
    "sk",
    "cy",
}
ROSTER_KINDS = {("it", "DOP"), ("es", "DOP"), ("es", "IGP"), ("at", "DOP")}
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FILE_NUMBER_RE = re.compile(r"^(PDO|PGI)-[A-Z]{2}(\+[A-Z]{2})?-[A-Z0-9]+$")
VINTAGE_RE = re.compile(r"^\d{4}$")


@pytest.fixture(scope="module")
def raw() -> str:
    return PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def table(raw: str) -> dict:
    return json.loads(raw)


def _assert_sources(sources: object, where: str) -> None:
    assert isinstance(sources, list) and sources, f"{where}: sources must be a non-empty list"
    for src in sources:
        assert set(src) == {"label", "url"}, f"{where}: source keys must be label+url"
        assert src["label"].strip(), f"{where}: empty source label"
        assert re.match(r"^https?://", src["url"]), f"{where}: not a URL: {src['url']}"


def _assert_locales(block: object, where: str) -> None:
    assert isinstance(block, dict) and set(block) == LOCALES, f"{where}: needs {sorted(LOCALES)}"
    for lang, text in block.items():
        assert isinstance(text, str) and text.strip(), f"{where}.{lang}: empty"


def test_canonical_serialisation(raw: str, table: dict) -> None:
    assert raw == json.dumps(table, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def test_top_level_keys(table: dict) -> None:
    assert set(table) == {"__doc__", "schemes", "constants", "rulings", "pins", "terms"}
    assert table["__doc__"].strip()


def test_schemes(table: dict) -> None:
    assert set(table["schemes"]) == SCHEME_IDS
    for sid, scheme in table["schemes"].items():
        assert set(scheme) == {"full", "note", "sources"}, sid
        _assert_locales(scheme["full"], f"schemes.{sid}.full")
        _assert_locales(scheme["note"], f"schemes.{sid}.note")
        _assert_sources(scheme["sources"], f"schemes.{sid}")


def test_constants_cover_every_country(table: dict) -> None:
    constants = table["constants"]
    assert set(constants) == COUNTRIES
    assert set(table["rulings"]) == COUNTRIES
    for cc, kinds in constants.items():
        for kind, term in kinds.items():
            assert kind in {"AOC", "IGP", "EDV", "DOP"}, (cc, kind)
            assert isinstance(term, str), (cc, kind)
            assert (cc, kind) not in ROSTER_KINDS, f"{cc}:{kind} is roster-served, not constant"
    for cc, kind in ROSTER_KINDS:
        assert kind not in constants.get(cc, {}), f"{cc}:{kind} must be omitted (roster)"


def test_rulings(table: dict) -> None:
    for cc, ruling in table["rulings"].items():
        assert set(ruling) == {"reason", "sources"}, cc
        assert ruling["reason"].strip(), cc
        _assert_sources(ruling["sources"], f"rulings.{cc}")


def test_pins(table: dict) -> None:
    assert set(table["pins"]) <= COUNTRIES
    for cc, by_file in table["pins"].items():
        assert by_file, cc
        for key, entry in by_file.items():
            where = f"pins.{cc}.{key}"
            # keyed by EU file number (rosters) or by slug (a record whose own
            # fields cannot carry the fact, e.g. an empty SIQO categorie row)
            assert FILE_NUMBER_RE.match(key) or SLUG_RE.match(key), where
            assert {"term", "sources"} <= set(entry) <= {
                "term", "since_vintage", "sources", "scheme", "note"
            }, where
            assert entry["term"].strip(), where
            if "since_vintage" in entry:
                assert VINTAGE_RE.match(entry["since_vintage"]), where
            _assert_sources(entry["sources"], where)


def test_at_pins_match_eambrosia_dacs(table: dict) -> None:
    index = Path(__file__).resolve().parents[1] / "raw" / "at" / "eambrosia" / "index.json"
    if not index.exists():
        pytest.skip("raw/at/eambrosia/index.json not fetched")
    wines = json.loads(index.read_text(encoding="utf-8"))["wines"]
    by_file = {w["fileNumber"]: w for w in wines}
    for file_number in table["pins"]["at"]:
        assert file_number in by_file, file_number
        assert by_file[file_number]["kind"] == "DOP", file_number


def test_terms(table: dict) -> None:
    for key, term in table["terms"].items():
        cc, _, spelled = key.partition(":")
        assert cc in COUNTRIES and spelled, key
        assert {"full", "scheme", "note", "sources"} <= set(term), key
        assert set(term) - {"full", "scheme", "note", "sources", "castilian_form"} == set(), key
        assert term["scheme"] in table["schemes"], key
        assert term["full"].strip(), key
        _assert_locales(term["note"], f"terms.{key}.note")
        _assert_sources(term["sources"], f"terms.{key}")


def test_every_constant_and_pin_term_is_defined(table: dict) -> None:
    used = {
        f"{cc}:{term}"
        for cc, kinds in table["constants"].items()
        for term in kinds.values()
        if term
    }
    used |= {
        f"{cc}:{entry['term']}"
        for cc, by_file in table["pins"].items()
        for entry in by_file.values()
    }
    missing = sorted(used - set(table["terms"]))
    assert not missing, f"terms without a definition: {missing}"


def test_scheme_none_only_for_switzerland(table: dict) -> None:
    for key, term in table["terms"].items():
        assert (term["scheme"] == "none") == key.startswith("ch:"), key
