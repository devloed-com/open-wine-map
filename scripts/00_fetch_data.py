"""Fetch the public reference datasets open wine map depends on.

Sources:
- INAO SIQO referentiel + INAO parcellaire viticole (data.gouv.fr, slug-resolved)
- French commune polygons via geo.api.gouv.fr (IGN AdminExpress under the hood),
  fetched per-département and merged into a single GeoJSON.

Each fetched artefact gets a manifest entry so subsequent runs are no-ops when
the upstream resource URL hasn't changed.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import requests
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"

DATAGOUV_API = "https://www.data.gouv.fr/api/1/datasets/{slug}/"
GEO_API = "https://geo.api.gouv.fr/communes"

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
    with open(tmp, "w") as f:
        json.dump(merged, f)
    tmp.rename(dest)

    return {
        "source": "https://geo.api.gouv.fr/communes",
        "departments": len(ALL_DEPTS),
        "features": len(features),
        "sha256": sha256(dest),
        "path": str(dest.relative_to(ROOT)),
    }


def main() -> int:
    manifest_path = RAW / "manifest.json"
    manifest: dict = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

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

    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"[done] manifest at {manifest_path.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
