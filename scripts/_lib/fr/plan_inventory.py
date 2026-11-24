"""INAO's inventory of delimitation plans, and the communes holding a parcel area.

INAO's «portail des plans officiels de délimitation»
(https://www.inao.gouv.fr/portail-plans-delimitation, linked as «ici» under
the map of every product page) is a public Nextcloud share. Beside the scanned
plans it carries `inventaire_etat_de_la_delimitation.xlsx`, one row per
(appellation, commune): «Délimitation parcellaire attendu» oui / non, the
plan's state (plan disponible / plan en cours d'élaboration / Aucune parcelle
classée). INAO calls the plans the only legally binding delimitation documents.

The parcellaire shapefile on data.gouv.fr has no row for some AOCs (Champagne,
Cassis, Bellet), and the INAO aires-communes rows of Champagne are its aire
géographique, 635 communes, while the parcel area lies in 319 (INAO's product
page). The inventory names those 319 (visitor note on Coteaux champenois,
2026-11-22; triage of 2026-11-23). `PARCEL_AREA_TABLE`
(`parcel_area_communes.json`, checked in) says which records are drawn from
the communes holding their parcel area, and from which source:

- `inao-plan-inventory`: the inventory's communes whose «Délimitation
  parcellaire attendu» reads oui for the named appellation. The inventory
  writes a commune of today once per former commune (Blancs-Coteaux: three
  rows oui, one non); a commune counts when any of its rows reads oui;
- `cahier`: the communes the record's own cahier places its vines in, quoted
  (Rosé des Riceys: «vignes situées sur la commune des Riceys»).

Stage 00 fetches the spreadsheet (`fetch`) and keeps the oui rows of every
appellation as JSON; stage 04 reads the JSON (`communes_for`).
"""
from __future__ import annotations

import json
import re
import zipfile
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEST_DIR = ROOT / "raw" / "inao" / "plans-portal"
INVENTORY_XLSX = DEST_DIR / "inventaire_etat_de_la_delimitation.xlsx"
PARCEL_AREA_JSON = DEST_DIR / "parcel-area-communes.json"
PARCEL_AREA_TABLE = Path(__file__).resolve().parent / "parcel_area_communes.json"

SHARE_TOKEN = "AfChDpBNxYPolzH"
PORTAL_URL = "https://www.inao.gouv.fr/portail-plans-delimitation"
SHARE_URL = f"https://inao.cognix.cloud/index.php/s/{SHARE_TOKEN}"
WEBDAV = "https://inao.cognix.cloud/public.php/webdav/"
INVENTORY_PATH = "inventaire_etat_de_la_delimitation.xlsx"

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_HEADERS = {
    "A": "signe", "B": "appellation", "C": "insee", "D": "commune",
    "E": "attendu", "F": "plan", "G": "revision", "H": "plan_aire_geographique",
}


def read_rows(xlsx: Path) -> list[dict]:
    """The inventory's rows (the venv has no xlsx reader: the sheet XML is read
    as it is). INAO's INSEE codes lose their leading zero; they are padded."""
    with zipfile.ZipFile(xlsx) as z:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(f"{_NS}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{_NS}t")))
        rows: list[dict] = []
        with z.open("xl/worksheets/sheet1.xml") as fh:
            for _ev, el in ET.iterparse(fh):
                if el.tag != f"{_NS}row":
                    continue
                row: dict = {}
                for c in el.iter(f"{_NS}c"):
                    col = re.match(r"[A-Z]+", c.get("r") or "").group(0)
                    if col not in _HEADERS:
                        continue
                    v = c.find(f"{_NS}v")
                    if v is not None and v.text is not None:
                        val = shared[int(v.text)] if c.get("t") == "s" else v.text
                    else:
                        val = "".join(t.text or "" for t in c.iter(f"{_NS}t")) or None
                    row[_HEADERS[col]] = val.strip() if isinstance(val, str) else val
                rows.append(row)
                el.clear()
    if rows and rows[0].get("appellation") == "appellation":
        rows = rows[1:]
    for r in rows:
        code = str(r.get("insee") or "")
        r["insee"] = code.zfill(5) if code.isdigit() else code
    return rows


def parcel_area_communes(rows: list[dict]) -> dict[str, dict[str, dict]]:
    """appellation (lower case) → {INSEE: {commune, plans}} for the communes
    whose «Délimitation parcellaire attendu» reads oui in any row."""
    out: dict[str, dict[str, dict]] = {}
    for r in rows:
        if (r.get("attendu") or "").lower() != "oui":
            continue
        app = (r.get("appellation") or "").strip().lower()
        entry = out.setdefault(app, {}).setdefault(
            r["insee"], {"commune": r.get("commune") or "", "plans": []})
        state = (r.get("plan") or "").strip()
        if state and state not in entry["plans"]:
            entry["plans"].append(state)
    return out


def fetch(session, dest_dir: Path = DEST_DIR) -> dict:
    """Download the inventory from INAO's share and keep its oui rows."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    url = WEBDAV + INVENTORY_PATH
    r = session.get(url, auth=(SHARE_TOKEN, ""), timeout=300)
    r.raise_for_status()
    if not r.content.startswith(b"PK"):
        raise RuntimeError(f"{url}: not an xlsx ({r.headers.get('Content-Type')})")
    xlsx = dest_dir / INVENTORY_XLSX.name
    xlsx.write_bytes(r.content)
    rows = read_rows(xlsx)
    areas = parcel_area_communes(rows)
    (dest_dir / PARCEL_AREA_JSON.name).write_text(
        json.dumps(areas, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    return {
        "url": url, "share": SHARE_URL, "portal": PORTAL_URL,
        "path": str(xlsx.relative_to(ROOT)), "rows": len(rows),
        "appellations_with_parcel_area": len(areas),
        "last_modified": r.headers.get("Last-Modified", ""),
    }


@lru_cache(maxsize=1)
def table() -> dict[str, dict]:
    data = json.loads(PARCEL_AREA_TABLE.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


@lru_cache(maxsize=1)
def _inventory(path: Path = PARCEL_AREA_JSON) -> dict[str, dict[str, dict]]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def communes_for(slug: str) -> dict[str, str] | None:
    """INSEE → name of the communes holding the record's parcel area, or None
    when the record is not in the table or its source is not on disk."""
    entry = table().get(slug)
    if not entry:
        return None
    if entry["source"] == "cahier":
        return dict(entry["communes"])
    if entry["source"] == "inao-plan-inventory":
        got = _inventory().get(entry["appellation"])
        return {c: v["commune"] for c, v in got.items()} if got else None
    raise ValueError(f"{slug}: unknown parcel-area source {entry['source']!r}")
