"""Fetch the public reference datasets the United Kingdom pipeline depends on.

Pipeline stage 00 (gb).

The UK is the corpus's first post-Brexit register: it is **not** in
eAmbrosia's live scheme (its pre-2021 GIs linger there as legacy rows,
but Sussex — registered 2022 — never appears), and Bétard 2022 is an EU
PDO layer carrying no `PDO-GB-*` rows. Both of the usual spines are
therefore unavailable, and both are replaced by UK-domestic ones:

1. **GOV.UK "protected food and drink names" register** (the spine).
   DEFRA publishes the UK GI schemes as a structured GOV.UK *finder*
   whose documents are queryable through the site's own search API:

     https://www.gov.uk/api/search.json
        ?filter_format=protected_food_drink_name
        &filter_register=wines
        &filter_country_of_origin=united-kingdom

   Each hit resolves to a per-GI content-API document carrying typed
   metadata (protection type, register, status, application + UK/EU
   registration dates, reason for protection) and — for every registered
   wine — an attachment: the **product specification**. Stage 01 fetches
   those; stage 02 parses them.

   v1 corpus: **6 registered wine GIs** — 4 PDO (English, Welsh, Sussex,
   Darnibole) + 2 PGI (English Regional, Welsh Regional). Every one of
   the 6 ships a public specification, so unlike ES/IT/GR/SI/HR/BG/SK/CZ
   the UK needs no national-spec fallback tier and has **no stub tier at
   all**. A 7th name, "The Crouch Valley" (PDO, applied for 2023-03-06),
   is still in assessment; it is filtered out by `status=registered` the
   way the eAmbrosia countries filter theirs, and reported by
   `scripts/audit_gb_coverage.py` so the queue stays visible.

2. **ONS Open Geography boundaries** (the geometry source), Open
   Government Licence v3.0, "Contains OS data © Crown copyright and
   database right", Source: Office for National Statistics:

     - Countries (December 2025) UK BGC — England + Wales, the
       `DEMARCATION` of four of the six GIs.
     - Counties and Unitary Authorities (December 2025) UK BGC — East
       Sussex + West Sussex + Brighton and Hove, whose union is the
       Sussex PDO's "administrative boundaries of the counties of East
       and West Sussex".

   BGC ("generalised, clipped to the coastline") is the right
   generalisation for a web map: full-resolution BFC is several times
   larger with no visible gain at the zooms this corpus renders.

   Darnibole needs no boundary download — its approximate polygon is
   reconstructed from the parcel references printed on its own
   specification plan (see `scripts/_lib/gb/darnibole.py`).

Outputs:
- raw/gb/gov-uk/index.json     — the 6 registered wine GIs + spec URLs
- raw/gb/gov-uk/manifest.json  — fetch metadata + the pending-application queue
- raw/gb/ons/countries.geojson — England + Wales
- raw/gb/ons/counties.geojson  — the three Sussex CTYUAs
- raw/gb/ons/manifest.json     — per-layer sha256 / feature counts / licence
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
GOVUK_DIR = ROOT / "raw" / "gb" / "gov-uk"
INDEX_PATH = GOVUK_DIR / "index.json"
GOVUK_MANIFEST = GOVUK_DIR / "manifest.json"
ONS_DIR = ROOT / "raw" / "gb" / "ons"
ONS_MANIFEST = ONS_DIR / "manifest.json"

SEARCH_URL = "https://www.gov.uk/api/search.json"
CONTENT_URL = "https://www.gov.uk/api/content"
REGISTER_BASE = "https://www.gov.uk/protected-food-drink-names"

UA = (
    "open-wine-map/0.0.1 (https://github.com/devloed-com/open-wine-map; "
    "mailto:winemap@devloed.com) python-requests"
)
GOVUK_LICENSE = "Open Government Licence v3.0 — © Crown copyright, DEFRA / GOV.UK"
ONS_LICENSE = (
    "Open Government Licence v3.0 — Source: Office for National Statistics "
    "licensed under the Open Government Licence. Contains OS data "
    "© Crown copyright and database right 2025."
)

ONS_FS = (
    "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services"
)
ONS_LAYERS = {
    "countries.geojson": {
        "service": "Countries_December_2025_Boundaries_UK_BGC",
        "where": "CTRY25NM IN ('England','Wales')",
        "out_fields": "CTRY25CD,CTRY25NM",
        "expected": 2,
        "label": "Countries (December 2025) Boundaries UK BGC",
    },
    "counties.geojson": {
        "service": "Counties_and_Unitary_Authorities_December_2025_Boundaries_UK_BGC",
        "where": "CTYUA25NM IN ('East Sussex','West Sussex','Brighton and Hove')",
        "out_fields": "CTYUA25CD,CTYUA25NM",
        "expected": 3,
        "label": "Counties and Unitary Authorities (December 2025) Boundaries UK BGC",
    },
}

# The GOV.UK register does not publish a GI file number — the per-entry
# metadata carries protection type and dates but no identifier (only
# Sussex's specification states one in its own text, "PDO GB number:
# W0006"). The rest of the corpus keys on the `PDO-xx-*` / `PGI-xx-*`
# file number, and all six UK wines are also listed in the EU register
# (the four 2011 names and Darnibole as pre-Brexit registrations kept
# protected under the Withdrawal Agreement; Sussex added 2025-01-31
# under the UK-EU agreement), so we bridge to those identifiers here.
# Verified against `raw/eambrosia-register/gi-index.json`
# (countryId=gb, qualityProductType=Wine).
_FILE_NUMBER_BY_SLUG: dict[str, str] = {
    "english-wine": "PDO-GB-A1585",
    "welsh-wine": "PDO-GB-A1587",
    "english-regional-wine": "PGI-GB-A1589",
    "welsh-regional-wine": "PGI-GB-A1590",
    "darnibole": "PDO-GB-N1636",
    "sussex": "PDO-GB-02365",
}

# The GOV.UK register writes the shorthand names the labels use ("English",
# "Welsh Regional"); the wine is "English wine" etc. Keep the register's own
# `registered_name` as the appellation name — it is what the label carries —
# but slugify to a stable, unambiguous slug.
_SLUG_OVERRIDES = {
    "english": "english-wine",
    "welsh": "welsh-wine",
    "english-regional": "english-regional-wine",
    "welsh-regional": "welsh-regional-wine",
}


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalise_kind(protection_type: str) -> str:
    """The GOV.UK register spells these out in English
    ("protected-designation-of-origin-pdo"). The corpus convention — and,
    concretely, the map's polygon-colour expression, which keys on
    `kind == 'IGP'` — is the DOP/IGP pair every other country uses."""
    p = (protection_type or "").lower()
    if "designation-of-origin" in p:
        return "DOP"
    if "geographical-indication" in p:
        return "IGP"
    return ""


def search_wines(session: requests.Session) -> list[dict]:
    params = {
        "filter_format": "protected_food_drink_name",
        "filter_register": "wines",
        "filter_country_of_origin": "united-kingdom",
        "count": 100,
        "fields": ",".join([
            "title", "link", "registered_name", "register", "status",
            "protection_type", "country_of_origin", "class_category",
            "date_application", "date_registration", "date_registration_eu",
            "reason_for_protection",
        ]),
    }
    r = session.get(SEARCH_URL, params=params, timeout=60)
    r.raise_for_status()
    return r.json().get("results") or []


def fetch_detail(session: requests.Session, link: str) -> dict:
    path = link.lstrip("/")
    r = session.get(f"{CONTENT_URL}/{path}", timeout=60)
    r.raise_for_status()
    return r.json()


def _spec_attachments(detail: dict) -> list[dict]:
    """Product-specification attachments, most useful first.

    A register entry links its product specification and (for the
    post-2021 applications) a decision notice; Welsh entries additionally
    carry a Welsh-language translation of the specification. Rank the
    English specification first and keep the rest as provenance.
    """
    out: list[dict] = []
    for att in (detail.get("details") or {}).get("attachments") or []:
        url = att.get("url") or ""
        if not url:
            continue
        title = (att.get("title") or "").strip()
        low = f"{title} {url}".lower()
        if "decision" in low and "notice" in low:
            role = "decision-notice"
        elif "welsh" in low and "translation" in low:
            role = "specification-welsh-translation"
        else:
            role = "product-specification"
        out.append({
            "role": role,
            "title": title,
            "url": url,
            "content_type": att.get("content_type") or "",
        })
    order = {"product-specification": 0, "specification-welsh-translation": 1,
             "decision-notice": 2}
    out.sort(key=lambda a: order.get(a["role"], 9))
    return out


def project(result: dict, detail: dict) -> dict:
    meta = (detail.get("details") or {}).get("metadata") or {}
    name = (meta.get("registered_name") or result.get("registered_name") or "").strip()
    base = slugify(name)
    slug = _SLUG_OVERRIDES.get(base, base)
    atts = _spec_attachments(detail)
    spec = next((a for a in atts if a["role"] == "product-specification"), None)
    return {
        "name": name,
        "slug": slug,
        "file_number": _FILE_NUMBER_BY_SLUG.get(slug, ""),
        "kind": normalise_kind(meta.get("protection_type") or ""),
        "protection_type": meta.get("protection_type") or "",
        "status": meta.get("status") or "",
        "register": meta.get("register") or "",
        "class_category": (meta.get("class_category") or [""])[0],
        "reason_for_protection": meta.get("reason_for_protection") or "",
        "date_application": meta.get("date_application") or "",
        "date_registration": meta.get("date_registration") or "",
        "date_registration_eu": meta.get("date_registration_eu") or "",
        "register_url": f"{REGISTER_BASE}/{(result.get('link') or '').rsplit('/', 1)[-1]}",
        "spec_url": (spec or {}).get("url") or "",
        "spec_title": (spec or {}).get("title") or "",
        "attachments": atts,
    }


def fetch_ons_layer(session: requests.Session, spec: dict) -> dict:
    url = f"{ONS_FS}/{spec['service']}/FeatureServer/0/query"
    params = {
        "where": spec["where"], "outFields": spec["out_fields"],
        "outSR": 4326, "f": "geojson",
    }
    print(f"[fetch] ONS {spec['service']}", file=sys.stderr)
    r = session.get(url, params=params, timeout=180)
    r.raise_for_status()
    return r.json()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true",
                    help="re-download the ONS boundary layers even when cached")
    args = ap.parse_args()

    session = requests.Session()
    session.headers["User-Agent"] = UA
    rc = 0

    # ---- 1. the register spine -------------------------------------
    GOVUK_DIR.mkdir(parents=True, exist_ok=True)
    results = search_wines(session)
    print(f"[fetch] GOV.UK wines register: {len(results)} UK entries", file=sys.stderr)

    wines: list[dict] = []
    pending: list[dict] = []
    for res in results:
        detail = fetch_detail(session, res.get("link") or "")
        rec = project(res, detail)
        if rec["status"] != "registered":
            pending.append({k: rec[k] for k in
                            ("name", "slug", "kind", "status", "date_application",
                             "register_url")})
            continue
        if not rec["file_number"]:
            print(f"[warn] {rec['name']} ({rec['slug']}): no file number bridged — "
                  "add it to _FILE_NUMBER_BY_SLUG (region + geometry key on it)",
                  file=sys.stderr)
            rc = 2
        if not rec["spec_url"]:
            print(f"[warn] {rec['name']}: registered but no product specification "
                  "attachment on the register page", file=sys.stderr)
            rc = 2
        wines.append(rec)

    wines.sort(key=lambda w: w["slug"])
    INDEX_PATH.write_text(
        json.dumps({"wines": wines}, ensure_ascii=False, indent=2), encoding="utf-8")

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    GOVUK_MANIFEST.write_text(json.dumps({
        "generated_at": now,
        "source_url": SEARCH_URL,
        "register": "wines",
        "country_of_origin": "united-kingdom",
        "license": GOVUK_LICENSE,
        "n_results": len(results),
        "n_registered": len(wines),
        "n_with_spec": sum(1 for w in wines if w["spec_url"]),
        "pending_applications": pending,
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(f"[done] register: {len(wines)} registered wine GIs "
          f"({sum(1 for w in wines if w['spec_url'])} with a product specification), "
          f"{len(pending)} pending → {INDEX_PATH.relative_to(ROOT)}", file=sys.stderr)

    # ---- 2. ONS boundaries -----------------------------------------
    ONS_DIR.mkdir(parents=True, exist_ok=True)
    layers: dict[str, dict] = {}
    for fname, spec in ONS_LAYERS.items():
        out_path = ONS_DIR / fname
        if out_path.exists() and not args.refresh:
            fc = json.loads(out_path.read_text(encoding="utf-8"))
        else:
            fc = fetch_ons_layer(session, spec)
            out_path.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
        feats = fc.get("features") or []
        if fc.get("exceededTransferLimit"):
            print(f"[error] {fname}: exceededTransferLimit — result truncated",
                  file=sys.stderr)
            rc = 2
        if len(feats) != spec["expected"]:
            print(f"[warn] {fname}: got {len(feats)} features, "
                  f"expected {spec['expected']}", file=sys.stderr)
            rc = rc or 2
        data = out_path.read_bytes()
        layers[fname] = {
            "service": spec["service"],
            "label": spec["label"],
            "where": spec["where"],
            "sha256": _sha256(data),
            "bytes": len(data),
            "n_features": len(feats),
            "expected": spec["expected"],
        }

    ONS_MANIFEST.write_text(json.dumps({
        "generated_at": now,
        "source_url": ONS_FS,
        "license": ONS_LICENSE,
        "layers": layers,
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(f"[done] ONS boundaries → {ONS_DIR.relative_to(ROOT)}", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main())
