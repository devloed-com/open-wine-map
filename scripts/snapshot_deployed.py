"""Snapshot the DEPLOYED site into a timestamped archive.

The remote as served — the Bunny Storage zone behind the CDN plus the pull-zone
config that routes it — not the local wiki/ build output. Companion to
scripts/deploy.py (same credentials, same listing), for the case where a build
has diverged from what is live and the live state needs to be kept, compared
or restored.

    .venv/bin/python scripts/snapshot_deployed.py [--env prod|beta] [--out DIR] [--workers N] [--keep-dir]

(loads the repo-root .env itself, like stage 04 — no deploy.sh-style wrapper;
`--env beta` reads the `_BETA` credentials and snapshots the preview zone into
`openwinemap-beta-deployed-<stamp>…`)

Output (under --out, default <repo>/snapshots/):

    openwinemap-deployed-<UTC stamp>.tar.gz
        openwinemap-deployed-<stamp>/
            site/                 every object in the storage zone, byte-exact
            bunny/pullzone.json   GET /pullzone/<id>: edge rules, hostnames, cache
                                  settings (secrets redacted)
            bunny/storagezone.json the storage zone entry (passwords redacted)
            bunny/live-root.json  headers + body sha of a live GET of the homepage
            MANIFEST.json         per-file sha256 / bytes / LastChanged, totals
    openwinemap-deployed-<stamp>.manifest.json   copy of MANIFEST.json, for
                                                  inspection without extracting
    openwinemap-deployed-<stamp>.tar.gz.sha256

Every downloaded object is hashed on the wire and compared with the SHA256 the
storage API reports in its LIST response; a mismatch (a deploy landing mid-
snapshot, a truncated body) is retried once, then aborts the run before any
archive is written — a snapshot that cannot vouch for its bytes is worse than
none. The staging tree is left in place on failure for inspection.

Env (same as deploy.py; beta reads the `_BETA`-suffixed per-zone variants):
  BUNNY_STORAGE_KEY[_BETA]    required — storage zone password
  BUNNY_API_KEY               optional — with BUNNY_PULLZONE_ID, captures the zone config
  BUNNY_PULLZONE_ID[_BETA]
  BUNNY_STORAGE_HOST          default storage.bunnycdn.com
  BUNNY_STORAGE_ZONE[_BETA]   default open-wine-map / open-wine-map-beta
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _lib.env import load_dotenv  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
# Mirrors deploy.py's _ENVS: per-zone .env suffix, default storage zone name,
# the served host, and the archive stem.
_ENVS: dict[str, dict] = {
    "prod": {"suffix": "", "zone": "open-wine-map", "host": "www.openwinemap.com",
             "stem": "openwinemap-deployed"},
    "beta": {"suffix": "_BETA", "zone": "open-wine-map-beta", "host": "beta.openwinemap.com",
             "stem": "openwinemap-beta-deployed"},
}
_SECRET_KEY_RE = re.compile(r"password|secret|key|token", re.IGNORECASE)


def make_session(access_key: str, pool: int) -> requests.Session:
    s = requests.Session()
    s.headers["AccessKey"] = access_key
    s.headers["Accept"] = "application/json"
    retry = Retry(
        total=5, connect=5, read=3, backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD"]),
    )
    s.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=pool))
    return s


def list_remote(session: requests.Session, host: str, zone: str, workers: int) -> dict[str, dict]:
    """Recursively list the storage zone, keeping each object's LIST entry.

    Same fan-out as deploy.list_remote (one GET per directory, ~11k leaf
    dirs), but the full entry is kept so the manifest can record when each
    file was last deployed, not only its checksum.
    """
    out: dict[str, dict] = {}
    lock = threading.Lock()

    def fetch_dir(prefix: str) -> list[str]:
        r = session.get(f"https://{host}/{zone}/{prefix}", timeout=60)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        subdirs: list[str] = []
        for entry in r.json():
            name = entry["ObjectName"]
            if entry.get("IsDirectory"):
                subdirs.append(f"{prefix}{name}/")
                continue
            with lock:
                out[f"{prefix}{name}"] = {
                    "sha256": (entry.get("Checksum") or "").lower(),
                    "bytes": int(entry.get("Length") or 0),
                    "content_type": entry.get("ContentType") or "",
                    "last_changed": entry.get("LastChanged"),
                    "date_created": entry.get("DateCreated"),
                }
        return subdirs

    n_dirs = 0
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        pending = {ex.submit(fetch_dir, "")}
        while pending:
            done, pending = cf.wait(pending, return_when=cf.FIRST_COMPLETED)
            for fut in done:
                for sub in fut.result():
                    pending.add(ex.submit(fetch_dir, sub))
                n_dirs += 1
                if n_dirs % 1000 == 0:
                    print(f"  listed {n_dirs} dirs, {len(out)} files so far ...", file=sys.stderr)
    return out


def safe_rel(rel: str) -> pathlib.PurePosixPath:
    p = pathlib.PurePosixPath(rel)
    if p.is_absolute() or any(part in ("..", "") for part in p.parts):
        raise SystemExit(f"refusing unsafe remote path: {rel!r}")
    return p


def download(session: requests.Session, host: str, zone: str, rel: str,
             dest: pathlib.Path, expected_sha: str) -> tuple[str, int]:
    """Stream one object to dest, hashing on the wire. Returns (sha256, bytes)."""
    url = f"https://{host}/{zone}/{quote(rel, safe='/')}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    for attempt in (1, 2):
        h = hashlib.sha256()
        n = 0
        with session.get(url, stream=True, timeout=600, headers={"Accept": "*/*"}) as r:
            if r.status_code == 404:
                raise FileNotFoundError(rel)
            r.raise_for_status()
            with tmp.open("wb") as f:
                for chunk in r.iter_content(1 << 16):
                    f.write(chunk)
                    h.update(chunk)
                    n += len(chunk)
        got = h.hexdigest()
        if not expected_sha or got == expected_sha:
            tmp.replace(dest)
            return got, n
        if attempt == 1:
            print(f"  checksum mismatch on {rel}, retrying ...", file=sys.stderr)
    tmp.unlink(missing_ok=True)
    raise ValueError(f"{rel}: sha256 {got} != listed {expected_sha}")


def redact(obj):
    if isinstance(obj, dict):
        return {
            k: ("<redacted>" if _SECRET_KEY_RE.search(k) and isinstance(v, str) and v else redact(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj


def capture_bunny_config(api_key: str, pullzone: str, zone_name: str, out: pathlib.Path) -> dict:
    """Pull-zone (edge rules, hostnames) + storage-zone entries, secrets redacted.

    Warn-don't-fail: the site bytes are the snapshot; the config is context."""
    headers = {"AccessKey": api_key, "Accept": "application/json"}
    status: dict = {}
    r = requests.get(f"https://api.bunny.net/pullzone/{pullzone}", headers=headers, timeout=30)
    if r.status_code == 200:
        pz = r.json()
        (out / "pullzone.json").write_text(json.dumps(redact(pz), indent=2, ensure_ascii=False))
        status["pullzone"] = {
            "id": pz.get("Id"), "name": pz.get("Name"),
            "hostnames": [h.get("Value") for h in pz.get("Hostnames") or []],
            "edge_rules": len(pz.get("EdgeRules") or []),
        }
    else:
        print(f"  warn: GET /pullzone/{pullzone} → {r.status_code}", file=sys.stderr)
        status["pullzone"] = {"error": r.status_code}
    r = requests.get("https://api.bunny.net/storagezone", headers=headers, timeout=30)
    if r.status_code == 200:
        sz = next((z for z in r.json() if z.get("Name") == zone_name), None)
        if sz is None:
            print(f"  warn: storage zone {zone_name!r} not in account listing", file=sys.stderr)
            status["storagezone"] = {"error": "not-found"}
        else:
            (out / "storagezone.json").write_text(json.dumps(redact(sz), indent=2, ensure_ascii=False))
            status["storagezone"] = {
                "id": sz.get("Id"), "region": sz.get("Region"),
                "files_stored": sz.get("FilesStored"), "storage_used": sz.get("StorageUsed"),
                "custom_404": sz.get("Custom404FilePath"),
            }
    else:
        print(f"  warn: GET /storagezone → {r.status_code}", file=sys.stderr)
        status["storagezone"] = {"error": r.status_code}
    return status


def probe_live_root(out: pathlib.Path, storage_index_sha: str | None, live_url: str) -> dict:
    """One live GET of the homepage through the CDN, so the manifest records
    whether the edge was serving the origin's current index.html at snapshot
    time (a failed purge would show here as a mismatch)."""
    try:
        r = requests.get(live_url, timeout=30, headers={"User-Agent": "owm-snapshot/1"})
    except requests.RequestException as e:
        return {"url": live_url, "error": str(e)}
    body_sha = hashlib.sha256(r.content).hexdigest()
    info = {
        "url": live_url,
        "status": r.status_code,
        "headers": dict(r.headers),
        "body_sha256": body_sha,
        "body_bytes": len(r.content),
        "matches_storage_index_html": (body_sha == storage_index_sha) if storage_index_sha else None,
    }
    (out / "live-root.json").write_text(json.dumps(info, indent=2, ensure_ascii=False))
    return info


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env", choices=sorted(_ENVS), default="prod",
                    help="which deployed environment to snapshot (default: prod)")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "snapshots",
                    help="directory for the archive (default: <repo>/snapshots)")
    ap.add_argument("--workers", type=int, default=int(os.environ.get("BUNNY_WORKERS", "16")),
                    help="concurrent downloads (default 16)")
    ap.add_argument("--list-workers", type=int, default=int(os.environ.get("BUNNY_LIST_WORKERS", "32")))
    ap.add_argument("--keep-dir", action="store_true",
                    help="keep the extracted staging tree next to the archive")
    args = ap.parse_args()

    load_dotenv()
    env = _ENVS[args.env]
    sfx = env["suffix"]
    storage_key = os.environ.get(f"BUNNY_STORAGE_KEY{sfx}")
    if not storage_key:
        sys.exit(f"set BUNNY_STORAGE_KEY{sfx} (storage zone password; same as the FTP password)")
    api_key = os.environ.get("BUNNY_API_KEY")
    pullzone = os.environ.get(f"BUNNY_PULLZONE_ID{sfx}")
    host = os.environ.get("BUNNY_STORAGE_HOST", "storage.bunnycdn.com")
    zone = os.environ.get(f"BUNNY_STORAGE_ZONE{sfx}", env["zone"])
    live_url = f"https://{env['host']}/"

    started = datetime.now(timezone.utc)
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    stem = f"{env['stem']}-{stamp}"
    args.out.mkdir(parents=True, exist_ok=True)
    staging = args.out / stem
    if staging.exists():
        sys.exit(f"staging dir already exists: {staging}")
    site_dir = staging / "site"
    bunny_dir = staging / "bunny"
    site_dir.mkdir(parents=True)
    bunny_dir.mkdir()

    session = make_session(storage_key, pool=max(args.workers, args.list_workers))

    print(f"listing {host}/{zone}/ ...", file=sys.stderr)
    t0 = time.monotonic()
    remote = list_remote(session, host, zone, args.list_workers)
    total_bytes = sum(e["bytes"] for e in remote.values())
    print(f"  {len(remote)} files, {total_bytes / 1e6:,.1f} MB listed in {time.monotonic() - t0:.0f}s",
          file=sys.stderr)
    for rel in remote:
        safe_rel(rel)

    print(f"downloading to {site_dir} with {args.workers} workers ...", file=sys.stderr)
    t0 = time.monotonic()
    failures: list[str] = []
    done_bytes = 0
    lock = threading.Lock()

    def fetch(rel: str) -> None:
        nonlocal done_bytes
        entry = remote[rel]
        try:
            got, n = download(session, host, zone, rel, site_dir / rel, entry["sha256"])
        except (ValueError, FileNotFoundError, requests.RequestException) as e:
            with lock:
                failures.append(f"{rel}: {e}")
            return
        with lock:
            entry["sha256"] = got
            entry["bytes"] = n
            done_bytes += n

    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(fetch, rel) for rel in sorted(remote)]
        for i, fut in enumerate(cf.as_completed(futures), 1):
            fut.result()
            if i % 2000 == 0 or i == len(futures):
                print(f"  [{i}/{len(futures)}] {done_bytes / 1e6:,.1f} MB, {len(failures)} failures",
                      file=sys.stderr)
    elapsed = time.monotonic() - t0
    if failures:
        print(f"\n{len(failures)} objects failed verification — no archive written; "
              f"staging left at {staging}", file=sys.stderr)
        for f in failures[:50]:
            print(f"  {f}", file=sys.stderr)
        return 1
    print(f"  verified {len(remote)} files in {elapsed:.0f}s", file=sys.stderr)

    manifest: dict = {
        "snapshot_started_at": started.isoformat(),
        "environment": args.env,
        "storage_host": host,
        "storage_zone": zone,
        "n_files": len(remote),
        "total_bytes": done_bytes,
        "files": {rel: remote[rel] for rel in sorted(remote)},
    }
    if api_key and pullzone:
        print("capturing pull-zone + storage-zone config ...", file=sys.stderr)
        manifest["bunny"] = capture_bunny_config(api_key, pullzone, zone, bunny_dir)
    else:
        print(f"  BUNNY_API_KEY / BUNNY_PULLZONE_ID{sfx} unset — skipping zone config capture", file=sys.stderr)
    print(f"probing the live homepage {live_url} ...", file=sys.stderr)
    live = probe_live_root(bunny_dir, (remote.get("index.html") or {}).get("sha256"), live_url)
    manifest["live_root"] = {k: v for k, v in live.items() if k != "headers"}
    if live.get("matches_storage_index_html") is False:
        print("  warn: the CDN served a homepage that differs from the storage zone's index.html "
              "(stale edge cache, or a deploy in flight)", file=sys.stderr)
    manifest["snapshot_finished_at"] = datetime.now(timezone.utc).isoformat()
    manifest_text = json.dumps(manifest, indent=1, ensure_ascii=False)
    (staging / "MANIFEST.json").write_text(manifest_text)
    (args.out / f"{stem}.manifest.json").write_text(manifest_text)

    archive = args.out / f"{stem}.tar.gz"
    print(f"archiving → {archive} ...", file=sys.stderr)
    t0 = time.monotonic()
    subprocess.run(["tar", "-C", str(args.out), "-czf", str(archive), stem], check=True)
    digest = hashlib.sha256()
    with archive.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    (args.out / f"{stem}.tar.gz.sha256").write_text(f"{digest.hexdigest()}  {archive.name}\n")
    print(f"  {archive.stat().st_size / 1e6:,.1f} MB in {time.monotonic() - t0:.0f}s, "
          f"sha256 {digest.hexdigest()[:16]}…", file=sys.stderr)
    if not args.keep_dir:
        shutil.rmtree(staging)

    print(f"\nsnapshot: {archive}\n  {len(remote)} files, {done_bytes / 1e6:,.1f} MB from "
          f"{host}/{zone}; manifest at {args.out / f'{stem}.manifest.json'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
