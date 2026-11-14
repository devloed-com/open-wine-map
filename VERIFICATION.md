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
| 4 | **Missing from INAO SIQO entirely** | Cabernet de Saumur (PDO-FR-A0257), Côtes de Blaye (PDO-FR-A0271) | ✅ **Resolved 2026-08-26 (web-research pass): both RETIRED — intentionally absent, no pinning.** *Cabernet de Saumur*: suppressed July 2016, folded into AOC Saumur as Saumur rosé — Arrêté du 19 juillet 2016 (JORF 29/07/2016), art. 2 abrogates Décret n° 2011-1360 (abrogation banner at legifrance.gouv.fr/loda/id/JORFTEXT000024717966); INAO product page 8125 is 404. *Côtes de Blaye*: not claimed since 2015, removed from INAO's AOC list (national retirement by cessation, no abrogation décret found); EU cancellation application **PDO-FR-A0271-CANCEL** filed 13/01/2026, status "Applied" in eAmbrosia as of 2026-08-26 (likely OJ notice C/2026/2994 — EUR-Lex WAF-blocked, confirm in a browser). Both eAmbrosia `registered` rows are stale-register artifacts (the Austrian-PDO precedent). |

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

### 2026-10-24 — Nivegy-völgy / Nivegy-völgyi added (eAmbrosia 42 → 43) ✅

Live eAmbrosia (`country=HU`, `productType=WINE`, `status=registered`) lists
43 wine GIs (37 DOP + 6 PGI); the cached index had 42. The delta is
**Nivegy-völgy / Nivegy-völgyi** (`PDO-HU-02816`), registered by Commission
Implementing Regulation (EU) 2026/2105 (OJ L, 21.9.2026; single document OJ
C/2026/2812 of 21.5.2026).

| Check | reference | pipeline | Match |
|---|---:|---:|:---:|
| eAmbrosia wine GIs | 43 | 43 (`raw/hu/eambrosia/index.json`) | ✓ |
| Nivegy-völgy single document | EUR-Lex C/2026/2812 | fetched (stage 01), 6 varieties, 7 települések, §8 link text 5.7 KB (stage 02) | ✓ |
| Region | mainly inside the Balatonfüred-Csopak PDO, partly Balaton-felvidék; "A címkén a „Balaton borrégió” megnevezés feltüntethető" (the document's own wording) | `Balaton` (`_lib/hu/region.py`) | ✓ |
| Geometry | post-Bétard; §6 lists Balatoncsicsó, Monoszló, Óbudavár, Szentantalfa, Szentjakabfa, Tagyon, Zánka | `gisco-commune-union` of the 7 GISCO LAU 2024 units — one polygon, 58.4 km²; `audit_geometry_vs_text.py` OK (7 named, 7 drawn) | ✓ |
| On the map | — | stage 04 (2026-10-24, 2,956 records): PDO, Balaton, White from the grape floor (the text names its two wine types by their yellow colour, never "fehér"); `audit_hu_coverage.py` 43 / 43 on the map | ✓ |
| Terroir facts | — | 15 facts (natural factors 7, human factors 4, product 3, interactions 1; all from the single document — hu.wikipedia has no wine article, pinned `missing`); gate 12 supported, 3 rewritten, 0 dropped; translated en / fr / es / nl, the back-check fixed 3 NL bullets | ✓ |

Recipe:

```
.venv/bin/python scripts/hu/00_fetch_data.py
.venv/bin/python scripts/hu/01_fetch_pliegos.py --only nivegy-volgy
.venv/bin/python scripts/hu/02_extract_pliegos.py --only nivegy-volgy
.venv/bin/python scripts/02b_fetch_aoc_lexicon.py --lang hu --source raw/hu/dokumentumok-extracted --only nivegy-volgy
.venv/bin/python scripts/hu/02d_extract_terroir_facts.py --only nivegy-volgy --provider anthropic
.venv/bin/python scripts/02d_verify_terroir_facts.py --only nivegy-volgy
.venv/bin/python scripts/hu/02e_translate_terroir_facts.py --only nivegy-volgy --provider anthropic
.venv/bin/python scripts/02e_verify_terroir_facts.py --only nivegy-volgy
.venv/bin/python scripts/hu/03_generate_wiki.py && .venv/bin/python scripts/04_build_maps.py
.venv/bin/python scripts/audit_hu_coverage.py
```

### 2026-09-20 — Mura / Murai added (eAmbrosia 41 → 42) ✅

Live eAmbrosia (`country=HU`, `productType=WINE`, `status=registered`) lists
42 wine GIs (36 DOP + 6 PGI); the cached index had 41. The delta is
**Mura / Murai** (`PDO-HU-02817`), registered by Commission Implementing
Regulation (EU) 2026/1792 of 15 July 2026 (single document OJ C/2026/1833).

| Check | reference | pipeline | Match |
|---|---:|---:|:---:|
| eAmbrosia wine GIs | 42 | 42 (`raw/hu/eambrosia/index.json`) | ✓ |
| Mura single document | EUR-Lex C/2026/1833 | fetched (stage 01), 12 varieties, 8 települések, §8 link text (stage 02) | ✓ |
| Region | Zalai borvidék → Balaton borrégió (the document's own wording) | `Balaton` (`_lib/hu/region.py`) | ✓ |
| Geometry | post-Bétard; §6 lists Becsehely, Csörnyeföld, Dobri, Letenye, Murarátka, Muraszemenye, Tormafölde, Zajk | `gisco-commune-union`, 8 / 8 communes matched | ✓ |
| On the map | — | 42 / 42 (`audit_hu_coverage.py`) | ✓ |
| Terroir facts | — | 12 (gate: 10 supported, 2 rewritten, 0 dropped), translated en/fr/es/nl + back-checked | ✓ |

Recipe:

```
.venv/bin/python scripts/hu/00_fetch_data.py
.venv/bin/python scripts/hu/01_fetch_pliegos.py --only mura
.venv/bin/python scripts/hu/02_extract_pliegos.py --only mura
.venv/bin/python scripts/02b_fetch_aoc_lexicon.py --lang hu --source raw/hu/dokumentumok-extracted
.venv/bin/python scripts/hu/02d_extract_terroir_facts.py --only mura --provider anthropic
.venv/bin/python scripts/02d_verify_terroir_facts.py --only mura
.venv/bin/python scripts/hu/02e_translate_terroir_facts.py --only mura --provider anthropic
.venv/bin/python scripts/02e_verify_terroir_facts.py --only mura
.venv/bin/python scripts/hu/03_generate_wiki.py && .venv/bin/python scripts/04_build_maps.py
.venv/bin/python scripts/audit_hu_coverage.py
```


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

---

## Malta (MT) — 2026-05-31

**Claim**: 3 Maltese wine GIs (2 DOP + 1 IGP), all 3 on the map.

- eAmbrosia (`country=MT` + `productType=WINE` + `status=registered`):
  **3** wines — Malta `PDO-MT-A1630`, Gozo `PDO-MT-A1629`,
  Maltese Islands `PGI-MT-A1631`. Matches Malta's wine law (the only
  two PDOs are the two inhabited islands; the PGI is the archipelago
  umbrella). No cancelled/duplicate registrations.
- Extraction: **2 / 2 PDOs** parsed from the EU-OJ English SINGLE
  DOCUMENT (sections 1–9, ~30 varieties each incl. the indigenous
  Ġellewża + Girgentina); the PGI is a `no-publication` content-stub.
- Geometry: **3 / 3 mapped** — 2 `figshare-pdo` (Bétard 2022 carries
  both MT PDOs) + 1 `region-pdo-union` (Maltese Islands = Malta ∪ Gozo).
- Styles: red / rosé / sparkling / white (from grape-colour + the
  oenological-practice block).
- Terroir-fact bullets (02d, country=mt, Wikipedia-primary — the
  amendment documents carry no link-to-terroir section): **2 each**
  for Malta / Gozo / Maltese-Islands, grounded on the en.wikipedia
  "Maltese wine" article, translated fr/es/nl.
- Curator queue: 1 (the PGI, geometrically resolved; no action needed).

**Re-run recipe**:

```
.venv/bin/python scripts/mt/00_fetch_data.py        # 3 wines (DOP=2, IGP=1)
.venv/bin/python scripts/mt/01_fetch_pliegos.py     # ok=2, no-pub=1
.venv/bin/python scripts/mt/02_extract_pliegos.py   # extracted=2 stubs=1
.venv/bin/python scripts/02b_fetch_aoc_lexicon.py --lang en --source raw/mt/dokumente-extracted
.venv/bin/python scripts/mt/02d_extract_terroir_facts.py --batch --provider anthropic
.venv/bin/python scripts/mt/02e_translate_terroir_facts.py --batch --provider anthropic
.venv/bin/python scripts/mt/03_generate_wiki.py
.venv/bin/python scripts/04_build_maps.py
.venv/bin/python scripts/audit_mt_coverage.py       # 3 wines, 2 figshare + 1 union, 0 open stubs
# Independent check: eAmbrosia register UI, filter country=Malta + Wine.
```

## Cyprus (CY) — 2026-05-31

**Claim**: 11 Cypriot wine GIs (7 PDO + 4 PGI), all 11 on the map with
grapes; 8 with terroir facts.

- eAmbrosia (`country=CY` + `productType=WINE` + `status=registered`):
  **11** wines — 7 PDO (`PDO-CY-A1622` Κουμανδαρία/Commandaria,
  `A1623` Κρασοχώρια Λεμεσού - Αφάμης, `A1624` … - Λαόνα, `A1625` Βουνί
  Παναγιάς – Αμπελίτης, `A1626` Λαόνα Ακάμα, `A1627` Πιτσιλιά, `A1628`
  Κρασοχώρια Λεμεσού) + 4 PGI (`PGI-CY-A1618` Πάφος, `A1619` Λεμεσός,
  `A1620` Λάρνακα, `A1621` Λευκωσία). The 4 PGIs are the island's wine
  districts; matches Cyprus wine law.
- Geometry: all 7 PDOs in Bétard 2022 `EU_PDO.gpkg` (`figshare-pdo`);
  the 4 PGIs union the GISCO LAU CY communities by district GISCO_ID
  digit (`gisco-district-union`). **11/11 on the map**, 0 stubs.
- National-spec source: moa.gov.cy Department of Agriculture τεχνικός
  φάκελος (Greek EU single-document PDF), one per wine. Stage 01c scrapes
  the «Αμπελουργία / Οινολογία» listing page (WAF-free) and name-matches
  all 11; stage 02f parses (pdftotext, OCR-`ell` fallback for the 3
  image-only scans). **11/11 with grapes (226 slugs)**; 11/11 with a
  terroir-source section (the 3 image-only scans were swapped for the
  text-layer eAmbrosia attachment PDFs — see CURATOR_TODO 2026-05-31).
- Grapes spot-check: Commandaria = Mavro + Xynisteri (the two canonical
  Commandaria varieties); Pitsilia = Giannoudi/Maratheftiko/Mavro/
  Xynisteri/Ofthalmo. Native Cypriot varieties folded into the lexicon
  with VIVC/wein.plus-researched colours.
- Terroir-fact bullets (02d, country=cy, Greek source → en/fr/es/nl):
  **4–10 each** for all 11 wines (73 bullets total),
  Anthropic batch.

**Re-run recipe**:

```
.venv/bin/python scripts/cy/00_fetch_data.py        # 11 wines (DOP=7, IGP=4)
.venv/bin/python scripts/cy/01_fetch_pliegos.py     # all no-pub (EU-OJ stubs)
.venv/bin/python scripts/cy/02_extract_pliegos.py   # 11 stubs
.venv/bin/python scripts/cy/01c_fetch_specifikacije.py   # scrape moa.gov.cy → fetch 11 PDFs
.venv/bin/python scripts/cy/02f_extract_national_specs.py --all   # grapes/terroir (OCR fallback)
.venv/bin/python scripts/02b_fetch_aoc_lexicon.py --lang el --source raw/cy/dokumenti-extracted
.venv/bin/python scripts/cy/02d_extract_terroir_facts.py --batch --provider anthropic
.venv/bin/python scripts/cy/02e_translate_terroir_facts.py --batch --provider anthropic
.venv/bin/python scripts/cy/03_generate_wiki.py
.venv/bin/python scripts/04_build_maps.py
.venv/bin/python scripts/audit_cy_coverage.py       # 11 wines, 7 figshare + 4 district-union, 11/11 grapes
# Independent check: eAmbrosia register UI, filter country=Cyprus + Wine.
```

## United Kingdom (GB) — 2026-09-06

**Independent cross-check** of the corpus count against the regulator's own
register, which for the UK is *not* eAmbrosia: since Brexit the authority is
the **GOV.UK "protected food and drink names" register** run by DEFRA.

- Source of truth queried directly (not via the cached index):
  `https://www.gov.uk/api/search.json?filter_format=protected_food_drink_name&filter_register=wines&filter_country_of_origin=united-kingdom`
  → **7 UK wine entries**, of which **6 `status=registered`** and 1
  `status=applied-for` (*The Crouch Valley*, PDO, applied 2023-03-06 — still
  in assessment, correctly excluded from the corpus).
- Corpus: **6 wines — 4 PDO** (`PDO-GB-A1585` English, `PDO-GB-A1587` Welsh,
  `PDO-GB-02365` Sussex, `PDO-GB-N1636` Darnibole) **+ 2 PGI**
  (`PGI-GB-A1589` English Regional, `PGI-GB-A1590` Welsh Regional).
  Matches WineGB's public PDO/PGI page.
- File numbers cross-checked against `raw/eambrosia-register/gi-index.json`
  (countryId=gb, qualityProductType=Wine): all 6 present there too — the
  five pre-Brexit names retained under the Withdrawal Agreement, Sussex
  added 2025-01-31 under the UK-EU agreement. The GOV.UK register itself
  publishes no file number, hence the bridge in stage 00.
- **Specification coverage: 6/6.** Every registered wine ships a public
  product specification from `assets.publishing.service.gov.uk` (5 PDF +
  Sussex's .docx). No stub tier, no national-spec fallback layer, no WAF.
- Grapes: **6/6 with a resolved roster** — English/Welsh PDO 81 each,
  the two Regional PGIs 85 each, Sussex 28, Darnibole 1 (100% Bacchus,
  as its specification states). Spot-check: the Sussex sparkling roster
  (Chardonnay, Pinot Noir, Pinot Meunier, Arbanne, Pinot Gris, Pinot
  Blanc, Petit Meslier, Pinot Noir Précoce) matches the specification's
  §7.2 verbatim.
- Geometry: **6/6 on the map**, all from ONS Open Geography (OGL v3.0) —
  Bétard 2022 is an EU PDO layer and has no `PDO-GB-*` rows.
  Areas cross-checked against published administrative figures:

  | record | resolved km² | published km² |
  |---|---:|---:|
  | English / English Regional | 130 522 | 130 279 (England) |
  | Welsh / Welsh Regional | 20 790 | 20 779 (Wales) |
  | Sussex | 3 788 | 3 782 (E. Sussex 1 709 + W. Sussex 1 991 + Brighton & Hove 82) |
  | Darnibole | 0.061 | "whole 5 hectare area" (its specification) |

- **Darnibole placement check** (its boundary is reconstructed — see
  CLAUDE.md): the resolved centroid sits 502 m from the ONS centroid of
  Camel Valley's postcode PL30 5LG and 918 m from Nanstallon village, and
  falls inside the English PDO polygon. An EU-DEM 25 m transect confirms
  the parcels sit at 47–80 m on a ~13 % south-facing slope with the valley
  floor at 11–14 m immediately south — matching the specification's "steep
  south facing slope" bounded by the River Camel's old bed.
- Terroir-fact bullets (02d, country=gb, English source → fr/es/nl):
  **51 bullets across 6/6 wines** (5–10 each), Anthropic batch;
  49 of 51 grounded in the specification itself (`provenance=cahier`),
  which is the expected shape for a cahier-primary country.

**Re-run recipe**:

```
.venv/bin/python scripts/gb/00_fetch_data.py        # 6 registered (+1 pending), ONS boundaries
.venv/bin/python scripts/gb/01_fetch_specs.py       # 6 specs (5 pdf + 1 docx)
.venv/bin/python scripts/gb/02_extract_specs.py     # 6/6 extracted, 0 stubs
.venv/bin/python scripts/02b_fetch_aoc_lexicon.py --lang en --source raw/gb/specs-extracted
.venv/bin/python scripts/gb/02d_extract_terroir_facts.py --batch --provider anthropic
.venv/bin/python scripts/gb/02e_translate_terroir_facts.py --batch --provider anthropic
.venv/bin/python scripts/gb/03_generate_wiki.py
.venv/bin/python scripts/04_build_maps.py
.venv/bin/python scripts/audit_gb_coverage.py       # 6 wines, 0 problems
# Independent check: https://www.gov.uk/protected-food-drink-names
#   → filter Register = "Wines", Country of origin = "United Kingdom".
```

## 2026-09-07 — traditional terms vs the national rosters (IT MASAF elenco, ES MAPA listado)

Independent cross-check of the `national_term` axis introduced with the two-axis naming
layer (`scripts/_lib/gi_terms.py`, `scripts/_lib/traditional_terms.json`).

| check | corpus (parents, wines) | reference | result |
|---|---:|---|---|
| IT DOCG | 79 | MASAF *Elenco alfabetico dei vini DOP* agg. 18.03.2026: 79 DOCG rows | ✅ equal |
| IT DOC | 333 | elenco 332 + Valtènesi (registered 2026-03-18, Reg. (EU) 2026/572, pinned) | ✅ equal |
| IT IGT | 111 | eAmbrosia IT PGI records (112 incl. the Salemi stub not on the map) | ✅ |
| ES DOCa/DOQ | 1 + 1 | MAPA listado 2 July 2026: DOCa 2 (Rioja, Priorat; Priorat shown as DOQ) | ✅ |
| ES Vino de Pago | 28 | listado VP 27 + Urbezo (VP per MAPA 2024-10-25, listado still DO; pinned) | ✅ |
| ES Vino de Calidad | 7 | listado VC 7 | ✅ |
| ES DO | 69 | listado DO 70 − Urbezo | ✅ |
| ES Vino de la Tierra | 43 | listado VT 43 (all 43 ES PGIs) | ✅ |
| AT DAC | 18 | BML DAC-Verordnungen page 17 + Wagram (RIS) | ✅ |
| sub == parent | 1,242 subs | every sub-denomination's (eu_scheme, national_term) equals its parent's | ✅ 0 mismatches |
| kind invariant | AOC 1404 / AOP 1 / DOP 944 / EDV 28 / IGP 537 | same counts in `appellations{,-villages}.geojson` before and after | ✅ unchanged |

Recipe:

```
.venv/bin/python scripts/it/00_fetch_data.py        # refreshes raw/it/masaf-elenchi/ (dated ServeAttachment link)
.venv/bin/python scripts/es/00_fetch_data.py        # refreshes raw/es/mapa/listado-dop-igp-vinos.pdf
.venv/bin/python scripts/04_build_maps.py
.venv/bin/python scripts/audit_gi_terms.py --strict
grep -o '"kind": *"[A-Z]*"' wiki/map-data/appellations.geojson | sort | uniq -c
```

## Austria — BML Produktspezifikation layer (2026-11-08)

Independent cross-check of the stage 01c / 02f layer that adds the national
specification's authorised roster to the 30 AT records (CLAUDE.md "AT
national-spec layer"). Reference: the BML Weinherkunft page
(`https://www.bmluk.gv.at/themen/landwirtschaft/landwirtschaft-in-oesterreich/pflanzliche-produktion/wein/Weinherkunft.html`)
and the PDFs it links, read by hand for the section f) shapes.

| check | corpus | reference | result |
|---|---:|---|---|
| PDFs the page links | 31 files | 30 designations, Eisenberg twice | ✅ 30 slugs matched, 0 unmatched files; the 2025 Eisenberg file pinned (its § f names Blaufränkisch and Welschriesling, as the EU single document in force) |
| sidecars | 30 / 30 | every file carries a section f) | ✅ roles: hauptsorten 5 · national-roster 9 · exclusive-list 15 · open 1 |
| national roster size | 35 slugs | the two colour blocks name 36 varieties, "Weißer Riesling (Riesling, Rheinriesling)" and the Bundesland lists' "Traminer (Gewürztraminer, Roter Traminer, Gelber Traminer)" one slug each | ✅ 35 on every Bundesland PDO and PGI |
| Wachau | 2 → 16 | § f: Hauptsorten Grüner Veltliner + Riesling; Gebietswein list of 17 incl. "Gemischter Satz" (a field blend, no variety) | ✅ hauptsorten = the EU § 7 pair; 14 accessories; tiers 16 / 9 / 2 |
| trap words | 0 wrong bindings | "Steiermark" (VIVC synonym of Furmint), bare "Burgunder" (→ Blaufränkisch), "Morillon" (French Pinot noir synonym; Austrian for Chardonnay) | ✅ none bound / Morillon → Chardonnay on Südsteiermark, Vulkanland, Weststeiermark |
| roster names the lexicon lacks | 0 | "Welschrielsing" (2025 Eisenberg typo) → `GRAPE_ALIAS` | ✅ unknowns queue empty |
| varieties added at stage 04 | 368 on 15 records | 10 Bundesland PDOs / PGIs 2–3 → 35, Oberösterreich 19 → 35, Wachau 2 → 16, Weststeiermark 1 → 9, Wiener Gemischter Satz 21 → 22, Salzburg 34 → 35 | ✅ `audit_at_coverage.py`; the 15 records whose EU document lists the closed roster gain nothing |
| terroir backfill | 1 record | Oberösterreich: EU link 347 chars, § g 3,567 | ✅ 9 facts (Sonnet 5.5, run `at-produktspez-2026-11-08`), gated, translated en/fr/es/nl, back-checked; the card validator's one misleading finding (the "einige wenige, vereinzelte Betriebe" hedge dropped) filed as a do-not-claim entry and re-gated: the bullet carries the hedge |
| colours the specification states | 4 cards | § b / § g sentences: Carnuntum "etwas mehr Rotwein als Weißwein", Oberösterreich "Die Rotweine werden aus den Sorten …", Wachau and Weinland "Rot- und Roséweine … untergeordnete Rolle" | ✅ Carnuntum + Red, Oberösterreich + Red, Wachau + Rosé, Weinland + Red + Rosé; the four records whose EU text states no colour (Bergland, Eisenberg, Kärnten, Steirerland) keep the berry floor by rule |
| card validator (Opus, en) | 2 cards | the rebuilt Wachau and Oberösterreich cards | ✅ Wachau "trust"; Oberösterreich "caution" → the hedge re-gated, Red merged, the BML text added to the card packet (the judge had read the grounded facts as "in no supplied document") |
| card validator, second grade | 1 card | Oberösterreich after those fixes | "caution" with two new findings: the glossary's DE "spritzig" rule rendered a still Heuriger as lightly sparkling (fixed in the glossary for en / nl / fr / es and on the back-check's watch-list — the back-check had reverted the translator's correction on its first pass; five German-source records re-translated and back-checked), and the sweet Prädikat categories of the specification's legal definitions list (queued — the SI boilerplate precedent) |

Recipe:

```
.venv/bin/python scripts/at/01c_fetch_produktspezifikationen.py        # 30 PDFs, manifest, the page cached
.venv/bin/python scripts/at/02f_extract_produktspezifikationen.py --all  # 30 sidecars
.venv/bin/python scripts/at/02d_extract_terroir_facts.py --only oberosterreich --provider anthropic
.venv/bin/python scripts/02d_verify_terroir_facts.py --country at --only oberosterreich --provider anthropic
.venv/bin/python scripts/at/02e_translate_terroir_facts.py --only oberosterreich --provider anthropic
.venv/bin/python scripts/02e_verify_terroir_facts.py --country at --only oberosterreich --provider anthropic
.venv/bin/python scripts/04_build_maps.py
.venv/bin/python scripts/audit_at_coverage.py                           # "## BML Produktspezifikation layer"
.venv/bin/python -m pytest tests/test_at_produktspezifikation.py -q
```

## Spirits and other alcoholic drinks (2026-11-12)

Independent cross-checks of the drink corpus against each register, read live on 2026-11-12 (`scripts/audit_drinks_coverage.py` reproduces the first table).

| check | count | how it was read | result |
|---|---:|---|---|
| EU register, Registered drink GIs of the corpus countries | 257 | the listing (`gi-index.json`, refreshed 2026-11-12): `qualityProductType = Spirit drink` 237, register classes 2.21 / 2.22 (aromatised wines) 5, ciders and perries 15 (class 1.8 — the curated list, INAO's rows, the UK's) | ✅ 189 in the drinks pipeline + 58 French + 10 UK rows read from GOV.UK instead; **0 in no pipeline** |
| French non-wine records | 59 parents | INAO's referentiel: sign AOC / AOP / IGP / IG, sector VITICOLE, a non-wine `categorie`; minus Genièvre (PGI-BE+NL+FR+DE-01962, a Belgian-filed GI) | ✅ 59 bound to a register file number (stage 01d), 59 on the map; 56 with a cahier, 3 stubs (CURATOR_TODO) |
| EU register rows the drinks pipeline holds | 189 | 15 countries: de 37, it 36, es 21, hu 16, gr 14, bg 12, pt 12, ro 9, at 8, hr 7, be 6, si 4, nl 3, cy 2, sk 2 | ✅ 189 / 189 extract: 167 from a technical file (5 of them the aromatised wines' `summarySheets`), 22 from an Official Journal single document |
| UK register, drinks other than wine | 16 registered + 1 applied for | GOV.UK search API: `filter_register=spirit-drinks` → Scotch Whisky, English Whisky (registered 2026-10-01), Single Malt Welsh Whisky, Dovey Native Botanical Gin (2025-03-31), Somerset Cider Brandy, Irish Whiskey, Irish Cream, Irish Poteen; food register class 1.8 → 8 cider / perry PGIs; Cornish Cyder Brandy is `applied-for` | ✅ 16 / 16 extract from their product specification; the EU register lists 10 of them (5 spirit rows, 5 "cider / perry" rows) |
| Swiss federal register of AOP / IGP | 4 spirits of 42 products | OFAG's register page ("Le registre compte actuellement 42 produits AOP/IGP"; 'Catégorie: Spiritueux'): Abricotine, Damassine, Eau-de-vie de poire du Valais, Zuger Kirsch / Rigi Kirsch — all AOP; three more are pending applications | ✅ 4 / 4 extract (cahier + application summary) |
| drinks records, total | 209 | 189 + 16 + 4 | ✅ 0 stubs; link text read for 207 (not Ratafia Ciociara, Trenčianska borovička Juniperus) |
| area pins | 151 | every quote against the record's own text, every unit against GISCO NUTS 2024 / LAU 2024 / ONS (`tests/test_drinks_areas.py`) | ✅ 151 / 151 |
| drawn | 201 of 209 | 151 from a pin, 50 from the technical file's NUTS rows | ✅ the 8 others listed with their reason in `area_queue.json` |
| no wine record changed | 0 of 2,956 | `diff_records.py` between the build before the work and each build since | ✅ only `genievre-flandre-artois` gained its region (NORD); the French spirit records gained their class fields |
| terroir facts | 2,883 on 243 records | the 209 drinks records and the 34 French spirit parents new to the corpus, runs `drinks-2026-11-12` and `drinks-2026-11-13` (extraction → claim-support gate → translation → back-check); every fact grounded on the record's own document, no Wikipedia hint | ✅ `audit_terroir_facts.py --strict` 0 failures; in the first run 2,930 extracted, 49 dropped and 333 narrowed by the gate; Batch API spend $36.96 over both runs |
| polygon against the text, drink records | 273 polygons | `audit_geometry_vs_text.py` scoped to the drink slugs, 2026-11-13 | ✅ 70 OK, 8 PINNED (the wine parsers read fewer names than the curator's pin), 175 without units, 12 above the commune tier; ❌→✅ Cassis de Saintonge was drawn as 34 communes for a cahier list of some four hundred (INAO's CSV stops after 36 rows) — pinned +363; Calvados Pays d'Auge +6, Pommeau de Bretagne +9, Pommeau de Normandie +11 pinned the same way; four aires whose rows are newer than the cahier in the build are queued |
| facts against the source, adversarial grader | 40 records, 492 English bullets | `audit_terroir_facts_llm.py` (Opus) on a seeded sample of the 243 records, two per country then at random, 2026-11-13 | ✅ 2 misleading = 0.41 % (95 % interval 0.11–1.47 %), target under 1.5 %; both were translation slips (PT "vinhas estremes" read as single-variety vineyards, BG "допринася" read as "means that"), corrected by a scoped back-check and filed in the records' feedback; 7 defective |
| whole cards against the documents | 20 drink cards | `audit_cards_llm.py --all-products` (Opus), judge told how a drink card differs from a wine card, 2026-11-13 | ✅ 19 trust, 1 caution; 24 findings, every quote verified; the 2 misleading ones are one card, Euskal Sagardoa (in the corpus before this work): a Spanish-French area drawn as its French communes — now said on the card in a cited note; the rest are omissions and by-design items listed in CURATOR_TODO |
| the map, headless | pill off / on, search, shared links | Playwright against `scripts/serve.py`, 2026-11-13 | ✅ pill off by default (2,383 of 3,191 drawn), `?sel=grappa` draws and opens nothing without `spirits=1` and Grappa with it (Brandy de Jerez, Ratafia catalana likewise); "ratafia" returns the three Ratafias with the hidden hint; `?grape=nebbiolo` 56 as before; `?style=whisky` turns the pill on and writes `spirits=1`; no page error |
| MCP server and WebMCP | same answers | `npm test` in mcp/ (24), `mcp/test/parity_webmcp.py` with four drink calls added (0 differences), local server on the new context | ✅ Spain 149 → 170 with `include_spirits` (Brandy de Jerez, Ratafia catalana among the 21), a drink category as `style` returns drinks without the flag |

Things the checks turned up: the plan expected 7 UK spirits and 5 UK cider PGIs — the live UK register has 8 and 8; the EU register holds a technical file for all five aromatised wines, in a field (`summarySheets`) the first fetch did not read; INAO's site reset every connection from this network, so 30 of the 34 new French spirits were bound through the register's `productSpecificationLink` rather than INAO's product page.

## France — the cahier wins: newer cahiers, aires against the cahier, former communes (2026-11-13)

Cross-checks made after Boris's answers of 2026-11-13 ("double check whether a newer cahier is published, cahiers are the real source of truth, so wins over inao data publication"). Sources read live that day: BO Agri's title search, geo.api.gouv.fr, INSEE's code officiel géographique 2026.

| check | count | how it was read | result |
|---|---:|---|---|
| a newer cahier than the build's, French drinks | 59 parents searched, 28 behind | BO Agri title search per name (`resultat_recherche_rapide?titre=`): the newest "Cahier des charges" against the record's `homologated_at`; every header read with pdftotext before pinning | ✅ 28 re-sourced (`raw/inao/cahiers/manual_overrides.json`: acts of 2013 to 10 June 2026), the 3 stubs among them; 0 French drink stubs left; Calvados has none newer than 17 December 2021 |
| aire rows against the cahier, French drinks | 34 records with a commune list and a CSV aire | `scripts/audit_aires_vs_cahier.py --drinks --strict` on the final build | ✅ OK 14, PINNED 20, 0 new, 0 unclear, 0 unread. 21 pins from the cahiers: 898 communes added, 10 rows removed (a neighbouring code where the cahier lists another commune), 28 named and not drawn. The first run of the day read 28 records and skipped six in silence — their list stood under a département heading stage 02 did not read; see the next row |
| cahier lists stage 02 had not read | 6 drink records | the polygon-versus-text audit's three "missing" communes of Marc d'Auvergne, then a sweep for a "Département de X" heading with no colon and for département keys the table lacks (`tmp/bare_dept_headers.py`, `tmp/aire_blind_spot.py`) | ❌→✅ read since: Eau-de-vie de cidre de Bretagne 2 → 369 names, Eau-de-vie de cidre du Maine 0 → 141, Marc du Bugey and Fine du Bugey 0 → 151, Marc d'Auvergne 88 under « Puy-deDôme » → Puy-de-Dôme, Pommeau de Bretagne +7 (Loire-Atlantique). Pinned from them: cidre du Maine +71 (INAO's rows stop at 62 of 141 communes; the polygon doubled, ×2.04), cidre de Bretagne +19 (+5 % area), Marc d'Auvergne +3 −1 (Pionsat, a neighbouring-code row whitelisted as a detached lobe the day before), Marc du Bugey +1. BO Agri's title search of the same afternoon lists no newer cahier for the four |
| the same audit, wines | 405 records | `scripts/audit_aires_vs_cahier.py` (`tmp/validation/aires-vs-cahier-all-d.json`) | ❌ queue: 28 NEW, 9 UNCLEAR, 4 UNREAD (CURATOR_TODO) — no pin written. Côtes Catalanes (222 communes) and Coteaux de l'Auxois (192), readable since the département fix, match INAO's rows |
| row codes the commune layer lacks | 31,845 over every aire of the two CSVs | `former_communes.resolve` against geo.api.gouv.fr's communes associées / déléguées (2,576 outlines) and INSEE's movements since 1943 | ✅ 21,754 drawn by their own outline, 9,700 inside a commune the aire draws, 156 dead codes of communes that left their département before 2009 for one the aire does not reach (not drawn: the cahier says "le département de …"), 235 with no outline anywhere (named on 27 cards) |
| dead codes, per record | 4 parents | INAO's `Actual` column (4 = old code after a change of département) and INSEE's event dates, against each cahier's zone sentence | ✅ IGP Isère 24 (Rhône since 1967–1971), Génépi des Alpes 24, IGP Coteaux de l'Ain 6 (1967–1968), IGP Haute-Marne 1 (Frettes, 1974); the three wine records draw exactly the area of the build before. Not in the class: a code whose new département the aire also holds (Antorpe, Jura → Doubs, on IGP Franche-Comté's units) |
| obsolete codes pinned | 4 | the French Wikipedia article of the commune that took each (read 2026-11-13): Hauteville-Lompnes "formée le 31 juillet 1942 par la réunion d'Hauteville et de Lompnes", Amélie-les-Bains-Palalda "créée en 1942 par la fusion" | ✅ `scripts/_lib/fr/former_commune_pins.json`; no card prints a bare code |
| records across a border | 2 | each quote against the record's zone text, each unit against GISCO NUTS 2024 (`tests/test_fr_cross_border.py`) | ✅ Euskal Sagardoa (France + Spain: Bizkaia, Gipuzkoa, Araba/Álava), Génépi des Alpes (France + Italy: Piemonte, Valle d'Aosta); both listed under both countries |
| the build against the one before the work | 3,191 → 3,191 records | `diff_records.py` (`records-drinks-final.json` → `records-cahiers-d.json`, the fourth and last build of the day) | ✅ 107 records changed, none added or removed. Wines: 24 changed area, every one an increase of 1.4 % or less (a former commune's outline; Cévennes +0.6 % from its Les Vignes pin); no wine lost ground. The last two rebuilds changed, against the build before each: Cévennes; then the four drinks pinned from the re-read lists |
| polygons | final build | `audit_geometry_overlaps.py --strict`, `audit_geometry_outliers.py --strict`, `audit_parcellaire_gaps.py --strict` | ✅ 0 suspicious slivers, 0 unreviewed outliers, parcel-gap pins 6 applied / 0 stale and carried-forward rows 2 applied / 0 stale. The first build of the day had 2 suspicious slivers: one was the Frettes dead code, the other a review keyed on the parents while the audit named a sub-denomination (reviews now match by family). Three outlier whitelist entries of 2026-09-25 and 2026-11-12 turned out to be wrong rows, not lobes, and were removed with the row: Marc du Jura (Les Fourgs), Marc des Côtes du Rhône (Gignac), Marc d'Auvergne (Pionsat) |
| polygon against the text, French drinks | 82 polygons | `audit_geometry_vs_text.py --country fr` scoped to the 72 French drink records and ten wines the day touched (`tmp/validation/gvt-fr-drinks-d.json`) | ✅ 68 OK, 13 without units, 1 above the commune tier, 0 SUSPECT. On the build before: 2 SUSPECT — Marc d'Auvergne (the unread list) and Pommeau de Normandie (its fifteen « Communes incluses en partie », pinned `not_drawn`, which the audit now reads as named in part) |
| stage 02, full French run | 1,575 records | every record against the snapshot taken before the run (`tmp/validation/cahier-extracted-before-full6/`) | ✅ 168 records changed (30 parents and their sub-denominations), `aire` only; none added or removed |
| terroir facts, French drinks | 57 records, 691 facts | runs `drinks-cahiers-2026-11-13` (28 records whose cahier changed) and `drinks-cahiers-2026-11-13b` (all 57, sliced by the link text's titles): extraction → claim-support gate → translation → back-check | ✅ 330 natural, 180 human, 137 product, 44 interactions; gate: 647 supported, 44 narrowed, 0 dropped; back-check 142 of 2,073 translated bullets corrected; $9.67 for both runs. Before: 50 of 58 French drinks carried natural factors only |
| translations the first back-check caught up | 19 records outside the French drinks | the chain's back-check is corpus-wide over unchecked caches (`backcheck-drinks-cahiers-2026-11-13.json`) | ✅ 40 bullets corrected: English on 10 Italian wines and Chiroubles, French or Dutch on 8 more (Italian and Greek wines; Greek, Cypriot and Hungarian drinks) — precision slips such as "temperate-cool" for "temperato e freddo" |
| a part of a commune named as a commune déléguée | 1 of 28 `not_drawn` pins | each pin's reason against the former-commune layer | ✅ IGP Cévennes: Massegros Causses Gorges "pour la partie correspondant au territoire de la commune déléguée Les Vignes" pinned as Les Vignes (48195): 4,952 → 4,981 km², one polygon; BO Agri lists no Cévennes cahier newer than 8 August 2024. The other 27 are cadastral sections, a road line, exclusions or another commune |
| the cards, headless | 12 cards | Playwright against `scripts/serve.py` on the final build (`tmp/headless_cahiers.py`) | ✅ no page error; both cross-border cards show the second country, the units drawn and the disclosure; Calvados names its 8 undrawn former communes; Isère 512, Haute-Marne 426, Coteaux de l'Ain 391, Cévennes 273, Eau-de-vie de cidre du Maine 120, Eau-de-vie de cidre de Bretagne 348, Marc d'Auvergne 87 communes |
| MCP server and WebMCP | same answers | `npm test` in mcp/ (24), `mcp/test/parity_webmcp.py` on the final build | ✅ 24 pass, 0 differences |
| release gate, quick | 15 checks | `scripts/validate_release.py --quick` on the final build (`tmp/validation/release-2026-11-13T230034.md`) | ✅ 11 pass — empty-grapes, gi-terms, styles, vivc-pins, grape-brackets, dup-keys, terroir-facts (strict), drinks-coverage, aires-vs-cahier, parcellaire-gaps, pytest (the full suite again after the last edits: 2,312 passed); ❌ 4 fail, each a standing curator queue this work did not open: grape-surfaces, ambiguous-synonyms (49), untranslated (125 pairs → 120 after the detector stopped reading a record's own name as a region), betard-delta (122). The About page says 2026-11-13: rebuild on the day of a deploy |

## France — the seat of a commune nouvelle (2026-11-14)

Boris's question on the rows whose code is today a larger commune nouvelle than the commune the row names: "Is there any clear legal interpretation about this? We should follow that reality vs deciding ourselves". Sources read live that day: the extracted cahiers of the build, the Official Journal notice of the Marsannay amendment (Publications Office, cellar copy of OJ C 89 of 16.3.2021), geo.api.gouv.fr's communes déléguées, INSEE's commune movements.

| check | count | how it was read | result |
|---|---:|---|---|
| the legal position | 500 French parent cahiers | grep of the extracted sections for "code officiel géographique" and for the restriction formulas; the "Description et motifs" of PDO-FR-A0175-AM01 (OJ C 89, 16.3.2021, p. 11) | ✅ 268 cahiers date their commune list by a code year (2017 to 2026); 521 restrictions "pour le seul territoire de la commune déléguée de …" (281 in 88 cahiers) or "des communes déléguées de …" (240 in 77), 174 "ancien territoire / ancienne commune" forms in 63; the notice: "sécuriser juridiquement la délimitation de l'aire géographique. Le périmètre de l'aire géographique reste strictement identique", "afin que celle-ci ne soit pas impactée ultérieurement par des fusions ou scissions de communes". A merger does not move an aire |
| seat rows, every French record with an aire | 2,579 rows in 234 parents, 422 of them with a merger since 2010 | `tmp/seat_rows_vs_cahier.py`: the code is a commune of today, the aire's rows lack a former commune of it; the cahier's zone text searched for today's name, the seat's former name and the restriction | ✅ the wording sorts them: restricted, old name, commune of today unrestricted, neither, no list (`tmp/validation/seat-rows-vs-cahier.json`) |
| seats the rule narrows | 176 rows in 78 records | `scripts/_lib/fr/seat_communes.py` dry run (`tmp/seats_dry_run.py`) | ✅ 102 in records drawn from parcels (no polygon moves), 74 in records drawn from INAO's rows, 25 of those with no effect (the rows carry the other former communes) |
| build with the rule | 3,191 records | full stage 04 (`tmp/logs/04-seats-e.log`), `diff_records.py` against a snapshot of the build that preceded it the same morning | ✅ 49 seats in 18 records narrowed; 19 records changed (Calvados Domfrontais inherits), `area` only, every one a decrease: Muscadet Sèvre et Maine Mouzillon-Tillières −58.8 %, Calvados Pays d'Auge −3.9 %, Calvados Domfrontais −2.1 %, Eau-de-vie de cidre du Maine −1.5 %, the two Bugey spirits −1.4 %, Calvados −1.0 %, Pommeau de Normandie −0.9 %, Pommeau de Bretagne −0.8 %, Terres du Midi −0.6 %, nine more under 0.5 %. No record added, removed or changed in any other field |
| evidence, read one by one | 49 seats | the quote each decision rests on (`tmp/validation/seats-dry-run-2.json`) | ✅ 40 by the old name in the cahier's list ("… Pointel, Putanges-Pont-Écrepin, Rabodanges …"), 7 by a restriction ("Lamballe-Armor (pour le seul territoire des communes déléguées de Lamballe, Meslin, Planguenoual)"), 2 by the date of the list (Montsûrs and La Gacilly in the cider spirits' décret of 13 February 2015, mergers of 2019 and 2017) |
| overlaps and detached parts | every pair, every record | `audit_geometry_overlaps.py --strict`, `audit_geometry_outliers.py --strict` | ✅ 0 suspicious slivers, 0 unreviewed parts |
| polygon against the text | 72 French drinks, 10 wines | `audit_geometry_vs_text.py` scoped (`tmp/validation/gvt-fr-drinks-e.json`); a narrowed seat is read as named in part | ✅ 67 OK, 13 without units, 1 above the commune tier; ❌ 1 SUSPECT, Comtés Rhodaniens, added to the scope for this run: the seven communes its cahier lists and INAO's rows lack (Pourchères … Cervens), already in the wines' queue of 2026-11-13, not this change |
| rows against the cahier, drinks | 34 records | `audit_aires_vs_cahier.py --drinks --strict` | ✅ OK 14, PINNED 20, as before |
| release gate, quick | 15 checks | `scripts/validate_release.py --quick` (`tmp/validation/release-2026-11-14T090914.md`) | ✅ 11 pass, the test suite among them; ❌ the same 4 standing queues (grape-surfaces, ambiguous-synonyms, untranslated, betard-delta) |
| left whole, the text being silent | 107 rows of rows-drawn records | `tmp/validation/seats-left-whole.json` | ❌ queued in CURATOR_TODO: 102 the cahier names in neither form (34 of them with the old name in INAO's own row), 5 where a commune kept its name and the cahier, homologated after the merger, dates its list nowhere |

