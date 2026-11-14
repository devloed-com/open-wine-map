#!/usr/bin/env python3
"""Stage 01 of the drinks pipeline: the documents behind each drink GI.

Per index entry (raw/drinks/eambrosia/index.json):

1. the register's detail record (`GET /api/gi-applications/id/<id>`), cached
   under raw/drinks/register-detail/<file number>.json;
2. every `singleDocTechFile` attachment (for an aromatised wine, which has
   none, the `summarySheets` one) — for a spirit drink the "technical
   file" of Reg. (EC) 110/2008 Art. 20 (the application language, and where
   the Commission had it translated an `_EN` / `_FR` copy), for a cider the
   Food-class single document — into
   raw/drinks/technical-files/<slug>.<lang>.pdf, content-checked (`%PDF`) and
   sha-pinned in the manifest;
3. the record's other public pointers, recorded for stage 02 and the card's
   Sources: the OJ publications the register lists and the
   `productSpecificationLink` (the member state's own specification);
4. a curator pin from raw/drinks/manual_overrides.json (slug → {url, format,
   source_org, note}) — the national specification of a GI the register
   holds no document for (the aromatised wines) — fetched into
   raw/drinks/national-specs/<slug>.<ext>.

Re-runnable: a cached detail record and an attachment already on disk under
its recorded sha256 are not fetched again (`--refresh` re-reads the details,
`--refetch` the attachments too).

    .venv/bin/python scripts/drinks/01_fetch_technical_files.py [--only SLUG …]
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import eambrosia_register as er  # noqa: E402
from _lib.drinks import uk_register as uk  # noqa: E402

INDEX_PATH = ROOT / "raw" / "drinks" / "eambrosia" / "index.json"
DETAIL_DIR = ROOT / "raw" / "drinks" / "register-detail"
FILES_DIR = ROOT / "raw" / "drinks" / "technical-files"
MANIFEST_PATH = FILES_DIR / "manifest.json"
OVERRIDES_PATH = ROOT / "raw" / "drinks" / "manual_overrides.json"
NATIONAL_DIR = ROOT / "raw" / "drinks" / "national-specs"

_LANG_SUFFIX_RE = re.compile(r"_([A-Z]{2})$")
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def detail_for(file_number: str, id_map: dict, session: requests.Session,
               refresh: bool, delay: float) -> dict | None:
    cache = DETAIL_DIR / f"{file_number}.json"
    if cache.exists() and not refresh:
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    detail = er.gi_detail(file_number, id_map, session)
    time.sleep(delay)
    if detail is None:
        return None
    DETAIL_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(detail, ensure_ascii=False, indent=1), encoding="utf-8")
    return detail


def attachment_lang(ref: str) -> str:
    """"native" for the application-language file, else the two-letter
    suffix the register gives a translation ("Ares(2017)3771120_FR")."""
    m = _LANG_SUFFIX_RE.search((ref or "").strip())
    return m.group(1).lower() if m else "native"


def fetch_files(entry: dict, detail: dict, prior: dict, session: requests.Session,
                refetch: bool, delay: float) -> list[dict]:
    out: list[dict] = []
    prior_by_uri = {f.get("uri"): f for f in (prior.get("files") or [])}
    seen_langs: set[str] = set()
    # An aromatised wine has no `singleDocTechFile`: its technical file
    # (Reg. (EU) No 251/2014 Art. 10) is the register's `summarySheets`
    # attachment, in the Commission's English translation.
    attachments = detail.get("singleDocTechFile") or detail.get("summarySheets") or []
    for att in attachments:
        uri = str(att.get("uri") or "").strip()
        if not uri:
            continue
        lang = attachment_lang(att.get("text") or "")
        if lang in seen_langs:
            # a second file of the same language is a later version of the
            # first: the register lists the current one first
            continue
        seen_langs.add(lang)
        dest = FILES_DIR / f"{entry['slug']}.{lang}.pdf"
        old = prior_by_uri.get(uri)
        if (old and not refetch and dest.exists()
                and sha256_bytes(dest.read_bytes()) == old.get("sha256")):
            out.append(old)
            continue
        ok = er.fetch_attachment(uri, dest, session)
        time.sleep(delay)
        if not ok:
            print(f"[fail] {entry['slug']}: attachment {uri} ({att.get('text')})", file=sys.stderr)
            continue
        data = dest.read_bytes()
        out.append({
            "lang": lang,
            "ref": (att.get("text") or "").strip(),
            "uri": uri,
            "url": er.ATTACHMENT_URL.format(uri=uri),
            "filename": dest.name,
            "sha256": sha256_bytes(data),
            "bytes": len(data),
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
    return out


def fetch_override(slug: str, override: dict, prior: dict, session: requests.Session,
                   refetch: bool) -> dict | None:
    """The curator-pinned national specification of a GI."""
    url = (override.get("url") or "").strip()
    if not url:
        return None
    old = prior.get("national_spec") or {}
    ext = (override.get("format") or "pdf").lower()
    dest = NATIONAL_DIR / f"{slug}.{ext}"
    if (old.get("url") == url and not refetch and dest.exists()
            and sha256_bytes(dest.read_bytes()) == old.get("sha256")):
        return old
    try:
        r = session.get(url, headers={"User-Agent": _UA}, timeout=90, allow_redirects=True)
    except requests.RequestException as exc:
        print(f"[fail] {slug}: national specification {url[:90]}: {exc}", file=sys.stderr)
        return None
    if r.status_code != 200 or not r.content:
        print(f"[fail] {slug}: national specification HTTP {r.status_code}", file=sys.stderr)
        return None
    if ext == "pdf" and not r.content[:5].startswith(b"%PDF"):
        print(f"[fail] {slug}: national specification is not a PDF ({url[:90]})", file=sys.stderr)
        return None
    NATIONAL_DIR.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return {
        "url": url,
        "final_url": r.url,
        "format": ext,
        "source_org": override.get("source_org", ""),
        "note": override.get("note", ""),
        "filename": dest.name,
        "sha256": sha256_bytes(r.content),
        "bytes": len(r.content),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", default=[], help="slug (repeatable)")
    ap.add_argument("--refresh", action="store_true", help="re-read the register detail records")
    ap.add_argument("--refetch", action="store_true", help="re-download attachments too")
    ap.add_argument("--delay", type=float, default=0.6, help="seconds between register requests")
    args = ap.parse_args()

    if not INDEX_PATH.exists():
        print(f"error: {INDEX_PATH} missing — run scripts/drinks/00_fetch_index.py", file=sys.stderr)
        return 1
    entries = json.loads(INDEX_PATH.read_text(encoding="utf-8"))["drinks"]
    if args.only:
        wanted = set(args.only)
        entries = [e for e in entries if e["slug"] in wanted]
    manifest: dict = (
        json.loads(MANIFEST_PATH.read_text(encoding="utf-8")) if MANIFEST_PATH.exists() else {}
    )
    overrides: dict = {}
    if OVERRIDES_PATH.exists():
        overrides = {k: v for k, v in json.loads(OVERRIDES_PATH.read_text(encoding="utf-8")).items()
                     if not k.startswith("_")}
    session = requests.Session()
    id_map = er.id_map_from_rows(er.load_gi_rows(session=session))
    FILES_DIR.mkdir(parents=True, exist_ok=True)

    counts = {"technical-file": 0, "publication-only": 0, "national-spec": 0, "nothing": 0,
              "no-detail": 0}
    try:
        for i, entry in enumerate(entries, 1):
            slug = entry["slug"]
            prior = manifest.get(slug, {})
            if entry.get("register") == "gov-uk":
                # a UK name: its product specification is an attachment of
                # its GOV.UK register entry
                try:
                    attachment = uk.spec_attachment(uk.content(session, entry["gov_uk_path"]))
                except requests.RequestException as exc:
                    print(f"[fail] {slug}: GOV.UK register entry: {exc}", file=sys.stderr)
                    attachment = None
                national = fetch_override(
                    slug, {"url": (attachment or {}).get("url", ""), "format": "pdf", "source_org": "defra",
                           "note": (attachment or {}).get("title", "")},
                    prior, session, args.refetch,
                ) if attachment else None
                status = "national-spec" if national else "nothing"
                manifest[slug] = {
                    "file_number": entry["file_number"], "id_register": None, "files": [],
                    "publications": [], "product_specification_link": "", "producer_group": "",
                    "registration_date": entry.get("registration_date", ""),
                    "register": "gov-uk", "register_url": entry.get("register_url", ""),
                    **({"national_spec": national} if national else {}),
                    "status": status,
                }
                counts[status] += 1
                time.sleep(args.delay)
                continue
            if entry.get("register") == "ofag":
                # a Swiss AOP: the cahier des charges, and the summary of the
                # application for its history and link sections
                national = fetch_override(
                    slug, {"url": entry["cahier_url"], "format": "pdf", "source_org": "ofag",
                           "note": "Cahier des charges (OFAG / BLW)"},
                    prior, session, args.refetch,
                )
                link_doc = fetch_override(
                    f"{slug}.resume", {"url": entry.get("resume_url", ""), "format": "pdf",
                                       "source_org": "ofag",
                                       "note": "Résumé de la demande d'enregistrement (OFAG / BLW)"},
                    {"national_spec": prior.get("national_link") or {}}, session, args.refetch,
                ) if entry.get("resume_url") else None
                status = "national-spec" if national else "nothing"
                manifest[slug] = {
                    "file_number": "", "id_register": None, "files": [], "publications": [],
                    "product_specification_link": "", "producer_group": "",
                    "registration_date": entry.get("registration_date", ""),
                    "register": "ofag", "register_url": entry.get("register_url", ""),
                    **({"national_spec": national} if national else {}),
                    **({"national_link": link_doc} if link_doc else {}),
                    "status": status,
                }
                counts[status] += 1
                time.sleep(args.delay)
                continue
            detail = detail_for(entry["file_number"], id_map, session, args.refresh, args.delay)
            if detail is None:
                print(f"[fail] {slug}: no register detail for {entry['file_number']}", file=sys.stderr)
                counts["no-detail"] += 1
                continue
            files = fetch_files(entry, detail, prior, session, args.refetch, args.delay)
            publications = [
                {"text": (p.get("text") or "").strip(), "uri": (p.get("uri") or "").strip(),
                 "date": p.get("date") or ""}
                for p in (detail.get("publications") or []) if (p.get("uri") or "").strip()
            ]
            national = None
            if slug in overrides:
                national = fetch_override(slug, overrides[slug], prior, session, args.refetch)
            meta = {
                "file_number": entry["file_number"],
                "id_register": detail.get("id"),
                "files": files,
                "publications": publications,
                "product_specification_link": (detail.get("productSpecificationLink") or "").strip(),
                "producer_group": (detail.get("producerGroupName") or "").strip(),
                "registration_date": detail.get("registrationDate") or "",
                "eu_protection_date": detail.get("euProtectionDate") or "",
                "legal_instrument": detail.get("legalInstrument") or "",
            }
            if national:
                meta["national_spec"] = national
            if files:
                status = "technical-file"
            elif national:
                status = "national-spec"
            elif publications:
                status = "publication-only"
            else:
                status = "nothing"
            meta["status"] = status
            counts[status] += 1
            manifest[slug] = meta
            if i % 20 == 0:
                print(f"[progress] {i}/{len(entries)}", file=sys.stderr)
    finally:
        MANIFEST_PATH.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )
    for slug, meta in sorted(manifest.items()):
        if meta.get("status") in ("publication-only", "nothing"):
            print(f"[queue] {slug} ({meta['file_number']}): {meta['status']}", file=sys.stderr)
    print(f"[done] {counts} manifest={MANIFEST_PATH.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
