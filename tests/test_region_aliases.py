"""The region level of the listing rule (scripts/_lib/region_aliases.py): an
appellation spanning several regions of its country's hierarchy is listed
under each. Pins the curated table (every quote is in the record's own text),
the two derivations (umbrella PGIs from their member table, FR from shared
aire communes) and the wiring of the sidebar, the card and the query core."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import region_aliases as ra  # noqa: E402

APP_JS = ROOT / "scripts" / "_lib" / "assets" / "app.js"
CORE = ROOT / "scripts" / "_lib" / "assets" / "query_core.mjs"


def _rec(slug, region, country="it", kind="DOP", **kw):
    return {"slug": slug, "name": kw.pop("name", slug), "country": country, "region": region, "kind": kind,
            "is_wine": True, "is_sub_denomination": False, "file_number": kw.pop("fn", ""),
            "geom_source": kw.pop("geom_source", ""), **kw}


def _fold(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def test_table_entries_are_complete_and_cited() -> None:
    table = ra.load_table()
    assert table["entries"], "empty table"
    for slug, e in table["entries"].items():
        assert e.get("country"), slug
        assert isinstance(e.get("regions"), list), slug
        assert e.get("reason") and e.get("verified"), slug
        assert e["regions"] == sorted(e["regions"]), f"{slug}: regions not sorted"
        if e["regions"]:
            assert e.get("evidence") or "member" in e["reason"].lower() or e["country"] == "de", slug
    for slug, by_region in table["rejected"].items():
        assert by_region and all(isinstance(v, str) and v for v in by_region.values()), slug


@pytest.mark.parametrize("slug", sorted(ra.load_table()["entries"]))
def test_every_quote_is_in_the_record(slug: str) -> None:
    for ev in ra.load_table()["entries"][slug].get("evidence") or []:
        path = ROOT / ev["file"]
        if not path.exists():
            pytest.skip(f"{ev['file']} not on disk (raw/ is not checked in)")
        node = json.loads(path.read_text(encoding="utf-8"))
        for key in ev["field"].split("."):
            node = (node or {}).get(key)
        assert _fold(ev["quote"]) in _fold(node or ""), f"{slug}: {ev['quote']!r} not in {ev['file']} {ev['field']}"


def test_member_table_umbrella_takes_its_members_regions() -> None:
    recs = [
        _rec("landwein-rhein", "Rheinland-Pfalz", "de", "IGP", fn="PGI-1", geom_source="region-pdo-union"),
        _rec("mosel", "Mosel", "de", fn="PDO-1"),
        _rec("pfalz", "Pfalz", "de", fn="PDO-2"),
        _rec("rheinhessen", "Rheinland-Pfalz", "de", fn="PDO-3"),
        # a PGI drawn another way keeps its members out
        _rec("other", "Bayern", "de", "IGP", fn="PGI-2", geom_source="gisco-commune-union"),
    ]
    tables = {"de": {"PGI-1": ("PDO-1", "PDO-2", "PDO-3"), "PGI-2": ("PDO-1",)}}
    assert ra.member_aliases(recs, tables) == {"landwein-rhein": ["Mosel", "Pfalz"]}


def test_fr_aire_rule_uses_bucket_cores_without_umbrellas() -> None:
    lang = {f"L{i}" for i in range(100)}
    rous = {f"R{i}" for i in range(20)}
    recs = [
        _rec("pays-d-oc", "LANGUEDOC", "fr", "IGP"),
        _rec("languedoc", "LANGUEDOC", "fr", "AOC"),
        _rec("faugeres", "LANGUEDOC", "fr", "AOC"),
        _rec("st-chinian", "LANGUEDOC", "fr", "AOC"),
        _rec("maury", "ROUSSILLON", "fr", "AOC"),
        _rec("collioure", "ROUSSILLON", "fr", "AOC"),
        _rec("fitou", "LANGUEDOC", "fr", "AOC"),
        _rec("rivesaltes", "ROUSSILLON", "fr", "AOC"),
        _rec("floc", "ARMAGNAC", "fr", "AOC"),
        _rec("gers", "SUD-OUEST", "fr", "IGP"),
    ]
    aires = {
        "pays-d-oc": lang | rous,
        # an umbrella (holds Faugères and Saint-Chinian): left out of LANGUEDOC's core
        "languedoc": lang | {"R0", "R1"},
        "faugeres": {f"L{i}" for i in range(10)},
        "st-chinian": {f"L{i}" for i in range(10, 30)},
        "maury": {f"R{i}" for i in range(10)},
        "collioure": {f"R{i}" for i in range(10, 20)},
        "fitou": {f"L{i}" for i in range(90, 100)},
        "rivesaltes": {f"R{i}" for i in range(20)} | {f"L{i}" for i in range(90, 100)},
        "floc": {f"G{i}" for i in range(50)},
        "gers": {f"G{i}" for i in range(50)},
    }
    out = ra.fr_aire_aliases(recs, aires.get)
    assert set(out["pays-d-oc"]) == {"ROUSSILLON"}
    assert out["rivesaltes"]["LANGUEDOC"]["via"] == ["fitou"]
    # two Roussillon communes in the Languedoc aire: under FR_MIN_SHARED
    assert "languedoc" not in out
    # ARMAGNAC is neither a target nor a source
    assert "gers" not in out and "floc" not in out


def test_curated_entry_overrides_and_suppresses() -> None:
    recs = [
        _rec("garda", "Lombardia"), _rec("soave", "Veneto"),
        _rec("bb", "Bayern", "de", "IGP", fn="PGI-1", geom_source="region-pdo-union"),
        _rec("baden", "Baden", "de", fn="PDO-1"),
        _rec("garda-sub", "Lombardia", is_sub_denomination=True),
    ]
    table = {"entries": {
        "garda": {"country": "it", "regions": ["Veneto", "Lombardia"]},
        "bb": {"country": "de", "regions": []},
        "garda-sub": {"country": "it", "regions": ["Veneto"]},
        "gone": {"country": "it", "regions": ["Veneto"]},
    }, "rejected": {}}
    out, warnings = ra.derive(recs, table=table, tables={"de": {"PGI-1": ("PDO-1",)}})
    # own region dropped, sorted; suppressed; a sub-denomination gets none
    assert out == {"garda": ["Veneto"]}
    assert any("gone" in w for w in warnings)


def test_alias_must_be_a_region_of_the_country() -> None:
    out, warnings = ra.derive([_rec("x", "Veneto")], table={"entries": {"x": {"country": "it", "regions": ["Atlantis"]}}, "rejected": {}}, tables={})
    assert out == {} and any("Atlantis" in w for w in warnings)


def test_sidebar_card_and_core_read_region_aliases() -> None:
    js = APP_JS.read_text(encoding="utf-8")
    tree = js[js.index("const COUNTRY_TREE"):js.index("function visibleSlugsInRegion")]
    assert "rec.region_aliases" in tree
    # sub-denominations stay in their own region: no inheritance of the parent's aliases
    assert "parent.region_aliases" not in tree
    # a record with no region of its own sits in its alias regions only
    assert "if (region || !regionAliases.length)" in tree
    assert "[r.region, ...(r.region_aliases || [])].filter(Boolean).map(regionLabel).join(', ')" in js
    core = CORE.read_text(encoding="utf-8")
    assert core.count("regionsOf(r)") >= 2
    from _lib.map_template import STARTUP_AOCS_FIELDS
    assert "region_aliases" in STARTUP_AOCS_FIELDS
