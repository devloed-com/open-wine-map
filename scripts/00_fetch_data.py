"""Fetch the public reference datasets Open Wine Map depends on.

Sources:
- INAO SIQO referentiel + INAO parcellaire viticole (data.gouv.fr, slug-resolved)
- French commune polygons via geo.api.gouv.fr (IGN AdminExpress under the hood),
  fetched per-département and merged into a single GeoJSON.
- INAO's inventory of delimitation plans (the public share of INAO's «portail
  des plans officiels de délimitation»): the communes holding each
  appellation's parcel area — scripts/_lib/fr/plan_inventory.py.
- Cadastre Etalab lieux-dits (cadastre.data.gouv.fr) for a curated set of
  parent appellations whose DGCs sit as named cadastral parcels inside the
  parent's communes (Chablis premier-cru climats, Givry premier cru,
  Santenay premier cru). One `.json.gz` per commune.

Each fetched artefact gets a manifest entry so subsequent runs are no-ops when
the upstream resource URL hasn't changed.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib.aires import load_aires  # noqa: E402
from _lib.aires import lookup as lookup_aire
from _lib.fr import plan_inventory  # noqa: E402

DATAGOUV_API = "https://www.data.gouv.fr/api/1/datasets/{slug}/"
GEO_API = "https://geo.api.gouv.fr/communes"
GEO_API_FORMER = "https://geo.api.gouv.fr/communes_associees_deleguees"
# INSEE, "Code officiel géographique au 1er janvier 2026"
# (https://www.insee.fr/fr/information/8740222): every change of commune since
# 1943 — mergers, communes nouvelles, code changes. Licence Ouverte 2.0.
COG_MOVEMENTS_URL = "https://www.insee.fr/fr/statistiques/fichier/8740222/v_mvt_commune_2026.csv"
CADASTRE_LIEUX_DITS_URL = (
    "https://cadastre.data.gouv.fr/data/etalab-cadastre/latest/"
    "geojson/communes/{dept}/{insee}/cadastre-{insee}-lieux_dits.json.gz"
)

# Parent appellations whose DGCs are climats / lieux-dits without parcellaire
# rows — see scripts/_lib/lieu_dit.py for the rationale. Each parent's
# commune set is resolved from the INAO aires CSV at fetch time.
CADASTRE_PARENTS = ["Chablis", "Givry", "Santenay"]

METRO_DEPTS = [f"{i:02d}" for i in range(1, 96) if i != 20] + ["2A", "2B"]
DROM_DEPTS = ["971", "972", "973", "974", "976"]
ALL_DEPTS = sorted(METRO_DEPTS + DROM_DEPTS)


@dataclass
class DatagouvSource:
    slug: str
    resource_match: str  # case-insensitive substring matched against title+url
    dest: Path


DATAGOUV_SOURCES = [
    DatagouvSource(
        slug="referentiel-des-produits-sous-signe-officiel-didentification-de-la-qualite-et-de-lorigine-siqo",
        resource_match="ref-produit-siqo",
        dest=RAW / "inao" / "siqo-referentiel.csv",
    ),
    DatagouvSource(
        slug="delimitation-parcellaire-des-aoc-viticoles-de-linao",
        resource_match="delim-parcellaire-aoc-shp",
        dest=RAW / "inao" / "parcellaire.zip",
    ),
]


def resolve_resource(slug: str, match: str) -> str:
    r = requests.get(DATAGOUV_API.format(slug=slug), timeout=30)
    r.raise_for_status()
    data = r.json()
    candidates = [
        res
        for res in data.get("resources", [])
        if match.lower() in (res.get("title", "") + res.get("url", "")).lower()
    ]
    if not candidates:
        raise RuntimeError(f"no resource on {slug} matched {match!r}")
    candidates.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return candidates[0]["url"]


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0)) or None
        with open(tmp, "wb") as f, tqdm(
            total=total, unit="B", unit_scale=True, desc=dest.name, leave=False
        ) as bar:
            for chunk in r.iter_content(chunk_size=1 << 16):
                f.write(chunk)
                bar.update(len(chunk))
    tmp.rename(dest)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_communes(dest: Path) -> dict:
    """One GeoJSON merging communes from every département via geo.api.gouv.fr.

    The API caps full-France queries at 400 KB; per-département queries each
    return well under that. Output schema: FeatureCollection with properties
    {code (INSEE), nom, departement, region}.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    features: list[dict] = []
    for dept in tqdm(ALL_DEPTS, desc="communes by dept", leave=False):
        params = {
            "codeDepartement": dept,
            "fields": "code,nom,codeDepartement,codeRegion",
            "format": "geojson",
            "geometry": "contour",
        }
        r = requests.get(GEO_API, params=params, timeout=60)
        r.raise_for_status()
        fc = r.json()
        features.extend(fc.get("features", []))

    merged = {"type": "FeatureCollection", "features": features}
    tmp = dest.with_suffix(dest.suffix + ".part")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(merged, f)
    tmp.rename(dest)

    return {
        "source": "https://geo.api.gouv.fr/communes",
        "departments": len(ALL_DEPTS),
        "features": len(features),
        "sha256": sha256(dest),
        "path": str(dest.relative_to(ROOT)),
    }


def fetch_former_communes(dest: Path) -> dict:
    """One GeoJSON of the communes associées and déléguées: the former communes
    a merger kept as a unit inside the commune that absorbed them, each with
    the INSEE code it had and its own outline (geo.api.gouv.fr, IGN
    AdminExpress under the hood, Licence Ouverte 2.0).

    INAO's aires CSV keeps the commune codes of the day each row was written;
    a commune merged since is no longer in the commune layer, and without
    this one it is not drawn (a quarter of the Calvados aire). Properties:
    {code, nom, chefLieu (the commune that holds it today), type,
    codeDepartement}.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    features: list[dict] = []
    for dept in tqdm(ALL_DEPTS, desc="former communes by dept", leave=False):
        params = {
            "codeDepartement": dept,
            "fields": "code,nom,chefLieu,type,codeDepartement",
            "format": "geojson",
            "geometry": "contour",
        }
        for attempt in range(4):
            try:
                r = requests.get(GEO_API_FORMER, params=params, timeout=60)
                r.raise_for_status()
                break
            except requests.RequestException:
                if attempt == 3:
                    raise
                time.sleep(2 * (attempt + 1))
        features.extend(f for f in r.json().get("features", []) if f.get("geometry"))

    merged = {"type": "FeatureCollection", "features": features}
    tmp = dest.with_suffix(dest.suffix + ".part")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(merged, f)
    tmp.rename(dest)

    return {
        "source": GEO_API_FORMER,
        "departments": len(ALL_DEPTS),
        "features": len(features),
        "sha256": sha256(dest),
        "path": str(dest.relative_to(ROOT)),
        "fetched_at": time.strftime("%Y-%m-%d"),
    }


def _dept_segment(insee: str) -> str:
    """Cadastre URL path segment for a commune INSEE — département prefix.

    Métropole INSEE codes start with the 2-digit dept (incl. 2A/2B for
    Corsica). DROM codes are 3-digit (97x). Cadastre URLs use those
    same prefixes as path segments.
    """
    if insee.startswith("97"):
        return insee[:3]
    return insee[:2]


def fetch_cadastre_lieux_dits(insee_codes: set[str], dest_dir: Path) -> dict:
    """Fetch one cadastre lieux-dits GeoJSON per commune INSEE.

    Caches by Last-Modified header in the per-commune sub-manifest entry.
    Skips communes whose file already exists with an unchanged remote
    timestamp. Returns a sub-manifest summary keyed by INSEE.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    sub_manifest_path = dest_dir / "manifest.json"
    sub: dict = (
        json.loads(sub_manifest_path.read_text(encoding="utf-8")) if sub_manifest_path.exists() else {}
    )
    fetched = 0
    skipped = 0
    missing: list[str] = []
    for insee in tqdm(sorted(insee_codes), desc="cadastre lieux-dits", leave=False):
        url = CADASTRE_LIEUX_DITS_URL.format(dept=_dept_segment(insee), insee=insee)
        out = dest_dir / f"{insee}.json.gz"
        prior = sub.get(insee, {})
        try:
            head = requests.head(url, timeout=30, allow_redirects=True)
        except Exception as exc:
            print(f"[skip] cadastre {insee}: {exc}", file=sys.stderr)
            missing.append(insee)
            continue
        if head.status_code == 404:
            # Communes without published lieux-dits (rare — typically very
            # small / new communes). Record so we don't retry forever.
            sub[insee] = {"url": url, "missing": True}
            missing.append(insee)
            continue
        head.raise_for_status()
        last_modified = head.headers.get("Last-Modified", "")
        if out.exists() and prior.get("last_modified") == last_modified and last_modified:
            skipped += 1
            continue
        try:
            download(url, out)
        except Exception as exc:
            print(f"[skip] cadastre {insee}: {exc}", file=sys.stderr)
            missing.append(insee)
            continue
        sub[insee] = {
            "url": url,
            "last_modified": last_modified,
            "size": out.stat().st_size,
            "sha256": sha256(out),
        }
        fetched += 1
    sub_manifest_path.write_text(json.dumps(sub, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "communes_total": len(insee_codes),
        "fetched": fetched,
        "cached": skipped,
        "missing": missing,
        "manifest": str(sub_manifest_path.relative_to(ROOT)),
    }


def collect_cadastre_communes() -> set[str]:
    """Resolve INSEE codes for every parent appellation in CADASTRE_PARENTS.

    Reads the INAO aires CSV (already fetched in this same stage 00 run)
    and unions every commune of every targeted parent. The aires CSV is
    a hard dependency of stage 04 anyway, so we expect it on disk.
    """
    aires_csv = RAW / "inao" / "aoc-aop-aires-communes.csv"
    if not aires_csv.exists():
        return set()
    aires = load_aires()
    out: set[str] = set()
    for parent in CADASTRE_PARENTS:
        codes = lookup_aire(aires, parent) or set()
        out |= set(codes)
    return out


def main() -> int:
    manifest_path = RAW / "manifest.json"
    manifest: dict = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

    for src in DATAGOUV_SOURCES:
        try:
            url = resolve_resource(src.slug, src.resource_match)
        except Exception as exc:
            print(f"[skip] {src.slug}: {exc}", file=sys.stderr)
            continue

        prior = manifest.get(src.slug, {})
        if src.dest.exists() and prior.get("url") == url:
            print(f"[cache] {src.dest.relative_to(ROOT)}", file=sys.stderr)
            continue

        print(f"[fetch] {src.slug} → {src.dest.relative_to(ROOT)}", file=sys.stderr)
        download(url, src.dest)
        manifest[src.slug] = {
            "url": url,
            "sha256": sha256(src.dest),
            "path": str(src.dest.relative_to(ROOT)),
        }

    communes_dest = RAW / "ign" / "communes.geojson"
    if communes_dest.exists() and "ign-communes" in manifest:
        print(f"[cache] {communes_dest.relative_to(ROOT)}", file=sys.stderr)
    else:
        print(f"[fetch] geo.api.gouv.fr communes → {communes_dest.relative_to(ROOT)}", file=sys.stderr)
        manifest["ign-communes"] = fetch_communes(communes_dest)

    movements_dest = RAW / "insee" / "v_mvt_commune.csv"
    if movements_dest.exists() and manifest.get("insee-commune-movements", {}).get("url") == COG_MOVEMENTS_URL:
        print(f"[cache] {movements_dest.relative_to(ROOT)}", file=sys.stderr)
    else:
        print(f"[fetch] INSEE commune movements → {movements_dest.relative_to(ROOT)}", file=sys.stderr)
        movements_dest.parent.mkdir(parents=True, exist_ok=True)
        download(COG_MOVEMENTS_URL, movements_dest)
        manifest["insee-commune-movements"] = {
            "url": COG_MOVEMENTS_URL,
            "sha256": sha256(movements_dest),
            "path": str(movements_dest.relative_to(ROOT)),
            "fetched_at": time.strftime("%Y-%m-%d"),
        }

    former_dest = RAW / "ign" / "communes-associees-deleguees.geojson"
    if former_dest.exists() and "ign-former-communes" in manifest:
        print(f"[cache] {former_dest.relative_to(ROOT)}", file=sys.stderr)
    else:
        print(f"[fetch] geo.api.gouv.fr former communes → {former_dest.relative_to(ROOT)}",
              file=sys.stderr)
        manifest["ign-former-communes"] = fetch_former_communes(former_dest)

    # INAO's plan inventory is rewritten in place on the share: re-read on
    # every run (14 MB), like the parcellaire's weekly resource.
    print(f"[fetch] INAO plan inventory → {plan_inventory.DEST_DIR.relative_to(ROOT)}",
          file=sys.stderr)
    try:
        manifest["inao-plan-inventory"] = {
            **plan_inventory.fetch(requests.Session()),
            "fetched_at": time.strftime("%Y-%m-%d"),
        }
    except Exception as exc:
        print(f"[skip] INAO plan inventory: {exc} — stage 04 keeps the last copy on disk",
              file=sys.stderr)

    cadastre_dest = RAW / "cadastre" / "lieux-dits"
    cadastre_insee = collect_cadastre_communes()
    if not cadastre_insee:
        print(
            "[skip] cadastre lieux-dits — no aires CSV on disk yet "
            f"(parents: {', '.join(CADASTRE_PARENTS)})",
            file=sys.stderr,
        )
    else:
        print(
            f"[fetch] cadastre lieux-dits: {len(cadastre_insee)} communes "
            f"({', '.join(CADASTRE_PARENTS)}) → {cadastre_dest.relative_to(ROOT)}",
            file=sys.stderr,
        )
        manifest["cadastre-lieux-dits"] = fetch_cadastre_lieux_dits(cadastre_insee, cadastre_dest)

    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(f"[done] manifest at {manifest_path.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
