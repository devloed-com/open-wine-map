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

A final fallback tier reads the **eAmbrosia EU GI register**, which serves
the same INAO cahier PDF as an attachment (`RegisterTier`, bound to an
appellation by the name→file-number map stage 01d writes). It runs only after
BO Agri and the curator overrides have both failed, so appellations that
already resolve keep their canonical source; disable it with `--no-register`.

Re-runnable: a manifest at `raw/inao/cahiers/manifest.json` records the
resolved show_texte id, BO Agri URL, and sha256 per appellation. Re-running
diffs against the manifest and only re-downloads what changed upstream.
Register-sourced entries additionally carry `source_kind` +
`register_file_number` + the attachment uri, and their PDF is cached by
sha256 under `raw/inao/register/`.
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
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import eambrosia_register as er  # noqa: E402
from _lib.fr import register_cahier as rc  # noqa: E402

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


class RegisterTier:
    """Last-resort cahier source: the eAmbrosia EU GI register.

    The register serves the same INAO cahier PDF that BO Agri publishes, so an
    appellation BO Agri surfaces nothing for no longer needs a curator URL, a
    Légifrance cookie, or OCR over a professional-org mirror. It runs strictly
    *after* BO Agri and the curator overrides, and only for an appellation
    with no cahier PDF on disk — a run that fails to *reach* INAO must not
    re-source an appellation that already has one (an INAO outage is not an
    upstream change). Recovering an appellation whose product page links the
    *wrong* arrêté — a PDF that downloads fine but carries someone else's
    cahier — is a stage-02 question, not a stage-01 one, and is out of scope
    here.

    Requires the name → file-number map from stage 01d; without it the tier is
    inert. `raw/inao/register/` holds the attachment cache, deliberately
    outside `raw/inao/cahiers/` — only a PDF that actually wins a resolution
    is promoted there, because stage 02 indexes every PDF in that directory.
    """

    def __init__(self, session: requests.Session, delay: float, enabled: bool = True):
        self.session = session
        self.delay = delay
        self.resolved = rc.load_resolved() if enabled else {}
        self.manifest = rc.load_manifest() if enabled else {}
        self._id_map: dict[str, int] | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.resolved)

    @property
    def id_map(self) -> dict[str, int]:
        """Derived from the same cached GI listing stage 01d resolved names
        against, so a binding can never name a file number the id map lacks."""
        if self._id_map is None:
            try:
                self._id_map = er.id_map_from_rows(er.load_gi_rows(session=self.session))
            except (requests.RequestException, ValueError, OSError) as exc:
                print(f"[register] GI listing unavailable ({exc}); tier inert "
                      f"for the rest of this run", file=sys.stderr)
                self._id_map = {}
        return self._id_map

    def cahier_for(self, id_appellation: str) -> rc.RegisterCahier | None:
        """Fetch (or reuse) the register cahier bound to `id_appellation`."""
        binding = self.resolved.get(id_appellation)
        if not binding or not binding.get("file_number"):
            return None
        cahier, status = rc.fetch(
            binding["file_number"], self.id_map, self.manifest,
            session=self.session, delay=self.delay,
        )
        if cahier is None:
            print(f"[register] {binding.get('name', id_appellation)}: {status}",
                  file=sys.stderr)
            return None
        return cahier

    def save(self) -> None:
        if self.enabled:
            rc.save_manifest(self.manifest)


def _promote_register_pdf(cahier: rc.RegisterCahier) -> Path:
    """Copy a register attachment into the content-addressed cahiers dir so
    stage 02 finds it on its normal path.

    Written through a temp file then renamed, like `download_pdf`: stage 02
    indexes every PDF in this directory, and a half-written file under a name
    that asserts a sha256 it does not have would be picked up as a cahier and
    never repaired (the existence check would skip it on every later run).
    A size mismatch is therefore treated as absent."""
    dest = OUT_DIR / f"{cahier.sha256}.pdf"
    if dest.exists() and dest.stat().st_size == cahier.bytes:
        return dest
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUT_DIR / f".part-register-{cahier.sha256}.pdf"
    tmp.write_bytes(cahier.path.read_bytes())
    tmp.replace(dest)
    return dest


def _apply_register(meta: dict, app: Appellation, cahier: rc.RegisterCahier,
                    binding: dict) -> dict:
    """Fill a manifest entry from a register-sourced cahier. The provenance
    keys are only ever written for entries the register actually won, so an
    appellation still served by BO Agri keeps a byte-identical entry."""
    dest = _promote_register_pdf(cahier)
    # `boagri_url` means "the BO Agri URL this PDF came from" all the way down
    # to the wiki's "BO Agri (PDF source)" line and the map panel's cahier
    # link. A register attachment did not come from BO Agri, so it gets its
    # own field rather than borrowing that one.
    meta["boagri_url"] = ""
    meta["register_attachment_url"] = cahier.attachment_url
    meta["filename"] = dest.name
    meta["sha256"] = cahier.sha256
    meta["fetched_at"] = cahier.fetched_at
    meta["source_kind"] = "eambrosia-register"
    meta["register_file_number"] = cahier.file_number
    meta["register_attachment_uri"] = cahier.attachment_uri
    meta["register_attachment_name"] = cahier.attachment_name
    meta["register_protected_name"] = binding.get("register_name", "")
    meta["register_matched_via"] = binding.get("matched_via", "")
    print(f"[register] {app.name} ({app.id_appellation}) -> "
          f"{cahier.file_number} {cahier.attachment_name}", file=sys.stderr)
    return meta


_INAO_META_KEYS = (
    "canonical_idproduit", "canonical_produit", "product_url", "show_texte_url",
    "show_texte_paths", "boagri_url_candidates", "legifrance_jorftext_ids",
)


def _stub_meta(app: Appellation, prior: dict | None = None) -> dict:
    """A manifest entry for an appellation INAO surfaced nothing for.

    Whatever INAO catalogue metadata an earlier run did record is carried
    over: this run failing to reach www2.inao.gouv.fr is not evidence that the
    product page, show_texte trail or Légifrance ids ceased to exist."""
    sample = app.canonical_product() if app.products else {}
    prior = prior or {}
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
    }
    for key in _INAO_META_KEYS:
        if prior.get(key):
            meta[key] = prior[key]
    return meta


def _process_override_only(
    session: requests.Session, app: Appellation, manifest: dict,
    override: dict, delay: float,
) -> tuple[str, int]:
    """INAO didn't surface any candidates but a manual override is set.
    Download the override URLs and seed a manifest entry from them so
    stage 02's cross-bundle rescue can pick this AOC up."""
    meta = _stub_meta(app)
    meta["manual_override_note"] = override.get("note", "")
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


def _has_usable_cahier(prior: dict) -> bool:
    """True when the manifest already points this appellation at a PDF that is
    still on disk."""
    sha = prior.get("sha256") or ""
    return bool(sha) and (OUT_DIR / f"{sha}.pdf").exists()


def _register_tier(
    app: Appellation, manifest: dict, meta: dict, register: RegisterTier | None,
    prior: dict, fallback: tuple[str, int] | None,
):
    """Final tier. Runs only once BO Agri and the curator overrides have both
    failed to yield a PDF *and* the appellation has none from an earlier run.

    That second condition is what keeps a transient INAO outage from
    re-sourcing a working appellation: `resolve_cahier` returns None for a
    5xx, a timeout, or an empty Drupal body just as it does for a genuinely
    absent cahier, and `_download_first_pdf` returns None for a BO Agri blip
    just as it does for a dead URL. Without the guard, one bad afternoon would
    flip canonical resolutions to the register and churn every downstream
    surface with no upstream change behind it.

    Returns `fallback` (or `(None, 0)` when fallback is None) if the register
    has nothing for this appellation."""
    miss = fallback if fallback is not None else (None, 0)
    if register is None or not register.enabled:
        return miss
    if _has_usable_cahier(prior):
        return miss
    cahier = register.cahier_for(app.id_appellation)
    if cahier is None:
        return miss
    manifest[app.id_appellation] = _apply_register(
        meta, app, cahier, register.resolved.get(app.id_appellation, {}))
    return "register", 0


def _process_app(
    session: requests.Session, app: Appellation, manifest: dict,
    overrides: dict, delay: float, register: RegisterTier | None = None,
) -> tuple[str, int]:
    """Resolve and download `app`'s cahier(s). Returns (status, alt_count)
    where status is one of: missed, cached, fetched, legifrance-only,
    override-only, register.
    """
    prior = manifest.get(app.id_appellation, {})
    override = overrides.get(app.id_appellation)
    has_override_urls = bool(override and override.get("boagri_urls"))

    result = resolve_cahier(session, app, delay)
    time.sleep(delay)
    if result is None:
        if has_override_urls:
            status, n = _process_override_only(session, app, manifest, override, delay)
            if status != "missed":
                return status, n
            stub = _stub_meta(app, prior)
            stub["manual_override_note"] = override.get("note", "")
            return _register_tier(app, manifest, stub, register, prior,
                                  fallback=("missed", n))
        return _register_tier(app, manifest, _stub_meta(app, prior), register, prior,
                              fallback=("missed", 0))
    meta, pdf_urls = result
    if has_override_urls:
        pdf_urls = _prepend_override_urls(override["boagri_urls"], pdf_urls)
        meta["boagri_url_candidates"] = pdf_urls
        meta["manual_override_note"] = override.get("note", "")

    if not pdf_urls:
        status, n = _register_tier(app, manifest, meta, register, prior, fallback=None)
        if status is not None:
            return status, n
        meta["filename"] = ""
        meta["sha256"] = ""
        meta["fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        manifest[app.id_appellation] = meta
        return "legifrance-only", 0

    # Walk pdf_urls in order; first URL that yields a real PDF becomes the
    # canonical. Earlier we returned "missed" the moment pdf_urls[0] raised
    # (e.g. BO Agri's modern uploads can be .docx, not PDF), losing whatever
    # PDF fallback the curator queued.
    prior_sha = prior.get("sha256", "")
    prior_url = prior.get("boagri_url", "")
    # Only treat the prior fetch as cached when it lines up with the *current*
    # canonical (pdf_urls[0]). When an override has just moved a different URL
    # into the canonical slot, the prior URL — even if still present as an
    # alternate — can't reuse the old PDF.
    if prior_url and pdf_urls and prior_url == pdf_urls[0] and (OUT_DIR / f"{prior_sha}.pdf").exists():
        rest = [u for u in pdf_urls if u != prior_url]
        n = _download_alt_candidates(session, app.name, rest, delay)
        return "cached", n
    download = _download_first_pdf(session, app.name, pdf_urls, delay)
    if download is None:
        return _register_tier(app, manifest, meta, register, prior, fallback=("missed", 0))
    canonical_url, digest, dest = download
    rest = [u for u in pdf_urls if u != canonical_url]
    n = _download_alt_candidates(session, app.name, rest, delay)
    meta["boagri_url"] = canonical_url
    meta["filename"] = dest.name
    meta["sha256"] = digest
    meta["fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest[app.id_appellation] = meta
    return "fetched", n


def _prepend_override_urls(override_urls: list[str], auto_urls: list[str]) -> list[str]:
    """Override URLs take precedence over show_texte-resolved URLs: the curator
    drops an override in *because* the auto-resolved doc was wrong (e.g. INAO's
    product page links a 23-IGP bundle that doesn't actually contain the AOC).
    Put override candidates first; auto-resolved URLs stay as alternates so
    stage 02's cross-bundle rescue can fall back if the override is dud."""
    ordered: list[str] = []
    for url in override_urls:
        if url not in ordered:
            ordered.append(url)
    for url in auto_urls:
        if url not in ordered:
            ordered.append(url)
    return ordered


def _download_first_pdf(
    session: requests.Session, app_name: str, pdf_urls: list[str], delay: float,
) -> tuple[str, str, Path] | None:
    """Try each candidate in order; return (canonical_url, sha256, dest_path)
    on first success, None if all fail. Useful when the primary URL serves a
    non-PDF (e.g. BO Agri's modern .docx uploads) and a later candidate is the
    real cahier PDF."""
    errors: list[str] = []
    for i, url in enumerate(pdf_urls):
        try:
            digest, dest = download_pdf(session, url, OUT_DIR)
            return url, digest, dest
        except (requests.RequestException, RuntimeError) as exc:
            errors.append(f"{url[:80]}: {exc}")
            if i + 1 < len(pdf_urls):
                time.sleep(delay)
    for err in errors:
        print(f"[fail] {app_name}: {err}", file=sys.stderr)
    return None


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
    ap.add_argument(
        "--no-register",
        action="store_true",
        help="skip the eAmbrosia register fallback tier",
    )
    ap.add_argument(
        "--register-delay",
        type=float,
        default=rc.DEFAULT_DELAY,
        help="seconds between eAmbrosia register requests",
    )
    args = ap.parse_args()

    appellations = load_appellations(SIQO_CSV)
    if args.only:
        needles = [s.lower() for s in args.only]
        appellations = [a for a in appellations if any(n in a.name.lower() for n in needles)]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")) if MANIFEST_PATH.exists() else {}
    overrides: dict = (
        json.loads(MANUAL_OVERRIDES_PATH.read_text(encoding="utf-8"))
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

    register = RegisterTier(requests.Session(), args.register_delay,
                            enabled=not args.no_register)
    if register.enabled:
        print(f"[register] {len(register.resolved)} name→file-number binding(s) "
              f"available as the final tier", file=sys.stderr)
    elif not args.no_register:
        print(f"[register] no {rc.RESOLVED_PATH.relative_to(ROOT)} — "
              f"run scripts/01d_resolve_register.py to enable the register tier",
              file=sys.stderr)

    fetched = cached = missed = extra = 0
    counters = {
        "fetched": 0, "cached": 0, "missed": 0,
        "legifrance-only": 0, "override-only": 0, "register": 0,
    }

    try:
        for app in tqdm(appellations, desc="cahiers", leave=False):
            status, alt_count = _process_app(
                session, app, manifest, overrides, args.delay, register
            )
            counters[status] += 1
            extra += alt_count
            time.sleep(args.delay)
    finally:
        register.save()
        MANIFEST_PATH.write_text(
            json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )

    fetched = counters["fetched"] + counters["override-only"]
    cached = counters["cached"]
    missed = counters["missed"] + counters["legifrance-only"]

    print(
        f"[done] fetched={fetched} cached={cached} register={counters['register']} "
        f"extra={extra} missed={missed} manifest={MANIFEST_PATH.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0 if missed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
