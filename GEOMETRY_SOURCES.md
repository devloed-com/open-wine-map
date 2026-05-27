# Geometry sources audit

Notes from the 2026-05-22/23 commune-precision rollout — every public
geometry source we evaluated per country, with the verdict and the
endpoint or attribution. Kept here for later revisitation, especially
when exploring a **simple-vs-advanced split per country** analogous to
France's existing tiered chain (parcellaire → aires-csv → communes).

The general shape that emerged:

- **Tier S (simple, EU-wide)** — Bétard 2022 `EU_PDO.gpkg`
  ([Figshare](https://doi.org/10.6084/m9.figshare.20059341),
  CC0). One-shot fetch, whole-municipality resolution, PDO-only by
  design. Always-on baseline; covers every PDO in Europe.
- **Tier A (advanced, per-country)** — official national or regional
  layers at the **delimited zone** resolution (consortium-validated
  boundaries, not municipality approximations), unioned per-appellation.
- **Tier P (precision, opportunistic)** — parcel-level sources (the FR
  parcellaire equivalent). Only exists for a small subset; SIGPAC for
  Spain, INAO parcellaire shapefile for France, ditto cadastre lieux-
  dits for FR DGC climats.

Active tiers per country as of today:

| Country | Tier S (always) | Tier A | Tier P |
|---|---|---|---|
| FR | ✓ (not used — FR has richer national sources) | INAO aires CSV + IGN communes | INAO parcellaire shapefile + cadastre lieux-dits |
| AT | ✓ (fallback) | **GISCO LAU + Statistik Austria registry** (commune-union from Einziges Dokument text) | — |
| ES | ✓ (fallback) | **MAPA national wine-zone layer** | SIGPAC parcels (Priorat comarca only) |
| IT | ✓ (fallback) | **5 regional geoportals** (Piemonte/Veneto/Lazio/Lombardia/Toscana) | — |
| PT | ✓ (DOPs fallback) | **DGT CAOP 2025 município-union** parsed from caderno "Área Delimitada" | — |
| SI | ✓ (DOPs); PGI = region-union of member-PDO Bétard polygons | none yet | — |

What follows lists every source consulted per country, including the ones
we ruled out — so the next pass doesn't repeat the discovery work.

---

## Italy

Italy publishes regional geoportals one regione at a time. Coverage varies
wildly. We audited every regione that hosts wine in our corpus (20 total).
Status legend: **active** (live in stage 04), **todo** (layer exists but
needs bespoke harvesting), **fallback** (no licence-clear open layer —
wines stay on Bétard).

### Active — wired into `scripts/_lib/it/zone_sources.py`

5 regions covering 218 of 531 IT wines, including most flagships.

| Regione | Layer | Endpoint | Licence | Attribution |
|---|---|---|---|---|
| **Piemonte** | Aree di produzione dei vini DOC/DOCG | [datigeo-piem-download.it shapefile zip](https://www.datigeo-piem-download.it/direct/Geoportale/RegionePiemonte/AGRICOLTURA/Aree_vini_DOC_DOCG/aree_produzione_vini.zip) | CC-BY 4.0 | Regione Piemonte — Direzione Agricoltura e Cibo |
| **Veneto** | ZONE DOC / DOCG / IGT (3 layers) | `idt2-geoserver.regione.veneto.it/geoserver/wfs` — `rv:c1016231_doc`, `rv:c1016271_docg`, `rv:c1016261_igt` | IODL 2.0 / CC-BY | Regione del Veneto |
| **Lazio** | Vini DOC / DOCG / IGT (ARSIAL, 3 layers) | `geoportale.regione.lazio.it/geoserver/wfs` — `geonode:Vini_{DOC,DOCG,IGT}_Regione_Lazio` | CC-BY 4.0 | Regione Lazio — ARSIAL |
| **Lombardia** | Aree di pregio vitivinicolo (3 sub-layers, ArcGIS MapServer) | `cartografia.servizirl.it/expo/rest/services/gpt/Aree_Pregio_Viti_Vinicolo/MapServer/{0,1,2}/query` | CC-BY 4.0 | Regione Lombardia |
| **Toscana** | Zone di produzione vitivinicola DOP/IGP | [regione.toscana.it/geoscopio shapefile zip](https://www502.regione.toscana.it/geoscopio/download/tematici/zone_prod_vini/zone_prod_vini.zip) (sub-layer `zo_vin_nom_zon_2026_05`) | CC-BY 4.0 | Regione Toscana — GEOscopio |

Name-field varies (`denominazi` for most; `NOME_ZONA` for Lombardia with
`strip_kind_prefix=True`; `NOM_ZON` for Toscana). Matching uses connector-
stripped + saint-folded normalisation in
[scripts/_lib/it/zones.py](scripts/_lib/it/zones.py).

### To-do — layer exists but harvesting still needs work

| Regione | What's there | Blocker |
|---|---|---|
| **Umbria** | dati.regione.umbria.it CKAN — ~23 separate per-appellation datasets, each a .7z shapefile | Bespoke CKAN-enumerate + 7z-extract fetch. Endpoint: `api/3/action/package_search?q=vini`. CC-BY 4.0. |
| **Puglia** | SIT Puglia (WFS / ArcGIS) | Endpoint not reachable as of 2026-05-22 — WFS/ArcGIS hosts probed returned 404 / empty; cartography page is login-gated. Need the live layer name. IODL 2.0 expected. |

### Fallback — no licence-clear open layer

| Regione | What's there | Reason fallback |
|---|---|---|
| **Abruzzo** | ArcGIS WMS layer "Carta zone vitivinicole DOC" | Licence is a custom "Regione Abruzzo" string, unverifiable; portal SSL cert expired at audit. Bétard suffices for the 9 Abruzzo DOPs. |
| **Campania** | sit2.regione.campania.it — "Aree produzione vini DOC/DOCG" | Dataset page 404s; licence unconfirmed. |
| **Friuli-Venezia Giulia** | irdat.regione.fvg.it portal | No wine-zone layer found under "agricoltura" or "vitivinicoltura"; CTR / land-use only. |
| **Sicilia** | sitr.regione.sicilia.it | Wine layer searched ("DOC", "vini") — none indexed. IRRTET catalogue is land-use only. |
| **Sardegna** | sardegnageoportale.it | No wine-zone layer; agriculture catalogue covers parcels and CTR. |
| **Emilia-Romagna** | geoportale.regione.emilia-romagna.it | Searched — no wine-zone dataset published. |
| **Marche** | sit.regione.marche.it | None found. |
| **Liguria** | geoportale.regione.liguria.it | None found. |
| **Basilicata** | rsdi.regione.basilicata.it | None found. |
| **Calabria** | geoportale.regione.calabria.it | None found. |
| **Molise** | geoportale.regione.molise.it | None found. |
| **Valle d'Aosta** | geoportale.regione.vda.it | None found — small DOC (Valle d'Aosta DOC + sub-denominations). |
| **Trentino / Alto Adige** | siat.provincia.tn.it / mapview.civis.bz.it | Provincial portals, not regional. Vineyard-suitability / land-use layers, no production-zone GIS. |

Italian DOCs **genuinely overlap** by design (a comune can belong to
several appellations, e.g. Soave / Valpolicella in Val d'Illasi), so
disjointness is not the IT success metric — geometric precision of the
delimited boundary is. Bétard's whole-municipality polygons over-cover;
the geoportal layers carve the real lines.

---

## Spain

### Active — wired into [scripts/_lib/es/zones.py](scripts/_lib/es/zones.py)

| Layer | Endpoint | Licence | Notes |
|---|---|---|---|
| **MAPA national** — "Zonas de Calidad Diferenciada: Vinos" (96 zones) | `wmts.mapama.gob.es/sig-api/ogc/features/v1/collections/alimentacion:CDZ_Vinos/items?f=json&limit=1000` (OGC API-Features GeoJSON) | CC BY 4.0 (per the MAPA IDE metadata; the .aspx page carries softer non-commercial wording — the machine-readable metadata is the citable licence and the project is non-commercial regardless) | © Ministerio de Agricultura, Pesca y Alimentación (MAPA). Single national layer covers ~90 of 106 ES DOPs. 16 newer Vinos de Pago post-date the layer and fall through to Bétard. |
| **SIGPAC** parcels — Priorat comarca | `descargas.sigpac.fega.es` | Open data | Currently only Priorat is downloaded (the wine whose pliego enumerates polygon inclusions per municipio). Add more comarcas by editing `SIGPAC_COMARCA_CODIS` in `scripts/es/00_fetch_data.py`. |

MAPA is municipality-resolution — that's why the Priorat / Montsant
overlap fix (SIGPAC parcel-resolution union from the pliego's enumerated
polígonos) must stay ahead of MAPA in the chain. Verified 2026-05-22:
MAPA still overlaps Priorat/Montsant by 27 %.

### Audited — optional refinement

| Layer | Endpoint | Licence | Status |
|---|---|---|---|
| **IDENA Navarra** — DO Navarra delimited zone | `idena.navarra.es` WMS / shapefile catalogue | CC-BY 4.0 (Gobierno de Navarra) | Layer found, but DO Navarra already resolves correctly via MAPA. Optional refinement only — not wired. |

### Audited — unclear / unverified

12 autonomous-community IDEs we couldn't conclusively confirm publish
a licence-clear wine-zone layer; MAPA covers their DOPs so the audit
was lower priority. Listed for revisit if MAPA gets retired:

- Castilla-La Mancha — idecm.jccm.es
- Castilla y León — idecyl.jcyl.es
- La Rioja — iderioja.larioja.org
- Cataluña — ICGC (icgc.cat) + DARP catalogues
- Galicia — mapas.xunta.gal
- Aragón — idearagon.aragon.es
- País Vasco — geo.euskadi.eus
- Murcia — sitmurcia.carm.es
- Extremadura — ide.juntaex.es
- Canarias — idecan.grafcan.com
- Madrid — idem.madrid.org
- Asturias — ideas.asturias.es

### Audited — confirmed absent

- **Andalucía** — DERA (Datos Espaciales de Referencia de Andalucía).
  Comprehensive coverage of land-use / cadastre / hydrography; no
  wine-zone layer published as GIS. Andalucía wines (Jerez, Manzanilla,
  Málaga, Montilla-Moriles, Condado de Huelva, etc.) resolve via MAPA.
- **Comunitat Valenciana** — IDEV (idev.gva.es). Searched — no wine-zone
  layer published.

---

## Portugal

**Audit result on wine-specific layers: negative.** No open,
licence-clear Portuguese wine-zone boundary geodata exists at the time
of audit (2026-05-22). Updated 2026-05-23: the actionable PT
improvement noted in this section (caderno-derived município-union
against DGT CAOP) **has shipped** — Tier A for PT is now the
`caop-concelho-union` step in stage 04, parsing each caderno's "Área
Delimitada" section and unioning the named CAOP municípios. All 14 PT
IGPs that previously had no polygon are now mapped (município
precision). The rest of this section remains as the negative record
for revisit if a wine-specific layer ever appears.

Sources checked:

| Source | URL | Result |
|---|---|---|
| IVV (Instituto da Vinha e do Vinho) | ivv.gov.pt | Publishes the caderno PDFs (the pipeline spine) but no GIS. |
| DGADR (Direção-Geral de Agricultura e Desenvolvimento Rural) | dgadr.gov.pt | Forest/agricultural catalogues; no wine-zone vector layer. |
| DGT (Direção-Geral do Território) | snig.dgterritorio.gov.pt | CAOP município polygons (already used for FR-style commune-union if we ever parse the caderno's per-concelho list) — but **no wine-appellation layer**. |
| SNIG (Sistema Nacional de Informação Geográfica) | snig.dgterritorio.gov.pt catalogue | Searched "vinho", "DOP", "denominação" — only metadata pointers to non-spatial PDFs. |
| dados.gov.pt | dados.gov.pt | Open-data portal; no wine-zone dataset. |
| IFAP (Instituto de Financiamento da Agricultura e Pescas) | ifap.pt | Parcel-level (iSIP / SIP) — but the wine-vineyard parcel data is access-controlled. No appellation-zone layer. |
| Per-CVR consortia | various CVR sites (Comissão Vitivinícola Regional Douro/Alentejo/Bairrada/Lisboa/…) | Maps embedded as raster images / PDFs on each CVR site; no machine-readable GIS. |
| IVBAM Madeira | ivbam.gov-madeira.pt | Madeira-specific CVR — no GIS export. |
| OT Açores | ot.azores.gov.pt | Pico Vinhas da Criação Velha — no GIS export of the wine area. |

### PT Tier A — DGT CAOP 2025 município-union (shipped 2026-05-23)

The caderno's "Área Delimitada" section enumerates the production area
in one of several patterns: a flat municípios/concelhos list, a
whole-distrito declaration ("todos os municípios do distrito de X"),
a bullet-list of concelhos, a bare "Distrito de Setúbal." sentence,
or a whole-archipelago phrase ("Arquipélago dos Açores" / "Região
Autónoma da Madeira"). [scripts/_lib/pt/commune_list.py](scripts/_lib/pt/commune_list.py)
covers all five patterns; the matched names union against DGT CAOP
2025 município polygons in [scripts/_lib/pt/geometry.py](scripts/_lib/pt/geometry.py)
via `PTPolygonIndex.union_from_parsed`. Stage 04 prefers this step
ahead of the Bétard fallback because it carries município-level
precision (no whole-município overlap padding between adjacent DOPs).

Coverage after the change: **23 / 30 PT DOPs + 14 / 14 PT IGPs** via
CAOP; the 7 DOP residuals fall through to `figshare-pdo` (Bétard
2022). Macro-region expansions are codified in `PT_MACRO_REGIONS`
(Açores = 7 ilhas / 16 municipios; Madeira = 2 ilhas / 11 municipios).

---

## Austria — for completeness

AT runs commune-precise out of the box, no Bétard polygons in the
default chain. Sources currently active:

| Source | Used by | Licence |
|---|---|---|
| Eurostat **GISCO LAU 2024** — `LAU_RG_01M_2024_3035.shp.zip` (Gemeinde polygons) | `ATCommuneIndex` polygon unions | Open data (EU Open Data Portal) |
| **Statistik Austria registry** — `polbezirke.csv` + `gemliste_knz.csv` (Bezirk ↔ 3-digit code, Gemeinde ↔ 5-digit Kennziffer) | Joining the Einziges-Dokument text against GISCO polygons | CC BY 4.0 — © Statistik Austria |
| Bétard 2022 EU_PDO.gpkg | Fallback only (not normally hit — all 30 mappable wines resolve via commune-union) | CC0 |

The Einziges-Dokument explicitly lists Bezirke / Gemeinden with
`ausgenommen` exclusions, so AT geometry is text-driven from the
single document itself; no separate national / regional layer needed.

---

## Slovenia — for completeness

SI is Bétard-PDO + region-union-for-IGP only.

| Source | Used by | Licence |
|---|---|---|
| Bétard 2022 EU_PDO.gpkg | All 14 SI DOPs (figshare-pdo) | CC0 |
| (derived) region-PDO-union | 3 SI IGPs (Podravje / Posavje / Primorska) — union of the Figshare polygons of the DOPs inside each region | derived |

No SI-specific layer audited yet. **Phase 2 todo**: the canonical
Slovenian national specification (specifikacija proizvoda) is published
by the MKGP — researching a public, licence-clear URL pattern (and
adding a per-source parser) is the route to (a) replace the 16 grand-
fathered-name content-stubs with extracted records, and (b) unlock the
podokoliš sub-denominations. Stage 04 Tier A would follow naturally.

---

## A potential "simple / advanced" tier split

What FR does today (concrete, runnable):

```
INAO parcellaire shapefile (parcel)
  → INAO aires CSV (commune list)
  → IGN communes (text-derived, fallback)
```

What the same shape could look like in other countries, framed as a
config-time choice (`--geom-tier=simple` vs `--geom-tier=advanced`):

```
AT:
  simple   = Bétard 2022 (whole-municipality)
  advanced = Statistik Austria + GISCO commune-union (current default)

ES:
  simple   = Bétard 2022
  advanced = SIGPAC parcels → MAPA national layer → Bétard
             (current default; SIGPAC remains ahead because MAPA is municipality-
             resolution and overlaps Priorat/Montsant by 27 %)

IT:
  simple   = Bétard 2022
  advanced = 5 regional geoportals → Bétard (current default; Umbria + Puglia
             would land here when their fetches are unblocked)

PT:
  simple   = Bétard 2022 (DOP only; IGPs invisible)
  advanced = caderno-concelho-list × CAOP 2025 union → Bétard 2022 fallback
             (shipped 2026-05-23; all 14 IGPs now mapped at município precision)

SI:
  simple   = Bétard 2022 + IGP-as-PDO-union (current default)
  advanced = + MKGP specifikacija parser (Phase 2)

BG:
  simple   = Bétard 2022 + IGP-as-PDO-union (current default — 100 %
             coverage: 52 PDOs in Bétard + 2 PGIs via member-PDO union;
             reuses raw/es/figshare/EU_PDO.gpkg + raw/es/gisco/LAU_RG_01M_2024_3035.shp.zip
             with CNTR_CODE='BG' as defensive commune-list fallback,
             ~265 obshtini)
  advanced = + Държавен вестник продуктова спецификация parser (Phase 2 —
             gates on the curator-pinned URL workflow)
```

The reproducibility contract (`uv sync` → stages 00 → 04 must rebuild
everything from scratch) means **simple** must be fully self-contained
and depend only on artifacts the fresh checkout downloads. Both today's
defaults satisfy that — there's no curator step gating the polygons.

The "advanced" path is more expensive (more fetches, more parsing, more
maintenance surface — the IT regional layers especially) but produces
the consortium-validated delimited boundaries rather than whole-
municipality approximations.

A flag, not two pipelines: one resolver per country with the chain
ordered top-down, and a `--geom-tier=simple` cut-over that short-circuits
to the figshare branch. Worth considering when the next country lands
or when one of the advanced sources gets retired / changes licence.
