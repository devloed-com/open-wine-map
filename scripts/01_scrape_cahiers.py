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
# Optional human-curated overrides: when INAO's product/show_texte pages
# don't surface a usable BO Agri PDF for an appellation, you can hand-add
# one (or more) document_administratif URLs here. Stage 01 treats them as
# additional candidate PDFs alongside whatever the scraper finds, so
# stage 02's cross-bundle rescue can promote the matching cahier.
# Schema:
#   {
#     "<id_appellation>": {
#       "name": "<appellation name, for cross-checking>",
#       "boagri_urls": ["https://info.agriculture.gouv.fr/.../document_administratif-…/telechargement", …],
#       "note": "free-form provenance: where you found it, JORF page, etc."
#     }, …
#   }
# Missing file is fine — overrides are optional. See CLAUDE.md for the
# workflow that pairs this with the human-facing BO Agri search UI.
MANUAL_OVERRIDES_PATH = OUT_DIR / "manual_overrides.json"

UA = "open-wine-map-bot/0.1 (+https://github.com/devloed-com/open-wine-map; INAO cahier mirror)"
WWW2_PRODUCT = "https://www2.inao.gouv.fr/produit/{idproduit}"
WWW2_SHOW_TEXTE = "https://www2.inao.gouv.fr{path}"

# Pulls the cahier des charges link off a www2 product page.
CAHIER_TEXT_LINK_RE = re.compile(
    r'<a\s+href="(/show_texte/\d+)"[^>]*>\s*acc[ée]der au cahier des charges',
    re.IGNORECASE,
)
# Any /show_texte/<id> link on the product page — older décrets, modifying
# arrêtés, related notices. Used as fallback candidates when the canonical
# "accéder au cahier des charges" link doesn't resolve to a useful PDF.
SHOW_TEXTE_LINK_RE = re.compile(
    r'href="(?:https?://www2\.inao\.gouv\.fr)?(/show_texte/(\d+))"',
    re.IGNORECASE,
)
# BO Agri (Bulletin Officiel Agriculture) PDF download URL — the canonical
# cahier file. The endpoint serves application/pdf with stable UUIDs.
BOAGRI_RE = re.compile(
    r"https://info\.agriculture\.gouv\.fr/[^\"\s]*/document_administratif-[0-9a-f-]+/telechargement",
    re.IGNORECASE,
)
# Légifrance JORFTEXT id — points at the original consolidated décret on
# legifrance.gouv.fr. The page is Cloudflare-walled so we can't fetch the
# PDF here, but we record the id so a later resolver (PISTE API,
# cloudscraper) can pick it up.
LEGIFRANCE_JORFTEXT_RE = re.compile(r"cidTexte=(JORFTEXT\d+)", re.IGNORECASE)


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


def _collect_show_texte_paths(html: str, canonical_first: str) -> list[str]:
    """Canonical show_texte path first, then every other /show_texte/<id>
    on the product page in document order (deduped). Older décrets,
    modifying arrêtés, and related notices are all retained — Phase 2's
    cross-bundle rescue treats them as candidate sources."""
    paths: list[str] = [canonical_first]
    for m in SHOW_TEXTE_LINK_RE.finditer(html):
        path = m.group(1)
        if path not in paths:
            paths.append(path)
    return paths


def _harvest_show_texte(
    session: requests.Session, paths: list[str], delay: float
) -> tuple[list[str], list[str]]:
    """Walk show_texte pages and return (boagri_urls, legifrance_jorftext_ids).

    Both lists preserve first-seen order and dedup across the walk.
    """
    boagri: list[str] = []
    legifrance: list[str] = []
    for path in paths:
        url = WWW2_SHOW_TEXTE.format(path=path)
        try:
            sr = session.get(url, timeout=30)
        except requests.RequestException:
            continue
        time.sleep(delay)
        if sr.status_code != 200:
            continue
        for bu in BOAGRI_RE.findall(sr.text):
            if bu not in boagri:
                boagri.append(bu)
        for jid in LEGIFRANCE_JORFTEXT_RE.findall(sr.text):
            if jid not in legifrance:
                legifrance.append(jid)
    return boagri, legifrance


def resolve_cahier(
    session: requests.Session, app: Appellation, delay: float
) -> tuple[dict, list[str]] | None:
    """Walk www2 product page → show_texte → BO Agri, broadly.

    Returns ({metadata}, [boagri_url, ...]) — the metadata records the
    canonical product/show_texte pair, and the URL list contains every
    BO Agri PDF reachable through that product's show_texte links
    (canonical first). Returns None when every product page miss-routes
    or returns no usable links.

    INAO's "accéder au cahier des charges" link often points at a
    *modification arrêté* PDF that re-publishes only some of the cahiers
    it modifies. By also collecting BO Agri URLs from every other
    show_texte link on the same product page, we widen the corpus so
    stage 02's cross-bundle rescue has a chance to find the AOC's cahier
    in a sibling JORF issue. Légifrance JORFTEXT ids are recorded for
    future resolvers (the legifrance.gouv.fr site is Cloudflare-walled).
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

        canonical_match = CAHIER_TEXT_LINK_RE.search(r.text)
        if not canonical_match:
            last_err = f"no cahier link on {prod_url}"
            continue

        canonical_show = canonical_match.group(1)
        show_paths = _collect_show_texte_paths(r.text, canonical_show)
        boagri_urls, legifrance_ids = _harvest_show_texte(session, show_paths, delay)

        if not boagri_urls and not legifrance_ids:
            last_err = (
                f"no BO Agri or Légifrance links across "
                f"{len(show_paths)} show_texte page(s)"
            )
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
            "show_texte_url": WWW2_SHOW_TEXTE.format(path=canonical_show),
            "show_texte_paths": show_paths,
            "boagri_url": boagri_urls[0] if boagri_urls else "",
            "boagri_url_candidates": boagri_urls,
            "legifrance_jorftext_ids": legifrance_ids,
        }
        return meta, boagri_urls

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


def _download_alt_candidates(
    session: requests.Session, app_name: str, urls: list[str], delay: float
) -> int:
    """Pull alternate candidate PDFs for `app_name`. Each download is
    content-addressed in the cahiers dir, so PDFs already present no-op.
    Returns the number of candidates we actually attempted."""
    n = 0
    for url in urls:
        try:
            _, _ = download_pdf(session, url, OUT_DIR)
            n += 1
        except (requests.RequestException, RuntimeError) as exc:
            print(f"[warn] {app_name} alt: {exc}", file=sys.stderr)
        time.sleep(delay)
    return n


def _process_override_only(
    session: requests.Session, app: Appellation, manifest: dict,
    override: dict, delay: float,
) -> tuple[str, int]:
    """INAO didn't surface any candidates but a manual override is set.
    Download the override URLs and seed a manifest entry from them so
    stage 02's cross-bundle rescue can pick this AOC up."""
    sample = app.products[0] if app.products else {}
    meta = {
        "name": app.name,
        "canonical_idproduit": "",
        "canonical_produit": "",
        "signe_fr": sample.get("signe_fr", ""),
        "signe_ue": sample.get("signe_ue", ""),
        "categorie": sample.get("categorie", ""),
        "comite_regional": sample.get("comite_regional", ""),
        "product_url": "",
        "show_texte_url": "",
        "show_texte_paths": [],
        "boagri_url": "",
        "boagri_url_candidates": [],
        "legifrance_jorftext_ids": [],
        "manual_override_note": override.get("note", ""),
    }
    n = _download_alt_candidates(session, app.name, override["boagri_urls"], delay)
    try:
        digest, dest = download_pdf(session, override["boagri_urls"][0], OUT_DIR)
    except (requests.RequestException, RuntimeError) as exc:
        print(f"[fail] {app.name} override: {exc}", file=sys.stderr)
        return "missed", n
    meta["filename"] = dest.name
    meta["sha256"] = digest
    meta["boagri_url"] = override["boagri_urls"][0]
    meta["fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest[app.id_appellation] = meta
    return "override-only", n


def _process_app(
    session: requests.Session, app: Appellation, manifest: dict,
    overrides: dict, delay: float,
) -> tuple[str, int]:
    """Resolve and download `app`'s cahier(s). Returns (status, alt_count)
    where status is one of: missed, cached, fetched, legifrance-only,
    override-only.
    """
    prior = manifest.get(app.id_appellation, {})
    override = overrides.get(app.id_appellation)
    has_override_urls = bool(override and override.get("boagri_urls"))

    result = resolve_cahier(session, app, delay)
    time.sleep(delay)
    if result is None:
        if has_override_urls:
            return _process_override_only(session, app, manifest, override, delay)
        return "missed", 0
    meta, pdf_urls = result
    if has_override_urls:
        for url in override["boagri_urls"]:
            if url not in pdf_urls:
                pdf_urls.append(url)
        meta["boagri_url_candidates"] = pdf_urls
        meta["manual_override_note"] = override.get("note", "")

    if not pdf_urls:
        meta["filename"] = ""
        meta["sha256"] = ""
        meta["fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        manifest[app.id_appellation] = meta
        return "legifrance-only", 0

    canonical_url = pdf_urls[0]
    prior_dest = OUT_DIR / f"{prior.get('sha256', '')}.pdf"
    if prior.get("boagri_url") == canonical_url and prior_dest.exists():
        n = _download_alt_candidates(session, app.name, pdf_urls[1:], delay)
        return "cached", n

    try:
        digest, dest = download_pdf(session, canonical_url, OUT_DIR)
    except (requests.RequestException, RuntimeError) as exc:
        print(f"[fail] {app.name}: {exc}", file=sys.stderr)
        return "missed", 0

    n = _download_alt_candidates(session, app.name, pdf_urls[1:], delay)
    meta["filename"] = dest.name
    meta["sha256"] = digest
    meta["fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest[app.id_appellation] = meta
    return "fetched", n


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
    overrides: dict = (
        json.loads(MANUAL_OVERRIDES_PATH.read_text())
        if MANUAL_OVERRIDES_PATH.exists() else {}
    )
    if overrides:
        print(f"[overrides] {len(overrides)} manual entr(ies) loaded", file=sys.stderr)

    if args.retry_misses:
        appellations = [a for a in appellations if a.id_appellation not in manifest]

    if args.limit:
        appellations = appellations[: args.limit]

    print(f"[plan] {len(appellations)} appellations to consider", file=sys.stderr)

    session = requests.Session()
    session.headers["User-Agent"] = UA

    fetched = cached = missed = extra = 0
    counters = {
        "fetched": 0, "cached": 0, "missed": 0,
        "legifrance-only": 0, "override-only": 0,
    }

    for app in tqdm(appellations, desc="cahiers", leave=False):
        status, alt_count = _process_app(
            session, app, manifest, overrides, args.delay
        )
        counters[status] += 1
        extra += alt_count
        time.sleep(args.delay)

    fetched = counters["fetched"] + counters["override-only"]
    cached = counters["cached"]
    missed = counters["missed"] + counters["legifrance-only"]

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False))

    print(
        f"[done] fetched={fetched} cached={cached} extra={extra} missed={missed} "
        f"manifest={MANIFEST_PATH.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0 if missed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
