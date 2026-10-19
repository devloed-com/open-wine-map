# Deploying — production and beta

Two environments serve the **same `wiki/` build**. Nothing in the build is
per-environment: the page picks its Plausible site and its CARTO basemap key
by `location.hostname` at runtime (`plausible_sites()` /
`carto_basemap_keys()` in [scripts/_lib/env.py](../scripts/_lib/env.py)), and
every canonical, hreflang, sitemap and `og:image` URL points at production
from either host — which is what a preview host should say about itself.

| | production | beta |
|---|---|---|
| URL | https://www.openwinemap.com/ | https://beta.openwinemap.com/ |
| Bunny pull zone | `open-wine-map` (5783020) | `open-wine-map-beta` (6623467) |
| Bunny storage zone | `open-wine-map` (DE, replicated LA/SG) | `open-wine-map-beta` (DE, replicated NY/LA/SG) |
| DNS (Hover) | `www` CNAME → `open-wine-map.b-cdn.net`; apex 301-forwards | `beta` CNAME → `open-wine-map-beta.b-cdn.net` |
| Plausible site | `openwinemap.com` (code default) | `beta.openwinemap.com` via `PLAUSIBLE_SITES` in `.env` |
| CARTO key | `CARTO_BASEMAP_KEY` | own key via `CARTO_BASEMAP_KEYS=beta.openwinemap.com=…` |
| `robots.txt` | as built (`Allow: /`) | overridden at deploy to `Disallow: /` |
| IndexNow ping | yes — only pages whose content changed (see below) | skipped |
| apex-301 smoke check | yes | skipped (no apex) |
| security headers, Force-SSL, custom 404 | set by deploy.py | set by deploy.py |
| status (2026-09-20) | live | **parked** — every request 301s to production (`--park`) |

## Parking beta (current state since 2026-09-20)

Beta is not in use, so it is *parked*: one catch-all Redirect edge rule on
its pull zone (`Parked: 301 every request to production`, target
`https://www.openwinemap.com{{path}}` — `{{path}}` carries the path **and**
query string, the same form as production's apex → www rule) sends every
request to production with a 301. The storage zone, DNS, certificate, CARTO
key and Plausible site all stay in place, so nothing has to be rebuilt to
bring it back:

    scripts/deploy.sh --env beta --park      # enable the redirect (uploads nothing)
    scripts/deploy.sh --env beta --unpark    # disable it (the rule is kept, disabled)
    scripts/deploy.sh --env beta             # then redeploy the preview as before

`deploy.py` refuses a file deploy to a parked environment (the upload would be
invisible behind the redirect) until it is unparked, and `--park` checks the
live host for the expected 301 + `Location` after applying the rule (edge rules
take up to ~60 s to propagate; a warning there is not a failure). Parking is
per environment (`park_to` in `_ENVS`); production cannot be parked.

## Waiting for storage replication before the purge (since 2026-10-11)

The storage zone's primary region is DE. It is replicated to UK / ES / NY /
LA / SG, and the pull zone fetches through one origin shield (Paris), so
every edge serves what the shield pulls. On 2026-10-11 the shield pulled
from the UK replicas (UK-317 / 384 / 689 / 965), which served the previous
copy of each file for about 40 minutes after its upload. The purge at the
end of the deploy therefore let the shield re-cache stale copies of
stable-URL files (`data/d/<lang>/*.json`, the HTML pages) for the zone's
30-day max-age. In a sample of 80 uploaded files, 2 were stale, the Kos
panel data among them. A content-hashed bundle is a new path and is never
affected.

`deploy.py` now waits for the replicas between the upload and the purge:

1. **Probe.** It takes up to eight just-uploaded stable-URL text files as
   probes (`pick_probes`): the last ones to finish uploading plus a few spread
   over the run. It purges each probe's URL, fetches it through the CDN with
   `Accept-Encoding: identity` and compares the sha256 with the upload. It
   repeats every 60 s until every probe matches or `--replication-timeout`
   passes (default 90 min). After a timeout it warns and purges anyway.
2. **Purge.** It purges the zone.
3. **Sample.** It fetches a random `--verify-sample` (default 60) of the
   uploaded stable-URL files through the CDN. It settles any stale one the
   same way and purges again. If any is still stale it says so, names the
   files and exits 3 once the IndexNow and config steps have run. The upload
   is done at that point; purge again once the replicas catch up.

IndexNow is submitted after these steps, so a crawler is never sent to a
stale copy. `--no-replication-wait` restores the old purge-at-once
behaviour. A deploy that uploads only hashed bundles has no probe, so it
skips the wait.

## IndexNow: content changes only

A rebuild that renames a content-hashed asset (`app.<locale>.<hash>.js`,
`style.<hash>.css`, the `aocs` data blob) re-uploads every page that references
it — ~11.6k files — while nothing a reader or a crawler sees has changed. Pinging
the whole site for that is what Bing Webmaster Tools reports as "IndexNow batch
mode". `deploy.py` therefore fingerprints every page with those references
normalised and keeps the set from the last deploy in
`tmp/deploy/indexnow-fingerprints-<env>.json` (gitignored, per checkout); only
pages whose fingerprint differs, plus new and deleted pages, are submitted. The
first deploy from a fresh checkout has no fingerprints and submits every
changed page, then writes the file. The upload itself is still the byte-level
diff against the storage zone — the filter only narrows the IndexNow list.

Since 2026-10-19 the fingerprint covers a page's **content**, not its shell
(`page_content`): the title, the description / robots / Open Graph / Twitter
metas, the canonical and hreflang links, the JSON-LD, the server-rendered
card (`<article id="ssr-content">`) and the entity nav. The sidebar every
page embeds, the panel skeleton, the viewport meta, the scripts and styles
are left out, so a UI release pings nothing (the unified-sidebar release
would have pinged all ~6.6k indexable pages). A page without a card — the
home pages, the browse index — is fingerprinted whole. Two flags go with it:
`--indexnow-baseline SITE_DIR` writes the environment's fingerprint file from
the pages under SITE_DIR (an extracted snapshot's `site/` tree) and exits —
run it once after a change to what `page_content` covers, so the next deploy
compares content with content rather than treating every page as changed;
`--no-indexnow` uploads and purges but submits nothing, recording the
fingerprints all the same, for a release whose content change is site-wide
and already announced by the sitemap.

Each page is submitted under its own canonical URL, the form the sitemap
carries (`public_url`: `/` for `index.html` and `en/index.html`, `/<lang>/`
and `/<lang>/appellations/` with the trailing slash, `/<lang>/<slug>` without
it), and a page whose head carries a robots `noindex` (the folded
sub-denomination / stub pages) is never submitted (`indexnow_urls`) — not
even when it has just turned noindex: Bing drops it on its own recrawl, and
the deploy log says how many noindex pages and duplicate URLs it left out. Until
2026-09-26 the deploy pushed the directory form of every page — 11,821 URLs
Bing had never seen in the sitemap — plus 5,180 noindex pages.

## Commands

    scripts/deploy.sh                 # production (unchanged default)
    scripts/deploy.sh --env beta      # preview
    .venv/bin/python scripts/snapshot_deployed.py [--env beta]

`deploy.sh` sources `.env` and forwards its arguments to
[scripts/deploy.py](../scripts/deploy.py). Typical release: build once
(`scripts/04_build_maps.py`), `--env beta`, check, then the production deploy
from the *same* `wiki/` — no rebuild in between, or the two hosts diverge.

### `.env` — beta reads the `_BETA`-suffixed per-zone values

    BUNNY_API_KEY=…                      # account key, shared by every environment
    BUNNY_STORAGE_KEY=…                  # prod storage zone password
    BUNNY_PULLZONE_ID=5783020
    BUNNY_STORAGE_KEY_BETA=…             # beta storage zone password
    BUNNY_PULLZONE_ID_BETA=6623467
    CARTO_BASEMAP_KEY=…                  # default key (prod, localhost, anything unlisted)
    CARTO_BASEMAP_KEYS=beta.openwinemap.com=…
    PLAUSIBLE_SITES=beta.openwinemap.com=pa-…

`BUNNY_STORAGE_ZONE[_BETA]` overrides the zone name defaults
(`open-wine-map` / `open-wine-map-beta`) if a zone is ever renamed.

### The guard

Before listing, hashing or uploading anything, `deploy.py` reads the target
pull zone back through the account API and **refuses** unless it (a) carries
the environment's hostname and (b) is backed by the storage zone the deploy
is about to write to. A `.env` whose beta ids still point at production — or
the reverse — stops with a message naming the offending variable. Fail-closed
on purpose: the purge step needs the same API, so an unreachable API would
abort the deploy anyway.

## Why beta is blocked at robots.txt and NOT with a noindex header

Every beta page carries `<link rel="canonical">` to its production URL.
Google treats *noindex + canonical to a different URL* as a contradictory
signal and may apply either to the whole canonical cluster — i.e. a noindex
edge rule on beta could leak into production's index. So: no `X-Robots-Tag`
on the beta pull zone, no `<meta name=robots>` difference in the build; the
crawl is simply disallowed at `robots.txt` (a one-file override the deploy
script hashes from its own body so the SHA256 diff stays honest). Don't add
beta to Search Console, and don't link to it from anything indexed.

## Setting up a new environment (what was done for beta, 2026-09-16)

1. **Bunny storage zone** — create, note the *FTP & API Access → Password*
   (→ `BUNNY_STORAGE_KEY_<ENV>`). Single region is enough for a preview.
2. **Bunny pull zone** — origin type *Storage Zone* → the zone above; note
   the numeric id (→ `BUNNY_PULLZONE_ID_<ENV>`). Hostnames → add the custom
   host, *Load Free Certificate* once DNS resolves. Add **no** edge rules by
   hand: deploy.py creates the security-header rules and the custom 404;
   directory-index serving is native. Never recreate the self-referential
   origin-override rule (it 508-loops on query strings — see the memory note
   in CLAUDE.md's Bunny section).
3. **DNS** — a CNAME for the subdomain to the pull zone's `*.b-cdn.net` host.
4. **CARTO** — a separate key per environment keeps quotas apart and lets
   each key be referrer-locked to its host; add it to `CARTO_BASEMAP_KEYS`.
   A key locked to the wrong host renders the "API KEY REQUIRED" watermark and
   nothing in the build says why.
5. **Plausible** — *+ Add website* with the bare hostname; copy the `pa-<id>`
   from the snippet into `PLAUSIBLE_SITES`. **Goals are per site**: configure
   on the new site the events you want to see there ([analytics.md](analytics.md)
   lists them; adding a goal is retroactive).
6. Add the environment to `_ENVS` in `deploy.py` and `snapshot_deployed.py`,
   rebuild stage 04 (the host maps sit in every page's shell, so this one
   rebuild churns the whole corpus), deploy with `--env <env>`.
7. Verify on the new host: Network tab loads `pa-<its id>.js` (not
   production's), `plausible.l === true`, basemap tiles carry the right
   `?key=` and no watermark, `/robots.txt` says `Disallow: /`,
   `/<locale>/<slug>` and `/<locale>/<slug>?x=1` both serve the page.
