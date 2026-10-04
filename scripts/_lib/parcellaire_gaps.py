"""INAO parcellaire gaps — aire communes the parcel layer does not cover, and
the curator fills that close them.

The INAO "délimitation parcellaire des AOC viticoles" layer is not complete.
A commune of an appellation's aire géographique (the INAO aires-communes
CSV; the cahier's section IV) can have no parcel row at all — for any AOC,
its delimitation not digitised (Vaison-la-Romaine, Saint-Marcellin-lès-
Vaison, Saint-Romain-en-Viennois and Mollans-sur-Ouvèze in the 2026-05-11
release) — or rows for other appellations only (Visan, Sérignan-du-Comtat
and Sorgues carry Côtes du Rhône parcels and no Côtes du Rhône Villages
row). A record drawn from the parcellaire then has a hole where some of the
appellation's best-known villages are (visitor flag 2026-09-29: Côtes du
Rhône Villages, boundary, at z8.8).

The layer does not say which of the two it means, and for a regional
appellation a vineless aire commune is genuinely not on the wine map
(Bourgogne: 46 of its 315 aire communes carry no parcel; the Alsace grand
cru rows list all 47 wine communes for every climat), so nothing is filled
automatically. Two things happen instead:

  * `scripts/audit_parcellaire_gaps.py` lists, per parcellaire record, the
    aire communes without a parcel row, classified `not-digitised` (no row
    for any AOC) / `other-aoc` (rows for other appellations only), with a
    `dgc-named` mark when a DGC aire of the same appellation lists the
    commune, for a curator to review against the cahier;
  * `parcellaire_gap_fills.json` (checked in) pins the communes a curator
    verified. Stage 04 fills each pinned commune with the parcels of a
    *donor* appellation inside that commune when a donor has some — the
    parent for a DGC, the regional AOC for a parent: Côtes du Rhône parcels
    stand in for the missing Villages parcels of Visan, a superset but the
    vineyard's shape rather than the commune's — else with the whole
    commune polygon (IGN AdminExpress, the way `aires-csv` records draw).
    The card says which communes were filled and how (`geom_parcel_fill`)
    and which gaps of a pinned record remain unfilled (`geom_parcel_gaps`).
    A pinned commune that carries parcels again is STALE: nothing is filled
    for it, stage 04 says so, and the audit fails `--strict` — the pin must
    be re-verified, as the geometry-outlier overrides are.

`geom_source` stays `parcellaire` / `parcellaire-dgc`: the footprint, the
audits and the map paint key on it; the fill is disclosed on the card.
"""
from __future__ import annotations

import csv
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from _lib.parcellaire import (
    PATCH_CSV,
    carry_forward_frames,
    log_carry_forward,
    release_of,
    resolve_shapefile,
)

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "raw" / "cache" / "parcellaire-coverage"
DEFAULT_FILLS_PATH = Path(__file__).with_name("parcellaire_gap_fills.json")

HOW_COMMUNE = "commune"
HOW_DONOR = "donor-parcels"


# ------------------------------------------------------------- coverage index
@dataclass
class ParcelCoverage:
    """Which communes the parcellaire layer carries, per appellation and per
    denomination — the attribute table only, no geometry."""

    shapefile: str
    by_app: dict[str, dict[str, set[str]]]
    digitised: set[str]
    # the carry-forward entries against this release: {label, key, release,
    # rows, state (APPLIED / STALE), reason}
    carried: list[dict] = field(default_factory=list)

    def communes_for_app(self, app: str) -> set[str]:
        """Every commune with a row for the appellation, any denomination —
        what the parent polygon is dissolved from (`build_aoc_polygons`)."""
        out: set[str] = set()
        for codes in (self.by_app.get(app) or {}).values():
            out |= codes
        return out

    def communes_for_denom(self, app: str, id_denom: str) -> set[str]:
        return set((self.by_app.get(app) or {}).get(str(id_denom)) or ())

    def has_any_row(self, insee: str) -> bool:
        return insee in self.digitised

    @property
    def apps(self) -> list[str]:
        return sorted(self.by_app)


def _apply_field_patches(df) -> None:
    """The INSEE-field patches of `inao-shapefile-patch.csv` (cross-
    département codes, the literal "ok"), so the coverage sees the same
    communes the polygons are dissolved from. Mirrors
    `parcellaire.apply_patches` without the geometry repair."""
    if not PATCH_CSV.exists():
        return
    with PATCH_CSV.open(encoding="utf-8") as fh:
        patches = list(csv.DictReader(fh))
    for p in patches:
        f = p["field"]
        if f not in df.columns:
            continue
        mask = (
            (df["app"] == p["app"])
            & (df["id_denom"].astype(str) == str(p["id_denom"]))
            & (df["insee"] == p["insee"])
            & (df[f] == p["current_value"])
            & (df["nomcom"] == p["nomcom"])
        )
        if int(mask.sum()) == 1:
            df.loc[mask, f] = p["proposed_value"]


def load_coverage(force: bool = False, shapefile: Path | None = None) -> ParcelCoverage | None:
    """The coverage index for the newest INAO release on disk, cached as JSON
    under raw/cache/parcellaire-coverage/<release>.json (a new release is a
    new file). None when no shapefile is present."""
    shp = shapefile or resolve_shapefile()
    if shp is None:
        return None
    import pyogrio

    df = pyogrio.read_dataframe(
        shp, read_geometry=False, columns=["app", "id_denom", "insee", "insee2011", "nomcom"],
    )
    _apply_field_patches(df)
    frames, states = carry_forward_frames(df, geometry=False)
    log_carry_forward(states, release_of(shp))
    carried = [
        {"label": sp.label, "key": sp.key, "release": sp.release, "rows": n, "state": state,
         "reason": sp.reason, "id_app": sp.id_app, "id_denom": sp.id_denom}
        for sp, state, n in states
    ]
    cache = CACHE_DIR / f"{shp.stem}.json"
    if cache.exists() and not force:
        data = json.loads(cache.read_text(encoding="utf-8"))
        same_carry = [(c["key"], c["release"], c["state"]) for c in data.get("carried", [])] == [
            (c["key"], c["release"], c["state"]) for c in carried
        ]
        if same_carry:
            return ParcelCoverage(
                shapefile=data["shapefile"],
                by_app={a: {d: set(c) for d, c in denoms.items()} for a, denoms in data["by_app"].items()},
                digitised=set(data["digitised"]),
                carried=carried,
            )
    if frames:
        import pandas as pd

        df = pd.concat([df, *frames], ignore_index=True)
    by_app: dict[str, dict[str, set[str]]] = {}
    digitised: set[str] = set()
    for r in df[["app", "id_denom", "insee", "insee2011"]].itertuples(index=False):
        # a row digitised against the current code only has `insee` null
        # (Côtes de Provence la Londe, 2026-09-28): a float NaN, never a code
        # a few rows carry two codes in one field ("49078,49115" — a merged
        # commune); each code counts
        codes = {
            part.strip()
            for c in (r.insee, r.insee2011) if isinstance(c, str)
            for part in c.split(",") if part.strip()
        }
        by_app.setdefault(r.app, {}).setdefault(str(r.id_denom), set()).update(codes)
        digitised |= codes
    cov = ParcelCoverage(shapefile=shp.name, by_app=by_app, digitised=digitised, carried=carried)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(
        json.dumps(
            {
                "shapefile": cov.shapefile,
                "by_app": {a: {d: sorted(c) for d, c in denoms.items()} for a, denoms in by_app.items()},
                "digitised": sorted(digitised),
                "carried": carried,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"  cached → {cache.relative_to(ROOT)}", file=sys.stderr)
    return cov


def parcel_gaps(
    aire_codes: set[str], parcel_codes: set[str], insee_idx: dict,
) -> tuple[set[str], set[str]]:
    """(gaps, unknown): the aire communes with no parcel row, in codes the
    IGN index carries; and the aire codes IGN no longer carries (a pre-merger
    code in the aires CSV — not a gap, reported apart by the audit)."""
    gaps = {c for c in aire_codes if c not in parcel_codes and c in insee_idx}
    unknown = {c for c in aire_codes if c not in insee_idx}
    return gaps, unknown


# ------------------------------------------------------------------ the pins
@dataclass
class FillSpec:
    slug: str
    communes: dict[str, str]
    donors: list[str]
    reason: str
    source: str
    verified: str = ""


def load_gap_fills(path: Path = DEFAULT_FILLS_PATH) -> dict[str, FillSpec]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, FillSpec] = {}
    for slug, ent in data.items():
        if slug.startswith("__"):
            continue
        communes = ent.get("communes") or {}
        if not isinstance(communes, dict) or not communes:
            raise ValueError(f"{path.name}: {slug}: `communes` must be a non-empty {{insee: name}} map")
        for code, name in communes.items():
            if not (isinstance(code, str) and len(code) == 5 and isinstance(name, str) and name.strip()):
                raise ValueError(f"{path.name}: {slug}: bad commune entry {code!r}: {name!r}")
        donors = ent.get("donors") or []
        if not isinstance(donors, list) or not all(isinstance(d, str) and d for d in donors):
            raise ValueError(f"{path.name}: {slug}: `donors` must be a list of slugs")
        if not (ent.get("reason") or "").strip() or not (ent.get("source") or "").strip():
            raise ValueError(f"{path.name}: {slug}: `reason` and `source` are required")
        out[slug] = FillSpec(
            slug=slug, communes=dict(communes), donors=list(donors),
            reason=ent["reason"], source=ent["source"], verified=ent.get("verified") or "",
        )
    return out


@dataclass
class FillResult:
    geom: BaseGeometry
    filled: list[dict] = field(default_factory=list)
    stale: list[dict] = field(default_factory=list)
    gaps: list[dict] = field(default_factory=list)


def apply_gap_fill(
    spec: FillSpec,
    geom: BaseGeometry,
    gap_codes: set[str],
    insee_idx: dict,
    insee_name_idx: dict[str, str],
    donor_geom: Callable[[str], BaseGeometry | None],
    donor_name: Callable[[str], str],
    donor_covers: Callable[[str, str], bool],
) -> FillResult:
    """Fill the pinned communes of one record. Pure: returns the verdict, logs
    nothing. A pinned commune that is not a current gap (parcels exist now,
    or IGN carries no polygon for the code) is `stale` and left alone.

    A donor stands in only where the coverage index says it has a parcel row
    in that commune (`donor_covers(slug, insee)`): the parcels of a
    neighbouring commune touch the boundary, so a geometric intersection
    alone would cut a sliver and call it the vineyard (Vaison-la-Romaine
    against the Côtes du Rhône parcels of Villedieu, 2026-09-29)."""
    pieces: list[BaseGeometry] = []
    filled: list[dict] = []
    stale: list[dict] = []
    for code, pinned_name in spec.communes.items():
        name = insee_name_idx.get(code) or pinned_name
        if code not in gap_codes:
            stale.append({"insee": code, "name": name, "why": "parcels present or not in the aire"})
            continue
        cg = insee_idx.get(code)
        if cg is None:
            stale.append({"insee": code, "name": name, "why": "no IGN commune polygon"})
            continue
        commune = shape(cg)
        piece: BaseGeometry | None = None
        how, donor = HOW_COMMUNE, ""
        for d in spec.donors:
            if not donor_covers(d, code):
                continue
            dg = donor_geom(d)
            if dg is None or dg.is_empty or not dg.intersects(commune):
                continue
            cut = dg.intersection(commune)
            if cut.is_empty:
                continue
            piece, how, donor = cut, HOW_DONOR, donor_name(d) or d
            break
        if piece is None:
            piece = commune
        pieces.append(piece)
        filled.append({"insee": code, "name": name, "how": how, "donor": donor})
    new_geom = unary_union([geom, *pieces]) if pieces else geom
    done = {f["insee"] for f in filled}
    gaps = [
        {"insee": c, "name": insee_name_idx.get(c) or c}
        for c in sorted(gap_codes - done, key=lambda c: insee_name_idx.get(c) or c)
    ]
    return FillResult(geom=new_geom, filled=filled, stale=stale, gaps=gaps)


def disclosure(result: FillResult) -> dict:
    """The panel-payload fields for one filled record."""
    return {
        "geom_parcel_fill": [
            {"name": f["name"], "how": f["how"], "donor": f["donor"]} for f in result.filled
        ],
        "geom_parcel_gaps": [g["name"] for g in result.gaps],
    }
