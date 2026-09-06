# Vendored runtime libraries

Self-hosted copies of the two JavaScript libraries the map needs at runtime.
They were previously loaded from `unpkg.com` at page load; vendoring them
removes the third-party CDN dependency (reliability, privacy, supply-chain),
which matters for the map's role as the site's front door.

These files are **tracked git inputs to stage 04**, not hand-drops into the
generated `wiki/` tree. `copy_brand_assets()` in
[`scripts/04_build_maps.py`](../../04_build_maps.py) mirrors the `.js`/`.css`
here into `wiki/assets/vendor/`, and
[`scripts/_lib/map_template.py`](../map_template.py) references them by the
same-origin path `/assets/vendor/<file>`. The version is pinned in the
filename, so the files are immutable and long-cacheable.

## Pinned versions & provenance

| File | Version | Source URL | bytes |
|---|---|---|---|
| `maplibre-gl-4.7.1.js` | maplibre-gl 4.7.1 | https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js | 803086 |
| `maplibre-gl-4.7.1.css` | maplibre-gl 4.7.1 | https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css | 65534 |
| `pmtiles-3.2.0.js` | pmtiles 3.2.0 | https://unpkg.com/pmtiles@3.2.0/dist/pmtiles.js | 51739 |

### Checksums

sha256 (hex):

```
be9633c4d870e26fb37f1cfe5c5a77181667114003ea16207ac7850d8da8add1  maplibre-gl-4.7.1.js
576b085fdd9487a65a19215328c1e086c07ce5bf6da09b666b3806d3d008dae9  maplibre-gl-4.7.1.css
367c19f8936d1d6c1b1820b0dee053f793fc29277655c3e471f5ed4d37b5f045  pmtiles-3.2.0.js
```

sha384 (base64, = the SRI `integrity` value the page used while loading from
unpkg; recorded here as a provenance cross-check — these exact bytes matched
the previously-shipped SRI):

```
sha384-SYKAG6cglRMN0RVvhNeBY0r3FYKNOJtznwA0v7B5Vp9tr31xAHsZC0DqkQ/pZDmj  maplibre-gl-4.7.1.js
sha384-MinO0mNliZ3vwppuPOUnGa+iq619pfMhLVUXfC4LHwSCvF9H+6P/KO4Q7qBOYV5V  maplibre-gl-4.7.1.css
sha384-QfbOCebHNw8pQiPAOd2IFee2v2A5VYZxBk0+JGZ5H+3mfzVIp6zsQNkTsfGJot93  pmtiles-3.2.0.js
```

## Staged (not yet wired): OpenFreeMap basemap styles

`openfreemap-positron.json` / `openfreemap-dark.json` are **not shipped** — the
mirror step only copies `.js`/`.css`, so these sit here as build inputs for a
basemap swap that has not happened yet.

Why they exist: in 2026-08 CARTO retired key-less access to its raster
basemaps (an unkeyed tile comes back with "API KEY REQUIRED" stamped into the
PNG), and told us raster is being retired outright in favour of vector. The map
runs on a free CARTO key today (`CARTO_BASEMAP_KEY`, see
[`app.js`](../assets/app.js)); these two styles are the key-free successor —
[OpenFreeMap](https://openfreemap.org/), OpenStreetMap data on the OpenMapTiles
schema, no account, no quota, and self-hostable if the public instance ever
goes away.

They were chosen because they drop into the existing architecture rather than
replacing it: both carry the same `sources` / `glyphs` / `sprite`, so the two
layer sets merge into ONE style and the light/dark toggle stays a
`setLayoutProperty` visibility flip — no `setStyle`, which would reorder layers
above the appellation polygons and drop their selection feature-state.

| File | Source URL | fetched | bytes |
|---|---|---|---|
| `openfreemap-positron.json` | https://tiles.openfreemap.org/styles/positron | 2026-08-30 | 60214 |
| `openfreemap-dark.json` | https://tiles.openfreemap.org/styles/dark | 2026-08-30 | 48790 |

```
221ade85123e80467a2500977ba88cf17877291ee049f4d0103cc2da5a7562f4  openfreemap-positron.json
72e31c2853a05a994c575328879fd558788a229278bd04e0faa4ac52bd659410  openfreemap-dark.json
```

(Re-serialised with `json.dumps(indent=2)` so the diff of a future refetch is
readable; the tile/glyph/sprite URLs are untouched.)

## Licences

- **maplibre-gl** 4.7.1 — BSD-3-Clause (© MapLibre contributors).
- **pmtiles** 3.2.0 — BSD-3-Clause (© Protomaps).
- **OpenFreeMap styles** — style JSON derived from OpenMapTiles/positron
  (BSD-3-Clause); the tiles they reference are © OpenStreetMap contributors
  (ODbL) served by OpenFreeMap. Attribution is required wherever they render.

Both permit redistribution with attribution; their licence text ships inside
the distributed `.js` headers.

## Upgrade procedure

1. Pick the new pinned versions and fetch them into this directory:
   ```bash
   curl -fsSLo scripts/_lib/vendor/maplibre-gl-<v>.js  https://unpkg.com/maplibre-gl@<v>/dist/maplibre-gl.js
   curl -fsSLo scripts/_lib/vendor/maplibre-gl-<v>.css https://unpkg.com/maplibre-gl@<v>/dist/maplibre-gl.css
   curl -fsSLo scripts/_lib/vendor/pmtiles-<v>.js      https://unpkg.com/pmtiles@<v>/dist/pmtiles.js
   shasum -a 256 scripts/_lib/vendor/*.js scripts/_lib/vendor/*.css   # update the table above
   ```
2. Delete the old versioned files (the build mirrors whatever is present).
3. Update the three `/assets/vendor/<file>` references in
   `scripts/_lib/map_template.py` to the new filenames.
4. Rebuild stage 04 and confirm `grep -rn unpkg wiki/` is empty and the map
   renders tiles with no console 404s.
