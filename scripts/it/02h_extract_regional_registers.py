"""Stage 02h (IT) — per-region authorised-variety register extraction.

Several Italian regional IGTs (IGT Umbria, Lazio, Calabria, Campania,
Sicilia + their sub-IGTs) define their grape roster by reference to the
Region's authorised-variety register ("i vitigni idonei alla coltivazione
nella Regione X, riportati nell'allegato 1"), and that annex is absent
from the consolidated MASAF disciplinare PDF. This stage downloads each
Region's published register (an official act of the Region, public-domain
under art. 5 L. 633/1941), parses the variety table via
`_lib.it.regional_register`, and writes one sidecar per region under
raw/it/regional-variety-registers/<region>.json with full provenance.

Stage 04 (`augment_it_records_with_regional_registers`) merges a region's
roster into the empty-grape IGTs listed in that region's `igts` array in
sources.json.

  uv run scripts/it/02h_extract_regional_registers.py            # all regions
  uv run scripts/it/02h_extract_regional_registers.py --region umbria
  uv run scripts/it/02h_extract_regional_registers.py --refresh  # re-fetch PDFs
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from _lib.it.regional_register import parse_register  # noqa: E402

REG_DIR = ROOT / "raw" / "it" / "regional-variety-registers"
SOURCES = REG_DIR / "sources.json"
UA = "open-wine-map/1.0 (winemap@devloed.com)"


def _pdftotext(path: Path) -> str:
    return subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        capture_output=True, text=True, check=True,
    ).stdout


CATALOGOVITI_SEARCH = "http://catalogoviti.politicheagricole.it/post1.php"
CATALOGOVITI_PAGE_SIZE = 50


def fetch_catalogoviti_province(province_code: str) -> list[list]:
    """Every wine-grape variety (clones excluded — `filtro00`) the MASAF
    Registro Nazionale classifies as idonea alla coltivazione in one
    province, walking the search endpoint's 50-row pages. Same query the
    site's Ricerca form issues (see the page's `aggiornamento()`)."""
    rows: list[list] = []
    page = 1
    while True:
        r = requests.get(
            CATALOGOVITI_SEARCH,
            params={
                "varieta": "", "codice": "", "nclone": "", "codice_clone": "",
                "gazzetta": "", "colore": "", "catalogo": "UV",
                "province": province_code, "denominazione": "",
                "sortname": "sort1", "sortorder": "sorting asc",
                "page": page, "filtro00": "true",
            },
            headers={"User-Agent": UA}, timeout=60,
        )
        r.raise_for_status()
        data = json.loads(r.content.decode("latin-1"))
        rows.extend(data.get("rows") or [])
        stats = data.get("stats") or {}
        if int(stats.get("end", 0)) >= int(stats.get("total", 0)) or not data.get("rows"):
            return rows
        page += 1


def _fetch_register_body(region: str, cfg: dict, refresh: bool) -> tuple[bytes, str]:
    """(cached bytes, text handed to the parser) for one region. A PDF
    register is fetched to `<region>.pdf` and read through pdftotext; a
    catalogoviti register is the JSON of the per-province rows, cached
    to `<region>.catalogoviti.json` and parsed as-is."""
    if cfg.get("format") == "catalogoviti":
        cache = REG_DIR / f"{region}.catalogoviti.json"
        if refresh or not cache.exists():
            provinces = {
                code: {"name": name, "rows": fetch_catalogoviti_province(code)}
                for code, name in cfg["provinces"].items()
            }
            cache.write_text(json.dumps({
                "endpoint": CATALOGOVITI_SEARCH,
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "provinces": provinces,
            }, ensure_ascii=False, indent=1), encoding="utf-8")
        body = cache.read_bytes()
        return body, body.decode("utf-8")
    pdf = REG_DIR / f"{region}.pdf"
    if refresh or not pdf.exists():
        r = requests.get(cfg["url"], headers={"User-Agent": UA}, timeout=60)
        r.raise_for_status()
        pdf.write_bytes(r.content)
    return pdf.read_bytes(), _pdftotext(pdf)


def process_region(region: str, cfg: dict, refresh: bool) -> dict:
    body, text = _fetch_register_body(region, cfg, refresh)
    varieties = parse_register(text, cfg["template"])
    sidecar = {
        "region": region,
        "source": {
            "url": cfg["url"],
            "source_org": cfg.get("source_org", ""),
            "note": cfg.get("note", ""),
            "template": cfg["template"],
            "format": cfg.get("format", "pdf"),
            "provinces": cfg.get("provinces", {}),
            "sha256": hashlib.sha256(body).hexdigest(),
            "bytes": len(body),
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "igts": cfg.get("igts", []),
        "n_varieties": len(varieties),
        "varieties": varieties,
    }
    (REG_DIR / f"{region}.json").write_text(
        json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
    return sidecar


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--region", default=None, help="process one region")
    ap.add_argument("--refresh", action="store_true", help="re-fetch the PDFs")
    args = ap.parse_args(argv)

    sources = json.loads(SOURCES.read_text(encoding="utf-8"))
    regions = {k: v for k, v in sources.items() if not k.startswith("_")}
    if args.region:
        regions = {args.region: regions[args.region]}

    for region, cfg in regions.items():
        sc = process_region(region, cfg, args.refresh)
        print(f"[ok] {region:10} {sc['n_varieties']:>3} varieties "
              f"→ {len(sc['igts'])} IGT(s): {', '.join(sc['igts'])}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
