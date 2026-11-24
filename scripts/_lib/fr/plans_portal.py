"""INAO's portal of official delimitation plans, listed folder by folder.

The plans are a public Nextcloud share (`plan_inventory.SHARE_URL`), readable
over WebDAV with the share token as the user and an empty password. A listing
is one `PROPFIND` with `Depth: 1` — `Depth: infinity` answers 412 — so the
share is walked one level at a time:

    AIRE_PARCELLAIRE/par_appellation/AOC_<NAME>/<INSEE>_<COMMUNE>/
        [<former INSEE>_<NAME>/] <INSEE>-<section><sheet>_DF.tif …

Every listing is cached under `raw/cache/inao-plans-portal/` (one JSON per
folder, named by a hash of its path, the path inside), so a re-run is offline.
A request waits `DELAY` seconds after the previous one. The share answers a
«Site en maintenance» HTML page now and then (2026-11-23, 15:25): that is not
a listing, `PortalUnavailable` is raised and nothing is cached.

Folder and file names are data: they are parsed, never followed as anything
but a path on the same share.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, unquote

from _lib.fr.plan_inventory import SHARE_TOKEN, WEBDAV

ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = ROOT / "raw" / "cache" / "inao-plans-portal"
PAR_APPELLATION = "AIRE_PARCELLAIRE/par_appellation/"
DELAY = 0.5
_HREF_PREFIX = "/public.php/webdav/"
_DAV = "{DAV:}"
_PROPFIND_BODY = (
    '<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop>'
    "<d:getlastmodified/><d:resourcetype/><d:getcontentlength/>"
    "</d:prop></d:propfind>"
)
# «02042_AY-CHAMPAGNE», «51612_BLANCS-COTEAUX»: an INSEE code (Corsica's 2A /
# 2B included), then the name
_COMMUNE_DIR_RE = re.compile(r"^(\d[\dAB]\d{3})[_ -](.+)$")
# «02042-0A05_DF.tif»: commune, cadastral section, sheet
_SHEET_RE = re.compile(r"^(\d[\dAB]\d{3})-([0-9A-Z]{1,2}?)(\d{2,3})?_")


class PortalUnavailable(RuntimeError):
    """The share answered something that is not a WebDAV listing."""


@dataclass(frozen=True)
class Entry:
    name: str
    is_dir: bool
    modified: str  # ISO date (UTC) of the share's getlastmodified, or ""
    size: int


def _cache_path(path: str, cache_dir: Path) -> Path:
    return cache_dir / (hashlib.sha1(path.encode("utf-8"), usedforsecurity=False).hexdigest()[:20] + ".json")


def parse_multistatus(xml_text: str, path: str) -> list[Entry]:
    """The entries of a Depth-1 listing of `path` (the folder itself left out)."""
    if not xml_text.lstrip().startswith("<?xml") or "multistatus" not in xml_text[:400]:
        raise PortalUnavailable(f"{path}: not a WebDAV listing ({xml_text[:80]!r})")
    root = ET.fromstring(xml_text)
    own = (_HREF_PREFIX + path).rstrip("/")
    out: list[Entry] = []
    for resp in root.iter(f"{_DAV}response"):
        href = unquote(resp.findtext(f"{_DAV}href") or "")
        if href.rstrip("/") == own:
            continue
        name = href.rstrip("/").rsplit("/", 1)[-1]
        prop = resp.find(f"{_DAV}propstat/{_DAV}prop")
        is_dir = prop is not None and prop.find(f"{_DAV}resourcetype/{_DAV}collection") is not None
        modified = ""
        raw = prop.findtext(f"{_DAV}getlastmodified") if prop is not None else None
        if raw:
            try:
                modified = parsedate_to_datetime(raw).date().isoformat()
            except (TypeError, ValueError):
                modified = ""
        size_txt = prop.findtext(f"{_DAV}getcontentlength") if prop is not None else None
        out.append(Entry(name=name, is_dir=is_dir, modified=modified,
                         size=int(size_txt) if size_txt and size_txt.isdigit() else 0))
    return sorted(out, key=lambda e: e.name)


class Portal:
    """Cached Depth-1 listings of the share. `offline=True` reads the cache
    only and answers None for a folder never listed."""

    def __init__(self, cache_dir: Path = CACHE_DIR, offline: bool = False, session=None,
                 delay: float = DELAY):
        self.cache_dir = cache_dir
        self.offline = offline
        self.delay = delay
        self._session = session
        self._last = 0.0
        self.requests = 0

    def _get_session(self):
        if self._session is None:
            import requests

            self._session = requests.Session()
            self._session.headers["User-Agent"] = "open-wine-map audit (winemap@devloed.com)"
        return self._session

    def cached(self, path: str) -> list[Entry] | None:
        p = _cache_path(path, self.cache_dir)
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        return [Entry(**e) for e in data["entries"]]

    def list(self, path: str, refresh: bool = False) -> list[Entry] | None:
        if not refresh:
            hit = self.cached(path)
            if hit is not None or self.offline:
                return hit
        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        url = WEBDAV + quote(path)
        resp = self._get_session().request(
            "PROPFIND", url, auth=(SHARE_TOKEN, ""), data=_PROPFIND_BODY,
            headers={"Depth": "1", "Content-Type": "application/xml"}, timeout=120,
        )
        self._last = time.monotonic()
        self.requests += 1
        if resp.status_code == 404:
            return []
        if resp.status_code != 207:
            raise PortalUnavailable(f"{path}: HTTP {resp.status_code}")
        entries = parse_multistatus(resp.text, path)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        _cache_path(path, self.cache_dir).write_text(
            json.dumps({"path": path, "listed": time.strftime("%Y-%m-%d"),
                        "entries": [e.__dict__ for e in entries]}, ensure_ascii=False),
            encoding="utf-8")
        return entries


def commune_dir(name: str) -> tuple[str, str] | None:
    """(INSEE, name) of a commune folder («02042_AY-CHAMPAGNE»), else None."""
    m = _COMMUNE_DIR_RE.match(name)
    return (m.group(1), m.group(2)) if m else None


def sheet_of(filename: str) -> tuple[str, str] | None:
    """(INSEE, section) of a plan sheet («02042-0A05_DF.tif»), else None."""
    m = _SHEET_RE.match(filename)
    return (m.group(1), m.group(2)) if m else None


def appellation_dirs(portal: Portal) -> list[str]:
    """The folder names under `par_appellation/` («AOC_CHAMPAGNE» …)."""
    entries = portal.list(PAR_APPELLATION) or []
    return [e.name for e in entries if e.is_dir]


def commune_folder_names(portal: Portal, app_dir: str) -> dict[str, str]:
    """INSEE → the commune folder's own name (to list it)."""
    entries = portal.list(PAR_APPELLATION + app_dir + "/") or []
    return {hit[0]: e.name for e in entries if e.is_dir and (hit := commune_dir(e.name))}


def commune_plan_dates(portal: Portal, app_dir: str, folder: str) -> tuple[str, str, int] | None:
    """(first, last, sheets) of one commune folder's plan sheets, the sheets of
    its former-commune sub-folders included; None when it is not cached
    (offline)."""
    path = PAR_APPELLATION + app_dir + "/" + folder + "/"
    entries = portal.list(path)
    if entries is None:
        return None
    files = [e for e in entries if not e.is_dir]
    for sub in (e for e in entries if e.is_dir):
        files += [e for e in (portal.list(path + sub.name + "/") or []) if not e.is_dir]
    dates = sorted(e.modified for e in files if e.modified and is_sheet(e.name))
    return (dates[0], dates[-1], len(dates)) if dates else ("", "", 0)


def commune_folders(portal: Portal, app_dir: str) -> dict[str, str] | None:
    """INSEE → name of the commune folders of one appellation folder, or None
    when the folder was never listed (offline)."""
    entries = portal.list(PAR_APPELLATION + app_dir + "/")
    if entries is None:
        return None
    out: dict[str, str] = {}
    for e in entries:
        if e.is_dir and (hit := commune_dir(e.name)):
            out[hit[0]] = hit[1]
    return out


# «02042-0A05_AZY-SUR-MARNE_AOC_0055_DF.tif»: the number after the sign is the
# SIQO id_denomination_geo (Champagne's 55); «…_AOC_0169_M_TA_DF.pdf» a
# modification's assemblage. Most plans are PDFs (2026-11-23: 4,265 sheets
# against 443 TIFs)
_DENOM_IN_FILE_RE = re.compile(r"_(?:AOC|AOP|IGP)_0*(\d{1,5})_(?:M_)?(?:TA_)?(?:DF|LEGENDE)\b")
_SHEET_FILE_RE = re.compile(r"_DF\.(?:tif|tiff|pdf)$", re.IGNORECASE)


def is_sheet(filename: str) -> bool:
    """A plan sheet (not the assemblage, not the legend)."""
    return bool(_SHEET_FILE_RE.search(filename)) and "_TA_" not in filename


def denom_of(filename: str) -> str | None:
    """The id_denomination_geo a plan file is drawn for, else None."""
    m = _DENOM_IN_FILE_RE.search(filename)
    return m.group(1) if m else None


@dataclass
class FolderSample:
    """What one commune folder of an appellation folder says: the
    id_denomination_geo its files carry and the dates of its sheets."""
    commune: str
    denoms: list[str]
    sheets: int
    first: str
    last: str
    subfolders: list[str]


def sample_folder(portal: Portal, app_dir: str, commune_folder: str) -> FolderSample | None:
    entries = portal.list(PAR_APPELLATION + app_dir + "/" + commune_folder + "/")
    if entries is None:
        return None
    files = [e for e in entries if not e.is_dir]
    dates = sorted(e.modified for e in files if e.modified and is_sheet(e.name))
    denoms = sorted({d for e in files if (d := denom_of(e.name))})
    return FolderSample(
        commune=commune_folder, denoms=denoms,
        sheets=sum(1 for e in files if is_sheet(e.name)),
        first=dates[0] if dates else "", last=dates[-1] if dates else "",
        subfolders=[e.name for e in entries if e.is_dir],
    )


def crawl(portal: Portal, sample: bool = True, log=print) -> dict:
    """List every appellation folder and, with `sample`, its first commune
    folder (for the id_denomination_geo and the sheet dates). Cached; a
    second run makes no request."""
    dirs = appellation_dirs(portal)
    n_communes = 0
    for i, d in enumerate(dirs, 1):
        cf = commune_folders(portal, d) or {}
        n_communes += len(cf)
        if sample and cf:
            entries = portal.list(PAR_APPELLATION + d + "/") or []
            first = next((e.name for e in entries if e.is_dir and commune_dir(e.name)), None)
            if first:
                sample_folder(portal, d, first)
        if i % 25 == 0:
            log(f"[portal] {i}/{len(dirs)} folders, {n_communes} commune folders, "
                f"{portal.requests} request(s)")
    return {"folders": len(dirs), "commune_folders": n_communes, "requests": portal.requests}


def folder_key(app_dir: str) -> str:
    """The match key of an appellation folder: its name without the sign
    prefix («AOC_», «IGP_»), letters and digits only, lower case."""
    import unicodedata

    s = re.sub(r"^(?:AOC|AOP|IGP|IG)[_ -]+", "", app_dir, flags=re.IGNORECASE)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return "".join(ch for ch in s if ch.isalnum())
