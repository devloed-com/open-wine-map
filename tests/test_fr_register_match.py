"""Guards for the FR SIQO → eAmbrosia register name resolver.

The resolver's failure mode is a *wrong* bind — attaching another
appellation's cahier des charges — which is worse than a gap, so the tests
below pin the three refusals (cross-product-type, ambiguity, collision)
alongside the synonym folds the register actually needs.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.fr import register_match as rm  # noqa: E402


def _row(file_number, name, product_type="Wine", status="Registered", country="fr"):
    return {
        "id": abs(hash(file_number)) % 100000,
        "fileName": file_number,
        "protectedName": name,
        "countryId": country,
        "qualityProductType": product_type,
        "geographicalIndicatorTypeCode": file_number.split("-")[0],
        "status": status,
        "showInRegister": True,
    }


def _app(id_app, name, categorie="Vin tranquille"):
    return {"id_appellation": id_app, "name": name, "categorie": categorie}


def test_register_keys_split_on_slash_synonyms() -> None:
    keys = rm.register_keys("Bourg / Côtes de Bourg / Bourgeais")
    assert "cotesdebourg" in keys
    assert "bourgeais" in keys


def test_siqo_alias_matches_register_slash_alias() -> None:
    rows = [_row("PDO-FR-A0828", "Bourg / Côtes de Bourg / Bourgeais")]
    resolved, unresolved = rm.resolve_all(
        [_app("1", "Côtes de Bourg, Bourg et Bourgeais")], rows, overrides={}
    )
    assert not unresolved
    assert resolved["1"].file_number == "PDO-FR-A0828"
    assert resolved["1"].matched_via == "alias"


def test_product_type_partition_keeps_wine_and_spirit_apart() -> None:
    """'Calvados' is both a Normandy IGP wine and an eau-de-vie PDO."""
    rows = [
        _row("PGI-FR-A1222", "Calvados", "Wine"),
        _row("PGI-FR-02033", "Calvados", "Spirit drink"),
    ]
    resolved, unresolved = rm.resolve_all(
        [
            _app("1", "Calvados", "Vin tranquille"),
            _app("2", "Calvados", "Eaux-de-vie de cidre et de poiré"),
        ],
        rows,
        overrides={},
    )
    assert not unresolved
    assert resolved["1"].file_number == "PGI-FR-A1222"
    assert resolved["2"].file_number == "PGI-FR-02033"


def test_unmapped_categorie_refuses_when_partitions_disagree() -> None:
    """With no categorie the resolver searches every partition, so a name
    claimed by two product types has to fall to the curator."""
    rows = [
        _row("PGI-FR-A1222", "Calvados", "Wine"),
        _row("PGI-FR-02033", "Calvados", "Spirit drink"),
    ]
    resolved, unresolved = rm.resolve_all(
        [_app("1", "Calvados", categorie="")], rows, overrides={}
    )
    assert not resolved
    assert unresolved[0]["reason"] == "ambiguous"


def test_unmapped_categorie_resolves_when_unique_across_partitions() -> None:
    rows = [_row("PDO-FR-A0201", "Côte Roannaise", "Wine")]
    resolved, unresolved = rm.resolve_all(
        [_app("1", "Côte roannaise", categorie="")], rows, overrides={}
    )
    assert not unresolved
    assert resolved["1"].file_number == "PDO-FR-A0201"
    assert resolved["1"].partition == "any"


def test_cancelled_row_loses_to_the_registered_one() -> None:
    rows = [
        _row("PDO-FR-0001", "Bandol", status="Cancelled"),
        _row("PDO-FR-A0002", "Bandol", status="Registered"),
    ]
    resolved, _ = rm.resolve_all([_app("1", "Bandol")], rows, overrides={})
    assert resolved["1"].file_number == "PDO-FR-A0002"


def test_two_appellations_claiming_one_gi_are_both_refused() -> None:
    rows = [_row("PDO-FR-A0100", "Bourgogne")]
    resolved, unresolved = rm.resolve_all(
        [_app("1", "Bourgogne"), _app("2", "Bourgogne ou Bourgogne")], rows, overrides={}
    )
    assert not resolved
    assert {u["reason"] for u in unresolved} == {"collision"}


def test_short_alias_fragment_cannot_bind() -> None:
    """A 3-letter alias remnant is too generic to attach a cahier on."""
    rows = [_row("PDO-FR-A0300", "Vin")]
    _, unresolved = rm.resolve_all([_app("1", "Quelque chose ou Vin")], rows, overrides={})
    assert unresolved[0]["reason"] == "no-name-match"


def test_no_name_match_goes_to_the_queue_not_a_fuzzy_bind() -> None:
    rows = [_row("PDO-FR-A0400", "Chablis Grand Cru")]
    resolved, unresolved = rm.resolve_all([_app("1", "Chablis")], rows, overrides={})
    assert not resolved
    assert unresolved[0]["reason"] == "no-name-match"


def test_override_pins_a_file_number_the_matcher_cannot_reach() -> None:
    rows = [_row("PGI-FR-01837", "Calvados Domfrontais", "Spirit drink")]
    resolved, unresolved = rm.resolve_all(
        [_app("1", "Calvados Domfontais", "Eaux-de-vie de cidre et de poiré")],
        rows,
        overrides={"1": {"file_number": "PGI-FR-01837"}},
    )
    assert not unresolved
    assert resolved["1"].matched_via == "override"


def test_empty_override_records_a_verified_absence() -> None:
    resolved, unresolved = rm.resolve_all(
        [_app("1", "Nowhere")], [], overrides={"1": {"file_number": ""}}
    )
    assert not resolved and not unresolved


def test_override_pointing_at_an_unknown_gi_is_reported() -> None:
    _, unresolved = rm.resolve_all(
        [_app("1", "Nowhere")], [], overrides={"1": {"file_number": "PDO-FR-XXXX"}}
    )
    assert unresolved[0]["reason"] == "override-file-number-not-in-register"


def test_cross_border_rows_are_french_rows() -> None:
    rows = rm.fr_rows([
        _row("PDO-ES-FR-02309", "Euskal Sagardoa", "Food", country="es,fr"),
        _row("PDO-ES-0001", "Rioja", "Wine", country="es"),
    ])
    assert [r["fileName"] for r in rows] == ["PDO-ES-FR-02309"]


def test_shipped_overrides_are_well_formed() -> None:
    for id_app, pin in rm.load_overrides().items():
        assert id_app.isdigit(), id_app
        assert "file_number" in pin and "note" in pin, id_app
        if pin["file_number"]:
            assert pin["file_number"].startswith(("PDO-", "PGI-")), id_app


def test_cancelled_gi_is_refused_not_bound() -> None:
    """A GI the Commission struck off cannot be an appellation's current
    specification; binding to one has to be a deliberate curator pin."""
    rows = [_row("PGI-FR-A1203", "Cité de Carcassonne", status="Cancelled")]
    resolved, unresolved = rm.resolve_all(
        [_app("1", "Cité de Carcassonne")], rows, overrides={}
    )
    assert not resolved
    assert unresolved[0]["reason"] == "withdrawn-registration"


def test_pending_registration_still_binds() -> None:
    rows = [_row("PDO-FR-03288", "Grés de Montpellier", status="Applied")]
    resolved, unresolved = rm.resolve_all(
        [_app("1", "Grés de Montpellier")], rows, overrides={}
    )
    assert not unresolved
    assert resolved["1"].status == "Applied"


def test_populated_but_unknown_categorie_refuses_rather_than_widening() -> None:
    rows = [_row("PGI-FR-99999", "Somewhere", "Spirit drink")]
    resolved, unresolved = rm.resolve_all(
        [_app("1", "Somewhere", categorie="Boisson inconnue")], rows, overrides={}
    )
    assert not resolved
    assert unresolved[0]["reason"] == "unmapped-categorie"


def test_every_siqo_categorie_in_the_corpus_is_mapped() -> None:
    """A new SIQO categorie must be added to the table, not silently widened
    to every product-type partition."""
    import csv
    from pathlib import Path

    siqo = Path(__file__).resolve().parents[1] / "raw" / "inao" / "siqo-referentiel.csv"
    if not siqo.exists():
        return
    with open(siqo, encoding="utf-8-sig", newline="") as f:
        seen = {
            row["categorie"].strip()
            for row in csv.DictReader(f)
            if row["secteur"].strip() == "VITICOLE"
            and row["lib_etat"].strip() == "Publié"
            and (row["signe_fr"].strip() or row["signe_ue"].strip()) in {"AOC", "AOP", "IGP"}
        }
    missing = sorted(c for c in seen if c and c not in rm.CATEGORIE_PRODUCT_TYPE)
    assert not missing, f"unmapped SIQO categorie values: {missing}"


def test_a_pin_survives_a_collision_and_the_auto_match_loses() -> None:
    rows = [_row("PDO-FR-A0100", "Bourgogne")]
    resolved, unresolved = rm.resolve_all(
        [_app("1", "Bourgogne"), _app("2", "Bourgogne")],
        rows,
        overrides={"2": {"file_number": "PDO-FR-A0100"}},
    )
    assert list(resolved) == ["2"]
    assert unresolved[0]["reason"] == "collision-with-pin"
