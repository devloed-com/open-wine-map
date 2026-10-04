"""The region search-term table (scripts/_lib/region_search_terms.json) and
the pin table in scripts/refresh_region_search_terms.py stay consistent.

No network: the JSON is read from disk, the refresh script is imported for
its pin table and pure helpers only (importing it performs no fetch)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "scripts" / "_lib" / "region_search_terms.json"
SCRIPT_PATH = ROOT / "scripts" / "refresh_region_search_terms.py"

# The region facet labels of the corpus, per country (the FR bassins are
# localised through gettext and live elsewhere). A region renamed in the
# corpus must fail here, loudly.
EXPECTED_LABELS: dict[str, set[str]] = {
    "gr": {"Νησιά Αιγαίου", "Κρήτη", "Θράκη", "Μακεδονία", "Ήπειρος", "Στερεά Ελλάδα",
           "Θεσσαλία", "Πελοπόννησος", "Ιόνια Νησιά"},
    "cy": {"Πάφος", "Λεμεσός", "Λάρνακα", "Λευκωσία"},
    "bg": {"Тракийска низина", "Черноморски район", "Дунавска равнина",
           "Долината на Струма", "Розова долина"},
    "it": {"Toscana", "Piemonte", "Veneto", "Lombardia", "Emilia-Romagna", "Puglia",
           "Sardegna", "Campania", "Lazio", "Sicilia", "Calabria", "Umbria", "Marche",
           "Liguria", "Friuli-Venezia Giulia", "Abruzzo", "Trentino-Alto Adige",
           "Basilicata", "Molise", "Italia", "Valle d'Aosta"},
    "de": {"Rheinland-Pfalz", "Mosel", "Baden", "Bayern", "Franken", "Württemberg", "Nahe",
           "Hessen", "Sachsen", "Ahr", "Brandenburg", "Hessische Bergstraße", "Saarland",
           "Sachsen-Anhalt", "Mittelrhein", "Pfalz", "Rheingau", "Rheinhessen",
           "Saale-Unstrut", "Baden-Württemberg"},
    "es": {"Galicia", "Castilla-La Mancha", "Comunidad Valenciana", "España", "Andalucía",
           "Castilla y León", "Cataluña", "Canarias", "Aragón", "Baleares", "Madrid",
           "Navarra", "Murcia", "La Rioja", "País Vasco", "Cantabria", "Asturias",
           "Extremadura"},
    "pt": {"Minho", "Alentejo", "Lisboa", "Douro/Porto", "Tejo", "Algarve", "Trás-os-Montes",
           "Açores", "Beira Interior", "Dão", "Madeira", "Setúbal", "Bairrada"},
    "at": {"Niederösterreich", "Burgenland", "Steiermark", "Österreich", "Wien", "Kärnten",
           "Oberösterreich", "Salzburg", "Tirol", "Vorarlberg"},
    "ch": {"Genève", "Deutschschweiz", "Valais", "Vaud", "Trois-Lacs", "Ticino"},
    "hu": {"Balaton", "Felső-Pannon", "Duna", "Felső-Magyarország", "Pannon", "Tokaj",
           "Zemplén"},
    "ro": {"Moldova", "Transilvania", "Oltenia", "Dobrogea", "Crișana și Maramureș", "Banat",
           "Muntenia", "Terasele Dunării"},
    "cz": {"Morava", "Čechy"},
    "sk": {"Malokarpatská", "Tokaj", "Južnoslovenská", "Nitrianska", "Slovensko",
           "Stredoslovenská", "Východoslovenská"},
    "si": {"Posavje", "Primorska", "Podravje"},
    "hr": {"Primorska Hrvatska", "Zapadna kontinentalna Hrvatska",
           "Istočna kontinentalna Hrvatska"},
    "nl": {"Gelderland", "Limburg", "Overijssel", "Drenthe", "Flevoland", "Friesland",
           "Groningen", "Noord-Brabant", "Noord-Holland", "Utrecht", "Zeeland", "Zuid-Holland"},
    "be": {"Vlaanderen", "Wallonie"},
    "lu": {"Moselle Luxembourgeoise"},
    "mt": {"Gozo", "Malta", "Maltese Islands"},
    "gb": {"England", "Wales"},
}


@pytest.fixture(scope="module")
def refresh():
    """The refresh script as a module: pins + pure helpers, no network."""
    stamp = JSON_PATH.stat().st_mtime_ns if JSON_PATH.exists() else None
    spec = importlib.util.spec_from_file_location("refresh_region_search_terms", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    assert (JSON_PATH.stat().st_mtime_ns if JSON_PATH.exists() else None) == stamp, (
        "importing the refresh script must not rewrite the JSON"
    )
    return mod


@pytest.fixture(scope="module")
def table() -> dict:
    return json.loads(JSON_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def entries(table) -> dict[str, dict]:
    return {k: v for k, v in table.items() if not k.startswith("__")}


def _countries(entry: dict) -> set[str]:
    c = entry["country"]
    return set(c) if isinstance(c, list) else {c}


def test_metadata(table, refresh):
    assert table["__license__"].startswith("Wikidata, CC0 1.0")
    assert table["__generated_by__"] == "scripts/refresh_region_search_terms.py"
    assert JSON_PATH.read_text(encoding="utf-8") == refresh.dumps(table), (
        "JSON must be written deterministically (sort_keys, indent 1, trailing newline)"
    )


def test_every_expected_label_is_covered(entries):
    expected: dict[str, set[str]] = {}
    for cc, labels in EXPECTED_LABELS.items():
        for label in labels:
            expected.setdefault(label, set()).add(cc)
    assert set(entries) == set(expected), (
        f"missing: {sorted(set(expected) - set(entries))}, "
        f"unexpected: {sorted(set(entries) - set(expected))}"
    )
    for label, ccs in expected.items():
        assert _countries(entries[label]) == ccs, f"{label}: country {entries[label]['country']}"


def test_pins_and_json_agree(entries, refresh):
    pins = refresh.PINS
    assert set(pins) == set(entries), (
        f"pins missing from JSON: {sorted(set(pins) - set(entries))}, "
        f"JSON labels without a pin: {sorted(set(entries) - set(pins))}"
    )
    for label, (country, lang, qid, _note) in pins.items():
        assert entries[label]["qid"] == qid, label
        expected = set(country) if isinstance(country, list) else {country}
        assert _countries(entries[label]) == expected, label
        assert lang in refresh.FORM_LANGS or lang in {"el", "bg", "it", "de", "pt", "hu", "ro",
                                                       "cs", "sk", "sl", "hr", "mt"}, (label, lang)


def test_entry_shape(entries):
    for label, entry in entries.items():
        assert entry["country"], label
        assert isinstance(entry["fetched_at"], str) and len(entry["fetched_at"]) == 10, label
        assert isinstance(entry["label_check"], str) and entry["label_check"], label
        assert isinstance(entry["forms"], list), label
        assert all(isinstance(f, str) and f.strip() for f in entry["forms"]), label
        qid = entry["qid"]
        if qid is None:
            assert entry["reason"], f"{label}: a null pin needs a reason"
            assert "source" not in entry and entry["forms"] == [], label
            continue
        assert qid.startswith("Q") and qid[1:].isdigit(), label
        assert entry["source"] == f"https://www.wikidata.org/wiki/{qid}", label
        assert entry["label_check"] == "exact" or entry["label_check"].startswith("variant: "), (
            f"{label}: {entry['label_check']}"
        )
        assert entry["forms"] or entry.get("forms_empty_reason"), (
            f"{label}: a pinned item with no forms must say why"
        )


def test_no_form_matches_its_own_native_label(entries, refresh):
    for label, entry in entries.items():
        n_key = refresh.normalize_key(label)
        for form in entry["forms"]:
            key = refresh.normalize_key(form)
            assert key and key != n_key and key not in n_key, f"{label}: {form!r}"


def test_no_form_equals_another_native_label(entries, refresh):
    natives = {refresh.normalize_key(label): label for label in entries}
    for label, entry in entries.items():
        for form in entry["forms"]:
            other = natives.get(refresh.normalize_key(form))
            assert other in (None, label), f"{label}: {form!r} is the native label of {other!r}"


def test_no_form_is_shared_across_countries_with_different_items(entries, refresh):
    owners: dict[str, list[tuple[str, frozenset, str]]] = {}
    for label, entry in entries.items():
        for form in entry["forms"]:
            owners.setdefault(refresh.normalize_key(form), []).append(
                (label, frozenset(_countries(entry)), entry["qid"])
            )
    for key, own in owners.items():
        for a in own:
            for b in own:
                if a[0] < b[0] and a[2] != b[2] and not (a[1] & b[1]):
                    pytest.fail(f"form {key!r}: {a[0]!r} and {b[0]!r} pin different items")


def test_forms_are_deduplicated(entries, refresh):
    for label, entry in entries.items():
        keys = [refresh.normalize_key(f) for f in entry["forms"]]
        assert len(keys) == len(set(keys)), f"{label}: duplicate forms"


def test_alias_filter_and_normaliser(refresh):
    assert refresh.normalize_key("Hessische Bergstraße") == "hessische bergstraße"
    assert refresh.normalize_key("Île-de-France") == "ile de france"
    assert refresh.normalize_key("Νησιά Αιγαίου (διαμέρισμα)") == "νησια αιγαιου διαμερισμα"
    assert refresh.strip_qualifier("Douro (DOC)") == "Douro"
    assert refresh.strip_qualifier("Dão  (DOC)") == "Dão"
    for ok in ("Candia", "Piedmont", "Castile-La Mancha", "Euskadi", "Hegyalja"):
        assert refresh.is_proper_name_alias(ok), ok
    for bad in ("Free State of Bavaria", "BY", "CH-GE", "BaWü", "Sardinia, Italy", "Ang.",
                "Gld", "Moezelwijn", "Région wallonne", "Autonomous Community of Madrid",
                "Canton of Wallis", "Isles of Flanders", "Baden-WB", "AT33"):
        assert not refresh.is_proper_name_alias(bad), bad


def test_label_check_variants(refresh):
    check = refresh._native_label_check
    assert check("Κρήτη", "Κρήτη", [], "el") == "exact"
    assert check("Πάφος", "Επαρχία Πάφου", [], "el") == "variant: Επαρχία Πάφου"
    assert check("Тракийска низина", "Горнотракийска низина", ["Тракийската низина"], "bg") \
        == "variant: Тракийската низина"
    assert check("Douro/Porto", "Douro (DOC)", [], "pt") == "variant: Douro (DOC)"
    assert check("Madrid", "Comunidad de Madrid", [], "es") == "variant: Comunidad de Madrid"
    assert check("Balaton", "Balatoni borrégió", [], "hu") == "none"
    assert check("Zemplén", "Zempléni-hegység", [], "hu") == "none"


def test_build_forms_rules(refresh):
    forms, labels = refresh.build_forms(
        "Mosel",
        {"en": "Mosel", "fr": "Moselle (région viticole)", "es": "Mosel-Saar-Ruwer", "nl": "Mosel"},
        {"nl": ["Moezel", "Moezelwijn"]},
    )
    assert forms == ["Moselle", "Moezel"]
    assert labels == ["Moselle"]
    forms, labels = refresh.build_forms(
        "Marche", {"en": "Marche", "fr": "Marches", "es": "Marcas", "nl": "Marken"},
        {"en": ["the Marches"], "es": ["las Marcas"], "nl": ["de Marken"]},
    )
    assert forms == ["Marches", "Marcas", "Marken"]
    assert labels == forms
    assert refresh.build_forms(
        "Aragón", {"en": "Aragon", "fr": "Aragon", "es": "Aragón"}, {}
    ) == ([], [])
    # A descriptive label ships as its bare name; a typo alias and a demonym
    # are excluded; a label that is only a descriptor is dropped.
    forms, labels = refresh.build_forms(
        "Vlaanderen",
        {"en": "Flemish Region", "fr": "Région flamande", "nl": "Vlaams Gewest"},
        {"en": ["Flanders"], "fr": ["Flandre"]},
    )
    # "Région flamande" keeps its generic word after the strip and is dropped.
    assert forms == ["Flemish", "Vlaams", "Flanders", "Flandre"]
    assert labels == ["Flemish", "Vlaams"]
    forms, _ = refresh.build_forms(
        "Πελοπόννησος", {"en": "Peloponnese"}, {"fr": ["Pelloponèse"], "es": ["Peloponesio"]}
    )
    assert forms == ["Peloponnese"]
