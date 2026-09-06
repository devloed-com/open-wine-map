"""Fetch + cache the eAmbrosia register's national cahier des charges PDF.

The register serves the INAO cahier itself (`productSpecifications[0]` —
attachment names are literally `CDC_Batard-Montrachet.pdf`), which the
existing stage-02 extractor parses unchanged. This module is the polite,
content-addressed cache in front of that endpoint, shared by stage 01's
last-resort tier and the shadow audit so neither re-hits the API for a
document the other already pulled.

Attachments are cached OUTSIDE `raw/inao/cahiers/` on purpose: stage 02's
cross-bundle rescue indexes every PDF in that directory, so dropping a few
hundred register cahiers there would silently rewrite `latest_known_pdf`
for unrelated appellations. Only a cahier that actually wins a resolution
is promoted into the cahiers directory, by stage 01.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

from .. import eambrosia_register as er

ROOT = Path(__file__).resolve().parents[3]
REGISTER_DIR = ROOT / "raw" / "inao" / "register"
PDF_DIR = REGISTER_DIR / "cahiers"
MANIFEST_PATH = REGISTER_DIR / "manifest.json"
RESOLVED_PATH = REGISTER_DIR / "resolved.json"
UNRESOLVED_PATH = REGISTER_DIR / "unresolved.json"

DEFAULT_DELAY = 1.0

# Outcomes that are a property of the register's own data rather than of the
# network, so they are worth remembering: re-asking costs a request and the
# answer will not change until the Commission attaches the document. A
# transient `fetch-failed` is deliberately NOT recorded.
STICKY_MISSES = ("no-cahier", "unresolved")


@dataclass
class RegisterCahier:
    file_number: str
    attachment_uri: str
    attachment_url: str
    attachment_name: str
    single_doc_ref: str
    filename: str
    sha256: str
    bytes: int
    fetched_at: str

    @property
    def path(self) -> Path:
        return PDF_DIR / self.filename


def load_manifest() -> dict[str, dict]:
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    return {}


def save_manifest(manifest: dict[str, dict]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )


def load_resolved() -> dict[str, dict]:
    if RESOLVED_PATH.exists():
        return json.loads(RESOLVED_PATH.read_text(encoding="utf-8"))
    return {}


_CAHIER_FIELDS = tuple(RegisterCahier.__dataclass_fields__)


def _from_entry(entry: dict) -> RegisterCahier:
    return RegisterCahier(**{k: entry[k] for k in _CAHIER_FIELDS if k in entry})


def cached(file_number: str, manifest: dict[str, dict]) -> RegisterCahier | None:
    """Return the cached cahier for `file_number`, or None when the entry is
    absent, records a miss, or its PDF no longer hashes to its own name.

    The PDF is re-hashed rather than merely existence-checked: it is fed to
    the stage-02 extractor as if it were the regulator's document, so a
    truncated or corrupted cache file has to fail loudly, not quietly."""
    entry = manifest.get(file_number)
    if not entry or entry.get("status", "ok") != "ok" or not entry.get("filename"):
        return None
    rc = _from_entry(entry)
    if not rc.path.exists():
        return None
    payload = rc.path.read_bytes()
    if len(payload) != rc.bytes or hashlib.sha256(payload).hexdigest() != rc.sha256:
        print(f"[register] {file_number}: cached {rc.filename} failed its sha256 "
              f"— re-fetching", file=sys.stderr)
        return None
    return rc


def recorded_miss(file_number: str, manifest: dict[str, dict]) -> str | None:
    """A remembered `STICKY_MISSES` outcome for `file_number`, if any."""
    status = (manifest.get(file_number) or {}).get("status")
    return status if status in STICKY_MISSES else None


def _record_miss(file_number: str, status: str, manifest: dict[str, dict]) -> None:
    if status not in STICKY_MISSES:
        return
    manifest[file_number] = {
        "file_number": file_number,
        "status": status,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    save_manifest(manifest)


def fetch(
    file_number: str,
    id_map: dict[str, int],
    manifest: dict[str, dict],
    session: requests.Session | None = None,
    refresh: bool = False,
    delay: float = DEFAULT_DELAY,
) -> tuple[RegisterCahier | None, str]:
    """Fetch `file_number`'s cahier attachment into the cache.

    Returns (cahier, status) where status is one of `cached`, `fetched`,
    `no-cahier` (the GI resolves but publishes no `productSpecifications`
    attachment), `unresolved` (the GI is absent from the register listing),
    `detail-failed` or `fetch-failed`.

    Only the first two misses are remembered — they are properties of the
    register's data. A failed request is not: recording it would let one bad
    network moment permanently blank the tier."""
    if not refresh:
        hit = cached(file_number, manifest)
        if hit is not None:
            return hit, "cached"
        miss = recorded_miss(file_number, manifest)
        if miss is not None:
            return None, miss

    if file_number not in id_map:
        # An empty id map means the listing itself could not be loaded, which
        # says nothing about this GI.
        if id_map:
            _record_miss(file_number, "unresolved", manifest)
        return None, "unresolved"

    s = session or requests.Session()
    refs = er.attachment_refs(file_number, id_map, session=s)
    time.sleep(delay)
    if refs is None:
        return None, "detail-failed"
    uri = refs.get("cahier_uri")
    if not uri:
        _record_miss(file_number, "no-cahier", manifest)
        return None, "no-cahier"

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    tmp = PDF_DIR / f".part-{file_number}.pdf"
    ok = er.fetch_attachment(uri, tmp, session=s)
    time.sleep(delay)
    if not ok:
        tmp.unlink(missing_ok=True)
        return None, "fetch-failed"

    payload = tmp.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    dest = PDF_DIR / f"{digest}.pdf"
    if dest.exists():
        tmp.unlink()
    else:
        tmp.rename(dest)

    rc = RegisterCahier(
        file_number=file_number,
        attachment_uri=str(uri),
        attachment_url=er.ATTACHMENT_URL.format(uri=uri),
        attachment_name=refs.get("cahier_name") or "",
        single_doc_ref=refs.get("single_doc_ref") or "",
        filename=dest.name,
        sha256=digest,
        bytes=len(payload),
        fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    manifest[file_number] = {"status": "ok", **asdict(rc)}
    # Persist per fetch, not per run: the PDFs are content-addressed, so
    # without the file_number → sha256 row an interrupted crawl leaves them on
    # disk but unreachable, and the next run re-hits the anti-bot-gated
    # endpoint for every one of them.
    save_manifest(manifest)
    return rc, "fetched"
