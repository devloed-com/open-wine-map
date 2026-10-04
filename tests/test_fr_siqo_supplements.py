"""The SIQO supplement rows (scripts/_lib/fr/siqo_supplements.json) and the
rule they implement: the FR corpus follows INAO's catalogue, not the
vintage of the data.gouv.fr export — a GI the export predates is added, a
row the export dropped is retained, and a full stage-02 run refuses to
remove a record the export merely stopped listing."""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.fr import siqo  # noqa: E402


def test_supplement_rows_validate():
    rows = siqo.load_supplements()
    assert rows, "no supplement rows"
    for r in rows:
        assert r["_status"] in siqo.SUPPLEMENT_STATUSES
        date.fromisoformat(r["_verified"])
        assert "http" in r["_source"], "cite the public act"
        assert set(siqo.SIQO_COLUMNS) <= set(r)
        if r["id_appellation"].startswith("p"):
            assert r["id_appellation"] == f"p{r['idproduit']}", "provisional id = p<idproduit>"


def test_montpeyroux_is_added_as_a_wine_appellation():
    rows = [r for r in siqo.load_supplements() if r["appellation"] == "Montpeyroux"]
    assert len(rows) == 1
    r = rows[0]
    assert r["_status"] == "added"
    assert siqo.is_wine_row(r)
    assert r["idproduit"] == "23354" and r["signe_fr"] == "AOC" and r["signe_ue"] == ""
    assert r["comite_regional"] == "LANGUEDOC-ROUSSILLON"


def test_rows_append_and_a_retained_row_yields_to_the_csv(tmp_path: Path):
    csv_path = tmp_path / "siqo.csv"
    csv_path.write_text(
        ",".join(siqo.SIQO_COLUMNS) + "\n"
        + "AOC,AOP,1,Vin tranquille,2,Vins,VITICOLE,1,Alpha,10,Alpha,Alpha rouge,100,2,Publié,,,CNV,X,,,2025-12-31\n",
        encoding="utf-8",
    )
    base = {c: "" for c in siqo.SIQO_COLUMNS}
    base.update(signe_fr="AOC", secteur="VITICOLE", lib_etat="Publié", categorie="Vin tranquille")
    sup = tmp_path / "sup.json"
    sup.write_text(json.dumps({"rows": [
        {**base, "_status": "added", "_source": "https://x", "_verified": "2026-10-03",
         "id_appellation": "p200", "appellation": "Beta", "id_denomination_geo": "p200",
         "denomination": "Beta", "produit": "Beta", "idproduit": "200"},
        {**base, "_status": "retained", "_source": "https://x", "_verified": "2026-10-03",
         "id_appellation": "1", "appellation": "Alpha", "id_denomination_geo": "11",
         "denomination": "Alpha Gamma", "produit": "Alpha Gamma rouge", "idproduit": "100"},
    ]}), encoding="utf-8")
    rows = siqo.siqo_rows(csv_path, sup)
    names = [(r["appellation"], r["denomination"]) for r in rows]
    assert ("Alpha", "Alpha") in names and ("Beta", "Beta") in names
    # the retained row's idproduit is back in the CSV → not doubled
    assert ("Alpha", "Alpha Gamma") not in names
    assert all(set(r) == set(siqo.SIQO_COLUMNS) for r in rows)


def test_supplement_colliding_with_another_appellation_raises(tmp_path: Path):
    csv_path = tmp_path / "siqo.csv"
    csv_path.write_text(
        ",".join(siqo.SIQO_COLUMNS) + "\n"
        + "AOC,AOP,1,Vin tranquille,2,Vins,VITICOLE,1,Alpha,10,Alpha,Alpha rouge,100,2,Publié,,,CNV,X,,,2025-12-31\n",
        encoding="utf-8",
    )
    base = {c: "" for c in siqo.SIQO_COLUMNS}
    sup = tmp_path / "sup.json"
    sup.write_text(json.dumps({"rows": [
        {**base, "_status": "added", "_source": "https://x", "_verified": "2026-10-03",
         "id_appellation": "1", "appellation": "Other", "idproduit": "999"},
    ]}), encoding="utf-8")
    with pytest.raises(ValueError, match="id_appellation 1"):
        siqo.siqo_rows(csv_path, sup)


def _stage02():
    spec = importlib.util.spec_from_file_location("s02", ROOT / "scripts" / "02_extract_cahiers.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_full_run_detects_a_denomination_the_export_dropped():
    s02 = _stage02()
    prior_index = {
        "1309": {"slug": "languedoc", "name": "Languedoc", "id_appellation": "257"},
        "1313": {"slug": "languedoc-montpeyroux", "name": "Languedoc Montpeyroux", "id_appellation": "257"},
        "app:1028": {"slug": "fiefs-vendeens", "name": "Fiefs Vendéens", "id_appellation": "1028"},
    }
    manifest = {"257": {"name": "Languedoc"}, "1028": {"name": "Fiefs Vendéens"}}
    denoms = {
        "257": [
            {"id_denomination_geo": "1309", "denomination": "Languedoc", "appellation": "Languedoc"},
        ],
        "1028": [
            {"id_denomination_geo": "2001", "denomination": "Fiefs Vendéens Brem", "appellation": "Fiefs Vendéens"},
        ],
    }
    dropped = s02.dropped_denominations(prior_index, manifest, denoms)
    assert [d["slug"] for d in dropped] == ["languedoc-montpeyroux"]
    # the DGC back in the referentiel → nothing to report
    denoms["257"].append(
        {"id_denomination_geo": "1313", "denomination": "Languedoc Montpeyroux", "appellation": "Languedoc"}
    )
    assert s02.dropped_denominations(prior_index, manifest, denoms) == []


def test_name_override_renames_the_row_and_its_parent_denomination(tmp_path: Path):
    csv_path = tmp_path / "siqo.csv"
    csv_path.write_text(
        ",".join(siqo.SIQO_COLUMNS) + "\n"
        + "AOC,IG,20,Eaux-de-vie de marc de raisin,3,Eaux-de-vie,VITICOLE,1091,Marc d'Alsace,2636,"
          "Marc d'Alsace,Marc d'Alsace Gewurztraminer ,13046,2,Publié,0,,CNV,ALSACE ET EST,,,2025-12-31\n"
        + "AOC,IG,20,Eaux-de-vie de marc de raisin,3,Eaux-de-vie,VITICOLE,1091,Marc d'Alsace,2999,"
          "Marc d'Alsace Vieux,Marc d'Alsace Vieux,13999,2,Publié,0,,CNV,ALSACE ET EST,,,2025-12-31\n",
        encoding="utf-8",
    )
    sup = tmp_path / "sup.json"
    sup.write_text(json.dumps({"rows": [], "name_overrides": {"1091": {
        "appellation": "Marc d'Alsace Gewurztraminer", "_reason": "r", "_source": "https://x",
        "_verified": "2026-10-04"}}}), encoding="utf-8")
    rows = siqo.siqo_rows(csv_path, sup)
    assert [(r["appellation"], r["denomination"]) for r in rows] == [
        ("Marc d'Alsace Gewurztraminer", "Marc d'Alsace Gewurztraminer"),
        # a DGC row keeps its own denomination
        ("Marc d'Alsace Gewurztraminer", "Marc d'Alsace Vieux"),
    ]


def test_name_override_reports_a_stale_pin():
    rows = [{"id_appellation": "1", "appellation": "Alpha", "denomination": "Alpha"}]
    stale = siqo.apply_name_overrides(rows, {
        "1": {"appellation": "Alpha"},     # the export caught up
        "2": {"appellation": "Beta"},      # no such row
    })
    assert stale == ["1", "2"]
    assert rows[0]["appellation"] == "Alpha"


def test_name_override_requires_reason_source_and_date(tmp_path: Path):
    sup = tmp_path / "sup.json"
    sup.write_text(json.dumps({"rows": [], "name_overrides": {"1": {"appellation": "X"}}}), encoding="utf-8")
    with pytest.raises(ValueError, match="name_overrides"):
        siqo.load_name_overrides(sup)


@pytest.mark.skipif(not siqo.SIQO_CSV.exists(), reason="raw/ not present")
def test_checked_in_name_override_is_live():
    overrides = siqo.load_name_overrides()
    assert overrides["1091"]["appellation"] == "Marc d'Alsace Gewurztraminer"
    date.fromisoformat(overrides["1091"]["_verified"])
    assert not siqo.apply_name_overrides(
        [r for r in siqo.siqo_rows(supplements_path=Path("/nonexistent"))], overrides,
    ), "the export row already carries the pinned name — drop the pin"
