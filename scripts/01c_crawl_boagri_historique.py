"""Crawl BO Agri's historique pages (per-week issue archives) for cahier
des charges PDFs that INAO's product-page resolver missed.

Pipeline stage 01c.

INAO's "accéder au cahier des charges" link points at a single
modification arrêté per AOC, often one that doesn't actually contain
the cahier text — see the audit/coverage gap documented in
`scripts/audit_coverage.py`. The full corpus of cahier publications
lives at info.agriculture.gouv.fr under predictable URLs:

    /boagri/historique/annee-{YEAR}/semaine-{WEEK}    ← weekly index
    /boagri/document_administratif-{UUID}             ← per-doc landing
    /boagri/document_administratif-{UUID}/telechargement   ← PDF

This script walks a year/week range, lists every document
administratif referenced in those weekly indexes, fetches each landing
page to filter to wine cahiers (OBJET contains "cahier" + "AOC/AOP/IGP"
keywords), downloads the PDFs into `raw/inao/cahiers/` (content-
addressed by sha256 — automatic dedup with stage 01's catalogue), and
records a sidecar manifest so reruns skip already-seen UUIDs.

Stage 02's existing cross-bundle rescue then promotes any AOCs whose
cahier header (`Cahier des charges de l'appellation d'origine
contrôlée «NAME»`) appears in the new PDFs.

Default range targets the 2010–2015 reform window where most Burgundy
stubs trace back. Override with --year-from / --year-to.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
CAHIERS_DIR = ROOT / "raw" / "inao" / "cahiers"
HISTORIQUE_MANIFEST = CAHIERS_DIR / "historique_manifest.json"

UA = (
    "open-wine-map-bot/0.1 "
    "(+https://github.com/devloed-com/open-wine-map; INAO cahier mirror)"
)
WEEK_URL = "https://info.agriculture.gouv.fr/boagri/historique/annee-{year}/semaine-{week}"
DOC_URL = "https://info.agriculture.gouv.fr/boagri/document_administratif-{uuid}"
PDF_URL = (
    "https://info.agriculture.gouv.fr/boagri/document_administratif-"
    "{uuid}/telechargement"
)

DOC_UUID_RE = re.compile(
    r"document_administratif-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}"
    r"-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)
# OBJET parsing: the landing-page text format is roughly:
#   "OBJET : <objet text> ( Télécharger le PDF (NNNko) ) REFERENCE EXTERNE :"
# Capture everything between "OBJET :" and the next sentinel.
OBJET_RE = re.compile(
    r"OBJET\s*:\s*(.+?)(?:\(\s*T[ée]l[ée]charger|REFERENCE\s+EXTERNE|"
    r"DATE\s+DE\s+PUBLICATION|Statut|$)",
    re.IGNORECASE | re.DOTALL,
)
# Heuristic: keep only documents whose OBJET screams "cahier des charges"
# and is wine-flavoured. The OBJET text on BO Agri uses both singulars
# ("Cahier des charges") and plurals ("Cahiers des charges"), and mentions
# AOCs/IGPs as "appellation" or "appellations d'origine" — be permissive
# on both. False positives just download a non-wine PDF; stage 02's
# bundle splitter ignores those.
WINE_CAHIER_RE = re.compile(r"cahiers?\s+des?\s+charges?", re.IGNORECASE)
WINE_KEYWORD_RE = re.compile(
    r"\b(?:AOC|AOP|IGP|VDN|appellations?|appell[ée]es?|origines?)\b",
    re.IGNORECASE,
)

PDF_TIMEOUT = 300
HTML_TIMEOUT = 30


def visible_text(html: str) -> str:
    text = re.sub(r"<script.*?</script>", "", html, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", "", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def list_week_uuids(session: requests.Session, year: int, week: int) -> list[str]:
    url = WEEK_URL.format(year=year, week=week)
    r = session.get(url, timeout=HTML_TIMEOUT)
    if r.status_code != 200:
        return []
    seen: list[str] = []
    for m in DOC_UUID_RE.finditer(r.text):
        uid = m.group(1).lower()
        if uid not in seen:
            seen.append(uid)
    return seen


def fetch_landing(session: requests.Session, uuid: str) -> tuple[str, str] | None:
    """Return (objet_text, page_text) for a document landing page, or None
    on transport/HTTP failure. We swallow RequestException (timeouts,
    connection resets, intermittent 5xx) so a single flaky request can't
    kill a long crawl — the UUID is recorded with status=landing-error
    and skipped on resume."""
    try:
        r = session.get(DOC_URL.format(uuid=uuid), timeout=HTML_TIMEOUT)
    except requests.RequestException as exc:
        print(f"[warn] landing {uuid[:8]}: {exc}", file=sys.stderr)
        return None
    if r.status_code != 200:
        return None
    text = visible_text(r.text)
    m = OBJET_RE.search(text)
    objet = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    return objet, text


def looks_like_wine_cahier(objet: str) -> bool:
    return bool(WINE_CAHIER_RE.search(objet) and WINE_KEYWORD_RE.search(objet))


def download_pdf(
    session: requests.Session, uuid: str, dest_dir: Path
) -> tuple[str, Path]:
    url = PDF_URL.format(uuid=uuid)
    tmp = dest_dir / f".part-{uuid}.pdf"
    h = hashlib.sha256()
    with session.get(url, stream=True, timeout=PDF_TIMEOUT) as r:
        r.raise_for_status()
        ct = r.headers.get("Content-Type", "").lower()
        if "pdf" not in ct:
            raise RuntimeError(f"non-pdf content-type for {uuid}: {ct}")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                f.write(chunk)
                h.update(chunk)
    digest = h.hexdigest()
    final = dest_dir / f"{digest}.pdf"
    if final.exists():
        tmp.unlink()
    else:
        tmp.rename(final)
    return digest, final


# Cheap to overshoot — the BO Agri historique returns an empty index
# for non-existent week numbers, so iterating 1..53 every year is fine.
WEEKS_PER_YEAR = 53


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _process_uuid(
    session: requests.Session, uuid: str, year: int, week: int,
    no_filter: bool, dry_run: bool, delay: float,
) -> tuple[str, dict]:
    """Resolve one document UUID: fetch landing → filter → optionally
    download. Returns (status, manifest_entry). Status is one of:
    landing-error, filtered, dry-run, downloaded, download-error.
    """
    base = {"year": year, "week": week, "fetched_at": _now_iso()}
    landing = fetch_landing(session, uuid)
    time.sleep(delay)
    if landing is None:
        return "landing-error", {**base, "status": "landing-error"}
    objet, _ = landing
    objet_short = objet[:300]
    if not no_filter and not looks_like_wine_cahier(objet):
        return "filtered", {**base, "status": "filtered", "objet": objet_short}
    if dry_run:
        return "dry-run", {**base, "status": "dry-run", "objet": objet_short}
    try:
        digest, _ = download_pdf(session, uuid, CAHIERS_DIR)
    except (requests.RequestException, RuntimeError) as exc:
        print(f"[fail] {uuid[:8]}: {exc}", file=sys.stderr)
        return "download-error", {
            **base, "status": "download-error",
            "objet": objet_short, "error": str(exc)[:200],
        }
    return "downloaded", {
        **base, "status": "downloaded",
        "sha256": digest, "objet": objet_short,
    }


def _process_week(
    session: requests.Session, year: int, week: int,
    manifest: dict, counters: dict, args, save_cb,
) -> bool:
    """Process one BO Agri historique week. Mutates manifest + counters
    in place. Returns True when the caller should stop (--limit-pdfs hit).
    """
    try:
        uuids = list_week_uuids(session, year, week)
    except requests.RequestException as exc:
        print(f"[warn] {year}/W{week}: {exc}", file=sys.stderr)
        time.sleep(args.delay)
        return False
    time.sleep(args.delay)
    if not uuids:
        return False
    counters["weeks_seen"] += 1
    for uuid in tqdm(uuids, desc=f"{year}/W{week}", leave=False):
        counters["uuids_total"] += 1
        entry = manifest.get(uuid)
        if entry and entry.get("status") in ("downloaded", "filtered"):
            continue
        counters["uuids_new"] += 1
        status, manifest[uuid] = _process_uuid(
            session, uuid, year, week,
            args.no_filter, args.dry_run, args.delay,
        )
        if status == "downloaded":
            counters["downloaded"] += 1
            time.sleep(args.delay)
        elif status == "filtered":
            counters["filtered"] += 1
        elif status in ("landing-error", "download-error"):
            counters["failed"] += 1
        if args.limit_pdfs and counters["downloaded"] >= args.limit_pdfs:
            print(f"[limit] reached --limit-pdfs={args.limit_pdfs}", file=sys.stderr)
            return True
    save_cb()
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--year-from", type=int, default=2010)
    ap.add_argument("--year-to", type=int, default=2015)
    ap.add_argument("--delay", type=float, default=0.4,
                    help="seconds between HTTP requests")
    ap.add_argument("--no-filter", action="store_true",
                    help="download every document_administratif PDF, not just wine cahiers")
    ap.add_argument("--dry-run", action="store_true",
                    help="discover UUIDs and write the manifest, but skip PDF download")
    ap.add_argument("--limit-pdfs", type=int, default=0,
                    help="stop after downloading N new PDFs (0=unlimited)")
    args = ap.parse_args()

    CAHIERS_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict = (
        json.loads(HISTORIQUE_MANIFEST.read_text(encoding="utf-8"))
        if HISTORIQUE_MANIFEST.exists() else {}
    )
    print(f"[plan] crawl {args.year_from}..{args.year_to} "
          f"(prior manifest entries: {len(manifest)})", file=sys.stderr)

    session = requests.Session()
    session.headers["User-Agent"] = UA

    counters = {
        "weeks_seen": 0, "uuids_total": 0, "uuids_new": 0,
        "downloaded": 0, "filtered": 0, "failed": 0,
    }

    def save() -> None:
        HISTORIQUE_MANIFEST.write_text(
            json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )

    for year in range(args.year_from, args.year_to + 1):
        for week in range(1, WEEKS_PER_YEAR + 1):
            done = _process_week(
                session, year, week, manifest, counters, args, save
            )
            if done:
                save()
                return 0

    save()
    print(
        f"[done] weeks={counters['weeks_seen']} "
        f"uuids_total={counters['uuids_total']} new={counters['uuids_new']} "
        f"downloaded={counters['downloaded']} filtered={counters['filtered']} "
        f"failed={counters['failed']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
