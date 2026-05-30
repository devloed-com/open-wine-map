# Corpus verification

Periodic reconciliations of each country's extracted appellation set against
an **independent**, public, licence-clear authority (i.e. not the same
upstream we use as the pipeline spine). One section per country.

The goal is to catch silent drift: stale eAmbrosia cache, missing pliegos, a
parser branch that dropped a record, or upstream re-numberings we'd never
notice from inside the pipeline.

---

## Spain

### 2026-05-17 — MAPA register reconciliation ✅

**Independent authority**: Ministerio de Agricultura, Pesca y Alimentación
(MAPA), *Listado de DOP/IGP de vinos registradas en la Unión Europea*, PDF
updated 2025-12-01.
URL: <https://www.mapa.gob.es/es/dam/jcr:f9643333-ef75-4a2f-8864-afd1ade63fd1/02_vinos.pdf>
Cached locally: `/tmp/mapa_vinos.pdf` (re-fetchable).

| Check | MAPA | Pipeline | Match |
|---|---:|---:|:---:|
| Total wines | 149 | 149 | ✓ |
| DOPs | 106 | 106 | ✓ |
| IGPs | 43 | 43 | ✓ |
| `Nº expediente UE` identity | 149 | 149 | 148/149 |
| First-synonym name (diacritic-normalized) | 149 | 149 | 149/149 |

**Discrepancies** — both benign:

1. **DOP Tharsys** (Valencia, Vino de Pago). MAPA's PDF carries
   `Nº expediente = PDO-ES-02086`; eAmbrosia carries `PDO-ES-02980`. Same
   wine (`name=Tharsys`, `slug=tharsys`). Likely a transposed-digit typo
   in MAPA's listing — eAmbrosia is the EU-authoritative source for the
   expediente number, so the pipeline carries the correct value.
2. **Manzanilla-Sanlúcar de Barrameda / Manzanilla** — synonym order
   differs between MAPA and our `name` field. Both forms are official.

**Recipe** (re-run as the pipeline ages):

```bash
# 1. Download fresh MAPA PDF + convert
curl -L 'https://www.mapa.gob.es/es/dam/jcr:f9643333-ef75-4a2f-8864-afd1ade63fd1/02_vinos.pdf' -o /tmp/mapa_vinos.pdf
pdftotext -layout /tmp/mapa_vinos.pdf /tmp/mapa_vinos.txt

# 2. Diff file-numbers
.venv/bin/python <<'PY'
import json, re
mapa = set(re.findall(r'(?:PDO|PGI)-ES-[A-Z0-9]+', open('/tmp/mapa_vinos.txt').read()))
idx = json.load(open('raw/es/pliegos-extracted/_index.json'))
ours = {v['file_number'] for v in idx.values() if not v.get('is_sub_denomination')}
print(f'MAPA: {len(mapa)}  Ours: {len(ours)}')
print(f'In MAPA only: {sorted(mapa - ours)}')
print(f'In ours only: {sorted(ours - mapa)}')
PY
```

Pipeline-internal spine ↔ extraction check (always run first): cardinality
of `raw/es/eambrosia/index.json` `wines[]` (status=registered) should equal
parent count in `raw/es/pliegos-extracted/_index.json`. Current: 149 = 149.

---

## France

### 2026-05-17 — eAmbrosia FR-wine reconciliation ✅

**Independent authority**: EU eAmbrosia GI register (separate
administrative pipeline from INAO's SIQO referentiel; same wines must
appear in both).
API: `https://webgate.ec.europa.eu/eambrosia-api/api/v1/geographical-indications`
(full register, ~6.5 MB / ~4000 GIs, JSON).
Cached locally: `/tmp/eambrosia_all.json`.

| Check | eAmbrosia (FR + WINE + registered) | Pipeline (FR wine parents) | Match |
|---|---:|---:|:---:|
| Total wines | 442 | 440 | Δ = 6 (after parent-detection fix; was 7 before) |

The Δ decomposes cleanly after manual review. **No silent dropouts** —
every divergence is either a known modeling choice or a known data
upstream gap. Findings:

| # | Pattern | Wines | Action |
|---|---|---|---|
| 1 | **Synonym / composite-name fold** | Bourg ↔ "Côtes de Bourg, Bourg et Bourgeais"; Corse ↔ "Vin de Corse ou Corse" | None — same wines, INAO uses long composite, eAmbrosia uses short form. Improve matcher to compare across all `protectedNames` not just `protectedNames[0]`. |
| 2 | **Bordeaux umbrella rollup** | Blaye, Sainte-Foy-Bordeaux | None — eAmbrosia tracks Blaye / Sainte-Foy-Bordeaux as separate PDOs (PDO-FR-A0712, A0407); INAO rolls them under id_appellation=685 "Côtes de Bordeaux" as DGCs. Same wines, modeling difference. |
| 3 | ~~**Parent-detection bug (4 AOCs)** ⚠️ Alsace (id=1), Blagny (id=136), Comté Tolosan (id=861), Fiefs Vendéens (id=1028)~~ | **Resolved 2026-05-17** | Stage 02's parent-detection used strict `denomination == appellation` equality and fell back to `denoms[0]` when it failed — the fallback row was then re-emitted as a DGC, clobbering the parent's index entry. Replaced with a `_is_parent_denom` helper that folds synonym order ("Alsace" vs "Alsace ou Vin d'Alsace"), case ("Comté Tolosan" vs "Comté tolosan"), and composite forms ("Blagny" vs "Blagny ou Blagny Côte de Beaune") via the existing `candidate_keys()` normaliser. When no SIQO row matches at all (Fiefs Vendéens — all 5 rows are DGCs), a parent is synthesized from the cahier header. DGC loop now skips by chosen parent's `id_denomination_geo`, not by strict equality. The bug also hit 3 cider/spirit AOCs (id=335 Calvados Domfontais, id=553 Cidre de Bretagne, id=1268 Euskal Sagardoa) — 7 orphans total, now 0. Also fixed a latent key-collision bug where `index[id_app]` fallback could clash with a same-numeric `id_denomination_geo` from another appellation (Fiefs Vendéens id_app=1028 vs Pommard DGC "Clos de la Commaraine" id_denom=1028) — synthetic-parent index entries now use `f"app:{id_app}"` keys. See `scripts/02_extract_cahiers.py:_is_parent_denom`. |
| 4 | **Missing from INAO SIQO entirely** | Cabernet de Saumur (PDO-FR-A0257), Côtes de Blaye (PDO-FR-A0271) | Upstream gap. Both exist in eAmbrosia but not in `raw/inao/siqo-referentiel.csv` (likely retired/merged on the INAO side without flowing through to the EU register). Curator follow-up: confirm via INAO product pages whether these are still in force, then either pin via `manual_overrides.json` or annotate. |

Two wines exist in our pipeline as `status=registered` parents but in
eAmbrosia as `status=applied` (not yet registered):
**Grés de Montpellier** (PDO-FR-03288), **Laudun** (PDO-FR-03408). Correct
behaviour — INAO publishes the cahier as soon as the French recognition
lands, ahead of the EU registration. They'll flip to `registered` upstream
when the EU register catches up.

**Out-of-scope by design**: eAmbrosia carries 53 FR `SPIRIT` GIs vs our 15.
The gap (Marc d'Auvergne, Cassis de Bourgogne, Absinthe de Pontarlier, …)
is fruit/herb eaux-de-vie + cassis IGPs that don't have a SIQO cahier
PDF — the pipeline scope only covers spirits that flow through INAO's
SIQO referentiel (Cognac, Armagnac, Calvados, Cognac sub-types, …).
This is documented behaviour, not a bug.

**Recipe** (re-run as the pipeline ages):

```bash
# 1. Fetch full eAmbrosia register
curl -sS -H 'Accept: application/json' \
  -H 'User-Agent: open-wine-map/0.0.1 (mailto:code@devloed.com)' \
  'https://webgate.ec.europa.eu/eambrosia-api/api/v1/geographical-indications' \
  -o /tmp/eambrosia_all.json

# 2. Diff FR wines (eAmbrosia status=registered vs our parents)
.venv/bin/python <<'PY'
import json, re, unicodedata
def norm(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()
d = json.load(open('/tmp/eambrosia_all.json'))
cc = lambda r: [c if isinstance(c,str) else c.get('code') for c in (r.get('countries') or [])]
ea = {norm((r.get('protectedNames') or [''])[0].split(' ou ')[0]): r.get('fileNumber')
      for r in d if 'FR' in cc(r) and r.get('productType')=='WINE' and r.get('status')=='registered'}
idx = json.load(open('raw/inao/cahier-extracted/_index.json'))
WINE = lambda r: any(c.startswith(('Vin ','Crémant')) for c in (r.get('categories') or []))
ours = {norm(r['name'].split(' ou ')[0]): r.get('id_appellation')
        for r in idx.values() if not r.get('is_sub_denomination') and WINE(r)}
print(f'eAmbrosia: {len(ea)}  ours: {len(ours)}')
print('EA-only:', sorted(set(ea) - set(ours)))
print('Ours-only:', sorted(set(ours) - set(ea)))
PY
```

---

## Portugal

### 2026-05-17 — eAmbrosia ↔ IVV spine cross-check ✅

**No separate Portuguese national-level register exists.** Unlike Spain
(MAPA maintains a parallel national register that we cross-checked
against eAmbrosia for the ES verification), Portugal's
[DGADR — Direção-Geral de Agricultura e Desenvolvimento Rural](https://www.dgadr.gov.pt/pt/dop-igp-etg)
explicitly defers to the EU eAmbrosia register as the authoritative
source (page last updated 2025-12-02: *"Os produtos que estão a ser
considerados ou que foram reconhecidos como IG constam dos registos
das indicações geográficas"* → links out to eAmbrosia + GIview).

So the strongest available verification is the **eAmbrosia ↔ IVV spine
cross-check**: two distinct administrative surfaces (the EU register
vs the Portuguese institute's caderno publication index) which the
pipeline uses jointly but which are independently maintained at
different administrative levels. They must agree by definition — any
divergence flags either a stale IVV crawl, an EU register update we
haven't refreshed, or a wine that's registered at the EU level but
hasn't had its caderno published nationally yet.

| Check | eAmbrosia (PT + WINE + registered) | IVV cadernos master indexes | Pipeline (parents) | Match |
|---|---:|---:|---:|:---:|
| Total wines | 44 | 44 | 44 | ✓ |
| DOPs | 30 | 30 | 30 | ✓ |
| IGPs | 14 | 14 | 14 | ✓ |
| First-name identity (diacritic-normalized) | 44 | — | 44 | 44/44 |

**Zero discrepancies.** Every PT wine in eAmbrosia has a caderno PDF on
IVV, and vice versa. Sub-regiões count separately: 32 sub-regiões
attached to the 44 parents (one IVV caderno per parent).

**Recipe** (re-run as the pipeline ages):

```bash
# 1. Refresh both spines
.venv/bin/python scripts/pt/00_fetch_data.py
.venv/bin/python scripts/pt/01_fetch_cadernos.py
.venv/bin/python scripts/pt/02_extract_cadernos.py  # rewrites _index.json

# 2. Cross-check
.venv/bin/python <<'PY'
import json, re, unicodedata
def norm(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()
ea = json.load(open('raw/pt/eambrosia/index.json'))
ea_names = {norm(w['name']): w.get('fileNumber') for w in ea['wines']}
idx = json.load(open('raw/pt/cadernos-extracted/_index.json'))['by_slug']
ours = {norm(v['name']): v for v in idx.values() if not v.get('is_sub_denomination')}
ivv = json.load(open('raw/pt/ivv/cadernos-index.json'))['entries']
print(f'eAmbrosia: {len(ea_names)}  IVV: {len(ivv)}  ours: {len(ours)}')
print(f'EA-only:   {sorted(set(ea_names) - set(ours))}')
print(f'Ours-only: {sorted(set(ours) - set(ea_names))}')
PY
```

**Trap to watch for**: `scripts/pt/02_extract_cadernos.py --only <slug>`
rewrites `_index.json` from scratch and **drops every record outside
the `--only` filter from the index** (per-AOC JSONs on disk are left
intact, but the index becomes a partial view). Always re-run stage 02
without `--only` after a `--only` invocation, otherwise the index
reports a misleadingly small parent count. Same pattern hit the FR
pipeline before the 2026-05-17 fix; the PT script has the same
destructive-write design and would benefit from the same hardening
(out of scope here — tracked as a code follow-up).

### Candidate stronger sources for future runs

- **Diário da República** — Portuguese national gazette listing of
  approved cadernos. Per-publication search is possible but doesn't
  yield a flat count of currently-in-force designations.
- **IVDP** (Instituto dos Vinhos do Douro e Porto) — separate institute
  for the Douro/Port cluster (subset of ~6 of our 44, including Douro,
  Porto, Moscatel do Douro, Trás-os-Montes, Beira Interior, Távora-
  Varosa). Useful for spot-checking that cluster only.
- **Wines of Portugal** (trade body) — high-level marketing surface;
  doesn't enumerate all 44 cleanly.

---

## Italy

### 2026-05-19 — initial pipeline drop ⏳ pending independent cross-check

**eAmbrosia count (pipeline spine, 2026-05-19 fetch)**:

| Bucket | Count |
|---:|:---|
| Total IT wine GIs (registered) | 531 |
| DOPs | 412 |
| IGPs | 119 |

**Independent authority candidates**:

- **MASAF DOP-IGP portal** — `https://dopigp.politicheagricole.gov.it/en/vino`
  Reports ~524 wines per the project plan's research. Reconcile by:
  scraping the portal index (HTML, no API), name-matching against
  eAmbrosia. Expected delta: ~7 (eAmbrosia's status=registered vs. MASAF's
  in-force list often diverge by a handful around recent amendments).
- **Qualivita** (Fondazione Qualivita, a private foundation) — publishes
  an annual `Atlante Qualivita` with the canonical IT wine GI count
  per region. Useful for per-regione cross-check.
- **Federdoc** — coordinating body of Italian consorzi di tutela.
  Member directory could surface DOP-equivalent wines.

**Re-run recipe**:

```
.venv/bin/python scripts/it/00_fetch_data.py
.venv/bin/python scripts/audit_it_coverage.py
# Then manually fetch MASAF portal HTML and count rows.
```

Expected drift: MASAF + eAmbrosia track each other within ~5 wines
month-to-month. A larger delta would indicate either an eAmbrosia
cache miss, a MASAF batch update we haven't seen, or a parser drop.

**Note on coverage**:

- 408 of 531 (76.8 %) wines have a Bétard 2022 Figshare polygon (all
  DOPs that existed pre-2022; newer DOPs and all 119 IGPs miss it).
- 129 of 531 (24.3 %) wines have a fully extracted documento unico
  (139 had an EUR-Lex URL; 9 failed `looks_like_documento_unico`;
  1 missing the DOCUMENTO UNICO anchor).
- 392 wines (74 %) have no eAmbrosia publication URL at all — they
  need MASAF / Gazzetta Ufficiale fallback via stage 02f or the
  curator manual-overrides path.

### 2026-05-30 — complete-coverage pass + 7 cancelled IGTs removed ✅

Corpus **531 → 524** after filtering the 7 Abruzzo IGTs cancelled by
Commission Implementing Regulations (EU) 2026/558–708 (consolidated into
IGP Terre Abruzzesi). **This corroborates the MASAF in-force count of
~524** noted in the 2026-05-19 entry above — the 7-wine delta between
eAmbrosia (`status=registered`, not retroactively cleaned) and MASAF was
exactly these cancellations. Registry: `CANCELLED_GIS` in
`scripts/it/00_fetch_data.py`, surfaced by `audit_it_coverage.py`.

Map coverage after this pass: **523 / 524** IT wines carry a polygon
(only Salemi — no parseable source, pending its own cancellation —
stays `stub-no-geometry`), up from 442 / 531. The new
`gisco-comune/provincia/regione-union` fallback resolves ~81 IGTs;
spot-checked areas land within ~1 % of the true administrative km²
(Umbria 8 455 vs 8 464 km², Lazio 17 214 vs 17 232, Pavia 2 972 vs
2 968). Sottozone: **0 → 38** sub-denomination records (Chianti's 7 etc.).
Re-run recipe:

```
.venv/bin/python scripts/it/00_fetch_data.py        # applies CANCELLED_GIS
.venv/bin/python scripts/it/02f_extract_masaf.py --all --include-nonstub
.venv/bin/python scripts/it/02h_extract_regional_registers.py
.venv/bin/python scripts/04_build_maps.py
.venv/bin/python scripts/audit_it_coverage.py
```

### 2026-05-20 — completeness audit + MASAF grape-extraction fix ✅

Independent re-audit of the IT pipeline. Spine intact: 531 eAmbrosia
wine GIs → 531 extracted records → 531 entries in `wiki/_index.json`.
Geometry: 408 / 531 Figshare polygons (4 newer DOPs + all 119 IGPs
miss — known v1 limitation). 15 wines carry neither a documento
unico nor a MASAF sidecar (2 DOPs keep a Figshare polygon; 13 IGPs
are stub-no-geometry).

Audit found the MASAF grape extraction badly under-performing — 108
of 388 sidecars had `grapes=0`, and `audit_it_coverage.py` reported
only "123 of 531 with grapes" because it reads the on-disk doc-unico
extractions and ignores the stage-04 MASAF augmentation. Root cause
was a parser defect, not (mostly) a vocab gap — see CURATOR_TODO.md
"MASAF grape-extraction fix". After the fix: **MASAF sidecars with
grapes 280 → 354 of 387**; residual 33 are 4 empty-Article-2, ~24
genuinely-generic IGTs, ~5 layout misses. No false-positive grape
matches remain (verified: no spurious `nielluccio` / `listan`).

**Re-run recipe**:

```
.venv/bin/python scripts/it/02f_extract_masaf.py --all
.venv/bin/python - <<'PY'
import json, pathlib
sc = {p.stem: json.loads(p.read_text())
      for p in pathlib.Path("raw/it/masaf-disciplinari-extracted").glob("*.json")
      if p.stem != "_index"}
ng = lambda d: len((d.get("grapes") or {}).get("principal", [])) \
             + len((d.get("grapes") or {}).get("accessory", []))
print("with grapes:", sum(1 for d in sc.values() if ng(d) > 0), "/", len(sc))
PY
.venv/bin/python scripts/04_build_maps.py
```

Caveat: `audit_it_coverage.py`'s "Wines with grapes" line still
reads doc-unico extractions only — it understates true coverage by
the whole MASAF-augmented set. Reading the MASAF sidecars (as the
recipe above does) gives the real figure.

---

## Austria

### 2026-05-21 — eAmbrosia ↔ de.wikipedia DAC-list cross-check ✅

**Independent authority**: German Wikipedia, *Weinbau in Österreich*
(CC BY-SA 4.0) — independent of the eAmbrosia EU-register spine.
URL: <https://de.wikipedia.org/wiki/Weinbau_in_Österreich>

The pipeline corpus is **32 wine GIs (29 DOP + 3 IGP)**, sourced from
eAmbrosia (`country=AT` + `productType=WINE` + `status=registered`).
Wikipedia independently enumerates **18 DAC** appellations and **3
Weinbauregionen** (Landwein / PGI: Bergland, Steirerland, Weinland).

| Check | Wikipedia | Pipeline | Match |
|---|---:|---:|:---:|
| DAC appellations | 18 | 18 | ✓ |
| Landwein regions (IGP) | 3 | 3 | ✓ |
| Total DOP | — | 29 | — |

**Reconciliation of the 29 DOP** (Wikipedia lists DACs, not the full
g.U. set): 18 DAC + 9 generic Bundesland g.U. (Niederösterreich,
Burgenland, Steiermark, Wien, Kärnten, Oberösterreich, Salzburg,
Tirol, Vorarlberg) + 2 superseded names still EU-registered
(Neusiedlersee-Hügelland → Leithaberg + Rosalia; Südburgenland →
Eisenberg) = 29. The 2 superseded names extract as content-stubs —
their only OJ-C publication is a *Löschungsantrag* (see CURATOR_TODO).

No discrepancies. The 18 Wikipedia DACs all appear in the corpus by
name.

**Re-run recipe**:

```
.venv/bin/python scripts/at/00_fetch_data.py
.venv/bin/python - <<'PY'
import json
w = json.load(open("raw/at/eambrosia/index.json"))["wines"]
print("DOP:", sum(1 for x in w if x["kind"] == "DOP"),
      "IGP:", sum(1 for x in w if x["kind"] == "IGP"),
      "total:", len(w))
PY
```

Compare against the DAC list at the Wikipedia URL above.

### 2026-05-22 — commune-precise geometry: DAC disjointness ✅

After switching AT geometry off Bétard 2022 (whole-municipality
polygons that overlap on shared communes) to commune-precise
resolution from each Einziges Dokument (`scripts/_lib/at/gemeinde.py`),
the 16 proper DACs must be mutually disjoint — Austrian wine law
assigns each commune to exactly one DAC.

| Check | Before (Bétard) | After (commune-union) |
|---|---|---|
| Südsteiermark ∩ Vulkanland Steiermark | 22.4 % | 0 % |
| Vulkanland Steiermark ∩ Weststeiermark | 6.7 % | 0 % |
| Leithaberg ∩ Neusiedlersee | 15.9 % | 0 % |
| Wagram ∩ Weinviertel | 4.5 % | 0 % |
| any proper-DAC pair | up to 22 % | **0 %** (all 120 pairs) |
| AT wines mapped | 27 / 32 | 30 / 32 |

The region-wide g.U.s (Steiermark, Niederösterreich, …) and the 3
Landwein IGPs (Steirerland, Weinland, Bergland) still contain their
DACs at 100 % — that is correct regulatory nesting, not an overlap.
The 2 unmapped wines are the *Löschungsantrag* content-stubs.

**Re-run recipe**:

```
.venv/bin/python scripts/04_build_maps.py --no-tippecanoe --no-translations
.venv/bin/python - <<'PY'
import json, itertools
from shapely.geometry import shape
fc = json.load(open("wiki/map-data/appellations.geojson"))
g = {f["properties"]["slug"]: shape(f["geometry"])
     for f in fc["features"] if f["properties"].get("country") == "at"}
regional = {"burgenland", "niederosterreich", "steiermark", "wien", "karnten",
            "oberosterreich", "salzburg", "tirol", "vorarlberg",
            "weinland", "steirerland", "bergland",
            "ruster-ausbruch", "wiener-gemischter-satz"}
dacs = [s for s in g if s not in regional]
bad = [(a, b) for a, b in itertools.combinations(dacs, 2)
       if g[a].intersects(g[b])
       and g[a].intersection(g[b]).area / min(g[a].area, g[b].area) > 0.005]
print("overlapping proper-DAC pairs:", bad or "none — all disjoint")
PY
```

---

## Slovenia

### 2026-05-22 — eAmbrosia ↔ vinorodne-dežele cross-check ✅

**Independent authority**: the Slovenian wine-law region/district
structure — 3 vinorodne dežele (wine regions) partitioned into 9
vinorodni okoliši (districts) — independent of the eAmbrosia EU-register
spine. Reference: English Wikipedia, *Slovenian wine* (CC BY-SA 4.0),
<https://en.wikipedia.org/wiki/Slovenian_wine>.

The pipeline corpus is **17 wine GIs (14 DOP + 3 IGP)**, sourced from
eAmbrosia (`country=SI` + `productType=WINE` + `status=registered`).

| Check | Expected | Pipeline | Match |
|---|---:|---:|:---:|
| Total wines | 17 | 17 | ✓ |
| DOP | 14 | 14 | ✓ |
| IGP (= the 3 vinorodne dežele) | 3 | 3 | ✓ |
| Figshare 2022 DOP polygons | 14 | 14 | ✓ |

**Reconciliation of the 14 DOP**: 9 vinorodni okoliši (Štajerska
Slovenija, Prekmurje, Bizeljsko Sremič, Dolenjska, Bela krajina, Goriška
Brda, Vipavska dolina, Kras, Slovenska Istra) + 5 traditional-name DOPs
(Cviček, Belokranjec, Bizeljčan, Metliška črnina, Teran) = 14. The 3
IGPs are the regions themselves (Podravje, Posavje, Primorska).

The curated `file_number → region` map in `scripts/_lib/si/region.py`
partitions all 17 wines cleanly across the 3 regions (7 + 5 + 2 DOP,
+ 1 IGP each). 16 of 17 are content-stubs (`no-publication`) — only
Cviček carries a fetchable EU single document; see CURATOR_TODO.

**Re-run recipe**:

```
.venv/bin/python scripts/si/00_fetch_data.py
.venv/bin/python scripts/audit_si_coverage.py
```

Compare the kind counts + region distribution against the region/
district structure at the Wikipedia URL above.

---

## Romania

### 2026-05-30 — eAmbrosia ↔ ONVPV national DOC/IG register cross-check ✅

**Independent authority**: Oficiul Național al Viei și Produselor
Vitivinicole (ONVPV), the Romanian national wine regulator — its
published *denumiri de origine controlată (DOC)* and *indicații
geografice (IG)* register pages (a different bureaucratic list from
the EU eAmbrosia register the pipeline is built on).
URLs: <https://www.onvpv.ro/ro/content/caiete-de-sarcini-pentru-obtinerea-vinurilor-cu-denumire-de-origine-controlata-doc-0>
(DOC) and <https://www.onvpv.ro/ro/content/indicatii-geografice> (IG).

| Check | ONVPV | Pipeline | Match |
|---|---:|---:|:---:|
| IG (IGP) | 12 | 12 | ✓ (exact, name-for-name) |
| DOC (DOP) | 35 | 34 | 34/35 — delta explained |

**Explained delta**: the one DOC in the ONVPV national register absent
from our corpus is **Strunga** (a Moldavian DOC). It is **not present
in eAmbrosia at all** (verified by scanning the full EU register, all
statuses) — i.e. it is a Romania-national-only DOC never registered /
protected at EU level. The pipeline's spine is the EU eAmbrosia
register, so excluding Strunga is correct by scope, not a dropped
record. All other 34 DOC names reconcile name-for-name.

**Note on the "54" figure**: earlier docs cited 54 RO wine GIs. That
counted eAmbrosia administrative *re-registrations* of the same wine
(Murfatlar, Dealu Mare, Panciu, … each carry a 2007-protected entry +
later modification entries, all `status=registered`). Stage 00
de-duplicates by slug to **46 unique GIs (34 DOP + 12 IGP)**, which is
what ONVPV's register also reflects (35 DOC − 1 national-only + 12 IG).

Re-runnable recipe:
```
.venv/bin/python scripts/audit_ro_coverage.py        # 46 wines, 0 stubs
# Independent counts: fetch the two ONVPV register pages above and
# count DOC / IG names; compare to `by_kind` in the audit header.
```

---

## Bulgaria

### 2026-05-23 — eAmbrosia ↔ Закон за виното (5-region structure) cross-check ✅

**Independent authority**: the Bulgarian Wine Act (Закон за виното и
спиртните напитки) partitions the country into 5 traditional wine
regions (винарски район). The 2 EU PGIs are themselves named regions
covering the two macro halves of the country (north / south of Stara
Planina). Reference: English Wikipedia, *Bulgarian wine* (CC BY-SA 4.0),
<https://en.wikipedia.org/wiki/Bulgarian_wine>.

The pipeline corpus is **54 wine GIs (52 DOP + 2 IGP)**, sourced from
eAmbrosia (`country=BG` + `productType=WINE` + `status=registered`).

| Check | Expected | Pipeline | Match |
|---|---:|---:|:---:|
| Total wines | 54 | 54 | ✓ |
| DOP | 52 | 52 | ✓ |
| IGP (= the 2 macro PGIs) | 2 | 2 | ✓ |
| Figshare 2022 PDO polygons | 52 | 52 | ✓ |

**Reconciliation of the 52 DOP across 5 wine regions** (via the curated
`file_number → region` map in [scripts/_lib/bg/region.py](scripts/_lib/bg/region.py)):

| Wine region | PDOs | PGI |
|---|---:|---|
| Дунавска равнина (North) | 21 | + 1 PGI |
| Черноморски район (Black Sea coast) | 8 | — |
| Розова долина (Sub-Balkan / Rose Valley) | 2 | — |
| Тракийска низина (South-Central) | 17 | + 1 PGI |
| Долината на Струма (Southwestern) | 4 | — |
| **Total** | **52** | **+ 2** |

The 2 PGIs map cleanly: Дунавска равнина PGI = the entire Northern
wine region (21 PDOs); Тракийска низина PGI = the four southern wine
regions combined (31 PDOs). Hand-verified mapping in
[scripts/_lib/bg/geometry.py](scripts/_lib/bg/geometry.py) `BG_PGI_MEMBER_PDOS`.

Only 3 of 54 wines (Мелник, Нова Загора, Дунавска равнина) carry a
fetchable EUR-Lex ЕДИНЕН ДОКУМЕНТ; the other 51 are content-stubs
(`no-publication`) — see CURATOR_TODO. Bétard 2022 nonetheless gives
every BG PDO a polygon, so 100 % of records render on the map.

**Re-run recipe**:

```
.venv/bin/python scripts/bg/00_fetch_data.py
.venv/bin/python scripts/audit_bg_coverage.py
```

Compare the kind counts + region distribution against the wine-law
5-region structure at the Wikipedia URL above. Note the asymmetric
PGI mapping — the south PGI subsumes 4 sub-regions while the north
PGI is coextensive with one.

### 2026-05-30 — ИАЛВ national-spec layer: grape + terroir coverage ✅

**Independent authority**: the ИАЛВ / IAVV per-wine продуктова
спецификация (Изпълнителна агенция по лозата и виното), published as
PDFs and listed at
<https://eavw.com/wps/portal/executive-ialv/legislation/wines.with.pdo.and.pgi/specifications.of.wines.with.pdo.and.pgi>
("Спецификации на вина със ЗНП и ЗГУ", upd. 14 Jun 2024 — 52 ЗНП + 2
ЗГУ). Official act of a state administration body → ЗАПСП Art. 4
copyright exemption. Resolved 2026-05-30 via `/research-gaps`; EUR-Lex
cross-check independently confirmed 0 of the 51 grandfathered names
have a published EU-OJ single document (only Мелник / Нова Загора /
Дунавска равнина do).

The 51 grandfathered stubs were augmented from this source (stages 01c
+ 02f → stage-04 augment → 02d/02e). Each spec is the same numbered
1–8 template: section 5 = винени сортове грозде, section 6 = Връзка с
географския район (terroir).

| Check | Expected | Pipeline | Match |
|---|---:|---:|:---:|
| Specs fetched (51 grandfathered) | 51 | 51 | ✓ |
| Sidecars with grapes | 51 | 51 | ✓ |
| Sidecars with terroir text ≥200 chars | 51 | 51 | ✓ |
| All 54 BG wines with ≥1 grape | 54 | 54 | ✓ |
| All 54 BG wines with terroir bullets (02d) | 54 | 54 | ✓ |
| Total principal grape slugs | — | 418 | — |
| Total terroir bullets (02d) | — | 544 | — |

Spot-checks (smoke wines): Поморие (Шардоне, Мускат отонел, Каберне
совиньон, Мерло; 2.4 KB terroir), Сухиндол (Каберне совиньон, Мерло,
Гъмза→kadarka), Долината на Струма (20 varieties incl. Широка мелнишка
лоза / Мелник 82). 18 BG-native crossings + 9 international synonyms
added to `grape_lexicon.py` with researched colours; 1 residual
source-typo (`Шардоне Димят`) handled by the parser's whitespace-split
fallback.

**Re-run recipe**:

```
.venv/bin/python scripts/bg/01c_fetch_specifikacije.py
.venv/bin/python scripts/bg/02f_extract_national_specs.py --all
.venv/bin/python scripts/audit_bg_coverage.py   # see the national-spec + terroir sections
```

---

## Hungary

### 2026-05-30 — eAmbrosia ↔ Agrárminisztérium termékleírás register cross-check ✅

**Independent authority**: the Agrárminisztérium (Hungarian Ministry of
Agriculture) wine-sector portal `boraszat.kormany.hu/termekleirasok2`
publishes the national **termékleírás** (product specification) for every
Hungarian OEM/OFJ — the regulator's own per-appellation register, a
different bureaucratic list from the EU eAmbrosia register the pipeline is
built on. HNT (Hegyközségek Nemzeti Tanácsa, `hnt.hu`) delegates to this
index. Public official act (Szjt. 1999. évi LXXVI. tv. §1(4) — úrhivatalos
exemption).

| Check | termékleírás register | Pipeline | Match |
|---|---:|---:|:---:|
| 15 grandfathered flagships have a published spec | 15 | 15 | ✓ (each fetched + sha-pinned in `raw/hu/national-specs/manifest.json`) |
| eAmbrosia wine GIs (corpus spine) | — | 41 (35 DOP + 6 PGI) | — |
| On the map | — | 41 / 41 (100 %) | — |
| Wines with grapes | — | 41 / 41 (1292 slugs; 16 via termékleírás) | — |
| Wines with terroir facts (02d) | — | 41 / 41 (368 bullets) | — |

(The 16th national spec is Badacsony — a non-stub whose EU document has an
awkward structure that left its grape section unrouted; it is backfilled
from its termékleírás via the fill-if-empty augment.)

**What was independently confirmed**: the 15 grandfathered wines whose
eAmbrosia entry carries only a non-fetchable `Ares(...)` reference (Tokaj,
Villány, Sopron, Szekszárd, Pannonhalma, Pécs, Bükk, Somlói, Nagy-Somló,
Balatonfüred-Csopak, Csongrád, Balatonboglár, Káli, + the Balatonmelléki
and Zemplén PGIs) each resolve to a published termékleírás PDF on the
Agrárminisztérium register — independently confirming they are genuine
Hungarian OEM/OFJ, not pipeline artefacts. Each spec is the EU
single-document template in Hungarian (Roman-numeral outline) and parses
cleanly (`hu-termekleiras-v1`): 15/15 yield grapes + commune list +
terroir text. The other 26 wines carry a fetchable EUR-Lex EGYSÉGES
DOKUMENTUM (the pipeline's primary path) and also appear on the register.

**Caveat / not-yet-done**: a full machine-countable cross-check of the
register *total* (to mirror the RO 35-DOC + 12-IG name-for-name table) is
blocked because the per-appellation leaf pages
(`…/termekleirasok2/<slug>`) are JavaScript shells — the document links are
JS-injected, not in the raw HTML. A curator browser pass (or the
`/research-gaps` Claude-extension prompt path) can enumerate the index to
confirm the 41-wine total against the register name-for-name.

Spot-checks (smoke wines): Tokaj (Furmint, Hárslevelű, Kabar, Kövérszőlő,
Sárgamuskotály→muscat-blanc, Zéta; 27 communes; UNESCO-világörökség
terroir text), Villány (29 varieties incl. Kékfrankos→blaufränkisch,
Kékoportó→blauer-portugieser; 16 communes), Soltvadkerti (single-variety
Ezerjó; section-8 terroir recovered after the older-template keyword fix —
meszes lepelhomok, 75 %+ kvarc → filoxéra-immunitás).

**Re-run recipe**:

```
.venv/bin/python scripts/hu/01c_fetch_specifikacije.py        # fetch 15 termékleírás (curl; incomplete TLS chain)
.venv/bin/python scripts/hu/02f_extract_national_specs.py --all
.venv/bin/python scripts/audit_hu_coverage.py                 # 41/41 mapped, 0 stubs needing input
# Independent check: open boraszat.kormany.hu/termekleirasok2 in a browser
# and confirm each corpus name has a termékleírás leaf page.
```

## Slovakia — national-spec layer (ÚPV SR špecifikácia výrobku)

**Date**: 2026-05-30. **Source**: Úrad priemyselného vlastníctva SR /
Slovak Industrial Property Office (indprop.gov.sk), register of
designations of origin / geographical indications — listing
`https://www.indprop.gov.sk/oznacenia-povodu-vyrobkov-a-zemepisne-oznacenia-vyrobkov/OPVAZOV/specifikacie-op-zo/vina-a-liehoviny`,
one text-layer PDF per protected name at
`/swift_data/source/pdf/specifikacie_op_oz/<slug>.pdf`. Official act
(úradné dielo, §3 Autorský zákon). Resolved via `/research-gaps
national-spec sk`.

**What was independently confirmed**:
- *EUR-Lex negative-check* — 0 of the 6 grandfathered SK wines
  (Východoslovenská, Južnoslovenská, Nitrianska, Malokarpatská,
  Karpatská perla, Slovenská PGI) have a fetchable EU-OJ JEDNOTNÝ
  DOKUMENT. Positive control passed: Skalický rubín (a non-stub) surfaced
  CELEX 32017D0713(01), OJ C 224/2017 — the search finds single documents
  when they exist. So the national source is the correct path.
- *National-source scout + fetch verification* — 5 of the 6 resolve to an
  ÚPV PDF (HTTP 200, real sizes 100–198 KB), each carrying §f variety
  table + §g terroir narrative + §d commune list. The 6th, Karpatská
  perla (`PDO-SK-A1598`), is absent from the ÚPV register (404) but its
  canonical spec is public on the **mpsr.sk** mirror
  (`download.php?fID=15089`): the 1996 ÚPV *Prihláška označenia pôvodu*
  (application 0005-96), an OCR-scanned PDF with the old numbered `03.N`
  template + flat §03.5 variety list — parsed by a second branch
  `upv-sr-prihlaska-v1`. Completed from its own spec, not aliased to
  Malokarpatská (which the public-source rule would forbid).

**Outcome scorecard** (`scripts/audit_sk_coverage.py`, 2026-05-31):
- National-spec sidecars: **6 / 6**, all with grapes + terroir ≥ 200
  chars; 237 principal grape-slugs total (41–42 per modern-spec wine; 31
  for Karpatská perla — the SK regions permit the full Listina
  registrovaných odrôd).
- Terroir-fact bullets (02d, country=sk): **10 / 10 wines, 91 bullets**
  (4 prior non-stubs + 5 modern-spec + Karpatská perla's 4 from the
  prihláška §03.2/03.4 granite-soil narrative), translated en/fr/es/nl.
- Geometry: **10 / 10 mapped** (unchanged — figshare-pdo + alias + PGI
  union).
- Curator queue: **0** (empty — every Slovak wine extracted).
- Parser `upv-sr-specifikacia-v1` takes only the left **Odroda** column of
  the §f `Odroda | Synonymum` table, so the Pesecká leánka ↔ Feteasca
  regala synonym confusion never reaches the matcher. 6 VÚVV/Pospíšilová
  crossings folded into `grape_lexicon.py` (VIVC-anchored): Breslava
  #1671, Mília #22818, Noria #22819 (blanc); Nitranka #17282, Rudava
  #17283, Torysa #22419 (noir).

**Re-run recipe**:

```
.venv/bin/python scripts/sk/01c_fetch_specifikacije.py
.venv/bin/python scripts/sk/02f_extract_national_specs.py --all
.venv/bin/python scripts/sk/02d_extract_terroir_facts.py --batch --provider anthropic
.venv/bin/python scripts/sk/02e_translate_terroir_facts.py --batch --provider anthropic
.venv/bin/python scripts/04_build_maps.py
.venv/bin/python scripts/audit_sk_coverage.py    # 6/6 augmented, 10/10 terroir, queue=0
# Independent check: open the ÚPV listing above (5 specs) + the mpsr.sk
# specifications listing (Karpatská perla = download.php?fID=15089).
```
