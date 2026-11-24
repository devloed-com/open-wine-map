"""The cross-check against INAO's delimitation-plan inventory and plans
(scripts/audit_plan_inventory.py, logic in scripts/_lib/fr/plan_inventory_audit.py)
on canned rows: binding, folding former communes, the six checks and their
buckets, and the WebDAV listing reader. No file, no network."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.fr import plan_inventory_audit as PIA  # noqa: E402
from _lib.fr import plans_portal as PP  # noqa: E402

# 51612 Blancs-Coteaux took 51001 (a former commune); 51002 is a commune of today
TODAY = {"51612", "51002", "51003", "51004", "51005"}
FORMER = {"51001": "51612"}


def canon(code: str) -> str:
    return code if code in TODAY else FORMER.get(code, code)


def row(app, insee, attendu="oui", plan="plan disponible", revision="non", signe="AOC", commune=""):
    return {"signe": signe, "appellation": app, "insee": insee, "commune": commune or insee,
            "attendu": attendu, "plan": plan, "revision": revision}


def inv(rows):
    return PIA.group_inventory(rows, canon)


def ctx(inv_app, **kw):
    base = dict(slug="x", name="X", is_dgc=False, geom_source="parcellaire", inv=inv_app,
                aire=set(), aire_own=True, cahier=set(), coverage=set())
    base.update(kw)
    return PIA.RecordContext(**base)


# ----------------------------------------------------------------- inventory
def test_rows_of_a_former_commune_fold_into_the_commune_of_today_and_any_oui_counts():
    got = inv([row("champagne", "51612", attendu="non", plan="Aucune parcelle classée"),
               row("champagne", "51001"), row("champagne", "51002", revision="oui")])
    app = got[("AOC", "champagne")]
    assert set(app.communes) == {"51612", "51002"}
    st = app.communes["51612"]
    assert st.raw == {"51612", "51001"} and st.oui and st.plan == PIA.PLAN_DISPO
    assert app.communes["51002"].revision and not st.revision


def test_the_sign_is_part_of_the_key():
    got = inv([row("calvados", "51002"), row("calvados", "51003", attendu="non", signe="IGP")])
    assert set(got) == {("AOC", "calvados"), ("IGP", "calvados")}


def test_identification_and_plan_states():
    got = inv([row("armagnac", "51002", attendu="identification parcellaire (non disponible)",
                   plan="Aucune parcelle classée"),
               row("x", "51003", plan="plan en cours d’élaboration")])
    assert got[("AOC", "armagnac")].communes["51002"].ident
    assert got[("AOC", "x")].communes["51003"].plan == PIA.PLAN_EN_COURS


# ----------------------------------------------------------------- binding
def _keys(*names, sign="AOC"):
    return [(sign, n) for n in names]


def test_binding_ladder():
    recs = [{"slug": "alsace", "name": "Alsace ou Vin d'Alsace", "kind": "AOC"},
            {"slug": "blagny", "name": "Blagny", "kind": "AOC"},
            {"slug": "meursault", "name": "Meursault", "kind": "AOC"},
            {"slug": "dom", "name": "Calvados Domfontais", "kind": "EDV"},
            {"slug": "liv", "name": "La Livinière", "kind": "AOC"},
            {"slug": "lorraine", "name": "Lorraine", "kind": "IGP"}]
    keys = _keys("alsace", "blagny ou blagny côte de beaune", "meursault", "calvados domfrontais",
                 "minervois-la livinière") + [("AOC", "lorraine")]
    near = lambda key, by: "calvadosdomfrontais" if key == "calvadosdomfontais" else None  # noqa: E731
    m = PIA.match_records(recs, keys, {"liv": {"inventory": "minervois-la livinière", "sign": "AOC"}}, near)
    via = {s: v[1] for s, v in m.by_slug.items()}
    assert via == {"alsace": "record-alias", "blagny": "inventory-alias", "meursault": "exact",
                   "dom": "near-exact", "liv": "pin"}
    (lor,) = m.unmatched_records
    assert lor["slug"] == "lorraine" and "an AOC of this name is" in lor["reason"]
    assert m.unmatched_inventory == [("AOC", "lorraine")]


def test_the_sign_of_a_cider_aoc_is_its_signe_fr():
    rec = {"slug": "domfront", "name": "Domfront", "kind": "IGP", "signe_fr": "AOC"}
    m = PIA.match_records([rec], [("AOC", "domfront")])
    assert m.by_slug == {"domfront": (("AOC", "domfront"), "exact")}


def test_two_records_claiming_one_appellation_keep_the_exact_one():
    recs = [{"slug": "parent", "name": "Calvados Domfontais", "kind": "EDV"},
            {"slug": "dgc", "name": "Calvados Domfrontais", "kind": "EDV"}]
    near = lambda key, by: "calvadosdomfrontais"  # noqa: E731
    m = PIA.match_records(recs, _keys("calvados domfrontais"), None, near)
    assert list(m.by_slug) == ["dgc"] and m.unmatched_records[0]["slug"] == "parent"


# ------------------------------------------------------------------ check 1
def test_check_1_parcels_missing_where_the_inventory_and_the_rows_agree():
    app = inv([row("x", "51002"), row("x", "51003"), row("x", "51004", plan="plan en cours d’élaboration")])
    c = ctx(app[("AOC", "x")], aire={"51002", "51003", "51004"}, coverage={"51002"},
            gap_audit_aire={"51002", "51003", "51004"},
            commune_plans={"51003": ("1999-10-24", "1999-10-24", 2)})
    got = {f.kind: f for f in PIA.check_parcellaire(c)}
    assert got["parcels-missing"].bucket == PIA.CONFLICT_OURS
    assert [r["insee"] for r in got["parcels-missing"].communes] == ["51003"]
    assert got["parcels-missing"].communes[0]["listed_by_gap_audit"]
    assert got["parcels-in-preparation"].bucket == PIA.REVISION


def test_check_1_without_a_plan_sheet_the_inventory_oui_settles_nothing():
    # the inventory's oui bleeds across products (the 20 Jurançon communes):
    # an empty or absent plan folder leaves the gap undetermined
    app = inv([row("x", "51002"), row("x", "51003")])[("AOC", "x")]
    c = ctx(app, aire={"51002", "51003"}, coverage={"51002"},
            commune_plans={"51003": ("", "", 0)})
    (f,) = [f for f in PIA.check_parcellaire(c) if f.check == "1a"]
    assert f.kind == "parcels-missing-no-plan" and f.bucket == PIA.UNDETERMINED


def test_check_1_a_plan_newer_than_the_cahier_is_a_revision():
    # Ladoix: a Magny-lès-Villers plan approved on 12 February 2026, a cahier of 2011
    app = inv([row("x", "51002")])[("AOC", "x")]
    c = ctx(app, aire={"51002"}, coverage={"51002", "51005"}, homologated_at="2011-11-15",
            commune_plans={"51005": ("2026-10-13", "2026-10-13", 1)})
    got = {f.kind: f for f in PIA.check_parcellaire(c)}
    assert got["parcels-newer-than-cahier"].bucket == PIA.REVISION
    assert "parcels-outside-aire" not in got


def test_check_1_a_name_the_zone_text_carries_is_in_the_area():
    # Ponteilla «en partie (sections A1, A2 …)»: the list reader drops it, the text names it
    app = inv([row("x", "51002")])[("AOC", "x")]
    c = ctx(app, aire={"51002"}, coverage={"51002", "51005"}, cahier_partial={"51005": "partial: …"})
    got = {f.kind: f.bucket for f in PIA.check_parcellaire(c)}
    assert got == {"parcels-inventory-non": PIA.CONFLICT_INVENTORY}


def test_check_1_a_pinned_gap_fill_is_not_a_finding():
    app = inv([row("x", "51002"), row("x", "51003")])[("AOC", "x")]
    c = ctx(app, aire={"51002", "51003"}, coverage={"51002"}, gap_fills={"51003"})
    assert not [f for f in PIA.check_parcellaire(c) if f.kind == "parcels-missing"]


def test_check_1_oui_outside_the_rows_is_ours_only_when_the_cahier_names_it():
    app = inv([row("x", "51002"), row("x", "51003"), row("x", "51004")])[("AOC", "x")]
    c = ctx(app, aire={"51002"}, coverage={"51002"}, cahier={"51002", "51003"})
    (f,) = [f for f in PIA.check_parcellaire(c) if f.kind == "parcels-missing-outside-aire"]
    assert f.bucket == PIA.CONFLICT_OURS and len(f.communes) == 2
    c = ctx(app, aire={"51002"}, coverage={"51002"})
    (f,) = [f for f in PIA.check_parcellaire(c) if f.kind == "parcels-missing-outside-aire"]
    assert f.bucket == PIA.CONFLICT_INVENTORY
    # a sub-denomination's cahier is its parent's: a name in it is no evidence
    c = ctx(app, is_dgc=True, cahier_own=False, aire={"51002"}, coverage={"51002"}, cahier={"51003"})
    (f,) = [f for f in PIA.check_parcellaire(c) if f.kind == "parcels-missing-outside-aire"]
    assert f.bucket == PIA.CONFLICT_INVENTORY


def test_check_1_parcels_in_a_commune_the_inventory_marks_non():
    app = inv([row("x", "51002"), row("x", "51003", attendu="non", plan="Aucune parcelle classée")])[("AOC", "x")]
    c = ctx(app, aire={"51002", "51003"}, coverage={"51002", "51003", "51005"})
    got = {f.kind: f for f in PIA.check_parcellaire(c)}
    assert got["parcels-inventory-non"].bucket == PIA.CONFLICT_INVENTORY
    assert [r["insee"] for r in got["parcels-inventory-non"].communes] == ["51003"]
    # 51005: neither INAO's rows nor the inventory put it in the appellation
    assert got["parcels-outside-aire"].bucket == PIA.CONFLICT_OURS


def test_check_1_only_for_parcellaire_records():
    app = inv([row("x", "51002")])[("AOC", "x")]
    assert PIA.check_parcellaire(ctx(app, geom_source="aires-csv", aire={"51002"})) == []


# ------------------------------------------------------------------ check 2
def test_check_2_card_line_against_the_inventory():
    app = inv([row("x", "51002"), row("x", "51003", attendu="non", plan="Aucune parcelle classée")])[("AOC", "x")]
    base = dict(geom_source="aires-csv", aire={"51002", "51003"}, drawn={"51002", "51003"})
    (f,) = [f for f in PIA.check_commune_union(ctx(app, own_parcel_area=True, **base)) if f.check == "2a"]
    assert f.kind == "card-says-no-parcel-area" and f.bucket == PIA.CONFLICT_OURS
    (f,) = [f for f in PIA.check_commune_union(ctx(app, **base)) if f.check == "2a"]
    assert f.bucket == PIA.UNDETERMINED
    (f,) = [f for f in PIA.check_commune_union(ctx(app, kind="IGP", **base)) if f.check == "2a"]
    assert f.bucket == PIA.CONFLICT_INVENTORY


def test_check_2_cassis_the_cahier_delimits_the_inventory_says_non():
    app = inv([row("cassis", "51002", attendu="non", plan="Aucune parcelle classée")])[("AOC", "cassis")]
    c = ctx(app, geom_source="aires-csv", aire={"51002"}, drawn={"51002"},
            card_parcel_area="unpublished", own_parcel_area=True)
    (f,) = PIA.check_commune_union(c)
    assert f.kind == "inventory-says-no-parcel-area" and f.bucket == PIA.CONFLICT_INVENTORY


def test_check_2_a_small_share_of_parcel_communes_is_a_champagne_candidate():
    app = inv([row("x", "51002")] + [row("x", c, attendu="non", plan="Aucune parcelle classée")
                                     for c in ("51003", "51004", "51005")])[("AOC", "x")]
    drawn = {"51002", "51003", "51004", "51005"}
    c = ctx(app, geom_source="aires-csv", aire=drawn, drawn=drawn,
            card_parcel_area="unpublished", own_parcel_area=True)
    (f,) = [f for f in PIA.check_commune_union(c) if f.check == "2b"]
    assert f.bucket == PIA.CONFLICT_OURS and f.evidence["share"] == 0.25
    # already drawn from the communes holding the parcel area: nothing to say
    c.parcel_area_table = "inao-plan-inventory"
    assert not [f for f in PIA.check_commune_union(c) if f.check == "2b"]


# ------------------------------------------------------------------ check 3
def _recoded(code):
    return False


def test_check_3_a_merger_is_not_a_difference():
    app = inv([row("x", "51001"), row("x", "51002")])[("AOC", "x")]
    c = ctx(app, geom_source="aires-csv", aire={"51612", "51002"}, cahier={"51612", "51002"})
    got, counts = PIA.check_aire(c, aire_raw={"51612", "51002"}, canon=canon, recoded=_recoded)
    assert got == [] and counts["merged"] == 2 and counts["different"] == 0


def test_check_3_who_is_right_follows_the_cahier():
    common = {f"52{n:03d}" for n in range(1, 21)}
    app = inv([row("x", c) for c in sorted(common | {"53001"})])[("AOC", "x")]
    aire = common | {"53002"}
    # the cahier lists the 20 and 53001: the rows lack 53001 (ours), and carry
    # 53002 that neither the inventory nor the cahier names (ours)
    c = ctx(app, geom_source="aires-csv", aire=aire, cahier=common | {"53001"})
    got = {f.kind: f.bucket for f in PIA.check_aire(c, aire_raw=aire, canon=canon, recoded=_recoded)[0]}
    assert got == {"aire-rows-lack": PIA.CONFLICT_OURS, "rows-extra": PIA.CONFLICT_OURS}
    # the cahier lists the rows: the inventory is the odd one out
    c = ctx(app, geom_source="aires-csv", aire=aire, cahier=aire)
    got = {f.kind: f.bucket for f in PIA.check_aire(c, aire_raw=aire, canon=canon, recoded=_recoded)[0]}
    assert got == {"inventory-extra": PIA.CONFLICT_INVENTORY, "inventory-lacks": PIA.CONFLICT_INVENTORY}
    # a cahier list that reads few of the rows says nothing about a missing name
    c = ctx(app, geom_source="aires-csv", aire=aire, cahier={"52001", "53001"})
    got = {f.kind: f.bucket for f in PIA.check_aire(c, aire_raw=aire, canon=canon, recoded=_recoded)[0]}
    assert got == {"aire-rows-lack": PIA.CONFLICT_OURS, "rows-extra": PIA.UNDETERMINED}
    # no cahier list: nothing settles it
    c = ctx(app, geom_source="aires-csv", aire=aire)
    got = {f.bucket for f in PIA.check_aire(c, aire_raw=aire, canon=canon, recoded=_recoded)[0]}
    assert got == {PIA.UNDETERMINED}


def test_check_3_a_name_another_product_shares_settles_nothing():
    # Valençay: the wine AOC and the cheese AOC, one name, one sign in the inventory
    app = inv([row("valençay", c) for c in ("51002", "51003", "51004", "51005")])[("AOC", "valençay")]
    c = ctx(app, geom_source="aires-csv", aire={"51002"}, cahier={"51002"}, name_shared=2)
    (f,), _ = PIA.check_aire(c, aire_raw={"51002"}, canon=canon, recoded=_recoded)
    assert f.kind == "inventory-name-shared" and f.bucket == PIA.UNDETERMINED


def test_check_3_needs_rows_of_the_records_own():
    app = inv([row("x", "51002")])[("AOC", "x")]
    c = ctx(app, is_dgc=True, aire_own=False, aire={"51003"})
    assert PIA.check_aire(c, aire_raw={"51003"}, canon=canon, recoded=_recoded) == ([], {})


# --------------------------------------------------------------- checks 4–6
def test_check_4_plans_against_the_inventory_are_internal():
    app = inv([row("x", "51002"), row("x", "51003")])[("AOC", "x")]
    c = ctx(app, folders={"51002": "A", "51004": "D"}, folder="AOC_X")
    got = {f.kind: f for f in PIA.check_plans(c)}
    assert {f.bucket for f in got.values()} == {PIA.INTERNAL}
    assert [r["insee"] for r in got["plan-disponible-no-folder"].communes] == ["51003"]
    assert [r["insee"] for r in got["folder-not-plan-disponible"].communes] == ["51004"]
    assert PIA.check_plans(ctx(app)) == []


def test_check_5_revision_plan_age_and_dropped_rows():
    app = inv([row("x", "51002", revision="oui"), row("x", "51003")])[("AOC", "x")]
    c = ctx(app, coverage={"51002"}, coverage_old={"51002", "51003", "51004"},
            homologated_at="2024-03-01", plan_dates=("2009-07-30", "2009-08-04"))
    got = {f.kind: f for f in PIA.check_dates(c)}
    assert got["revision-under-way"].bucket == PIA.REVISION
    assert got["plan-older-than-cahier"].bucket == PIA.REVISION
    dropped = got["parcel-rows-dropped"]
    assert dropped.bucket == PIA.CONFLICT_OURS and {r["insee"] for r in dropped.communes} == {"51003", "51004"}


def test_check_6_a_sub_denomination_with_its_own_plans_drawn_coarser():
    app = inv([row("x cru", "51002")])[("AOC", "x cru")]
    c = ctx(app, is_dgc=True, geom_source="parent-appellation", drawn={"51002", "51003"},
            folders={"51002": "A"}, folder="AOC_X_CRU")
    (f,) = PIA.check_subdenomination(c)
    assert f.kind == "precision-candidate" and f.bucket == PIA.UNDETERMINED
    assert PIA.check_subdenomination(ctx(app, is_dgc=True, geom_source="parcellaire-dgc")) == []


def test_check_6_an_override_lacking_a_named_commune_is_ours():
    # Champagne grand cru: Oger (Blancs-Coteaux since 2018) is in the list,
    # the override drew Le Mesnil-sur-Oger for it
    app = inv([row("champagne grand cru", "51612"), row("champagne grand cru", "51002")])[
        ("AOC", "champagne grand cru")]
    c = ctx(app, is_dgc=True, cahier_own=False, geom_source="dgc-village-override", drawn={"51002"},
            cahier_partial={"51612": "named by its former commune Oger (51411)"})
    got = {f.kind: f for f in PIA.check_subdenomination(c)}
    assert got["override-lacks-commune"].bucket == PIA.CONFLICT_OURS
    c = ctx(app, is_dgc=True, cahier_own=False, geom_source="dgc-village-override", drawn={"51002"})
    assert {f.kind: f for f in PIA.check_subdenomination(c)}["override-lacks-commune"].bucket == PIA.UNDETERMINED


# ------------------------------------------------------------------- portal
_LISTING = """<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:"><d:response><d:href>/public.php/webdav/AIRE_PARCELLAIRE/par_appellation/AOC_CHAMPAGNE/</d:href>
<d:propstat><d:prop><d:getlastmodified>Fri, 24 Mar 2023 10:00:00 GMT</d:getlastmodified><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat></d:response>
<d:response><d:href>/public.php/webdav/AIRE_PARCELLAIRE/par_appellation/AOC_CHAMPAGNE/02042_AZY-SUR-MARNE/</d:href>
<d:propstat><d:prop><d:getlastmodified>Fri, 24 Mar 2023 10:00:00 GMT</d:getlastmodified><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat></d:response>
<d:response><d:href>/public.php/webdav/AIRE_PARCELLAIRE/par_appellation/AOC_CHAMPAGNE/02042-0A05_AZY-SUR-MARNE_AOC_0055_DF.tif</d:href>
<d:propstat><d:prop><d:getlastmodified>Tue, 04 Aug 2009 08:00:00 GMT</d:getlastmodified><d:resourcetype/><d:getcontentlength>369736</d:getcontentlength></d:prop></d:propstat></d:response>
</d:multistatus>"""


def test_portal_listing_reader():
    got = PP.parse_multistatus(_LISTING, "AIRE_PARCELLAIRE/par_appellation/AOC_CHAMPAGNE/")
    assert [(e.name, e.is_dir, e.modified) for e in got] == [
        ("02042-0A05_AZY-SUR-MARNE_AOC_0055_DF.tif", False, "2009-08-04"),
        ("02042_AZY-SUR-MARNE", True, "2023-03-24")]
    assert PP.commune_dir("02042_AZY-SUR-MARNE") == ("02042", "AZY-SUR-MARNE")
    assert PP.commune_dir("2A004_AJACCIO") == ("2A004", "AJACCIO")
    assert PP.denom_of("02042-0A05_AZY-SUR-MARNE_AOC_0055_DF.tif") == "55"
    assert PP.denom_of("02042_AZY-SUR-MARNE_AOC_0055_TA_DF.tif") == "55"
    assert PP.folder_key("AOC_VOSNE-ROMANEE_PREMIER_CRU_AUX_BRULEES") == "vosneromaneepremiercruauxbrulees"


def test_a_maintenance_page_is_no_listing_and_is_never_cached(tmp_path):
    page = "<!DOCTYPE html><html><head><title>Site en maintenance</title></head></html>"
    with pytest.raises(PP.PortalUnavailable):
        PP.parse_multistatus(page, "x/")

    class Resp:
        status_code = 207
        text = page

    class Session:
        def request(self, *a, **k):
            return Resp()

    portal = PP.Portal(cache_dir=tmp_path, session=Session(), delay=0)
    with pytest.raises(PP.PortalUnavailable):
        portal.list("x/")
    assert list(tmp_path.iterdir()) == []


def test_offline_portal_reads_the_cache_only(tmp_path):
    class Resp:
        status_code = 207
        text = _LISTING

    class Session:
        calls = 0

        def request(self, *a, **k):
            Session.calls += 1
            return Resp()

    path = "AIRE_PARCELLAIRE/par_appellation/AOC_CHAMPAGNE/"
    PP.Portal(cache_dir=tmp_path, session=Session(), delay=0).list(path)
    offline = PP.Portal(cache_dir=tmp_path, offline=True, session=Session(), delay=0)
    assert [e.name for e in offline.list(path)][1] == "02042_AZY-SUR-MARNE"
    assert offline.list("never/listed/") is None and Session.calls == 1
