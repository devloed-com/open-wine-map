"""The Bavarian Gemeinde-list reader (scripts/_lib/de/gemeinde_list.py).

Franken and Landwein Main are delimited by Regierungsbezirk and Kreis; Bétard
drew Franken before its 2025 amendment removed fifteen Gemeinden and added
three (feedback triage 2026-11-24)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.de import gemeinde_list as gl  # noqa: E402

# The layout of Franken's single document (C/2025/6794, section 9): "—"
# bullets, Regierungsbezirk headers, Kreis lists.
FRANKEN_EXCERPT = """Zur geschützten Ursprungsbezeichnung Franken gehören die Rebflächen folgender Städte, Gemeinden und deren Ortsteile.
—
Regierungsbezirk Oberfranken:
—
Kreisfreie Stadt: Bamberg
—
Landkreis Bamberg: Oberhaid, Viereth-Trunstadt
—
Regierungsbezirk Unterfranken:
—
Kreisfreie Städte: Aschaffenburg, Schweinfurt, Würzburg
—
Landkreis Haßberge: Aidhausen, Königsberg in Bayern, Sand am Main, Zeil am Main
—
Landkreis Main-Spessart: Erlenbach bei Marktheidenfeld, Gemünden
am Main, Karlstadt.
Die genaue Abgrenzung ergibt sich aus den Karten mit den parzellenmäßig abgegrenzten Rebflächen der obengenannten Städte und Gemeinden, welche unter www.ble.de/eu-qualitaetskennzeichen-wein einsehbar sind."""

# Franken's BLE § 4 prints the closing sentence before the lists.
BLE_ORDER = """Zur geschützten Ursprungsbezeichnung Franken gehören die Rebflächen folgender Städte,
Gemeinden und deren Ortsteile. Die genaue Abgrenzung ergibt sich aus den Karten mit den
parzellenscharf abgegrenzten Rebflächen, welche unter www.ble.de/eu-
qualitaetskennzeichen-wein einsehbar sind.

Regierungsbezirk Oberfranken:
Kreisfreie Stadt: Bamberg
Landkreis Bamberg: Oberhaid, Viereth-Trunstadt
"""


def test_parse_lists_reads_every_kreis_under_its_regierungsbezirk():
    lists = gl.parse_lists(FRANKEN_EXCERPT)
    got = [(k.rb, k.kreisfrei, k.kreis, k.names) for k in lists]
    assert got == [
        ("Oberfranken", True, "", ["Bamberg"]),
        ("Oberfranken", False, "Bamberg", ["Oberhaid", "Viereth-Trunstadt"]),
        ("Unterfranken", True, "", ["Aschaffenburg", "Schweinfurt", "Würzburg"]),
        ("Unterfranken", False, "Haßberge",
         ["Aidhausen", "Königsberg in Bayern", "Sand am Main", "Zeil am Main"]),
        ("Unterfranken", False, "Main-Spessart",
         ["Erlenbach bei Marktheidenfeld", "Gemünden am Main", "Karlstadt"]),
    ]
    assert gl.n_names(lists) == 13


def test_closing_sentence_before_the_lists_does_not_cut_them():
    assert gl.n_names(gl.parse_lists(BLE_ORDER)) == 3


def test_no_regierungsbezirk_header_is_not_this_layout():
    # The Rhineland lists: "Gemeinden und deren Ortsteile Alf (1599), …".
    assert gl.parse_lists("Zur geschützten Ursprungsbezeichnung gehören die Rebflächen der "
                          "Gemeinden Alf (1599), Alken (1375), Landkreis Cochem: Bremm") == []


@pytest.mark.parametrize("printed, gisco", [
    ("Sand am Main", "Sand a.Main"),
    ("Königsberg in Bayern", "Königsberg i.Bay., St"),
    ("Neustadt an der Aisch", "Neustadt a.d.Aisch, St"),
    ("Neustadt a. d. Aisch", "Neustadt a.d.Aisch, St"),
    ("Erlenbach bei Marktheidenfeld", "Erlenbach b.Marktheidenfeld"),
    ("Michelau im Steigerwald", "Michelau i.Steigerwald"),
    ("Alzenau i. UFr.", "Alzenau in Unterfranken, St"),
    ("Rothenburg ob der Tauber", "Rothenburg ob der Tauber, GKSt"),
    ("Markt Einersheim", "Markt Einersheim, M"),
    ("Haßfurt", "Haßfurt, St"),
])
def test_name_key_folds_bavarian_abbreviations(printed, gisco):
    assert gl.name_key(printed) == gl.name_key(gisco)


ROWS = [
    ("DE_09461000", "Bamberg"),                 # kreisfreie Stadt, Oberfranken
    ("DE_09471156", "Oberhaid"),
    ("DE_09471207", "Viereth-Trunstadt"),
    ("DE_09662000", "Schweinfurt"),             # kreisfreie Stadt, Unterfranken
    ("DE_09678139", "Schonungen"),
    ("DE_09678170", "Waigolshausen"),
    ("DE_09679999", "Schonungen"),              # a homonym in another Landkreis
    ("DE_09187999", "Oberhaid"),                # a homonym in Oberbayern
]


def test_resolve_scopes_by_regierungsbezirk_kreis_and_kreisfrei_status():
    lists = [
        gl.KreisList("Oberfranken", "4", True, "", ["Bamberg"]),
        gl.KreisList("Oberfranken", "4", False, "Bamberg", ["Oberhaid", "Viereth-Trunstadt"]),
        gl.KreisList("Unterfranken", "6", False, "Schweinfurt", ["Schonungen", "Waigolshausen"]),
    ]
    res = gl.resolve(lists, ROWS)
    assert [(n, gid) for n, gid, _ in res.drawn] == [
        ("Bamberg", "DE_09461000"),
        ("Oberhaid", "DE_09471156"),
        ("Viereth-Trunstadt", "DE_09471207"),
        ("Schonungen", "DE_09678139"),
        ("Waigolshausen", "DE_09678170"),
    ]
    assert res.unmatched == [] and res.share == 1.0


def test_a_name_with_no_commune_in_its_kreis_is_reported_not_guessed():
    lists = [gl.KreisList("Unterfranken", "6", False, "Schweinfurt",
                          ["Waigolshausen", "Atlantis"])]
    res = gl.resolve(lists, ROWS)
    assert res.unmatched == ["Atlantis"]
    assert res.share == 0.5


# ── against the extracted corpus, when present ──────────────────────────

EXTRACTED = ROOT / "raw" / "de" / "dokumente-extracted"
SIDECARS = ROOT / "raw" / "de" / "produktspezifikationen-extracted"

# PDO-DE-A1267-AM01 (8 October 2025), "Abgrenzung des Gebiets".
REMOVED_2025 = {
    "Kemmern", "Markt Erlbach", "Uffenheim", "Wonfurt", "Martinsheim", "Wiesentheid",
    "Hasloch", "Röthlein", "Werneck", "Altertheim", "Aub", "Bieberehren", "Höchberg",
    "Holzkirchen", "Prosselsheim",
}
ADDED_2025 = {"Neustadt an der Aisch", "Sulzthal", "Röllbach"}


@pytest.mark.skipif(not (EXTRACTED / "franken.json").exists(), reason="no extracted corpus")
def test_franken_and_landwein_main_are_read_from_their_own_lists():
    areas = gl.load_areas(EXTRACTED, SIDECARS)
    fr = areas["PDO-DE-A1267"]
    assert fr["source_kind"] == "eu-single-document"
    fr_keys = {gl.name_key(n) for k in fr["lists"] for n in k.names}
    assert gl.n_names(fr["lists"]) == 127
    assert not fr_keys & {gl.name_key(n) for n in REMOVED_2025}
    assert {gl.name_key(n) for n in ADDED_2025} <= fr_keys
    lm = areas["PGI-DE-A1282"]
    assert lm["source_kind"] == "ble-produktspezifikation"
    lm_keys = {gl.name_key(n) for k in lm["lists"] for n in k.names}
    # Landwein Main lists what Franken listed before the amendment.
    assert lm_keys - fr_keys == {gl.name_key(n) for n in REMOVED_2025}
    assert fr_keys <= lm_keys
    # Only these two records are in the Bavarian layout.
    assert set(areas) == {"PDO-DE-A1267", "PGI-DE-A1282"}
