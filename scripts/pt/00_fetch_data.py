"""Fetch the public reference datasets the Portugal pipeline depends on.

Pipeline stage 00 (pt).

Sources:

1. **eAmbrosia EU register** (metadata spine — list of PT wine GIs)
   `https://webgate.ec.europa.eu/eambrosia-api/api/v1/geographical-indications`
   Filtered client-side to country=PT + productType=WINE + status=registered
   → 44 wine GIs (30 DOP + 14 IGP). Same fetch idiom as the ES stage.

2. **IVV cadernos master indexes** (text spine — actual pliego PDFs)
   - DOP list: `https://www.ivv.gov.pt/np4/8617.html` (30 entries)
   - IGP list: `https://www.ivv.gov.pt/np4/8616.html` (14 entries)
   Each row carries a wine name + a PDF link of the form
   `{$clientServletPath}/?newsId=8617&fileName=<NAME>.pdf` (the NP4
   templating literal resolves server-side; URL-encoded fetch works).
   We scrape both pages into `raw/pt/ivv/cadernos-index.json`, which
   stage 01 reads to fetch the per-DOP PDFs.

3. **DGT CAOP 2025** (geometry — commune-precision boundaries)
   `https://geo2.dgterritorio.gov.pt/caop/CAOP_{Continente,RAA,RAM}_2025-gpkg.zip`
   Three regional GPKGs: Continente, RAA (Açores), RAM (Madeira).
   CC-BY-4.0. Used by stage 04 as a fallback when Bétard 2022 lacks
   a PDO row (newer DOPs, all IGPs).

The pre-existing Figshare `EU_PDO.gpkg` (Bétard 2022) and GISCO LAU
zip live under `raw/es/`; they cover the whole EU so we do not
re-download them for PT.
"""

from __future__ import annotations

import hashlib
import html as html_mod
import json
import re
import sys
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]

OUT_DIR = ROOT / "raw" / "pt" / "eambrosia"
INDEX_PATH = OUT_DIR / "index.json"
MANIFEST_PATH = OUT_DIR / "manifest.json"

IVV_OUT_DIR = ROOT / "raw" / "pt" / "ivv"
IVV_INDEX_PATH = IVV_OUT_DIR / "cadernos-index.json"
IVV_INDEX_MANIFEST = IVV_OUT_DIR / "cadernos-index-manifest.json"
IVV_DOP_URL = "https://www.ivv.gov.pt/np4/8617.html"
IVV_IGP_URL = "https://www.ivv.gov.pt/np4/8616.html"
# `{$clientServletPath}` is the NP4 templating literal in the href text.
# It resolves server-side when fetched verbatim (URL-encoded as %7B%24...).
IVV_PDF_TEMPLATE = (
    "https://www.ivv.gov.pt/np4/%7B%24clientServletPath%7D/"
    "?newsId={news_id}&fileName={file_name}"
)

CAOP_OUT_DIR = ROOT / "raw" / "pt" / "caop"
CAOP_MANIFEST_PATH = CAOP_OUT_DIR / "manifest.json"
CAOP_REGIONS = {
    "continente": "https://geo2.dgterritorio.gov.pt/caop/CAOP_Continente_2025-gpkg.zip",
    "raa": "https://geo2.dgterritorio.gov.pt/caop/CAOP_RAA_2025-gpkg.zip",
    "ram": "https://geo2.dgterritorio.gov.pt/caop/CAOP_RAM_2025-gpkg.zip",
}
CAOP_LICENSE = (
    "© DGT / Direção-Geral do Território. CAOP 2025 — CC-BY-4.0."
)

EAMBROSIA_LIST_URL = (
    "https://webgate.ec.europa.eu/eambrosia-api/api/v1/geographical-indications"
)
EAMBROSIA_LICENSE = (
    "© European Union, eAmbrosia register. Reuse authorised with attribution."
)
IVV_LICENSE = (
    "© Instituto da Vinha e do Vinho, I.P. Public regulator data; "
    "redistributed with attribution."
)

UA = (
    "open-wine-map/0.0.1 (https://github.com/devloed-com/open-wine-map; "
    "mailto:code@devloed.com) python-requests"
)


def slugify(s: str) -> str:
    """Same shape as scripts/02_extract_cahiers.py:slug and
    scripts/es/00_fetch_data.py:slugify — strip diacritics, keep
    [A-Za-z0-9], collapse separators to single hyphens, lowercase."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s


def normalise_kind(gi_type: str) -> str:
    """eAmbrosia uses `PDO`/`PGI`; Portuguese convention is `DOP`/`IGP`
    (same as ES). We render the local form because the surface UI uses it."""
    return {"PDO": "DOP", "PGI": "IGP"}.get(gi_type, gi_type)


# eAmbrosia (`protectedNames`) and the IVV cadernos master index both
# label the Tejo DOP "DoTejo" — the space is dropped in both upstream
# registers. The official Portuguese name is "Do Tejo" (DOC Do Tejo).
# Correct the human-readable label at ingest so `name`/`slug` and the
# IVV name-match key agree; file identifiers (IVV `DO_DoTejo.pdf`,
# eAmbrosia `giIdentifier`) stay verbatim. Keyed by the exact bad
# string, so it self-heals if either register fixes the spelling.
_LABEL_CORRECTIONS = {"DoTejo": "Do Tejo"}


def correct_label(name: str) -> str:
    """Map a known-malformed upstream GI label to its official spelling."""
    s = (name or "").strip()
    return _LABEL_CORRECTIONS.get(s, s)


def project(rec: dict) -> dict:
    """Reduce one full eAmbrosia record to the fields downstream stages need.
    Shape matches scripts/es/00_fetch_data.py:project so stage 04's loader
    is country-agnostic."""
    name = correct_label((rec.get("protectedNames") or [""])[0])
    return {
        "giIdentifier": rec["giIdentifier"],
        "fileNumber": rec.get("fileNumber") or "",
        "name": name,
        "slug": slugify(name),
        "kind": normalise_kind(rec.get("giType") or ""),
        "status": rec.get("status") or "",
        "eu_protection_date": rec.get("euProtectionDate") or "",
        "modification_date": rec.get("modificationDate") or "",
        "producer_group": {
            "name": rec.get("producerGroupName") or "",
            "url": rec.get("producerGroupUrl") or "",
            "email": rec.get("producerGroupEmail") or "",
            "address": rec.get("producerGroupAdress") or "",
            "country": rec.get("producerGroupCountry") or "",
        },
        "publications": rec.get("publications") or [],
        "raw": rec,
    }


def fetch_list() -> tuple[list[dict], str]:
    print(f"[fetch] {EAMBROSIA_LIST_URL}", file=sys.stderr)
    r = requests.get(
        EAMBROSIA_LIST_URL,
        headers={"User-Agent": UA, "Accept": "application/json"},
        timeout=120,
    )
    r.raise_for_status()
    return r.json(), r.headers.get("etag") or ""


def _fetch_binary_with_manifest(
    *,
    label: str,
    url: str,
    out_path: Path,
    manifest_path: Path,
    extra_manifest: dict,
) -> None:
    """Download a binary artifact once and cache by sha. Mirrors
    scripts/es/00_fetch_data.py:_fetch_binary_with_manifest."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists() and manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            existing = {}
        if existing.get("sha256"):
            cur_sha = hashlib.sha256(out_path.read_bytes()).hexdigest()
            if cur_sha == existing["sha256"]:
                print(
                    f"[{label}] cached → {out_path.relative_to(ROOT)}",
                    file=sys.stderr,
                )
                return
    print(f"[{label}] fetching {url}", file=sys.stderr)
    r = requests.get(url, headers={"User-Agent": UA}, timeout=600)
    r.raise_for_status()
    out_path.write_bytes(r.content)
    sha = hashlib.sha256(r.content).hexdigest()
    manifest_path.write_text(
        json.dumps(
            {
                **extra_manifest,
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "source_url": url,
                "bytes": len(r.content),
                "sha256": sha,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print(
        f"[{label}] {len(r.content) // (1 << 20)} MB → "
        f"{out_path.relative_to(ROOT)}",
        file=sys.stderr,
    )


_IVV_ROW_RE = re.compile(
    r"<tr>\s*<td(?![^>]*colspan)[^>]*>(.*?)</td>"
    r"\s*<td[^>]*>\s*\[<a\s+href=\"[^\"]*?fileName=([^&\"]+?\.pdf)\"",
    re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _scrape_ivv_index(url: str, news_id: str, kind: str) -> list[dict]:
    """Scrape one IVV cadernos master page → list of {name, kind, pdf_url}."""
    print(f"[ivv] {url}", file=sys.stderr)
    r = requests.get(url, headers={"User-Agent": UA}, timeout=120)
    r.raise_for_status()
    body = r.text
    rows: list[dict] = []
    for raw, pdf_name in _IVV_ROW_RE.findall(body):
        text = _TAG_RE.sub("", raw)
        text = html_mod.unescape(text).strip()
        # Strip leading non-breaking space + the boilerplate header that
        # bleeds into the first row from the preceding header-cell.
        text = text.lstrip("\xa0").strip()
        text = re.sub(r"^Documento\s+", "", text, flags=re.DOTALL).strip()
        if not text:
            continue
        text = correct_label(text)
        rows.append(
            {
                "name": text,
                "kind": kind,
                "pdf_filename": pdf_name,
                "news_id": news_id,
                "pdf_url": IVV_PDF_TEMPLATE.format(
                    news_id=news_id, file_name=pdf_name
                ),
            }
        )
    return rows


def fetch_ivv_index() -> None:
    """Scrape the two IVV master pages → cadernos-index.json."""
    IVV_OUT_DIR.mkdir(parents=True, exist_ok=True)
    dop = _scrape_ivv_index(IVV_DOP_URL, "8617", "DOP")
    igp = _scrape_ivv_index(IVV_IGP_URL, "8616", "IGP")
    entries = dop + igp
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    IVV_INDEX_PATH.write_text(
        json.dumps(
            {"generated_at": now, "entries": entries},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    IVV_INDEX_MANIFEST.write_text(
        json.dumps(
            {
                "fetched_at": now,
                "license": IVV_LICENSE,
                "source_dop_url": IVV_DOP_URL,
                "source_igp_url": IVV_IGP_URL,
                "n_dop": len(dop),
                "n_igp": len(igp),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print(
        f"[ivv] {len(dop)} DOP + {len(igp)} IGP → "
        f"{IVV_INDEX_PATH.relative_to(ROOT)}",
        file=sys.stderr,
    )


def fetch_caop() -> None:
    """Pull the three CAOP 2025 regional GPKG zips and extract each."""
    CAOP_OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary: dict[str, dict] = {}
    for region, url in CAOP_REGIONS.items():
        zip_path = CAOP_OUT_DIR / f"CAOP_{region}_2025-gpkg.zip"
        sub_manifest = CAOP_OUT_DIR / f"manifest-{region}.json"
        _fetch_binary_with_manifest(
            label=f"caop/{region}",
            url=url,
            out_path=zip_path,
            manifest_path=sub_manifest,
            extra_manifest={"license": CAOP_LICENSE, "region": region},
        )
        with zipfile.ZipFile(zip_path) as zf:
            gpkg_inner = next(
                (n for n in zf.namelist() if n.lower().endswith(".gpkg")),
                None,
            )
            if gpkg_inner is None:
                print(f"[caop/{region}] no .gpkg inside zip", file=sys.stderr)
                continue
            gpkg_path = CAOP_OUT_DIR / Path(gpkg_inner).name
            if not gpkg_path.exists():
                with zf.open(gpkg_inner) as src, open(gpkg_path, "wb") as dst:
                    dst.write(src.read())
                print(
                    f"[caop/{region}] extracted → {gpkg_path.relative_to(ROOT)}",
                    file=sys.stderr,
                )
        summary[region] = {
            "zip": zip_path.name,
            "gpkg": Path(gpkg_inner).name if gpkg_inner else "",
        }
    CAOP_MANIFEST_PATH.write_text(
        json.dumps(
            {
                "license": CAOP_LICENSE,
                "fetched_at": datetime.now(timezone.utc).isoformat(
                    timespec="seconds"
                ),
                "source": "DGT — Direção-Geral do Território (geo2.dgterritorio.gov.pt)",
                "regions": summary,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. eAmbrosia slice
    full, etag = fetch_list()
    pt_wines_all = [
        g
        for g in full
        if "PT" in (g.get("countries") or []) and g.get("productType") == "WINE"
    ]
    pt_wines = [g for g in pt_wines_all if g.get("status") == "registered"]
    n_skipped_applied = len(pt_wines_all) - len(pt_wines)

    by_slug: dict[str, list[dict]] = {}
    projected = [project(rec) for rec in pt_wines]
    for p in projected:
        by_slug.setdefault(p["slug"], []).append(p)
    collisions = {s: ps for s, ps in by_slug.items() if len(ps) > 1}
    if collisions:
        print(
            f"[warn] {len(collisions)} slug collisions inside PT wines:",
            file=sys.stderr,
        )
        for s, ps in collisions.items():
            ids = ", ".join(p["fileNumber"] or p["giIdentifier"] for p in ps)
            print(f"  {s}: {ids}", file=sys.stderr)

    projected.sort(key=lambda p: p["slug"])

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    INDEX_PATH.write_text(
        json.dumps(
            {"generated_at": now, "wines": projected},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    by_kind: dict[str, int] = {}
    for p in projected:
        by_kind[p["kind"]] = by_kind.get(p["kind"], 0) + 1

    MANIFEST_PATH.write_text(
        json.dumps(
            {
                "generated_at": now,
                "source_url": EAMBROSIA_LIST_URL,
                "license": EAMBROSIA_LICENSE,
                "etag": etag,
                "n_total_eu": len(full),
                "n_pt_wines": len(projected),
                "n_skipped_applied": n_skipped_applied,
                "by_kind": by_kind,
                "n_slug_collisions": len(collisions),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    print(
        f"[done] eAmbrosia: total_eu={len(full)} pt_wines={len(projected)} "
        f"by_kind={by_kind} → {INDEX_PATH.relative_to(ROOT)}",
        file=sys.stderr,
    )

    # 2. IVV master indexes (DOP + IGP)
    fetch_ivv_index()

    # 3. CAOP 2025 GPKGs (Continente + RAA + RAM)
    fetch_caop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
