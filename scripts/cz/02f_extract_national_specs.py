"""Extract Czech national-spec data from the two implementing decrees
that pin every Czech wine GI's authorised varieties + delimited area.

Pipeline stage 02f (cz). Sibling of `scripts/es/02f_extract_national_pliegos.py`
and `scripts/it/02f_extract_masaf.py` — fills the gap left by stage 02
when an eAmbrosia entry carries no fetchable EU-OJ Jednotný dokument.

Two source documents (both published in Sbírka zákonů, fetched from the
zakonyprolidi.cz mirror because eSbírka is a JS SPA; Sbírka is the
canonical attribution):

  1. **Vyhláška č. 88/2017 Sb.**, Příloha č. 2 — the national variety
     table. Three colour blocks (35 white + 26 red + 6 zemské-víno
     varieties = 67 total). The same list applies to every Czech
     jakostní víno regardless of podoblast (CZ wine law does not
     restrict varieties per appellation).

  2. **Vyhláška č. 254/2010 Sb.**, Příloha — the per-podoblast obec list
     (3-column table with `<td rowspan>` cells for the obec / KÚ / trať
     hierarchy). Feeds commune-union geometry for the 6 podoblasti.

Outputs:
  - raw/cz/national-specs/vyhlaska-88-2017.html  (cached source HTML)
  - raw/cz/national-specs/vyhlaska-254-2010.html  (cached source HTML)
  - raw/cz/national-specs/varieties.json  (parsed national variety roster)
  - raw/cz/national-specs/communes/<podoblast-slug>.json  (per-podoblast
    obec list, 6 files)
  - raw/cz/national-specs/manifest.json  (provenance + counts)

Re-runnable: cached HTMLs are kept; pass --refresh to re-fetch.
The sidecar JSONs are always regenerated when the HTML changes
(sha256 tracked in the manifest).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.cz.national_spec import parse_commune_tree, parse_varieties  # noqa: E402

OUT_DIR = ROOT / "raw" / "cz" / "national-specs"
COMMUNES_DIR = OUT_DIR / "communes"
MANIFEST_PATH = OUT_DIR / "manifest.json"

UA = (
    "open-wine-map/0.0.1 (https://github.com/devloed-com/open-wine-map; "
    "mailto:winemap@devloed.com) python-requests"
)

# Each source is fetched from zakonyprolidi.cz (the most accessible CZ-law
# mirror — eSbírka is a JS SPA, the Sbírka scan-PDF is image-only).
# The canonical attribution is the Sbírka zákonů PDF URL.
SOURCES: dict[str, dict[str, str]] = {
    "vyhlaska-88-2017": {
        "fetch_url": "https://www.zakonyprolidi.cz/cs/2017-88",
        "canonical_url": (
            "https://aplikace.mv.gov.cz/sbirka-zakonu/ViewFile.aspx"
            "?type=c&id=61787"
        ),
        "title": (
            "Vyhláška č. 88/2017 Sb., kterou se provádějí některá "
            "ustanovení zákona o vinohradnictví a vinařství"
        ),
        "sbirka_castka": "32/2017",
        "purpose": "varieties",
    },
    "vyhlaska-254-2010": {
        "fetch_url": "https://www.zakonyprolidi.cz/cs/2010-254",
        "canonical_url": (
            "https://aplikace.mv.gov.cz/sbirka-zakonu/ViewFile.aspx"
            "?type=c&id=5785"
        ),
        "title": (
            "Vyhláška č. 254/2010 Sb., kterou se stanoví seznam "
            "vinařských podoblastí, vinařských obcí a viničních tratí"
        ),
        "sbirka_castka": "92/2010",
        "purpose": "communes",
    },
}


def fetch_html(url: str, dest: Path, *, refresh: bool, throttle: float = 0.5) -> tuple[bytes, bool]:
    if dest.exists() and not refresh:
        body = dest.read_bytes()
        return body, True
    if throttle:
        time.sleep(throttle)
    print(f"[02f/cz] fetch {url}", file=sys.stderr)
    r = requests.get(
        url,
        headers={"User-Agent": UA, "Accept": "text/html"},
        timeout=60,
    )
    r.raise_for_status()
    dest.write_bytes(r.content)
    return r.content, False


def write_varieties_sidecar(html: bytes, src_meta: dict) -> dict:
    parsed = parse_varieties(html.decode("utf-8", errors="replace"))
    payload = {
        "country": "cz",
        "source_lang": "cs",
        "source_anchor": parsed.get("source_anchor", ""),
        "source_title": src_meta["title"],
        "source_canonical_url": src_meta["canonical_url"],
        "source_sbirka_castka": src_meta["sbirka_castka"],
        "source_fetch_url": src_meta["fetch_url"],
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_total": len(parsed["varieties"]),
        "n_white": parsed["n_white"],
        "n_red": parsed["n_red"],
        "n_zemske": parsed["n_zemske"],
        "varieties": parsed["varieties"],
    }
    (OUT_DIR / "varieties.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False),
        encoding="utf-8",
    )
    return payload


def write_communes_sidecars(html: bytes, src_meta: dict) -> dict:
    parsed = parse_commune_tree(html.decode("utf-8", errors="replace"))
    podoblasti = parsed.get("podoblasti", {})
    COMMUNES_DIR.mkdir(parents=True, exist_ok=True)
    summary: dict[str, dict] = {}
    for slug, d in podoblasti.items():
        payload = {
            "country": "cz",
            "source_lang": "cs",
            "podoblast_slug": slug,
            "podoblast_name": d["name"],
            "macro_region": d["macro_region"],
            "source_anchor": parsed.get("source_anchor", ""),
            "source_title": src_meta["title"],
            "source_canonical_url": src_meta["canonical_url"],
            "source_sbirka_castka": src_meta["sbirka_castka"],
            "source_fetch_url": src_meta["fetch_url"],
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "n_communes": len(d["communes"]),
            "communes": d["communes"],
        }
        out = COMMUNES_DIR / f"{slug}.json"
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False), encoding="utf-8")
        summary[slug] = {
            "name": d["name"],
            "macro_region": d["macro_region"],
            "n_communes": len(d["communes"]),
        }
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true",
                    help="re-fetch source HTMLs even if cached")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "license": (
            "Czech law text is public per §3(d) of the Czech Copyright Act "
            "(úřední dílo). Layout of the fetch source (zakonyprolidi.cz) "
            "is © AION CS; we extract only the law text. Canonical "
            "attribution is Sbírka zákonů."
        ),
        "sources": {},
    }

    n_varieties = 0
    n_podoblasti = 0
    for key, meta in SOURCES.items():
        dest = OUT_DIR / f"{key}.html"
        body, cached = fetch_html(meta["fetch_url"], dest, refresh=args.refresh)
        sha = hashlib.sha256(body).hexdigest()
        manifest["sources"][key] = {
            "fetch_url": meta["fetch_url"],
            "canonical_url": meta["canonical_url"],
            "title": meta["title"],
            "sbirka_castka": meta["sbirka_castka"],
            "purpose": meta["purpose"],
            "bytes": len(body),
            "sha256": sha,
            "cached": cached,
        }
        if meta["purpose"] == "varieties":
            v = write_varieties_sidecar(body, meta)
            n_varieties = v["n_total"]
            manifest["sources"][key]["parsed_counts"] = {
                "white": v["n_white"], "red": v["n_red"],
                "zemske": v["n_zemske"], "total": v["n_total"],
            }
        elif meta["purpose"] == "communes":
            s = write_communes_sidecars(body, meta)
            n_podoblasti = len(s)
            manifest["sources"][key]["parsed_counts"] = {
                "n_podoblasti": len(s),
                "n_communes_total": sum(d["n_communes"] for d in s.values()),
                "by_podoblast": s,
            }

    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2,
                                        sort_keys=True), encoding="utf-8")
    print(
        f"[02f/cz] varieties={n_varieties} podoblasti={n_podoblasti} "
        f"→ {OUT_DIR.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
