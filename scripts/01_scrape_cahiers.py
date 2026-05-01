"""Scrape INAO cahiers des charges (cdc) PDFs for every wine appellation.

Pipeline stage 01.

Reads `raw/inao/siqo-referentiel.csv` (fetched by stage 00), groups by
`id_appellation`, and resolves each appellation's cahier through the legacy
www2.inao.gouv.fr stack:

    www2/produit/<idproduit>            (one row per appellation)
      → /show_texte/<text_id>           (link titled "accéder au cahier des charges")
        → info.agriculture.gouv.fr      (BO Agri "telechargement" — the actual PDF)

The newer www.inao.gouv.fr/produit/ pages serve empty bodies for many
appellations (Drupal cache misbehaviour); the legacy site renders reliably.
The cahier text is published to the JORF and mirrored on BO Agri, which is
where we ultimately download from.

Re-runnable: a manifest at `raw/inao/cahiers/manifest.json` records the
resolved show_texte id, BO Agri URL, and sha256 per appellation. Re-running
diffs against the manifest and only re-downloads what changed upstream.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import requests
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
SIQO_CSV = RAW / "inao" / "siqo-referentiel.csv"
OUT_DIR = RAW / "inao" / "cahiers"
MANIFEST_PATH = OUT_DIR / "manifest.json"

UA = "open-wine-map-bot/0.1 (+https://github.com/devloed-com/open-wine-map; INAO cahier mirror)"
WWW2_PRODUCT = "https://www2.inao.gouv.fr/produit/{idproduit}"
WWW2_SHOW_TEXTE = "https://www2.inao.gouv.fr{path}"

# Pulls the cahier des charges link off a www2 product page.
CAHIER_TEXT_LINK_RE = re.compile(
    r'<a\s+href="(/show_texte/\d+)"[^>]*>\s*acc[ée]der au cahier des charges',
    re.IGNORECASE,
)
# BO Agri (Bulletin Officiel Agriculture) PDF download URL — the canonical
# cahier file. The endpoint serves application/pdf with stable UUIDs.
BOAGRI_RE = re.compile(
    r"https://info\.agriculture\.gouv\.fr/[^\"\s]*/document_administratif-[0-9a-f-]+/telechargement",
    re.IGNORECASE,
)


@dataclass
class Appellation:
    id_appellation: str
    name: str
    products: list[dict] = field(default_factory=list)

    def canonical_product(self) -> dict:
        for p in self.products:
            if p["produit"].strip() == self.name.strip():
                return p
        return min(self.products, key=lambda p: len(p["produit"]))


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


WINE_SIGNS = {"AOC", "AOP", "IGP"}


def load_appellations(csv_path: Path) -> list[Appellation]:
    """Parse SIQO csv → list[Appellation], wine AOC/AOP/IGP + Publié only.

    SIQO bundles cider and a few stray Label Rouge entries under sector
    VITICOLE; we keep only rows with an AOC/AOP/IGP sign so the manifest
    matches what publishes a cahier des charges.
    """
    groups: dict[str, Appellation] = {}
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["secteur"].strip() != "VITICOLE":
                continue
            if row["lib_etat"].strip() != "Publié":
                continue
            sign = row["signe_fr"].strip() or row["signe_ue"].strip()
            if sign not in WINE_SIGNS:
                continue
            id_app = row["id_appellation"].strip()
            name = row["appellation"].strip()
            grp = groups.setdefault(id_app, Appellation(id_appellation=id_app, name=name))
            grp.products.append(
                {
                    "idproduit": row["idproduit"].strip(),
                    "produit": row["produit"].strip(),
                    "signe_fr": row["signe_fr"].strip(),
                    "signe_ue": row["signe_ue"].strip(),
                    "categorie": row["categorie"].strip(),
                    "comite_regional": row.get("comite_regional", "").strip(),
                }
            )
    return sorted(groups.values(), key=lambda a: a.name.lower())


def resolve_cahier(session: requests.Session, app: Appellation) -> tuple[dict, str] | None:
    """Walk www2 product page → show_texte → BO Agri.

    Returns ({metadata}, pdf_url) or None on failure.
    """
    last_err = None
    for product in app.products:
        prod_url = WWW2_PRODUCT.format(idproduit=product["idproduit"])
        try:
            r = session.get(prod_url, timeout=30)
        except requests.RequestException as exc:
            last_err = f"{type(exc).__name__} on {prod_url}: {exc}"
            continue
        if r.status_code != 200 or not r.text:
            last_err = f"HTTP {r.status_code} on {prod_url}"
            continue

        m = CAHIER_TEXT_LINK_RE.search(r.text)
        if not m:
            last_err = f"no cahier link on {prod_url}"
            continue

        show_texte_path = m.group(1)
        show_url = WWW2_SHOW_TEXTE.format(path=show_texte_path)
        try:
            sr = session.get(show_url, timeout=30)
        except requests.RequestException as exc:
            last_err = f"{type(exc).__name__} on {show_url}: {exc}"
            continue
        if sr.status_code != 200:
            last_err = f"HTTP {sr.status_code} on {show_url}"
            continue

        bm = BOAGRI_RE.search(sr.text)
        if not bm:
            last_err = f"no BO Agri link on {show_url}"
            continue

        meta = {
            "name": app.name,
            "canonical_idproduit": product["idproduit"],
            "canonical_produit": product["produit"],
            "signe_fr": product["signe_fr"],
            "signe_ue": product["signe_ue"],
            "categorie": product["categorie"],
            "comite_regional": product["comite_regional"],
            "product_url": prod_url,
            "show_texte_url": show_url,
            "boagri_url": bm.group(0),
        }
        return meta, bm.group(0)

    if last_err:
        print(f"[miss] {app.name} ({app.id_appellation}): {last_err}", file=sys.stderr)
    return None


def download_pdf(session: requests.Session, url: str, out_dir: Path) -> tuple[str, Path]:
    """Download `url` into a content-addressed PDF file under `out_dir`.

    Many BO Agri URLs serve a JORF "sommaire" that bundles multiple cahiers
    into a single PDF (e.g. all 51 Alsace grand crus reference one file).
    Storing by sha256 makes the dedupe automatic: 51 manifest entries map
    to one on-disk file. Returns (sha256, dest_path).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / f".part-{abs(hash(url))}.pdf"
    with session.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        if "pdf" not in r.headers.get("Content-Type", "").lower():
            raise RuntimeError(f"non-pdf content-type: {r.headers.get('Content-Type')}")
        h = hashlib.sha256()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                f.write(chunk)
                h.update(chunk)
    digest = h.hexdigest()
    dest = out_dir / f"{digest}.pdf"
    if dest.exists():
        tmp.unlink()
    else:
        tmp.rename(dest)
    return digest, dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0, help="stop after N appellations (0=all)")
    ap.add_argument("--only", action="append", default=[], help="match appellation name (substring, repeatable)")
    ap.add_argument("--delay", type=float, default=0.8, help="seconds between requests")
    ap.add_argument(
        "--retry-misses",
        action="store_true",
        help="only re-attempt appellations not yet in the manifest",
    )
    args = ap.parse_args()

    appellations = load_appellations(SIQO_CSV)
    if args.only:
        needles = [s.lower() for s in args.only]
        appellations = [a for a in appellations if any(n in a.name.lower() for n in needles)]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict = json.loads(MANIFEST_PATH.read_text()) if MANIFEST_PATH.exists() else {}

    if args.retry_misses:
        appellations = [a for a in appellations if a.id_appellation not in manifest]

    if args.limit:
        appellations = appellations[: args.limit]

    print(f"[plan] {len(appellations)} appellations to consider", file=sys.stderr)

    session = requests.Session()
    session.headers["User-Agent"] = UA

    fetched = cached = missed = 0

    for app in tqdm(appellations, desc="cahiers", leave=False):
        prior = manifest.get(app.id_appellation, {})

        result = resolve_cahier(session, app)
        time.sleep(args.delay)
        if result is None:
            missed += 1
            continue
        meta, pdf_url = result

        prior_dest = OUT_DIR / f"{prior.get('sha256', '')}.pdf"
        if prior.get("boagri_url") == pdf_url and prior_dest.exists():
            cached += 1
            continue

        try:
            digest, dest = download_pdf(session, pdf_url, OUT_DIR)
        except (requests.RequestException, RuntimeError) as exc:
            print(f"[fail] {app.name}: {exc}", file=sys.stderr)
            missed += 1
            continue

        meta["filename"] = dest.name
        meta["sha256"] = digest
        meta["fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        manifest[app.id_appellation] = meta
        fetched += 1

        time.sleep(args.delay)

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False))

    print(
        f"[done] fetched={fetched} cached={cached} missed={missed} "
        f"manifest={MANIFEST_PATH.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0 if missed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
