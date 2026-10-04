"""Regression tests for the detached-part detector in
scripts/audit_geometry_outliers.py.

The detector is the guard against a resolver drawing an appellation
somewhere it does not belong. It had a hole: the "main body" was
assembled by AREA RANK — the largest parts until they held 95% of the
total — and any part in that set was exempt from the test. A large
detached part could therefore be absorbed into the body and never
checked. Saale-Unstrut's Werderaner Wachtelberg (117 km², 87 km from the
main Sachsen-Anhalt body) was exactly the part that tipped the
accumulator past 95%, so the audit reported nothing for it and its own
whitelist entry read as stale — the detector had silently stopped
covering the case its override documents.

Two neighbours of the audits ride along: a false entry in the overlap
whitelist, and the omnisearch pick that has to reveal a record the
IGP / spirits gates hide.

The last section pins the 2026-09-24 review of the Greek findings in
`geometry_outlier_overrides.json`: each clip is re-applied to the source
polygon it targets (Bétard for the Patras PDOs, the GISCO NUTS union for
the island PGIs) and every dropped part must sit in the GISCO community
its reason cites — a clip written from memory would not survive that.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from shapely.geometry import MultiPolygon, box
from shapely.ops import transform as shp_transform
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")

sys.path.insert(0, str(ROOT / "scripts"))

from _lib.geometry_overrides import (  # noqa: E402
    GeometryOverrides,
    _parts,
    _to_3035,
    part_signature,
)


@pytest.fixture(scope="module")
def audit():
    spec = importlib.util.spec_from_file_location(
        "owm_audit_outliers", ROOT / "scripts" / "audit_geometry_outliers.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sq(x, y, side_m):
    """A square in EPSG:3035 metres."""
    return box(x, y, x + side_m, y + side_m)


def test_large_far_part_is_not_absorbed_into_the_body(audit):
    """The Saale-Unstrut shape: one dominant body, a few mid-size parts
    beside it, and one large part far away that ranks high enough to be
    swallowed by an area-rank body."""
    main = _sq(0, 0, 48_000)                  # ~2300 km²
    near = [_sq(60_000, 0, 16_000),           # ~256 km², 12 km away
            _sq(0, 60_000, 15_500),           # ~240 km²
            _sq(-30_000, 0, 12_500)]          # ~156 km²
    far = _sq(400_000, 400_000, 10_800)       # ~117 km², far from everything
    geom = MultiPolygon([p for p in [main, *near, far]])

    outliers = audit.detect_outliers(geom, gap_km=25, area_frac=0.20)
    assert len(outliers) == 1
    assert outliers[0].area_km2 == pytest.approx(117, abs=5)
    assert outliers[0].gap_km > 25


def test_a_fragmented_cloud_stays_one_body(audit):
    """A parcellaire union is thousands of parcels, each close to its
    neighbours; the chain must not be read as a string of outliers."""
    parts = [_sq(i * 10_000, 0, 6_000) for i in range(40)]
    geom = MultiPolygon(parts)
    assert audit.detect_outliers(geom, gap_km=25, area_frac=0.20) == []


def test_a_part_too_large_to_be_an_outlier_is_still_exempt(audit):
    """`area_frac` is what separates a mis-attributed fragment from a
    genuinely two-part appellation; the isolation rule must not override
    it."""
    a = _sq(0, 0, 30_000)
    b = _sq(400_000, 0, 30_000)   # same size — a real second lobe, not a sliver
    assert audit.detect_outliers(MultiPolygon([a, b]), gap_km=25, area_frac=0.20) == []


def test_an_isolated_main_part_still_anchors_the_body(audit):
    """Los Palacios y Villafranca: the Sevilla body has no other part within
    `gap_km`, and the homonym leak for Villafranca is two touching parts in
    Navarra. A body that skips isolated parts took the Navarra pair as the
    body, and the leak went unreported."""
    main = _sq(0, 0, 34_700)                  # ~1204 km², nothing else near it
    leak = [_sq(600_000, 600_000, 6_800),     # ~46 km²
            _sq(606_800, 600_000, 300)]       # ~0.1 km², touching it
    outliers = audit.detect_outliers(MultiPolygon([main, *leak]), gap_km=25, area_frac=0.20)
    assert sorted(round(o.area_km2) for o in outliers) == [0, 46]
    assert all(o.gap_km > 25 for o in outliers)



def test_the_body_is_the_largest_cluster_not_the_cluster_of_the_largest_part(audit):
    """Crémant de Bourgogne: 85% of the area is thousands of small parcels
    in one lobe, but the single largest parcel is in the detached Yonne
    lobe. Seeding the body with that parcel would report the whole main
    lobe; the Yonne lobe is the detached one."""
    main = [_sq(i * 3_000, j * 3_000, 1_500) for i in range(20) for j in range(20)]  # 900 km²
    yonne = [_sq(200_000, 0, 9_000), _sq(210_000, 0, 5_000)]                         # 106 km²
    outliers = audit.detect_outliers(MultiPolygon(main + yonne), gap_km=25, area_frac=0.20)
    assert sorted(round(o.area_km2) for o in outliers) == [25, 81]


def test_a_fragmented_second_lobe_is_exempt_like_a_single_one(audit):
    """`area_frac` applies to the detached cluster, not to each of its
    parcels: a lobe holding a third of the area is a genuine second lobe
    whether it is drawn as one polygon or as a hundred parcels."""
    main = _sq(0, 0, 40_000)                                                 # 1600 km²
    lobe = [_sq(300_000 + i * 3_000, j * 3_000, 2_000)
            for i in range(10) for j in range(20)]                             # 800 km²
    assert audit.detect_outliers(MultiPolygon([main, *lobe]), gap_km=25, area_frac=0.20) == []

# ---- geometry_overlap_overrides.json -------------------------------------------


def test_sithonia_overlap_with_ayio_oros_is_not_whitelisted():
    """ΠΓΕ Σιθωνία delimits 'την χερσόνησο της Σιθωνίας στο Νομό Χαλκιδικής'
    (ΥΑ 359490/1996), the middle prong. Its polygon is the whole NUTS unit
    EL527, and that is what covers Ouranoupoli on the Athos prong: a
    precision artefact to fix in the resolver, not nesting to accept."""
    data = json.loads((ROOT / "scripts" / "_lib" / "geometry_overlap_overrides.json")
                      .read_text(encoding="utf-8"))
    pairs = {frozenset(e["pair"]) for e in data["whitelist"]}
    assert frozenset({"ayio-oros", "sithonia"}) not in pairs


# ---- app.js: picking a hidden record from the omnisearch -----------------------


def _js_function(src: str, name: str) -> str:
    """The source of `function name(...) {...}` in app.js ('' when absent),
    brace-matched past string literals and line comments."""
    m = re.search(r"\bfunction " + re.escape(name) + r"\(", src)
    if not m:
        return ""
    j, depth, quote = src.index("{", m.end()), 0, None
    while j < len(src):
        c = src[j]
        if quote:
            if c == "\\":
                j += 2
                continue
            if c == quote:
                quote = None
        elif c in "'\"`":
            quote = c
        elif src.startswith("//", j):
            j = src.index("\n", j)
            continue
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[m.start():j + 1]
        j += 1
    raise AssertionError(f"unbalanced braces in app.js function {name}")


def _pick_from_omnisearch(app_js: str, rec: dict) -> dict:
    """Run app.js's own pickOmni on one record from the default state (simple
    mode, IGPs and spirits off) and return the gates' state afterwards."""
    fns = "\n".join(_js_function(app_js, n)
                    for n in ("spiritsVisible", "hiddenGates", "hiddenBy", "pickOmni",
                              "openAppellation"))
    prog = f"""
let showIgp = false, showSpirits = false, viewMode = 'simple';
const LANG = 'en', LOD = {{ overview_max_zoom: 11.9 }}, map = {{}};
const AOCS = {{ rec: {json.dumps(rec)} }};
const events = [];
const track = (name, props) => events.push([name, props.kind || props.mode || props.slug]);
const localStorage = {{ setItem: () => {{}} }};
const document = {{ getElementById: () => null }};
let lastPanelTrigger = null, lastStackKey = null, stackFocusIndex = 0;
const applyFilter = () => {{}}, applyMode = () => {{}}, buildAppellationFacet = () => {{}};
const renderPanelStack = () => {{}}, fitBbox = () => null;
{fns}
pickOmni('appellation', 'rec');
console.log(JSON.stringify({{ hidden: hiddenBy(AOCS.rec), showIgp, showSpirits, viewMode,
  events }}));
"""
    out = subprocess.run([NODE, "-"], input=prog, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)



@pytest.mark.skipif(NODE is None, reason="node not installed")
@pytest.mark.parametrize("rec, igp, spirits", [
    ({"kind": "IGP", "is_wine": False}, True, True),    # cidre de Bretagne / de Normandie
    ({"kind": "IGP", "is_wine": True}, True, False),
    ({"kind": "AOC", "is_wine": False}, False, True),
    ({"kind": "AOC", "is_wine": True}, False, False),
])
def test_picking_a_hidden_record_turns_on_every_gate_that_hides_it(rec, igp, spirits):
    """A cider PGI is behind the IGP toggle AND the spirits gate. Picking it
    from the omnisearch used to turn on only the first, so its panel opened
    while the map and the tree still hid it. Only the gates that actually
    hide a record are touched."""
    app_js = (ROOT / "scripts" / "_lib" / "assets" / "app.js").read_text(encoding="utf-8")
    after = _pick_from_omnisearch(app_js, rec)
    assert after["hidden"] == ""
    assert after["showIgp"] is igp
    assert (after["viewMode"] == "advanced" and after["showSpirits"]) is spirits
    toggled = [e[1] for e in after["events"] if e[0] == "Kind Toggled"]
    assert toggled == [k for k, on in (("igp", igp), ("spirits", spirits)) if on]


# ---- geometry_outlier_overrides.json: the 2026-09-24 Greek review ---------------

# Point at another copy of the overrides file (e.g. the pre-review one) to see
# these tests fail: OWM_OUTLIER_OVERRIDES=/path/to/before.json pytest …
OVERRIDES = Path(os.environ.get("OWM_OUTLIER_OVERRIDES")
                 or ROOT / "scripts" / "_lib" / "geometry_outlier_overrides.json")
BETARD = ROOT / "raw" / "es" / "figshare" / "EU_PDO.gpkg"
GISCO_LAU = ROOT / "raw" / "es" / "gisco" / "LAU_RG_01M_2024_3035.shp.zip"
NUTS3 = ROOT / "raw" / "gr" / "nuts" / "NUTS_RG_03M_2024_4326_LEVL_3.geojson"
NUTS2 = ROOT / "raw" / "nl" / "nuts" / "NUTS_RG_03M_2024_4326_LEVL_2.geojson"
_GISCO_ID_RE = re.compile(r"\bEL_\d{8}\b")

# slug → (source layer, NUTS_NAME the resolver unions, parts the clip must drop)
# slug → (source layer, NUTS_NAME the resolver unions, parts the clip must
# drop, the least gap in km between the dropped cluster and the kept geometry)
_ISLAND_CLIPS = {
    "zakynthos": (NUTS3, "Ζάκυνθος", 1, 25),        # Strofades
    "verdea-zakyntou": (NUTS3, "Ζάκυνθος", 1, 25),  # Strofades
    "kriti": (NUTS2, "Κρήτη", 2, 25),               # Gavdos + Gavdopoula
    # (Skyros is no longer clipped for any retsina: ΠΓΕ Εύβοια keeps it —
    # the regional unit includes it — and Ρετσίνα Ευβοίας / Χαλκίδας /
    # Καρύστου are drawn from LAU unions since 2026-09-24: the island's
    # units, the former province of Chalkida, and the former province of
    # Karystia, which held Skyros — all whitelisted or simply absent.)
}
# slug → parts the clip must drop from the Bétard polygon
_PATRAS_CLIPS = {
    "moschatos-riou-patras": 2,   # Δ.Κ. Πλατάνου of Aigialeia, in two pieces
    "moschato-patron": 1,         # Δ.Κ. Αγίου Νικολάου of Kalavryta
    "mavrodafni-patron": 5,       # both of those, plus two Ilia homonyms
}


@pytest.fixture(scope="module")
def overrides():
    return GeometryOverrides(OVERRIDES)


def _dropped_parts(geom_4326, dropped, tol_km):
    """The 3035 parts of `geom_4326` that the clip's ledger says it dropped."""
    parts = _parts(shp_transform(_to_3035, geom_4326))
    out = []
    for d in dropped:
        lat, lon = d["centroid_latlon"]
        best = min(parts, key=lambda p: (part_signature(p)[0] - lat) ** 2
                   + (part_signature(p)[1] - lon) ** 2)
        blat, blon, _ = part_signature(best)
        assert abs(blat - lat) < tol_km / 100 and abs(blon - lon) < tol_km / 100
        out.append(best)
    return out


def _lau_polygons(gisco_ids):
    import geopandas as gpd
    ids = ", ".join(f"'{i}'" for i in sorted(gisco_ids))
    gdf = gpd.read_file(GISCO_LAU, where=f"GISCO_ID IN ({ids})")
    return dict(zip(gdf["GISCO_ID"], gdf.geometry))


def _assert_parts_sit_in_cited_communities(geom_4326, spec, res):
    """Every dropped part lies (> 50 %) in a GISCO community its reason cites."""
    parts = _dropped_parts(geom_4326, res.dropped, spec.get("match_tol_km", 1.5))
    cited = [_GISCO_ID_RE.findall(d["reason"]) for d in spec["drop"]]
    assert all(cited), "every clip reason must cite the GISCO LAU id of the part"
    if not GISCO_LAU.exists():
        pytest.skip("GISCO LAU zip not fetched")
    lau = _lau_polygons({i for ids in cited for i in ids})
    for part, ids in zip(parts, cited):
        share = max(part.intersection(lau[i]).area / part.area for i in ids if i in lau)
        assert share > 0.5, (ids, share)


def test_welsh_wines_are_not_whitelisted(overrides):
    """Under the proximity detector the Anglesey islets chain to the Welsh
    mainland (The Skerries → Anglesey), so nothing is detached and the two
    entries matched nothing: a whitelist entry that covers no finding is
    noise that would silently accept a future real one."""
    assert "welsh-wine" not in overrides.whitelist
    assert "welsh-regional-wine" not in overrides.whitelist


def test_thraki_whitelist_is_samothrace_inside_evros(overrides, audit):
    """ΠΓΕ Θράκη is drawn as EL511 + EL512 + EL513; its one detached part is
    the island of Samothrace, which lies in EL511 Έβρος — legitimate, since
    the spec delimits 'όλες τις περιοχές της Θράκης' and cites the unit."""
    reason = overrides.whitelist.get("thraki", "")
    assert "Σαμοθράκ" in reason and "EL511" in reason
    if not NUTS3.exists():
        pytest.skip("GISCO NUTS-3 layer not fetched")
    import geopandas as gpd
    n3 = gpd.read_file(NUTS3)
    units = n3[n3["NUTS_ID"].isin(["EL511", "EL512", "EL513"])]
    outliers = audit.detect_outliers(
        shp_transform(_to_3035, unary_union(list(units.geometry))), gap_km=25, area_frac=0.20)
    assert len(outliers) == 1
    (evros,) = units[units["NUTS_ID"] == "EL511"].geometry
    from shapely.geometry import Point
    assert evros.contains(Point(outliers[0].rep_lon, outliers[0].rep_lat))
    assert outliers[0].area_km2 == pytest.approx(181, abs=3)


@pytest.mark.skipif(not BETARD.exists(), reason="Bétard EU_PDO.gpkg not fetched")
@pytest.mark.parametrize("slug, n_drop", sorted(_PATRAS_CLIPS.items()))
def test_patras_clips_drop_exactly_the_homonym_parts(overrides, audit, slug, n_drop):
    """Bétard drew three Patras PDOs with parts that are homonyms of the
    communities their specs name (Πλατάνι of Rio → Δ.Κ. Πλατάνου of
    Aigialeia, Άγιος Νικόλαος of Larissos → the Kalavryta one, …). Each clip
    must match exactly one Bétard part, keep the rest, stay inactive when
    another resolver won the record, and every dropped part must sit in the
    community the reason cites."""
    spec = overrides.clip_specs.get(slug)
    assert spec and spec["geom_source"] == "figshare-pdo"
    geom = audit.load_figshare_polygons(BETARD, {spec["file_number"]})[spec["file_number"]]
    res = overrides.clip(slug, geom, "figshare-pdo")
    assert res.stale == []
    assert len(res.dropped) == n_drop
    assert not res.geom.is_empty
    assert overrides.clip(slug, geom, "gisco-commune-list").dropped == []
    _assert_parts_sit_in_cited_communities(geom, spec, res)


@pytest.mark.parametrize("slug", sorted(_ISLAND_CLIPS))
def test_island_clips_match_the_nuts_union(overrides, slug):
    """Ζάκυνθος, Βερντέα Ζακύνθου and Κρήτη are drawn as a GISCO NUTS unit,
    which carries islets their specs exclude ('τις περιοχές της νήσου
    Ζακύνθου', 'όλη την νήσο Ζάκυνθο', 'όλες τις περιοχές της νήσου Κρήτης'):
    the Strofades, Gavdos and Gavdopoula. There is no Bétard polygon to
    re-derive against, so the clip is verified on the union stage 04 clips."""
    layer, nuts_name, n_drop, gap_km = _ISLAND_CLIPS[slug]
    spec = overrides.clip_specs.get(slug)
    assert spec and spec["geom_source"] == "gisco-nuts-region"
    if not layer.exists():
        pytest.skip(f"{layer.name} not fetched")
    import geopandas as gpd
    gdf = gpd.read_file(layer)
    rows = gdf[(gdf["CNTR_CODE"] == "EL") & (gdf["NUTS_NAME"] == nuts_name)]
    assert len(rows) == 1
    geom = unary_union(list(rows.geometry))
    res = overrides.clip(slug, geom, "gisco-nuts-region")
    assert res.stale == []
    assert len(res.dropped) == n_drop
    assert overrides.clip(slug, geom, "figshare-pdo").dropped == []
    kept = shp_transform(_to_3035, res.geom)
    parts = _dropped_parts(geom, res.dropped, spec.get("match_tol_km", 1.5))
    # the dropped parts form one detached cluster: its far edge is beyond
    # the detector's 25 km gap, and every islet chains to the cluster
    # (Sarakino lies 15 km off Euboea but belongs with Skyros)
    assert max(part.distance(kept) for part in parts) > gap_km * 1000
    for part in parts:
        assert part.distance(kept) > gap_km * 1000 or any(
            part is not other and part.distance(other) < gap_km * 1000 for other in parts
        )
    _assert_parts_sit_in_cited_communities(geom, spec, res)
