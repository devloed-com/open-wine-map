"""National tier, France — INAO's datasets on data.gouv.fr (the one-call
release check of memory `reference_inao_datagouv_datasets`).

The INAO organisation lists seven datasets; four are consumed: the
parcellaire shapefile (weekly, replaced in place under a dated filename),
the SIQO referentiel CSV (labelled weekly, frozen since 2025-12-31) and the
two aires-communes CSVs (AO and IG). The probe compares the dated resource
the listing serves now with the one `raw/manifest.json` and the files under
`raw/inao/` were built from.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import CURRENT, NEWER, ROOT, UNREACHABLE, UNVERIFIABLE, Http, Probe

ORG_ID = "534fff80a3a7292c64a77e54"
LIST_URL = f"https://www.data.gouv.fr/api/1/datasets/?organization={ORG_ID}&page_size=100&sort=-last_update"

# dataset slug → (label, local file, manifest key)
CONSUMED = {
    "delimitation-parcellaire-des-aoc-viticoles-de-linao": (
        "INAO parcellaire (delimitation parcellaire des AOC viticoles)", ROOT / "raw" / "inao" / "parcellaire.zip",
        "delimitation-parcellaire-des-aoc-viticoles-de-linao",
        "scripts/00_fetch_data.py (new release) → 04_build_maps.py; then audit_parcellaire_gaps.py --strict and the carry-forward table"),
    "referentiel-des-produits-sous-signe-officiel-didentification-de-la-qualite-et-de-lorigine-siqo": (
        "SIQO referentiel CSV", ROOT / "raw" / "inao" / "siqo-referentiel.csv",
        "referentiel-des-produits-sous-signe-officiel-didentification-de-la-qualite-et-de-lorigine-siqo",
        "scripts/00_fetch_data.py → 01 → 02 (the drop guard lists any denomination the new export lacks) → 04"),
    "aires-geographiques-des-aoc-aop": (
        "INAO aires-communes CSV (AOC/AOP)", ROOT / "raw" / "inao" / "aoc-aop-aires-communes.csv", "",
        "re-fetch the CSV, re-run 04; re-verify scripts/_lib/aires_supplements.json pins (a pinned commune the CSV carries again is STALE)"),
    "aire-geographique-des-igp-et-des-ig": (
        "INAO aires-communes CSV (IGP/IG)", ROOT / "raw" / "inao" / "igp-aires-communes.csv", "",
        "re-fetch the CSV, re-run 04; re-verify scripts/_lib/aires_supplements.json pins"),
}
# Signals only (not consumed): the dissolved aires shapefile's orphan rows are the
# fresher drift signal for cancelled / promoted denominations.
SIGNAL = {
    "delimitation-des-aires-geographiques-des-siqo": "INAO aire-géographique shapefile (not consumed; its orphan rows signal a retired denomination)",
}


def _md5(path: Path) -> str:
    h = hashlib.md5()  # noqa: S324 — static.data.gouv.fr's ETag is the file's md5
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _held_url(manifest_key: str) -> str:
    mp = ROOT / "raw" / "manifest.json"
    if not manifest_key or not mp.exists():
        return ""
    try:
        return (json.loads(mp.read_text(encoding="utf-8")).get(manifest_key) or {}).get("url") or ""
    except ValueError:
        return ""


def probe(http: Http) -> list[Probe]:
    data = http.get_json(LIST_URL)
    if isinstance(data, str):
        return [Probe(tier="national", source_key="datagouv-inao", url=LIST_URL, verdict=UNREACHABLE, method="api", reason=data)]
    out: list[Probe] = []
    by_slug = {ds.get("slug"): ds for ds in data.get("data") or []}
    for slug, (label, local, mkey, recipe) in CONSUMED.items():
        ds = by_slug.get(slug)
        if not ds:
            out.append(Probe(tier="national", source_key=label, url=LIST_URL, verdict=UNVERIFIABLE, method="api",
                             reason=f"dataset {slug} not in the INAO organisation listing"))
            continue
        # the newest non-archive resource: the dated filename replaced in place
        res = sorted((r for r in ds.get("resources") or [] if r.get("url")),
                     key=lambda r: r.get("last_modified") or "", reverse=True)
        res = [r for r in res if "rhum" not in (r.get("title") or "").lower()] or res
        if not res:
            out.append(Probe(tier="national", source_key=label, url=ds.get("page") or LIST_URL, verdict=UNVERIFIABLE,
                             method="api", reason="no resources on the dataset"))
            continue
        top = res[0]
        up_url = top["url"]
        up_date = (top.get("last_modified") or "")[:10]
        held_url = _held_url(mkey)
        held_label = held_url.rsplit("/", 1)[-1] if held_url else (local.name if local.exists() else "(not fetched)")
        up_label = up_url.rsplit("/", 1)[-1]
        same_url = held_url and held_url == up_url
        same_file = False
        fetched_after = False
        method = "api"
        if not same_url and local.exists():
            etag = ""
            h = http.head(up_url)
            if isinstance(h, dict):
                etag = (h.get("etag") or "").strip('"').lower().removeprefix("w/").strip('"')
            if etag and len(etag) == 32:
                same_file = _md5(local) == etag
                method = "api+etag"
            else:
                # no comparable ETag: a local file saved after the upstream resource
                # date was fetched from this very publication
                from datetime import datetime, timezone
                mtime = datetime.fromtimestamp(local.stat().st_mtime, tz=timezone.utc).date().isoformat()
                fetched_after = bool(up_date) and mtime >= up_date
                method = "api+mtime"
                held_label = f"{held_label} (saved {mtime})"
        if same_url or same_file or fetched_after:
            out.append(Probe(tier="national", source_key=label, url=up_url, verdict=CURRENT, held=held_label,
                             upstream=f"{up_label} ({up_date})", method=method))
        else:
            out.append(Probe(tier="national", source_key=label, url=ds.get("page") or up_url, verdict=NEWER,
                             held=held_label, upstream=f"{up_label} ({up_date})", upstream_url=up_url, method=method,
                             reason="the listing serves a newer dated resource than the one the build was fetched from",
                             recipe=recipe))
    for slug, label in SIGNAL.items():
        ds = by_slug.get(slug)
        if ds:
            res = sorted((r for r in ds.get("resources") or [] if r.get("url") and "rhum" not in (r.get("title") or "").lower()),
                         key=lambda r: r.get("last_modified") or "", reverse=True)
            if res:
                out.append(Probe(tier="national", source_key=label, url=res[0]["url"], verdict=CURRENT, held="(signal only)",
                                 upstream=f"{res[0]['url'].rsplit('/', 1)[-1]} ({(res[0].get('last_modified') or '')[:10]})",
                                 method="api", reason="not consumed by the build; compare its orphan rows with the SIQO export when a denomination vanishes"))
    return out
