"""Deploy wiki/ to Bunny Storage via the HTTP Storage API.

Replaces the FTP/rclone deploy: the HTTP API exposes per-file SHA256 in
its LIST response, accepts a `Checksum` header on PUT for server-side
integrity verification, and has no session limits, so the diff is
content-addressed and uploads can fan out further than FTP allowed.

Also configures, idempotently, the pull zone's security response headers
(via Edge Rules) and Force-SSL on every hostname, plus the storage zone's
Custom404FilePath (/404.html) — each compares against the current state and
only writes what's missing.

Env:
  BUNNY_STORAGE_KEY    storage zone password (Bunny dash → Storage →
                       <zone> → FTP & API access → Password; same value
                       as the FTP password)
  BUNNY_API_KEY        account API key, for the cache purge + edge rules
  BUNNY_PULLZONE_ID    numeric pullzone id, for the cache purge + edge rules

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
import re
import sys
import threading
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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


def list_remote(session: requests.Session, host: str, zone: str, workers: int) -> dict[str, str]:
    """Recursively list the storage zone, fanning out across directories.

    Returns {relative_posix_path: sha256_hex_lowercase}. Bunny serves
    `Checksum` as uppercase hex; we lowercase for comparison.

    Bunny's Storage API has no flat recursive listing — one GET per
    directory is unavoidable — and the clean-URL `<slug>/index.html`
    layout means ~11k leaf directories. A sequential walk turns that
    into a ~30-minute "hang" before any diff, so directories are listed
    concurrently: each completed listing feeds its subdirectories back
    into the pool, keeping `workers` GETs in flight.
    """
    out: dict[str, str] = {}
    lock = threading.Lock()

    def fetch_dir(prefix: str) -> list[str]:
        url = f"https://{host}/{zone}/{prefix}"
        if not url.endswith("/"):
            url += "/"
        r = session.get(url, timeout=60)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        subdirs: list[str] = []
        for entry in r.json():
            name = entry["ObjectName"]
            if entry.get("IsDirectory"):
                subdirs.append(f"{prefix}{name}/")
            else:
                checksum = (entry.get("Checksum") or "").lower()
                with lock:
                    out[f"{prefix}{name}"] = checksum
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


# IndexNow: notify the participating search engines (Bing / Yandex / Seznam /
# Naver share one endpoint) when pages change, so they re-crawl promptly. The
# key value is never hard-coded here — it lives only in the `<key>.txt` file
# stage 04 emits into wiki/ (sourced from .env at build time), so it stays out
# of version control.
#
# Submission is the bulk POST `urlList` form (≤ 10,000 URLs/request), NOT
# per-URL GET streaming. A static-site deploy changes pages in bulk at one
# instant — a routine data-bundle-hash rebuild churns thousands of files — and
# streaming that one GET at a time (even pooled) makes the step take tens of
# minutes and blocks the whole deploy on a best-effort SEO ping. Bulk POST
# represents what actually happened (a batch), notifies the entire changed set
# in ~1-2 requests, and stays warm-don't-fail so a ping blip never aborts a
# deploy whose real work (upload + purge) is already done.
_INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
_INDEXNOW_CHUNK = 10_000  # IndexNow urlList hard cap per request
_INDEXNOW_KEY_RE = re.compile(r"^[0-9a-f]{32}$")


def find_indexnow_key(root: pathlib.Path) -> tuple[str, str] | None:
    """Locate the IndexNow key file in wiki/ — a 32-hex `<key>.txt` whose body
    equals its own name (the IndexNow convention). Returns (key, keyLocation
    URL) or None when no key file is present (IndexNow then skipped)."""
    for p in sorted(root.glob("*.txt")):
        stem = p.stem
        if _INDEXNOW_KEY_RE.match(stem) and p.read_text(encoding="utf-8").strip() == stem:
            return stem, f"https://{_CANONICAL_HOST}/{p.name}"
    return None


def public_url(rel: str) -> str | None:
    """Map a wiki/-relative path to its public clean URL, or None if it is not a
    crawlable page. Only `.html` pages map (404.html is noindex). The clean-URL
    layout means every page is `<dir>/index.html`; we emit the directory URL
    (trailing slash) and engines consolidate to the page's <link rel=canonical>."""
    if not rel.endswith(".html") or rel == "404.html":
        return None
    base = f"https://{_CANONICAL_HOST}"
    if rel == "index.html":
        return base + "/"
    if rel.endswith("/index.html"):
        return f"{base}/{rel[: -len('index.html')]}"
    return f"{base}/{rel}"


def _indexnow_post_chunk(
    chunk: list[str], key: str, key_location: str
) -> object:
    """POST one ≤10,000-URL `urlList` batch to IndexNow, retrying once on a 429
    rate-limit. Returns the HTTP status code or an `error: …` string; never
    raises (warn-don't-fail is the caller's policy)."""
    body = {
        "host": _CANONICAL_HOST,
        "key": key,
        "keyLocation": key_location,
        "urlList": chunk,
    }
    for attempt in (0, 1):
        try:
            r = requests.post(
                _INDEXNOW_ENDPOINT,
                json=body,
                headers={"Content-Type": "application/json; charset=utf-8"},
                timeout=60,
            )
        except requests.RequestException as e:
            return f"error: {e}"
        if r.status_code == 429 and attempt == 0:
            time.sleep(2)
            continue
        return r.status_code
    return 429


def submit_indexnow(key: str, key_location: str, urls: list[str]) -> None:
    """Notify IndexNow of the changed URLs via the bulk POST `urlList` form,
    chunked at the 10,000-URL cap (see the note above on bulk vs. streaming).
    Warm-don't-fail — a deploy must not abort on an SEO-ping blip. Uses fresh
    requests (NOT the Bunny storage session) so the Bunny AccessKey is never
    sent to a 3rd party."""
    if not urls:
        print("  indexnow: no changed pages to submit", file=sys.stderr)
        return

    accepted = 0
    failed = 0
    failures: list[tuple[int, object]] = []
    chunks = [urls[i : i + _INDEXNOW_CHUNK] for i in range(0, len(urls), _INDEXNOW_CHUNK)]
    for n, chunk in enumerate(chunks, 1):
        status = _indexnow_post_chunk(chunk, key, key_location)
        # 200 = accepted, 202 = accepted/validation pending — both success.
        if status in (200, 202):
            accepted += len(chunk)
        else:
            failed += len(chunk)
            failures.append((n, status))

    print(
        f"  indexnow: submitted {len(urls)} URLs in {len(chunks)} batch(es) "
        f"({accepted} accepted, {failed} failed)",
        file=sys.stderr,
    )
    for n, status in failures:
        print(f"  warn: indexnow batch {n}/{len(chunks)} → {status}", file=sys.stderr)


# Security response headers to enforce on every response.
# Bunny Edge Rule ActionType 5 = SetResponseHeader.
# Bunny rejects an empty Triggers list ("At least one condition is required"),
# so each rule carries a catch-all Url trigger (Type 0, pattern "*") to apply
# unconditionally.
_CATCH_ALL_TRIGGER: dict = {
    "Type": 0,
    "PatternMatches": ["*"],
    "PatternMatchingType": 0,
    "Parameter1": "",
}
_SECURITY_HEADERS: list[tuple[str, str]] = [
    ("Strict-Transport-Security", "max-age=31536000"),
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "SAMEORIGIN"),
    ("Referrer-Policy", "strict-origin-when-cross-origin"),
    ("Permissions-Policy", "geolocation=(), microphone=(), camera=()"),
]


def ensure_security_headers(api_key: str, pullzone: str) -> None:
    """Idempotently set security response headers via Bunny Edge Rules.

    Fetches the current pull zone to find existing header rules, then adds
    only the rules that are missing or have the wrong value.
    """
    base = "https://api.bunny.net"
    headers = {"AccessKey": api_key, "Content-Type": "application/json", "Accept": "application/json"}

    r = requests.get(f"{base}/pullzone/{pullzone}", headers=headers, timeout=30)
    if r.status_code != 200:
        print(f"  warn: could not fetch pull zone for edge rule check ({r.status_code})", file=sys.stderr)
        return

    existing: dict[str, dict] = {}
    for rule in r.json().get("EdgeRules") or []:
        if rule.get("ActionType") == 5:
            name = (rule.get("ActionParameter1") or "").lower()
            existing[name] = rule

    for header_name, header_value in _SECURITY_HEADERS:
        key = header_name.lower()
        current = existing.get(key)
        if current and current.get("ActionParameter2") == header_value:
            print(f"  security header {header_name}: already set", file=sys.stderr)
            continue

        body: dict = {
            "ActionType": 5,
            "ActionParameter1": header_name,
            "ActionParameter2": header_value,
            "Description": f"Security: {header_name}",
            "Enabled": True,
            "Triggers": [dict(_CATCH_ALL_TRIGGER)],
            "TriggerMatchingType": 0,
        }
        if current:
            body["Guid"] = current.get("Guid") or current.get("Id") or ""

        resp = requests.post(
            f"{base}/pullzone/{pullzone}/edgerules/addOrUpdate",
            headers=headers,
            json=body,
            timeout=30,
        )
        if resp.status_code in (200, 201, 204):
            action = "updated" if current else "added"
            print(f"  security header {header_name}: {action}", file=sys.stderr)
        else:
            print(f"  warn: edge rule for {header_name} → {resp.status_code} {resp.text[:120]}", file=sys.stderr)


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


def ensure_force_ssl(api_key: str, pullzone: str) -> None:
    """Idempotently force HTTPS on every pull-zone hostname.

    Without this, `http://www.openwinemap.com/` serves 200 over plain HTTP
    (the apex 301-redirects, but the www host did not). Fetches the pull zone,
    and for each hostname whose `ForceSSL` is off, POSTs setForceSSL. Warn,
    don't fail — a deploy shouldn't abort on a config-API blip.
    """
    base = "https://api.bunny.net"
    headers = {"AccessKey": api_key, "Content-Type": "application/json", "Accept": "application/json"}

    r = requests.get(f"{base}/pullzone/{pullzone}", headers=headers, timeout=30)
    if r.status_code != 200:
        print(f"  warn: could not fetch pull zone for Force-SSL check ({r.status_code})", file=sys.stderr)
        return

    for hn in r.json().get("Hostnames") or []:
        name = hn.get("Value") or ""
        if not name:
            continue
        if hn.get("ForceSSL"):
            print(f"  force-SSL {name}: already on", file=sys.stderr)
            continue
        resp = requests.post(
            f"{base}/pullzone/{pullzone}/setForceSSL",
            headers=headers,
            json={"Hostname": name, "ForceSSL": True},
            timeout=30,
        )
        if resp.status_code in (200, 201, 204):
            print(f"  force-SSL {name}: enabled", file=sys.stderr)
        else:
            print(f"  warn: setForceSSL {name} → {resp.status_code} {resp.text[:120]}", file=sys.stderr)


def ensure_custom_404(api_key: str, zone_name: str) -> None:
    """Idempotently point the storage zone's Custom404FilePath at /404.html.

    Without it Bunny serves its generic error page. Resolves the storage zone
    id by name (the deploy only knows the zone name), and updates only when the
    path differs. Warn, don't fail; the dashboard fallback is Storage → <zone>
    → Custom 404 file path.
    """
    base = "https://api.bunny.net"
    headers = {"AccessKey": api_key, "Content-Type": "application/json", "Accept": "application/json"}
    want = "/404.html"

    r = requests.get(f"{base}/storagezone", headers=headers, timeout=30)
    if r.status_code != 200:
        print(f"  warn: could not list storage zones for custom-404 check ({r.status_code})", file=sys.stderr)
        return

    zone = next((z for z in r.json() if z.get("Name") == zone_name), None)
    if zone is None:
        print(f"  warn: storage zone {zone_name!r} not found for custom-404 check", file=sys.stderr)
        return
    if zone.get("Custom404FilePath") == want:
        print("  custom 404: already set", file=sys.stderr)
        return

    body = {
        "ReplicationZones": zone.get("ReplicationZones") or [],
        "OriginUrl": zone.get("OriginUrl") or "",
        "Rewrite404To200": bool(zone.get("Rewrite404To200")),
        "Custom404FilePath": want,
    }
    resp = requests.post(f"{base}/storagezone/{zone.get('Id')}", headers=headers, json=body, timeout=30)
    if resp.status_code in (200, 201, 204):
        print(f"  custom 404: set to {want}", file=sys.stderr)
    else:
        print(f"  warn: storage zone update → {resp.status_code} {resp.text[:120]}", file=sys.stderr)


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
    # Listing is one cheap GET per directory over ~11k leaf dirs, so fan
    # out far wider than the (heavier) upload PUTs.
    list_workers = int(os.environ.get("BUNNY_LIST_WORKERS", "32"))

    root = pathlib.Path(__file__).resolve().parent.parent / "wiki"
    if not root.is_dir():
        sys.exit(f"no such directory: {root}")

    storage = requests.Session()
    storage.headers["AccessKey"] = storage_key
    storage.headers["Accept"] = "application/json"
    # Fanning out list/upload across many threads means one transient DNS or
    # 5xx blip would otherwise abort the whole run; retry with backoff and
    # size the connection pool to the widest concurrency so threads don't
    # contend for (or discard) pooled sockets.
    pool = max(workers, list_workers)
    retry = Retry(
        total=5, connect=5, read=3, backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "PUT", "DELETE", "HEAD", "POST"]),
    )
    storage.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=pool))

    print(f"listing {host}/{zone}/ ...", file=sys.stderr)
    remote = list_remote(storage, host, zone, list_workers)
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

    print("notifying IndexNow of changed pages ...", file=sys.stderr)
    keyinfo = find_indexnow_key(root)
    if keyinfo is None:
        print("  indexnow: no key file in wiki/ — skipping (set INDEXNOW_KEY in .env, rerun stage 04)", file=sys.stderr)
    else:
        key, key_location = keyinfo
        changed = sorted({u for rel in (*to_upload, *to_delete) if (u := public_url(rel))})
        submit_indexnow(key, key_location, changed)

    print("configuring security headers ...", file=sys.stderr)
    ensure_security_headers(api_key, pullzone)
    print("configuring Force-SSL + custom 404 ...", file=sys.stderr)
    ensure_force_ssl(api_key, pullzone)
    ensure_custom_404(api_key, zone)
    check_apex_redirect()
    print("\ndeployed. https://www.openwinemap.com/", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
