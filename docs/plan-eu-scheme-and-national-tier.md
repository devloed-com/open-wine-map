# Task brief — separate the EU scheme from the national term, and localise both

## Objective

Two related defects in how the corpus names what an appellation *is*:

1. **`kind` is never localised.** It is stored as a project-internal token (`AOC` / `DOP` / `IGP` / `EDV`) and rendered verbatim in all four
   locales. An English visitor sees `DOP` on Chianti — and on the six **British** GIs, where the UK register itself says PDO.
2. **The national term is not modelled at all.** Everything an EU member state protects is flattened to `DOP` / `IGP`, so Barolo **DOCG**
   and a generic Piedmont **DOC** are indistinguishable, Priorat **DOQ** looks exactly like Montsant **DO**, Kamptal **DAC** like
   Niederösterreich g.U.

The fix is to stop conflating two orthogonal things:

| axis | what it is | values |
|---|---|---|
| **EU scheme** (`eu_scheme`, new, derived) | the legal scheme the name is registered under | `pdo` · `pgi` · `spirit-gi` · `uk-pdo` · `uk-pgi` · `none` |
| **National term** (`national_term`, new) | the EU-registered *traditional term* the member state attaches to the GI as a whole — Reg. (EU) 1308/2013 Art. 112(a), Reg. (EC) 607/2009 Annex XII (copy: legislation.gov.uk/eur/2009/607/annex/XII) — inside PDO **or PGI** | DOCG, DOC, IGT, DOQ, DOCa, DO, Vino de Pago, Vino de la Tierra, AOC, DAC, Landwein, Vinho Regional, DOK, … |

The stored `kind` token stays exactly as it is. Rendering is **`TERM (SCHEME)`** — `DOQ (PDO)`, `DOCG (AOP)` in FR, `AOC (PDO)`, `Vinho
Regional (PGI)` — term only when there is no scheme (Swiss `AOC`), scheme only when the country has no term (UK `PDO`, Mosel `PDO`, French
`PGI`), and never `IGP (IGP)`.

A third, dependent work item rides along: the **About dialog** and the homepage / browse meta descriptions, which are stale and write the EU
scheme as a language salad (`AOC, AOP, IGP, DOP`).

## Established facts — verified 2026-09-06/07, do not re-litigate

### Terminology

For **wine** the EU defines exactly two schemes; each language abbreviates the same two things differently.

| | scheme 1 | scheme 2 |
|---|---|---|
| EN | PDO | PGI |
| FR | AOP | IGP |
| ES · IT · PT | DOP | IGP |
| DE | g.U. | g.g.A. |
| NL | BOB | BGA |
| EL | ΠΟΠ | ΠΓΕ |

Three qualifications, all live in the corpus:

- **Spirit drinks have one scheme, not two** — the *geographical indication* of Reg. (EU) 2019/787 Art. 3(4). The 28 `EDV` records are
  exactly the SIQO rows with `signe_fr = AOC`, `signe_ue = IG` (Cognac, Armagnac, Calvados, but also Whisky breton, Rhum de la Martinique
  and three Pommeaux); the eAmbrosia register types them `GI`. "Eau-de-vie" is a product category, not a scheme, and wrong for five of the
  28.
- **The UK registers under its own scheme** (GOV.UK register, since 2021-01-01) using the words PDO / PGI. The six UK wines are *also* in
  the EU register (Sussex added 2025-01-31), so a localised scheme word (AOP in the FR locale) is not false; the tooltip names the UK
  register.
- **Switzerland is outside any EU scheme.** The 75 CH records carry no `signe_fr` / `signe_ue`; `AOC` is the OFAG répertoire's own
  designation.

**AOC is not a scheme.** It is the French national traditional term for the French PDO (INAO: both words may appear on the bottle), and
separately the Swiss designation. DOCG / DOC / IGT (IT), DOQ / DOCa / DO / Vino de Pago / Vino de Calidad / Vino de la Tierra (ES), DOC /
Vinho Regional (PT), DOC / IG (RO), DAC / Landwein (AT), Landwein (DE), DOK / IĠT (MT) are likewise Annex XII traditional terms bound to PDO
or to PGI.

**Scheme abbreviations are decoys, not terms.** OEM/OFJ (HU), ZOP/ZGO (SI), ZOI/ZOZP (HR), CHOP/CHZO (SK/CZ), ЗНП/ЗГУ (BG), ΠΟΠ/ΠΓΕ (GR/CY),
g.U./g.g.A., BOB/BGA, PDO/PGI, AOP are the *scheme* in a local alphabet and are never a `national_term`. Lot-level quality grades
(Qualitätswein / Prädikatswein, kakovostno / vrhunsko, kvalitetno / vrhunsko KZP, akostné víno, jakostní víno, minőségi bor) vary inside one
GI and are excluded by construction.

### Corpus state

Stored `kind` distribution (2,914 records, from the built startup blob):

| value | n | where |
|---|---:|---|
| `AOC` | 1,404 | fr 1,329 + ch 75 |
| `DOP` | 944 | every other EU country + gb |
| `IGP` | 537 | all countries |
| `EDV` | 28 | fr spirits (`is_wine: false`) |
| `AOP` | 1 | `marc-d-alsace-gewurztraminer` — stray, see Traps |

Stage 04 collapses the EU scheme into the stored token (`04_build_maps.py:2320-2331`: `if sfr == "AOC" or sue == "AOP": mvt_kind = "AOC"`),
so the scheme of a stored `AOC` is only recoverable from `country` / `signe_ue` — which is why `eu_scheme` is derived and no label is keyed
on the token. `signe_ue` is not in the startup blob.

`kind` is **not** translated anywhere; `labels["kind_aoc"]` / `labels["kind_igp"]` (`map_template.py:73-74`) are translatable but every
locale left them at `"AOC / AOP"` / `"IGP"`. The paint is binary (`map_template.py:585-590`: `kind == 'IGP'` green, everything else maroon),
so the maroon swatch covers FR AOC, every DOP, the 75 Swiss AOCs and — toggle on — the 28 spirit GIs.

**The `classifications` facet is a different axis.** It carries ageing and traditional mentions (riserva 220, reserva 123, crianza 113,
superiore 67, the Prädikat and výběr ladders, Tokaj terms), built by `_aging_tiers_from_text` (`04_build_maps.py:461`) over
`scripts/_lib/aging_taxonomy.py`, which also owns the word `tier`. Folding the national term into that tree as a fourth root was designed
and rejected: one heading for two axes, sub-denomination-inflated counts, and a load-bearing `scan=False` guard so `do` / `doc` / `ig` never
become text-scan keys.

### Italy — MASAF publishes the roster keyed by EU file number

The "Elenco alfabetico dei vini DOP" PDF on MASAF IDPagina/4625 carries, per row, the scheme, the *Menzione tradizionale* (DOC / DOCG) and
the eAmbrosia file number: **79 DOCG · 332 DOC** (411 rows; the IGP elenco lists 111 IGT). A file-number join resolves 410 of the 412 IT DOP
records with zero disagreements against the Article-1 text rule. The two misses: `nizza` (elenco `PDO-IT-A1896` vs eAmbrosia `PDO-IT-01896`
— compare by numeric tail) and `valtenesi` (DOC, registered 2026-03-18, newer than the roster).

Counts that must not be conflated: **522** MASAF sidecars in `raw/it/masaf-disciplinari-extracted/` (plus `_index.json`), **523**
non-sottozone IT parents in the built blob, **524** wines in `raw/it/eambrosia/index.json` = elenco 522 + Valtènesi + Salemi (IGT, pending
cancellation, off the map for lack of geometry). Exactly two eAmbrosia wines have no sidecar, no cached PDF and no bundle entry:
`ciro-classico` (`PDO-IT-03209`, DOCG via Reg. (EU) 2025/1518; a full EUR-Lex extraction that *is* on the map) and `salemi`. Anything
present in eAmbrosia but absent from the elenco is **pinned, never defaulted**.

The Article-1 regex survives as an **audit**, not a source. Over the 522 sidecars it yields 76 DOCG · 330 DOC · 105 IGT · 11 unresolved; the
79 = those 76 + `sforzato-di-valtellina` (its `article_bodies` has no key `"1"` — keys 2 / 3 / 9 — although `articles_present` is [2..10];
Article 2 opens with the tier) + `vermentino-di-gallura` (Article 1 reads *"La DOCG «…»"*, an acronym the phrase regex cannot match; the
apostrophe variant does **not** recover it) + `ciro-classico` (no sidecar). The unanchored blob scan gives 77 = anchored + sforzato, a true
positive: unanchored in principle, not a false friend in this corpus. The apostrophe variant (`denominazione d'origine` / `d’origine`) still
matters — requiring `di` alone loses 30 wines:

```python
ORIG = r"denominazion\w*\s+d(?:i|['’´])\s*origine"
DOCG = re.compile(ORIG + r"\s+controllata\s+e\s+garantita|\bD\.?O\.?C\.?G\b", re.I)
DOC  = re.compile(ORIG + r"\s+controllata(?!\s+e\s+garantita)|\bD\.?O\.?C\b(?!\.?G)", re.I)
# head = (article_bodies.get("1") or article_bodies.get("2") or "")[:400]
```

Record `kind == IGP` settles IGT with certainty (0 text-vs-kind disagreements over 511 resolved sidecars); an IGT phrase inside a `dop-*`
bundle is a cross-reference to flag. The six regional geoportal layers carry a per-feature tier that `ITZoneIndex` drops — a secondary audit
signal (230 / 233 agreement; Veneto stale on one promotion, Umbria conflates DOC and DOCG), never an authority. **Wikidata P31 was tested
and rejected**: two DOCG-typed items exist in all of Wikidata; stage 02i stays `sameAs`-only.

### Spain — MAPA publishes the roster keyed by EU file number

MAPA's "Listado de DOP e IGP de vinos registradas en la UE" (updated 2026-07-02) lists all 149 Spanish wine GIs with a *Término tradicional*
column and the EU file number: **DO 70 · DOCa 2 · VP 27 · VC 7 · VT 43**, joining on `file_number` for 148 / 149 (the miss is `tharsys`, a
Vino de Pago with a file-number mismatch). Display forms are the words on the bottle — `Vino de Pago`, `Vino de Calidad`, `Vino de la
Tierra` — not MAPA's column shorthand. `es/00_fetch_data.py::fetch_mapa_listado` fetches it sha-pinned to
`raw/es/mapa/listado-dop-igp-vinos.pdf` + `manifest.json`; `scripts/_lib/es/national_term.py` parses it.

A pliego **text scan is NOT safe** and is not used: `Calificada` matches 20 pliegos but only two are real (`cadiz` matches on
*des*calificada); the earlier scan-derived VP (13) and VC (9) lists were materially wrong — `uruena` is a Vino de Pago,
`serra-de-tramuntana-costa-nord` is a PGI (VP / VC / DOCa are PDO-only), `tierra-del-vino-de-zamora` has been a plain DO since 2007, 14 of
the 27 VPs were missing and 12 listado VPs carry no `pago` token at all. The MAPA GIS zone layer is stale (Priorat as plain DO) and is a
cross-check, not a seed. VP / VC therefore **ship in v1**. Priorat's own documento único, its pliego (`PC-Priorat-DOQ-nov-21`), the Consell
Regulador and Catalan wine law (Llei 15/2002) all write **DOQ**; the listado writes DOCa (see Decisions).

### Austria — DAC is the DOCG-vs-DOC problem with a closed statutory roster

Exactly **18** of the 27 AT PDOs are DACs — the 27 minus the 9 Bundesland g.U. — per Weingesetz 2009 §10 Abs. 7 and one RIS DAC-Verordnung
each (Wagram: BGBl. II Nr. 30/2022; Thermenregion 2023). The BMLUK DAC page listing 17 is stale (no Wagram); the ÖWM list has 18. eAmbrosia
names carry no "DAC" and only 9 of the 18 single documents mention it (Weinviertel, Wachau, Traisental, Carnuntum, Neusiedlersee,
Südsteiermark, Weststeiermark, Wiener Gemischter Satz, Ruster Ausbruch: 0 hits), so the roster is a pin keyed by file number. The 3 Landwein
PGIs read `Landwein`. Do not copy the two cancelled entries in `scripts/_lib/at/region.py` (`PDO-AT-A0220`, `PDO-AT-A0227`) into the pin.

### Everywhere else — keyed on (country, kind), a ruling per row

Constants keyed on country alone would have stamped DO on the 43 Spanish IGPs (MAPA: VT 43 / 43), DOC on the 14 PT IGPs (14 / 14 cadernos
say *Vinho Regional*, 0 say DOC) and DOC on the 12 RO IGPs (0 say DOC; `terasele-dunarii` reads "☐ DOP ☑ IGP ☐ IG") — 69 records. Hence the
(country, kind) table, and a checklist line asserting no IGP record anywhere carries a PDO-only term.

| country | PDO side | PGI side | source / ruling |
|---|---|---|---|
| fr | `AOC` (`signe_fr`, incl. the 28 spirits; the 4 records with empty signe fields take AOC iff derived `mvt_kind == AOC`) | `""` — the bottle reads IGP; Annex XII's *Vin de pays* is no longer printed | SIQO referentiel |
| ch | `AOC` (all 75) | — | OFAG répertoire; the OFAG tier (cantonale / régionale / locale) and `grand_cru` go in the tooltip, not the term |
| it | `DOCG` / `DOC` (elenco join) | `IGT` (constant) | MASAF |
| es | `DO` / `DOCa` / `DOQ` / `Vino de Pago` / `Vino de Calidad` | `Vino de la Tierra` | MAPA listado |
| pt | `DOC` (29 / 30 cadernos self-declare; `dao` takes the constant) | `Vinho Regional` | IVV cadernos, constant per (country, kind) |
| ro | `DOC` | `IG` | DOCUMENT UNIC / ONVPV, constant |
| at | `DAC` (18, pinned) / `""` (9 Bundesland) | `Landwein` (3) | RIS DAC-Verordnungen + BML DAC page |
| de | `""` — Qualitätswein / Prädikatswein are lot-level | `Landwein` (26 by name + Großräschener See pinned with its BLE Produktspezifikation) | BLE |
| mt | `DOK` | `IĠT` | the MT single documents literally say "The mention DOK" |
| gb | `""` — PDO / PGI are the register's words | `""` | GOV.UK register |
| gr · cy | `""` in v1 (ΟΠΑΠ / ΟΠΕ / ΟΕΟΠ are real Annex XII terms, but only 1 of 132 cached ΥΠΑΑΤ specs carries *Ελεγχόμενη* — no in-build document attaches them per GI) | `""` | empty pin section; curator pass citing the founding FEK decisions |
| cz | `""` in v1 (VOC / Znojmo: producer-association mark, 0 / 13 records mention it) | `""` | empty pin section |
| hu · si · hr · sk · bg · be · nl · lu | `""` — no per-GI traditional term (Marque Nationale abolished; local abbreviations are scheme decoys) | `""` | ruling recorded |

An empty `national_term` renders as *nothing*, never a placeholder.

## Decisions taken

Stated as decided; none is open.

1. **Rendering is `TERM (SCHEME)`**, the scheme word in the UI locale's own word — EN PDO / PGI, FR AOP / IGP, ES DOP / IGP, NL BOB / BGA.
   Term only when the scheme is `none` (CH `AOC`); scheme only when there is no term; never `IGP (IGP)`; both empty renders nothing. Chablis
   reads `AOC (PDO)` in EN and `AOC (AOP)` in FR — the two French words the visitor conflates, once each.
2. **UK wines localise the scheme word** (`PDO` / `AOP` / `DOP` / `BOB`), the UK register named in the tooltip; `national_term` is empty.
3. **French spirits read `AOC (spirit-drink GI)` / `AOC (IG spiritueux)`** / `AOC (IG de bebida espirituosa)` / `AOC (GA gedistilleerde
   drank)` — the product word never enters the slot. The FR msgid is `IG spiritueux`, not `IG (boisson spiritueuse)`: the render adds the
   bracket.
4. **The stored `kind` token is untouched.** Four new derived fields carry everything: `eu_scheme`, `national_term`, `class_key`,
   `class_label`.
5. **`national_term` is the regulator's string, never translated** — the region-name rule. Priorat → `DOQ` under the rule *"use the
   autonomous community's wine-law form when it has one"* (Llei 15/2002), recorded in `scripts/_lib/es/national_term_overrides.json` with
   `castilian_form: DOCa`; the one sanctioned deviation from a roster string.
6. **Admission rule** (all three must hold, else `""` with a recorded ruling): (a) registered in Annex XII / the eAmbrosia traditional-terms
   register for that country; (b) applies to the GI as a whole, not per lot; (c) attached to that GI by a public regulator document — a
   roster keyed by file number, the GI's own specification in the build, or a checked-in pin citing the founding act.
7. **GR ΟΠΑΠ / ΟΠΕ, CZ VOC and CH Grand Cru / premier cru are scheme-only in v1** — pin sections created empty, filled by a later curator
   pass. Unpinned renders scheme-only, never wrong.
8. **Tooltips on both tokens** reuse the pill-tooltip mechanism (definition + regulator source); Wikipedia extracts are a follow-up.
9. **The facet is its own two-level tree "Appellation type"**, not a fourth root of the ageing tree, and ships as the **last** phase. **No
   paint change** — the facet, not colour, separates DOCG from DOC.
10. **`locale/*.po` + `messages.pot` are committed**; `.gitignore` narrows to `locale/**/*.mo`.
11. **Stage-03 wiki frontmatter keeps the stored `kind`** — out of scope, noted; the `.md` files are unlinked, octet-stream and absent from
    the sitemap. Analytics keep the stored token (`Kind Toggled {kind:'igp'}`, `Appellation Viewed {kind}`) for series continuity.

## Work item A — data model (`scripts/_lib/gi_terms.py` + `traditional_terms.json`)

Set at record assembly in `04_build_maps.py` inside `common_props` (2535-2560, next to `"kind": mvt_kind`), computed right after the block
that derives `mvt_kind` from `signe_fr` / `signe_ue` (2312-2331) so every existing signe correction is inherited, and read back at ~3673
exactly as `kind` is. `common_props` is written verbatim to GeoJSON and tippecanoe, so all four fields **are MVT properties** (negligible
tile cost); all four go into `STARTUP_AOCS_FIELDS` (`map_template.py:1327`) and its contract comment, naming the readers: `docTitleFor`
(runs pre-hydration at `app.js:2441`), the `renderAocCard` meta line, `matchesClient` / `matchesExceptFacets` / `refreshFacetAvailability`,
the omnisearch term index. The lazy panel payload (`wiki/data/d/**`) is untouched and must stay byte-identical.

1. **`eu_scheme`** (`gi_terms.derive_eu_scheme`) — `ch` → `none`; `gb` → `uk-pdo` / `uk-pgi` (from the register's `protection_type`, or
   `mvt_kind`); `fr` → `signe_ue` AOP→`pdo`, IGP→`pgi`, IG→`spirit-gi`, empty `signe_ue` → from `mvt_kind` (AOC→`pdo`, IGP→`pgi`,
   EDV→`spirit-gi`; the stray `AOP` → `spirit-gi`, register `PGI-FR-01836` type GI); every other country → DOP→`pdo`, IGP→`pgi`.
2. **`national_term`** (`resolve_national_term`) — in order: FR `signe_fr` (AOC iff derived `mvt_kind ∈ {AOC, EDV}`); CH constant; roster
   join on `file_number` (IT elenco, ES listado, AT / DE / MT pins); the (country, kind) constants; else `""`. Rosters, pins, constants,
   rulings and the per-scheme / per-term tooltip definitions (4 locales, each with cited sources) live in the checked-in
   **`scripts/_lib/traditional_terms.json`**. A scheme abbreviation in a term slot raises at load.
3. **`class_key`** — the facet's filter string, `;{eu_scheme};{cc}:{term-slug};` (`;pdo;it:docg;`, `;pgi;de:landwein;`, `;none;ch:aoc;`,
   `;pdo;hu:;`), consumed by the existing `['in', ';v;', ['get', field]]` expression (`app.js:1328`); each key is its own descendant, no
   expansion table.
4. **`class_label`** — per locale, precomputed **in Python only** by `gi_terms.classification_label(national_term, eu_scheme, labels)` at
   emission (the startup blob and the SSR card are both emitted per locale). JS reads `r.class_label`; SSR reads the same value; nothing
   composes the label client-side. The scheme msgids (FR `AOP`, `IGP`, `IG spiritueux`) are folded into `build_labels` so
   `RenderCtx.labels` already carries them — no `RenderCtx` signature change; `uk-*` reuses the pdo / pgi msgstrs.

**Sources fetched, sha-pinned, parsed** (public, licence-clear, joined on file number by numeric tail):

- IT — `it/00_fetch_data.py` fetches the MASAF *Elenco alfabetico* DOP + IGP PDFs into `raw/it/masaf-elenchi/elenco-{dop,igp}.pdf` (sha256 +
  `fetched_at` in the manifest); `scripts/_lib/it/national_term.py` parses `file_number → DOC | DOCG` (79 / 332); `IGT` is a constant for IT
  PGIs; `scripts/_lib/it/national_term_overrides.json` pins the residue (Cirò Classico → DOCG citing Reg. (EU) 2025/1518, Valtènesi → DOC
  citing its Gazzetta Ufficiale decree, …). The Article-1 regex moves to `audit_gi_terms.py` and must report 0 disagreements.
- ES — `scripts/_lib/es/national_term.py` parses the listado's *Término tradicional* column (DO 70 / VT 43 / VP 27 / VC 7 / DOCa 2);
  `scripts/_lib/es/national_term_overrides.json` carries Priorat → DOQ (`castilian_form: DOCa`), the `tharsys` file-number bridge, and any
  disagreement the three-way audit (listado ∪ pliego §9 *término tradicional* sentence ∪ zone-layer `tpr_ds_descripcion`) surfaces.
- AT — DAC pinned by file number from the BML DAC-Verordnungen page (18, RIS citations); Landwein constant for the 3 PGIs. PT DOC / Vinho
  Regional, RO DOC / IG, DE Landwein (PDO `""`), MT DOK / IĠT — constants or pins in `traditional_terms.json`; everything else `""` with its
  ruling row.

**Sub-denominations** resolve through their own `file_number` / `signe` (ES subzonas carry the parent's number — `rioja-rioja-alavesa` has
`PDO-ES-A0117`; IT sottozone are `dict(record)` copies made at `04_build_maps.py:893`; PT sub-regiões and LU communes share the parent's),
with a **parent-slug fallback pass** in the parents-first record loop (`04_build_maps.py:1022`, the `es_region_by_parent_slug` side-dict
pattern at 2340-2347). Nothing inherits "at the rendering layer" — no code in `app.js` or `content_block.py` looks up a parent at render. A
test asserts every child's `(national_term, eu_scheme)` equals its parent's (`rioja-rioja-alta` == DOCa / pdo, `chianti-rufina` == DOCG /
pdo).

`audit_gi_terms.py` re-derives every roster and pin on each run and reports CONFIRMED / DRIFT / UNPINNED (the geometry-outlier-override
pattern), lists every corpus record the rosters lack, and diffs the elenco / listado counts against the eAmbrosia corpus, so a silent PDF
layout change shows up as a count mismatch, not as wrong labels.

## Work item B — render sites

Every surface renders `class_label`; each is a one-line replacement of `kind`.

| file:line | surface | note |
|---|---|---|
| `app.js:2328` | client panel meta line | `{flag} {Country} · {class_label} · {Region}`; term and scheme each wrapped `<span class="gi-term has-info">` for the tooltip; bracket muted, non-breaking |
| `content_block.py:858` | SSR panel meta line | same spans, `<abbr title="{definition}">` so crawlers get the definition without JS |
| `app.js:2376` | `docTitleFor` / stack header | reads the startup blob, correct before hydration |
| `map_template.py:1104-1109` | entity page `<title>` | `{name} — {class_label} · {Region}, {Country} · Open Wine Map` — "Barolo DOCG", "Priorat DOQ" are the search phrases |
| `map_template.py:1113-1114` | entity meta description → og:description, Place JSON-LD `description` | `{name} — {class_label}, {Region}, {Country}. {grapes}. {scheme_long}.` clamped to 160; no new schema.org property |
| `map_template.py:1251, 1264-1266` | browse page `<small>` | |
| `map_template.py:1707` → `content_block.py:760` | children nav `sub-kind` | only when the child's label differs from the parent's (never, after inheritance) |
| `map_template.py:73-74`, `2365-2366` | legend swatches | **new msgids** `Protected origin (PDO, AOC, DOC, DO…)` / `Geographical indication (PGI, IGT, Landwein…)` — honest for FR AOC + every DOP + CH + spirits |
| `map_template.py:41-45` | homepage `meta_description` → `<meta>`, og, WebSite JSON-LD (1527), `llms.txt` blockquote (`04_build_maps.py:4269`) | rewritten msgid, no salad |
| `map_template.py:263-266` | `browse_meta_description` | rewritten msgid |
| `map_template.py:82, 93` | `show_igp_label`, `count_hidden_igp_hint` | msgstr-only: EN "Show PGIs", NL "BGA tonen" |
| `wiki/llms.txt` entries | `— DOCG (PDO)` suffix | follows automatically |

Worked readings (EN unless stated): Priorat `🇪🇸 Spain · DOQ (PDO) · Cataluña` (FR `DOQ (AOP)`, ES `DOQ (DOP)`, NL `DOQ (BOB)`); Montsant `DO
(PDO)`; Barolo `DOCG (PDO)`; Langhe `DOC (PDO)`; Terre Siciliane `IGT (PGI)`; Chablis `AOC (PDO)` / FR `AOC (AOP)`; Pays d'Oc `PGI` / FR
`IGP`; Vully `AOC`; Cognac `AOC (spirit-drink GI)` / FR `AOC (IG spiritueux)`; Sussex `PDO` / FR `AOP`; Landwein Rhein `Landwein (PGI)`;
Mosel `PDO`; Weinviertel `DAC (PDO)` vs Niederösterreich `PDO`; Σάμος `PDO` in v1; Malta `DOK (PDO)`; Rioja Alavesa `DOCa (PDO)` inherited.

**Tooltips**: the existing pill tooltip (`app.js:2615-2700` — `resolvePillInfo`, `showPillTip`, `aria-describedby`) gains a
`.gi-term.has-info` branch reading a per-locale `TERMS_INFO` (`gi_terms.build_terms_info`) injected like `STYLES_INFO`
(`map_template.py:1598`), keyed `{cc}:{term-slug}` and `scheme:{eu_scheme}`: one definition sentence + the regulator source links (the
`appellation_notes.json` shape; the CH card adds the OFAG tier + cantons from the record). Wikipedia extracts are a follow-up.

## Work item C — About dialog, meta descriptions, README

`map_template.py:224-278` is wrong in four ways: `about_roadmap_html` hardcodes "20 pays européens" and enumerates them without Royaume-Uni;
`about_data_html` credits **IGN** as "le fond cartographique" (IGN supplies French commune polygons; the basemap is OpenStreetMap / CARTO);
it names four sources for a pipeline drawing on the EU register plus a dozen national regulators; nothing discloses the LLM layers.

Replacement, paragraphs in order (as shipped): lead → sources (documentary + cartographic) → the LLM layer → coverage
(interpolated counts) → errors / contributions → browse link → made-by → data-updated. The About dialog is about Open Wine Map,
not about the naming layer: the **"how names work"** explanation was dropped from it on review (owner's call, 2026-09-07) and lives
in the README only; the tooltips on the two tokens carry the per-term explanation in the UI.

- **Lead** — names the actual registers, in the locale's own scheme words: EN "A reference map of Europe's wine appellations, generated
  automatically from public regulator data: the EU register of protected designations of origin (PDO) and protected geographical indications
  (PGI), the national regulators behind them, the Swiss federal repertoire of cantonal AOCs and the UK GI register." FR msgid uses « régime
  », never « schéma ».
- **How names work** — README subsection "Appellation names: traditional term and legal scheme" only (not an About
  paragraph; no `about_names_html` msgid).
- **Homepage `meta_description`** — EN "Interactive map of European wine appellations: PDO and PGI with their label term (AOC, DOCG, DOQ,
  DAC…), Swiss AOCs and UK PDOs — grapes, styles and terroir from official registers."; **`browse_meta_description`** likewise. Keep "AOC"
  in the string — 1,329 records, the largest search token.
- **Counts** — `{n}` `{c}` `{parents}` `{subs}` computed once in `emit_html` from the same `aocs` dict as the startup blob, **wine-only**,
  formatted with `babel.numbers.format_decimal(n, locale=lang)` (2 914 / 2.914 / 2,914), passed to **both** `_build_about_dialog` call sites
  (`map_template.py:1640` and `:1676`); no plural msgids; same formatting for `browse_intro_html`.
- **LLM disclosure, per layer, with the models actually recorded**: terroir notes extracted from the regulator text and translated by Claude
  Sonnet 4.6; grape / style tooltip extracts translated from Wikipedia mostly by Mistral Small 3.2 via Ollama, with a Claude residual;
  cahier summaries mostly human-translated with a machine-translated residual — each item carrying its own attribution line.
- Claims that must **not** be made: ~~"every appellation is on the map"~~ (true today, silently false at the first stub); ~~"the panel shows
  each boundary's source"~~ — `_approx_line` (`content_block.py:708`) only flags *approximate* geometries; say "approximations are flagged".
- **README** is a separate work item, not a three-line fold-in: intro still says "six streams" and lists FR/ES/PT/IT/AT/SI, Status counts
  are stale, the sources table repeats the IGN-as-basemap error, says GISCO LAU 2021 (now 2024) and names `claude-haiku-4-5` (never used),
  the licence list omits OGL v3 / IODL 2.0 / MAPA CC-BY / CARTO + OSM attribution. Either an explicit README checklist or cut Status /
  Sources to a pointer at CLAUDE.md plus a build-generated country table.

## Work item D — facet (last phase)

Its own `<details data-modes="advanced" data-facet="appellation-type">` under the Appellation facet and above « Classement », heading FR « Type
d'appellation » → EN "Appellation type", ES "Tipo de denominación", NL "Type appellatie". There is no "region facet" to copy —
`facet_regions` (`04_build_maps.py:3807`) only seeds the omnisearch, and the user-facing region control is the country → region tri-state
inside the Appellation tree, which filters by slug expansion. The live model is the classifications tree: `buildTreeFacet` (`app.js:799`)
over the MVT `class_key` with `inField` (`app.js:1325-1330`); the tree comes from `gi_terms.build_term_tree`.

- Level 1 = scheme rows, gettext-labelled (PDO · PGI · Spirit-drink GI · PDO (UK scheme) · PGI (UK scheme) · AOC (Switzerland)); level 2 =
  term rows keyed `{cc}:{term-slug}`, labelled flag + regulator string (`🇮🇹 DOCG 79`, `🇪🇸 Vino de Pago 27`, `🇦🇹 DAC 18`, `🇵🇹 DOC 30`) — the
  flag disambiguates the three DOC rows and the two Landwein rows. Countries with no term contribute to the scheme row only.
- Wiring, the ten classifications sites copied: `filters.appellationType` (`app.js:614`), `buildFilterExpr`, `matchesClient` (1345),
  `matchesExceptFacets` (1357, new except key), active-filter chips + removal (655-680, 1379), `refreshFacetBadges` (1428),
  `refreshFacetAvailability` (1449), reset (1271), `Filter Applied {facet:'appellation-type'}`. No deep-link / localStorage work.
- **Counts are parent-only and wine-only** (skip `is_sub_denomination == "1"` and `is_wine == "0"` in the count loop at `04:3717`), so the
  facet numbers equal the acceptance numbers: DOCG = the elenco roster, DOCa = 1, DOQ = 1, DAC = 18 — not roster + 38 inherited sottozone,
  not Rioja + 3.
- Omnisearch term index (typing "DOCG" / "DOQ" / "DAC" offers the facet node, the `pickOmni` region pattern, 1646): **deferred** — not
  in v1; the facet tree is the entry point.

## Sequencing

1. **Copy + legend + catalogs** — commit `locale/*.po` + `.pot`, rewrite the About / meta msgids, new legend msgids, toggle msgstrs, IGN
   credit, counts interpolation. Zero runtime risk.
2. **Fields + render sites + tooltips** — `gi_terms.py`, `traditional_terms.json`, the IT / ES parsers and pins, `common_props` +
   `STARTUP_AOCS_FIELDS`, the twelve sites above, `TERMS_INFO`, tests. One full rebuild with the golden diff (expected set: `app.<lang>.js`,
   `aocs.<lang>.js`, entity / browse / home HTML, `llms.txt`; `wiki/data/d/**` identical).
3. **Facet + omnisearch** — last, its own risk class.

Deploy: phase 2 rewrites ~11.7k entity pages + 5 homepages + 4 browse pages + 4 `app.js`; the panel JSONs stay byte-identical (every new
field is in the startup blob). Deploy is SHA256-diffed; run `compare_build_output.py` first; take the PUT rate from the last deploy log.

## i18n mechanics — read before touching any string

- `locale/*.po` and `messages.pot` are **committed** from this work on; `.gitignore` carries `locale/**/*.mo`. Commit the catalogs *before*
  any msgid change so the diff shows the translations.
- **Editing an existing `msgstr` is safe. Changing a `msgid` is not** — pybabel fuzzy-matches new msgids onto unrelated entries, and
  `compile_catalogs` → `write_mo(use_fuzzy=False)` silently drops fuzzy entries, so the French msgid renders. Prevent it with
  `--no-fuzzy-matching` (below); `.venv/bin/pybabel` has a broken shebang and `uv` is not installed. Extract from the **directory**, never a
  single file. Then set every new `msgstr` explicitly in en / es / nl **and** fr; the legend and scheme entries are new msgids, so they
  start empty.
- Two pre-existing `#, fuzzy` entries in `locale/fr` (`le registre eAmbrosia de l'UE`, the stale country-count string) — clear them, do not
  let them mask new ones.
- `national_term` values are **never** gettext'd; a test asserts the field is byte-identical across the four startup blobs. Stage 04 calls
  `compile_catalogs()` at start; it rebuilds `.mo` only when the `.po` is newer.

```
.venv/bin/python -m babel.messages.frontend extract -F locale/babel.cfg -o locale/messages.pot scripts/_lib/
.venv/bin/python -m babel.messages.frontend update --no-fuzzy-matching -i locale/messages.pot -d locale
```

## Verification

- [ ] `.venv/bin/python -m pytest tests/ -q` — 368 before the change; expect edits: `tests/test_content_block.py:227` (EN children list
      expects a literal `AOC`) and every meta-line / `kind: "DOP"` fixture.
- [ ] New tests: `classification_label` per locale — IT `DOCG (PDO)` / `(AOP)` / `(DOP)` / `(BOB)`; FR `AOC (PDO)` (never `AOC · AOC`); CH
      `AOC` once, no scheme token; GB `PDO` in EN, `AOP` in FR, `national_term == ""`; EDV `AOC (spirit-drink GI)`; French IGP `PGI`, never
      `IGP (IGP)`; empty / missing term → no `None`, `—` or dangling ` · `; `_build_entity_meta` description contains `DOCG`; IT audit-regex
      fixtures (`«X»` DOCG, straight + typographic apostrophe, `La DOCG «Vermentino di Gallura»`, Article-1-less sidecar whose Art. 2 says
      *controllata e garantita*, cross-reference decoy → DOC); ES listado parser fixture (DO 70 / DOCa 2 / VP 27 / VC 7 / VT 43);
      sub-denomination == parent; scheme abbreviation in a term slot raises; `national_term` byte-identical across locales; all four fields
      in `STARTUP_AOCS_FIELDS`.
- [ ] `.venv/bin/python -m ruff check scripts/ tests/`
- [ ] `npx --yes eslint@9 scripts/_lib/assets/app.js` — 0 errors (6 pre-existing warnings)
- [ ] Full `scripts/04_build_maps.py` run green; asset content-hashes match their filenames.
- [ ] Golden comparator (`scripts/compare_build_output.py`, text files only: html / js / css / xml / txt) against a pre-change snapshot —
      expected diff set as under Sequencing; `wiki/data/d/**` identical.
- [ ] **Direct kind-count diff** on `wiki/map-data/appellations.geojson` and `appellations-villages.geojson` (the comparator skips
      `.geojson` and `.pmtiles`): `AOC 1404 / AOP 1 / DOP 944 / EDV 28 / IGP 537` unchanged before and after — the mechanical guard for the
      six `=== 'IGP'` gates.
- [ ] Counts: IT `national_term` non-empty for every non-sottozone parent (523), DOCG set == the elenco's DOCG rows (79 today; URL + sha256
      + date recorded), audit reports 0 regex disagreements and lists every one-side-only slug; ES DO 70 · DOCa 1 · DOQ 1 · Vino de Pago 27
      · Vino de Calidad 7 · Vino de la Tierra 43; AT DAC 18; no IGP record anywhere carries a PDO-only term (DO / DOC / DOCG / DOCa / DOQ /
      VP / VC / DAC / DOK); every `gb` record `eu_scheme` starts `uk-`; every `ch` record `eu_scheme == "none"`.
- [ ] Static grep of `<title>`, `<meta name=description>` and the SSR `.meta` line on one IT / FR / CH / GB / EDV entity page per locale —
      server-rendered, so the grep *does* prove them; the whisky-breton / rhum-de-la-martinique titles never contain "Eau-de-vie" as a
      classification.
- [ ] Browser check for the client-rendered tree, chips, panel meta, stack header, tooltips and IGP paint: serve with `.venv/bin/python
      scripts/serve.py` (Range-capable, port 8765 — plain `http.server` ignores Range and PMTiles never load), then a one-off Playwright
      script from the `bootstrap` group (`.venv/bin/python -m playwright install chromium`). Assert SSR meta line == client meta line for
      the same slug; nothing enforces it otherwise.
- [ ] IGP toggle still filters and IGP polygons still paint differently; `marc-d-alsace-gewurztraminer` still `is_wine: false`;
      `wiki/llms.txt` carries the new copy.

## Traps

- **Never change the stored `kind` token.** Six code sites gate on `=== 'IGP'` (`map_template.py:588`, `app.js:747, 1323, 1346, 1358,
  1626`).
- **Never key a label on the stored token.** Stored `AOC` is FR PDO *and* CH no-scheme; stored `EDV` is a spirit GI. Only `eu_scheme`
  decides. Do not print an untranslated English "PDO" inside a French line for UK wines either — localise the scheme word and let the 🇬🇧
  chip + tooltip carry the register.
- **`tier` is a taken word twice** — `aging_taxonomy.py` owns it, and every CH extracted record carries an OFAG `tier` plus 12 Valais
  `grand_cru` blocks; read neither as the ageing tier, and do not fold either into `national_term` in v1. **`classifications` is ageing
  tiers**, not GI terms — different axis, own facet, own MVT property.
- **The ES text scan is a false friend**: 20 "calificada" hits, 2 real. Use the listado. **The IT blob scan is unanchored, not wrong**: in
  this corpus it adds only sforzato, a true positive. Neither it nor the anchored regex is the source; the elenco is.
- **Scheme abbreviations are decoys.** A record scan finds OEM (23 / 41 HU), ZOP, ZOI, CHOP, ЗНП, PDO and would produce `ZOP (PDO)`. The
  loader raises.
- **Sub-denominations do not inherit at render time.** Resolve in the build loop; a slug-keyed lookup leaves every child empty or wrong.
  **Facet counts include subs and spirits by default** (`region_counts` increments per MVT feature) — count parent-only, wine-only.
- **`marc-d-alsace-gewurztraminer`** is the corpus's only `kind: "AOP"`; it is `is_wine: false` only because its SIQO `categorie` is empty,
  not because the code knows it is a spirit. `eu_scheme` maps it to `spirit-gi`; leave the token. If fixed at all, fix the SIQO row via the
  register pin or stage 02's kind parse — never a stage-04 slug special-case.
- **Stage-03 frontmatter (`type:` / `kind:` / `categories`)** in the 19 per-country `03_generate_wiki.py` keeps the stored token. Out of
  scope.

## Corrections vs. the previous draft

Facts the review refuted or the owner overruled, folded in above:

- **`AOC · AOC` contradiction** — the label table keyed on the stored token made decision 1's `PDO · AOC` unreachable and would have stamped
  a scheme on Switzerland; replaced by the derived `eu_scheme` (F01).
- **69 IGP records** — "everything else DO", "PT / RO constant DOC" ignored `kind`; the axis now covers PGI-side terms, keyed on (country,
  kind) (F02).
- **EDV** — spirits are a single-scheme GI (Reg. 2019/787), nationally AOC; "Eau-de-vie" was a wrong product word for whisky / rum / pommeau
  (F03).
- **Austria** — 18 DACs (not "leave empty", not the stale 17); pinned by file number (F04).
- **"All eight" render sites** — missed the homepage `meta_description` → og / WebSite JSON-LD / `llms.txt`, `browse_meta_description` and
  the IGP toggle strings (F05).
- **DOCG is 79, not 77** — the checklist hard-coded the blob-scan number B3 itself forbade; the elenco settles it (F06). **522 sidecars, not
  523** (`_index.json` was counted); 523 blob parents; 524 eAmbrosia; `ciro-classico` and `salemi` have no sidecar (F07).
- **Vermentino di Gallura** is recovered by the `DOCG` acronym, not the apostrophe variant; **sforzato** lacks `article_bodies["1"]`, while
  `articles_present` is [2..10] (F08, F35).
- **MASAF elenco** joins on file number and is the source; the regex is an audit (F12). **MAPA listado** likewise; the scan-derived VP / VC
  lists were wrong and VP / VC ship in v1 (F13). **Priorat → DOQ** is a rule, not a question; no Basque / Galician DO is top-tier (F17).
- **MVT / facet mechanics** — `common_props` is the MVT property path, so "MVT only if paint changes" was false; `facet_regions` is not a
  facet; the fields must be in `STARTUP_AOCS_FIELDS` unconditionally (F09, F10). **Inheritance happens at build time**, not "at the
  rendering layer" (F11). Facet counts parent-only (F21).
- **`locale/` committed** — hand-carrying msgstrs perpetuated a break of the reproducibility rule (F14); `--no-fuzzy-matching` and
  module-form pybabel commands (F30). **Legend** — the maroon swatch is honest only as "Protected origin (PDO, AOC, DOC, DO…)" (F15).
- **GR / CZ / decoys** — ruled explicitly: scheme-only in v1 with empty pin sections; scheme abbreviations and lot-level grades excluded by
  rule (F16, F22). FR empty-signe records take AOC from the derived `mvt_kind` (F19); CH `tier` / `grand_cru` acknowledged (F20).
- **Verification method** — the static grep *does* prove SSR title / meta; Playwright needs `scripts/serve.py`, not `http.server` (F18); the
  comparator skips `.geojson` / `.pmtiles`, hence the direct kind-count diff (F32); tests named (F24); `RenderCtx` unchanged (F25).
- **Wikidata rejected** as a tier source; geoportal tier a secondary audit signal only (F26, F27).
- **LLM disclosure** per layer with the models actually recorded; `claude-haiku-4-5` was never used (F28); counts locale-formatted,
  wine-only, both call sites (F29); README scoped (F31); deploy blast radius ~11.7k pages, "~3 min" uncited (F33); sequencing added (F34);
  marc-d-alsace is a stage-02 / SIQO matter (F36).
- **Decisions** — all five former "ask the user" gates are settled (F23); rendering, UK / spirits policy, facet shape and tooltips taken by
  the owner from the design panel.


