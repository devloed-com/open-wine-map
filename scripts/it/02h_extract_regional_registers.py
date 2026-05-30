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


def process_region(region: str, cfg: dict, refresh: bool) -> dict:
    pdf = REG_DIR / f"{region}.pdf"
    if refresh or not pdf.exists():
        r = requests.get(cfg["url"], headers={"User-Agent": UA}, timeout=60)
        r.raise_for_status()
        pdf.write_bytes(r.content)
    body = pdf.read_bytes()
    varieties = parse_register(_pdftotext(pdf), cfg["template"])
    sidecar = {
        "region": region,
        "source": {
            "url": cfg["url"],
            "source_org": cfg.get("source_org", ""),
            "note": cfg.get("note", ""),
            "template": cfg["template"],
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
