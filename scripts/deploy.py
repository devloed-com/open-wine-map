"""Deploy wiki/ to Bunny Storage via the HTTP Storage API.

Replaces the FTP/rclone deploy: the HTTP API exposes per-file SHA256 in
its LIST response, accepts a `Checksum` header on PUT for server-side
integrity verification, and has no session limits, so the diff is
content-addressed and uploads can fan out further than FTP allowed.

Env:
  BUNNY_STORAGE_KEY    storage zone password (Bunny dash → Storage →
                       <zone> → FTP & API access → Password; same value
                       as the FTP password)
  BUNNY_API_KEY        account API key, for the cache purge
  BUNNY_PULLZONE_ID    numeric pullzone id, for the cache purge

Optional:
  BUNNY_STORAGE_HOST   default: storage.bunnycdn.com
  BUNNY_STORAGE_ZONE   default: open-wine-map
  BUNNY_WORKERS        default: 8
"""

from __future__ import annotations

import concurrent.futures as cf
import fnmatch
import hashlib
import os
import pathlib
import sys

import requests

# Mirror the rclone --exclude globs from the old deploy.sh.
# Patterns are matched against the wiki/-relative POSIX path.
EXCLUDE_GLOBS = (
    "map-data/*.geojson",  # huge intermediates; only the .pmtiles ship
    "_index.json",         # top-level wiki index, not for the CDN
    "**/_index.json",      # any nested index files
    ".DS_Store",
    "**/.DS_Store",
    ".gitkeep",
    "**/.gitkeep",
)


def excluded(rel: str) -> bool:
    return any(fnmatch.fnmatchcase(rel, pat) for pat in EXCLUDE_GLOBS)


def sha256_hex(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def list_remote(session: requests.Session, host: str, zone: str) -> dict[str, str]:
    """Recursively list the storage zone.

    Returns {relative_posix_path: sha256_hex_lowercase}. Bunny serves
    `Checksum` as uppercase hex; we lowercase for comparison.
    """
    out: dict[str, str] = {}

    def walk(prefix: str) -> None:
        url = f"https://{host}/{zone}/{prefix}"
        if not url.endswith("/"):
            url += "/"
        r = session.get(url, timeout=60)
        if r.status_code == 404:
            return
        r.raise_for_status()
        for entry in r.json():
            name = entry["ObjectName"]
            if entry.get("IsDirectory"):
                walk(f"{prefix}{name}/")
            else:
                checksum = (entry.get("Checksum") or "").lower()
                out[f"{prefix}{name}"] = checksum

    walk("")
    return out


def hash_local(root: pathlib.Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if excluded(rel):
            continue
        out[rel] = sha256_hex(path)
    return out


# Set Content-Type at upload so served files don't depend on a Bunny edge
# rule sniffing the extension (and so an HTML page never ships as a binary
# download under X-Content-Type-Options: nosniff). Anything not listed —
# .pmtiles, .md, fonts — keeps the octet-stream default, unchanged behaviour.
_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".xml": "application/xml; charset=utf-8",
    ".webmanifest": "application/manifest+json",
    ".txt": "text/plain; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".ico": "image/x-icon",
}


def content_type_for(rel: str) -> str:
    ext = pathlib.PurePosixPath(rel).suffix.lower()
    return _CONTENT_TYPES.get(ext, "application/octet-stream")


def put(session: requests.Session, host: str, zone: str,
        root: pathlib.Path, rel: str, checksum: str) -> None:
    url = f"https://{host}/{zone}/{rel}"
    with (root / rel).open("rb") as body:
        r = session.put(
            url,
            data=body,
            headers={
                "Checksum": checksum.upper(),
                "Content-Type": content_type_for(rel),
            },
            timeout=600,
        )
    if r.status_code not in (200, 201):
        raise SystemExit(f"PUT {rel} → {r.status_code} {r.text[:200]}")


def delete(session: requests.Session, host: str, zone: str, rel: str) -> None:
    url = f"https://{host}/{zone}/{rel}"
    r = session.delete(url, timeout=60)
    if r.status_code not in (200, 404):
        raise SystemExit(f"DELETE {rel} → {r.status_code} {r.text[:200]}")


# The apex → www 301 is a Bunny edge rule (dashboard config, NOT in this repo).
# Without it Google indexes both hosts and splits ranking signals — Search
# Console flags "Duplicate without user-selected canonical". This post-deploy
# smoke check surfaces a missing / regressed redirect loudly but never fails the
# deploy (the redirect lives outside this script's control).
_CANONICAL_HOST = "www.openwinemap.com"
_APEX_HOST = "openwinemap.com"


def check_apex_redirect() -> None:
    bad: list[str] = []
    for path in ("/", "/fr/"):
        url = f"https://{_APEX_HOST}{path}"
        try:
            r = requests.head(url, allow_redirects=False, timeout=30)
        except requests.RequestException as e:
            print(f"warn: apex redirect check skipped ({url}): {e}", file=sys.stderr)
            return
        loc = r.headers.get("Location", "")
        want = f"https://{_CANONICAL_HOST}{path}"
        if r.status_code not in (301, 308) or loc.rstrip("/") != want.rstrip("/"):
            bad.append(f"  {url} → {r.status_code} {loc or '(no Location)'}  (want 301 → {want})")
    if bad:
        print(
            "\nwarn: apex host is NOT 301-redirecting to the www canonical:\n"
            + "\n".join(bad)
            + f"\n  Fix in Bunny: Pull Zone → Edge Rules → if request host = {_APEX_HOST},"
            f"\n  Redirect (301) to https://{_CANONICAL_HOST}/<path> (preserve path + query)."
            "\n  Until then Search Console reports 'Duplicate without user-selected canonical'.",
            file=sys.stderr,
        )
    else:
        print(f"apex → {_CANONICAL_HOST} 301 redirect: OK", file=sys.stderr)


def main() -> int:
    storage_key = os.environ.get("BUNNY_STORAGE_KEY")
    api_key = os.environ.get("BUNNY_API_KEY")
    pullzone = os.environ.get("BUNNY_PULLZONE_ID")
    if not storage_key:
        sys.exit("set BUNNY_STORAGE_KEY (storage zone password; same as the FTP password)")
    if not api_key or not pullzone:
        sys.exit("set BUNNY_API_KEY and BUNNY_PULLZONE_ID for the cache purge")

    host = os.environ.get("BUNNY_STORAGE_HOST", "storage.bunnycdn.com")
    zone = os.environ.get("BUNNY_STORAGE_ZONE", "open-wine-map")
    workers = int(os.environ.get("BUNNY_WORKERS", "8"))

    root = pathlib.Path(__file__).resolve().parent.parent / "wiki"
    if not root.is_dir():
        sys.exit(f"no such directory: {root}")

    storage = requests.Session()
    storage.headers["AccessKey"] = storage_key
    storage.headers["Accept"] = "application/json"

    print(f"listing {host}/{zone}/ ...", file=sys.stderr)
    remote = list_remote(storage, host, zone)
    print(f"  {len(remote)} remote files", file=sys.stderr)

    print(f"hashing {root} ...", file=sys.stderr)
    local = hash_local(root)
    print(f"  {len(local)} local files", file=sys.stderr)

    to_upload = sorted(rel for rel, h in local.items() if remote.get(rel) != h)
    to_delete = sorted(rel for rel in remote if rel not in local)
    print(f"diff: upload {len(to_upload)}, delete {len(to_delete)}", file=sys.stderr)

    if to_upload:
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {
                ex.submit(put, storage, host, zone, root, rel, local[rel]): rel
                for rel in to_upload
            }
            for i, fut in enumerate(cf.as_completed(futures), 1):
                rel = futures[fut]
                fut.result()
                print(f"  [{i}/{len(to_upload)}] PUT {rel}", file=sys.stderr)

    if to_delete:
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(delete, storage, host, zone, rel): rel for rel in to_delete}
            for i, fut in enumerate(cf.as_completed(futures), 1):
                rel = futures[fut]
                fut.result()
                print(f"  [{i}/{len(to_delete)}] DEL {rel}", file=sys.stderr)

    print("purging cache ...", file=sys.stderr)
    r = requests.post(
        f"https://api.bunny.net/pullzone/{pullzone}/purgeCache",
        headers={"AccessKey": api_key},
        timeout=60,
    )
    if r.status_code not in (200, 204):
        sys.exit(f"purgeCache → {r.status_code} {r.text[:200]}")

    check_apex_redirect()
    print("\ndeployed. https://www.openwinemap.com/", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
