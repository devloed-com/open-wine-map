"""Source-freshness probes — is every source a card cites still the newest
the publisher has? (docs/plan-validators.md § 1).

One module per upstream family; each probe answers with a `Probe`: the
vintage we hold, the vintage upstream, where it looked, how, and a
verdict:

  CURRENT          the upstream still serves what we hold
  NEWER-UPSTREAM   the publisher has a newer document / release / listing
  RELINKED         same content, new URL (the manifest should follow)
  GONE             404 / 410 — link rot on the card
  UNREACHABLE      the host refused or fenced us (the reason names the known
                   workaround: BO Agri wants a French exit node, minagric the
                   four-w host, mpsr.sk a browser UA)
  IN-OPPOSITION    a modification is open (INAO PNO notice, eAmbrosia
                   amendmentsInProgressFlag) — a new act will follow
  SNAPSHOT         a frozen dataset by design (Bétard 2022): never "newer"
  COVERED          another probe answers for this URL (EUR-Lex → eAmbrosia)
  UNVERIFIABLE     no public listing to compare against; the reason says why

Shared plumbing lives here: the HTTP session (the project's User-Agent, a
browser one for the hosts that gate on it), a per-host politeness delay and
circuit breaker (three connection failures in a row and the host is marked
unreachable for the run — BO Agri resets every connection from outside
France, nothing is learnt from the 467th attempt), and a one-day JSON cache
under `raw/cache/freshness/` so a re-run after a fix costs nothing.
Probes never write anywhere else.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import requests

ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = ROOT / "raw" / "cache" / "freshness"
UA = "open-wine-map-validators/0.1 (+https://www.openwinemap.com; winemap@devloed.com)"
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
# Hosts that answer a bot UA with a WAF page or a refusal, and want a browser one.
BROWSER_UA_HOSTS = ("ec.europa.eu", "mpsr.sk", "indprop.gov.sk", "boraszat.kormany.hu",
                    "agriculture.public.lu", "www.mapa.gob.es", "eavw.com")
# EUR-Lex / data.europa.eu answer non-browser clients with an AWS WAF challenge
# (HTTP 202 + JS): never probed directly — the eAmbrosia probe covers the EU tier.
WAF_HOSTS = ("eur-lex.europa.eu", "data.europa.eu", "publications.europa.eu")
# Known fences, with the workaround the verdict names.
FENCED_HOSTS = {
    "info.agriculture.gouv.fr": "BO Agri answers French IPs only — connect through a French exit node",
    "www.minagric.gr": "Akamai WAF; the reachable host is the legacy four-w http://wwww.minagric.gr/",
    "minagric.gov.gr": "Akamai WAF; the reachable host is the legacy four-w http://wwww.minagric.gr/",
    "www.legifrance.gouv.fr": "Cloudflare-walled; use the DILA JORF dumps or INAO's Textes JO index",
}
DEFAULT_DELAY = {"default": 0.6, "www2.inao.gouv.fr": 1.0, "ec.europa.eu": 1.0,
                 "wwww.minagric.gr": 1.0, "www.gov.uk": 0.3, "www.data.gouv.fr": 0.3}
CACHE_TTL = timedelta(hours=24)
MAX_BODY = 40 * 1024 * 1024

CURRENT, NEWER, RELINKED, GONE, UNREACHABLE, IN_OPPOSITION, SNAPSHOT, COVERED, UNVERIFIABLE = (
    "CURRENT", "NEWER-UPSTREAM", "RELINKED", "GONE", "UNREACHABLE", "IN-OPPOSITION", "SNAPSHOT",
    "COVERED", "UNVERIFIABLE")
VERDICTS = (CURRENT, NEWER, RELINKED, GONE, UNREACHABLE, IN_OPPOSITION, SNAPSHOT, COVERED, UNVERIFIABLE)


@dataclass
class Probe:
    tier: str                # eu | national | regional | trade | geometry | reference | spine
    source_key: str          # the card's source key (boagri, eur_lex_url, …) or a corpus label
    url: str
    verdict: str
    held: str = ""           # what we hold (a date, a sha prefix, a release label, a URL)
    upstream: str = ""       # what the publisher serves now
    upstream_url: str = ""
    method: str = ""         # head | sha | api | listing | page
    reason: str = ""
    recipe: str = ""         # what to run when the verdict asks for action
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def as_dict(self) -> dict:
        return asdict(self)


def log(msg: str) -> None:
    print(f"[freshness] {msg}", file=sys.stderr)


def host_of(url: str) -> str:
    try:
        return urlsplit(url).netloc.lower()
    except ValueError:
        return ""


def cache_key(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]


class Cache:
    def __init__(self, directory: Path = CACHE_DIR, ttl: timedelta = CACHE_TTL, refresh: bool = False):
        self.dir = directory
        self.ttl = ttl
        self.refresh = refresh
        self.dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str):
        if self.refresh:
            return None
        p = self.dir / f"{key}.json"
        if not p.exists():
            return None
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            return None
        at = datetime.fromisoformat(d.get("_at", "1970-01-01T00:00:00+00:00"))
        if datetime.now(timezone.utc) - at > self.ttl:
            return None
        return d.get("value")

    def put(self, key: str, value) -> None:
        p = self.dir / f"{key}.json"
        p.write_text(json.dumps({"_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                 "value": value}, ensure_ascii=False) + "\n", encoding="utf-8")


class Http:
    """A polite session: one request at a time, a per-host delay, a circuit
    breaker, and a request budget so a corpus run cannot run away."""

    def __init__(self, cache: Cache, *, max_requests: int = 2000, timeout: int = 30):
        self.cache = cache
        self.session = requests.Session()
        self.session.headers["User-Agent"] = UA
        self.max_requests = max_requests
        self.timeout = timeout
        self.n_requests = 0
        self._last: dict[str, float] = {}
        self._failures: dict[str, int] = {}
        self.dead: dict[str, str] = {}

    def _headers(self, url: str) -> dict:
        h = host_of(url)
        if any(h == b or h.endswith("." + b) for b in BROWSER_UA_HOSTS):
            return {"User-Agent": BROWSER_UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
        return {}

    def _wait(self, host: str) -> None:
        delay = DEFAULT_DELAY.get(host, DEFAULT_DELAY["default"])
        last = self._last.get(host)
        if last is not None:
            dt = time.monotonic() - last
            if dt < delay:
                time.sleep(delay - dt)
        self._last[host] = time.monotonic()

    def _fail(self, host: str, reason: str) -> None:
        self._failures[host] = self._failures.get(host, 0) + 1
        if self._failures[host] >= 3 and host not in self.dead:
            self.dead[host] = FENCED_HOSTS.get(host, reason)
            log(f"host {host} marked unreachable for this run: {self.dead[host]}")

    def request(self, method: str, url: str, *, stream: bool = False, allow_redirects: bool = True,
                headers: dict | None = None):
        """A response, or a string reason when the request could not be made."""
        host = host_of(url)
        if host in self.dead:
            return self.dead[host]
        if self.n_requests >= self.max_requests:
            return "request budget exhausted (--max-requests)"
        self._wait(host)
        self.n_requests += 1
        try:
            r = self.session.request(method, url, timeout=self.timeout, stream=stream,
                                     allow_redirects=allow_redirects, headers={**self._headers(url), **(headers or {})})
        except requests.RequestException as e:
            reason = f"{type(e).__name__}: {str(e)[:120]}"
            self._fail(host, reason)
            return FENCED_HOSTS.get(host, reason)
        self._failures[host] = 0
        return r

    def head(self, url: str) -> dict | str:
        """HEAD, falling back to a ranged GET for hosts that refuse HEAD.
        Cached for the run day."""
        key = cache_key("head", url)
        c = self.cache.get(key)
        if c is not None:
            return c
        r = self.request("HEAD", url)
        if not isinstance(r, str) and r.status_code in (405, 403, 400, 501):
            r = self.request("GET", url, stream=True, headers={"Range": "bytes=0-0"})
        if isinstance(r, str):
            return r
        out = {"status": r.status_code, "final_url": r.url, "etag": r.headers.get("ETag", ""),
               "last_modified": r.headers.get("Last-Modified", ""),
               "content_type": r.headers.get("Content-Type", ""),
               "content_length": r.headers.get("Content-Length", "")}
        if not isinstance(r, str):
            r.close()
        self.cache.put(key, out)
        return out

    def sha256(self, url: str, *, max_bytes: int = MAX_BODY) -> dict | str:
        key = cache_key("sha", url)
        c = self.cache.get(key)
        if c is not None:
            return c
        r = self.request("GET", url, stream=True)
        if isinstance(r, str):
            return r
        if r.status_code >= 400:
            out = {"status": r.status_code, "final_url": r.url}
            r.close()
            self.cache.put(key, out)
            return out
        h = hashlib.sha256()
        n = 0
        for chunk in r.iter_content(1 << 16):
            h.update(chunk)
            n += len(chunk)
            if n > max_bytes:
                r.close()
                return {"status": r.status_code, "final_url": r.url, "too_large": True, "bytes": n}
        out = {"status": r.status_code, "final_url": r.url, "sha256": h.hexdigest(), "bytes": n,
               "content_type": r.headers.get("Content-Type", "")}
        r.close()
        self.cache.put(key, out)
        return out

    def get_json(self, url: str, *, ttl_key: str | None = None, params: dict | None = None):
        key = cache_key("json", url, json.dumps(params or {}, sort_keys=True))
        c = self.cache.get(key)
        if c is not None:
            return c
        r = self.request("GET", url + (("?" + "&".join(f"{k}={v}" for k, v in params.items())) if params else ""),
                         headers={"Accept": "application/json"})
        if isinstance(r, str):
            return r
        if r.status_code != 200:
            return f"HTTP {r.status_code}"
        try:
            data = r.json()
        except ValueError:
            return "not JSON"
        self.cache.put(key, data)
        return data

    def get_text(self, url: str) -> str | dict:
        """Page text (cached) or a dict {error} — for listings and pages."""
        key = cache_key("text", url)
        c = self.cache.get(key)
        if c is not None:
            return c
        r = self.request("GET", url)
        if isinstance(r, str):
            return {"error": r}
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}", "status": r.status_code}
        text = r.text
        self.cache.put(key, text)
        return text


def parse_http_date(s: str) -> datetime | None:
    if not s:
        return None
    from email.utils import parsedate_to_datetime
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
