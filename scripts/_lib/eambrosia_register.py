"""Client for the EU GI register public API (eAmbrosia, new register).

Resolves a GI file number to its register attachments — the EU **single
document / fiche technique** (`singleDocTechFile`) and the **full national
cahier des charges** (`productSpecifications`) — both reachable as PDFs
even for grandfathered Art.107/Reg.1308/2013 wines whose old-API
`publications` array is empty. This is the corpus-wide source behind the
per-country register-fiche national-spec layers (see the project memory
`project_eambrosia_attachment_endpoint` + the CLAUDE.md endpoint section).

Resolver recipe (verified 2026-06-01 spike, 47/47 sample):

1. file_number → internal id. **Not** `int(giIdentifier[4:])` — that 500s
   for ~1/3 of GIs. Resolve from the bulk filter listing
   (`POST /api/gi-applications/filter {"filters":[]}`), cached to
   `raw/eambrosia-register/filenumber-id-map.json`.
2. `GET /api/gi-applications/id/<id>` (NOTE: no `/v1/`) → read
   `singleDocTechFile[].uri` + `productSpecifications[].uri`.
3. `GET /api/v1/attachments/<uri>` → the PDF. Browser-gated: real browser
   UA + an `Accept` WITHOUT `application/pdf` (an explicit pdf Accept trips
   the stub gate); answers HTTP 202 with the PDF body.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests

API = "https://ec.europa.eu/geographical-indications-register/eambrosia-public-api"
_FILTER_URL = f"{API}/api/gi-applications/filter"
_GI_DETAIL_URL = f"{API}/api/gi-applications/id/{{gid}}"  # no /v1/ on this path
ATTACHMENT_URL = f"{API}/api/v1/attachments/{{uri}}"

# Browser UA + an Accept WITHOUT application/pdf — the attachment endpoint's
# anti-bot gate serves a 3 KB HTML stub otherwise, and answers 202+body.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
}
_JSON_HEADERS = {"User-Agent": BROWSER_HEADERS["User-Agent"], "Accept": "application/json"}

ROOT = Path(__file__).resolve().parents[2]
ID_MAP_CACHE = ROOT / "raw" / "eambrosia-register" / "filenumber-id-map.json"


def load_id_map(refresh: bool = False, session: requests.Session | None = None) -> dict[str, int]:
    """Return {file_number: internal_id} for every GI in the register.

    One ~4 MB POST covers all ~4000 GIs; cached on disk and reused unless
    `refresh`."""
    if ID_MAP_CACHE.exists() and not refresh:
        try:
            return json.loads(ID_MAP_CACHE.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    s = session or requests.Session()
    r = s.post(
        _FILTER_URL,
        headers={**_JSON_HEADERS, "Content-Type": "application/json"},
        json={"first": 0, "rows": 100000, "showTSGs": "false", "filters": []},
        timeout=180,
    )
    r.raise_for_status()
    rows = r.json().get("results", [])
    id_map = {
        row["fileName"]: row["id"]
        for row in rows
        if row.get("fileName") and row.get("id") is not None
    }
    ID_MAP_CACHE.parent.mkdir(parents=True, exist_ok=True)
    ID_MAP_CACHE.write_text(json.dumps(id_map, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return id_map


def gi_detail(
    file_number: str, id_map: dict[str, int], session: requests.Session | None = None,
) -> dict | None:
    """Return the GI-application detail JSON, or None if unresolved."""
    gid = id_map.get(file_number)
    if gid is None:
        return None
    s = session or requests.Session()
    try:
        r = s.get(_GI_DETAIL_URL.format(gid=gid), headers=_JSON_HEADERS, timeout=60)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except ValueError:
        return None


def attachment_refs(
    file_number: str, id_map: dict[str, int], session: requests.Session | None = None,
) -> dict | None:
    """Return {single_doc_uri, single_doc_ref, cahier_uri, cahier_name,
    file_name} for a file number, or None if the GI doesn't resolve. Any
    individual uri may be None."""
    d = gi_detail(file_number, id_map, session)
    if d is None:
        return None
    sdt = (d.get("singleDocTechFile") or [{}])[0]
    ps = (d.get("productSpecifications") or [{}])[0]
    return {
        "file_name": d.get("fileName"),
        "single_doc_uri": sdt.get("uri"),
        "single_doc_ref": sdt.get("text"),
        "cahier_uri": ps.get("uri"),
        "cahier_name": ps.get("text"),
    }


def fetch_attachment(
    uri: str, dest: Path, session: requests.Session | None = None, retries: int = 3,
) -> bool:
    """Download attachment `uri` to `dest` (a PDF). Handles the browser gate
    + HTTP 202-with-body; verifies a real `%PDF` payload. Returns success."""
    s = session or requests.Session()
    url = ATTACHMENT_URL.format(uri=uri)
    for attempt in range(retries):
        try:
            r = s.get(url, headers=BROWSER_HEADERS, timeout=90, allow_redirects=True)
        except requests.RequestException:
            time.sleep(1.5 * (attempt + 1))
            continue
        ctype = (r.headers.get("Content-Type") or "").lower()
        if r.status_code in (200, 202) and "pdf" in ctype and r.content[:5].startswith(b"%PDF"):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r.content)
            return True
        time.sleep(1.5 * (attempt + 1))
    return False
