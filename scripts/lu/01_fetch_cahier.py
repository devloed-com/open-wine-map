"""Verify the IVV cahier des charges PDF is present + write a manifest
with provenance.

Pipeline stage 01 (lu).

Unlike the EU-OJ-fetching siblings (ES/IT/SI/HR/HU/RO/BG/GR/SK/CZ
stage 01), Luxembourg has no fetchable single-document URL — the
canonical specification is a single PDF hosted on the LU Ministry of
Agriculture site:

  https://agriculture.public.lu/dam-assets/veroeffentlichungen/
  dokumentationen/weinbau/oenologie/
  2020-cahier-des-charges-aop-moselle-luxembourgeoise.pdf

Programmatic fetch via python-requests / curl from a sandbox keeps
returning HTTP 000 (TCP reset against agriculture.public.lu's WAF).
The curator workflow is therefore a one-off manual download into
``raw/lu/ivv/cahiers/2020-cahier.pdf`` — same shape as the FR
``manual_overrides.json`` pattern (memory: ``feedback_manual_downloads_ok``).

This stage verifies the PDF + auxiliary IVV-Weinbaukartei shapefile
are present, computes sha256s, regenerates the ``pdftotext -layout``
sidecar text if stale, and writes a manifest with full provenance.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAHIER_DIR = ROOT / "raw" / "lu" / "ivv" / "cahiers"
CAHIER_PDF = CAHIER_DIR / "2020-cahier.pdf"
CAHIER_TXT = CAHIER_DIR / "2020-cahier.txt"
IVV_VINEYARDS_DIR = ROOT / "raw" / "lu" / "ivv" / "vineyards"
IVV_VINEYARDS_SHP = IVV_VINEYARDS_DIR / "weinberge-lu-2022" / "weinberge_lu_2022.shp"
MANIFEST_PATH = ROOT / "raw" / "lu" / "ivv" / "manifest.json"

CAHIER_SOURCE_URL = (
    "https://agriculture.public.lu/dam-assets/veroeffentlichungen/"
    "dokumentationen/weinbau/oenologie/"
    "2020-cahier-des-charges-aop-moselle-luxembourgeoise.pdf"
)
CAHIER_PUBLISHER = (
    "Institut Viti-Vinicole / Ministère de l'Agriculture, "
    "Grand-Duché de Luxembourg"
)
CAHIER_REGLEMENTS = (
    {
        "title": "Règlement grand-ducal du 9 septembre 2009 déclarant "
                 "obligatoire le périmètre viticole",
        "eli": "https://legilux.public.lu/eli/etat/leg/rgd/2009/09/09/n2/jo",
    },
    {
        "title": "Règlement grand-ducal du 6 mai 2004 fixant les variétés "
                 "de vignes recommandées, autorisées et tolérées … "
                 "(modifié 26 novembre 2014)",
        "eli": "https://legilux.public.lu/eli/etat/leg/rgd/2014/11/26/n2/jo",
    },
    {
        "title": "Règlement grand-ducal du 17 décembre 2015 fixant "
                 "certaines modalités d'application du Règl. (CEE) 607/2009 "
                 "(étiquetage AOP + Crémant)",
        "eli": "https://legilux.public.lu/eli/etat/leg/rgd/2015/12/17",
    },
)

IVV_VINEYARDS_SOURCE_URL = "https://data.public.lu/en/datasets/vineyards/"
IVV_VINEYARDS_PUBLISHER = "Institut Viti-Vinicole — Weinbaukartei (vineyard registry) 2022"
# TODO(curator): verify the exact licence shown on data.public.lu when the
# dataset is re-downloaded. data.public.lu's IVV organisation page typically
# uses CC-BY 4.0 / CC0; the existing IT/CZ Eurostat-shared datasets do the
# same. This value is the project's working assumption until confirmed.
IVV_VINEYARDS_LICENCE = "Open Data Luxembourg (CC-BY 4.0 / CC0 — pending curator confirmation)"


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def ensure_pdftotext(pdf: Path, txt: Path) -> bool:
    """Regenerate ``txt`` from ``pdf`` if missing or older than the
    PDF. Returns True if the sidecar text exists at end of call."""
    if txt.exists() and txt.stat().st_mtime >= pdf.stat().st_mtime:
        return True
    if shutil.which("pdftotext") is None:
        print(
            "[warn] pdftotext binary not on $PATH — install poppler "
            "(brew install poppler) so stage 02 can read the cahier",
            file=sys.stderr,
        )
        return txt.exists()
    print(f"[pdftotext] -layout {pdf.name}", file=sys.stderr)
    subprocess.run(
        ["pdftotext", "-layout", str(pdf), str(txt)],
        check=True,
    )
    return txt.exists()


def main() -> int:
    if not CAHIER_PDF.exists():
        print(
            f"[error] cahier PDF missing at {CAHIER_PDF.relative_to(ROOT)}.\n"
            f"        Download manually from:\n"
            f"          {CAHIER_SOURCE_URL}\n"
            f"        (sandbox curl/python-requests get HTTP 000 — TCP reset).",
            file=sys.stderr,
        )
        return 2

    has_txt = ensure_pdftotext(CAHIER_PDF, CAHIER_TXT)
    cahier_sha = sha256_file(CAHIER_PDF)
    cahier_size = CAHIER_PDF.stat().st_size

    ivv_present = IVV_VINEYARDS_SHP.exists()
    ivv_sha = sha256_file(IVV_VINEYARDS_SHP) if ivv_present else ""
    if not ivv_present:
        print(
            f"[warn] IVV vineyard shapefile missing at "
            f"{IVV_VINEYARDS_SHP.relative_to(ROOT)} — stage 04 will fall "
            f"back to GISCO admin polygons for sub-denominations. Download "
            f"from {IVV_VINEYARDS_SOURCE_URL} (zip → unpack under "
            f"raw/lu/ivv/vineyards/weinberge-lu-2022/).",
            file=sys.stderr,
        )

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    MANIFEST_PATH.write_text(json.dumps({
        "generated_at": now,
        "cahier": {
            "path": str(CAHIER_PDF.relative_to(ROOT)),
            "source_url": CAHIER_SOURCE_URL,
            "publisher": CAHIER_PUBLISHER,
            "sha256": cahier_sha,
            "bytes": cahier_size,
            "pdftotext_sidecar": str(CAHIER_TXT.relative_to(ROOT)) if has_txt else "",
            "reglements": list(CAHIER_REGLEMENTS),
            "license_note": (
                "Public regulator document published by the LU Ministry of "
                "Agriculture / IVV. Re-distribution with attribution is "
                "consistent with Luxembourg's open-data principles for "
                "government publications. Cite the original URL when "
                "rendering."
            ),
        },
        "ivv_vineyards": {
            "present": ivv_present,
            "path": str(IVV_VINEYARDS_SHP.relative_to(ROOT)) if ivv_present else "",
            "source_url": IVV_VINEYARDS_SOURCE_URL,
            "publisher": IVV_VINEYARDS_PUBLISHER,
            "license_note": IVV_VINEYARDS_LICENCE,
            "sha256_shp": ivv_sha,
        },
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    print(
        f"[done] cahier sha256={cahier_sha[:12]}… bytes={cahier_size} "
        f"pdftotext={'yes' if has_txt else 'no'} "
        f"ivv_vineyards={'yes' if ivv_present else 'no'} "
        f"→ {MANIFEST_PATH.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
