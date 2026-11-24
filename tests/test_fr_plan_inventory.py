"""INAO's inventory of delimitation plans and the records drawn as the communes
holding their parcel area (triage of 2026-11-23: Champagne was drawn as its
635-commune aire géographique; the parcel area lies in 319)."""
from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.fr import plan_inventory as pi  # noqa: E402

_SHEET = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c>
<c r="D1" t="s"><v>3</v></c><c r="E1" t="s"><v>4</v></c><c r="F1" t="s"><v>5</v></c></row>
{rows}
</sheetData></worksheet>"""


def _xlsx(tmp_path: Path, rows: list[tuple]) -> Path:
    strings = ["signe", "appellation", "insee commune", "nom commune",
               "Délimitation parcellaire attendu", "Disponibilité plans aires parcellaires"]
    def s(v: str) -> int:
        if v not in strings:
            strings.append(v)
        return strings.index(v)
    body = []
    for i, (app, insee, nom, attendu, plan) in enumerate(rows, start=2):
        body.append(
            f'<row r="{i}"><c r="A{i}" t="s"><v>{s("AOC")}</v></c>'
            f'<c r="B{i}" t="s"><v>{s(app)}</v></c><c r="C{i}"><v>{insee}</v></c>'
            f'<c r="D{i}" t="s"><v>{s(nom)}</v></c><c r="E{i}" t="s"><v>{s(attendu)}</v></c>'
            f'<c r="F{i}" t="s"><v>{s(plan)}</v></c></row>')
    sheet = _SHEET.format(rows="\n".join(body))
    shared = ('<?xml version="1.0" encoding="UTF-8"?><sst xmlns="http://schemas.openxmlformats.org/'
              'spreadsheetml/2006/main">' + "".join(f"<si><t>{x}</t></si>" for x in strings) + "</sst>")
    path = tmp_path / "inv.xlsx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", sheet)
        z.writestr("xl/sharedStrings.xml", shared)
    return path


def test_rows_codes_padded_and_header_dropped(tmp_path: Path) -> None:
    rows = pi.read_rows(_xlsx(tmp_path, [("champagne", "2042", "AZY-SUR-MARNE", "oui", "plan disponible ")]))
    assert rows == [{"signe": "AOC", "appellation": "champagne", "insee": "02042",
                     "commune": "AZY-SUR-MARNE", "attendu": "oui", "plan": "plan disponible"}]


def test_a_commune_of_today_counts_when_any_of_its_rows_reads_oui(tmp_path: Path) -> None:
    """Blancs-Coteaux: one row per former commune, three oui and one non."""
    rows = pi.read_rows(_xlsx(tmp_path, [
        ("champagne", "51612", "BLANCS-COTEAUX", "oui", "plan disponible"),
        ("champagne", "51612", "BLANCS-COTEAUX", "non", "Aucune parcelle classée"),
        ("champagne", "51251", "FLAVIGNY", "non", "Aucune parcelle classée"),
        ("champagne", "2439", "LES SEPTVALLONS", "oui", "plan en cours d’élaboration"),
    ]))
    areas = pi.parcel_area_communes(rows)
    assert set(areas["champagne"]) == {"51612", "02439"}
    assert areas["champagne"]["02439"]["plans"] == ["plan en cours d’élaboration"]


def test_table_entries() -> None:
    table = pi.table()
    assert {"champagne", "coteaux-champenois", "rose-des-riceys"} <= set(table)
    for slug, e in table.items():
        assert e["source"] in ("inao-plan-inventory", "cahier"), slug
        assert e.get("reason") and e.get("verified"), slug
        if e["source"] == "inao-plan-inventory":
            assert e.get("appellation") and e.get("source_url"), slug
        else:
            assert e.get("communes") and all(re.fullmatch(r"\d[\dAB]\d{3}", c) for c in e["communes"]), slug


def _fold(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


@pytest.mark.parametrize("slug", [s for s, e in pi.table().items() if e["source"] == "cahier"])
def test_cahier_entry_quotes_its_record(slug: str) -> None:
    ev = pi.table()[slug]["evidence"]
    path = ROOT / ev["file"]
    if not path.exists():
        pytest.skip(f"{path} not on disk")
    rec = json.loads(path.read_text(encoding="utf-8"))
    body = rec
    for part in ev["field"].split("."):
        body = body[part]
    assert _fold(ev["quote"]) in _fold(body)


def test_champagne_list_on_disk() -> None:
    """With the inventory on disk: about INAO's 319, none of the cahier's
    communes «aucune parcelle n'a été retenue» among them."""
    if not pi.PARCEL_AREA_JSON.exists():
        pytest.skip("inventory not fetched")
    got = pi.communes_for("champagne")
    assert got and 300 <= len(got) <= 340
    assert pi.communes_for("coteaux-champenois") == got
    names = {re.sub(r"[^A-Z]", "", v) for v in got.values()}
    for none in ("BRIENNELECHATEAU", "CORFELIX", "VERDON", "POTANGIS", "CORROBERT"):
        assert none not in names
    assert pi.communes_for("rose-des-riceys") == {"10317": "Les Riceys"}
    assert pi.communes_for("cassis") is None
