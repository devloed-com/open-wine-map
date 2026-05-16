# Curator todo

Actionable manual lookups across the corpus. One section per country. Reconcile against [scripts/audit_coverage.py](scripts/audit_coverage.py) (FR) and [scripts/audit_es_coverage.py](scripts/audit_es_coverage.py) (ES) after each run.

Legend: ✅ done · 🟡 URL queued, awaiting pipeline rerun · 🟢 in progress · ⏳ blocked on code · ❌ open

Last reconciled: 2026-05-14 (Rully + Maranges CAVB cahiers landed via Type 1C OCR fallback — 35 new slugs (24 Rully premier-crus + 9 Maranges climats), section X 8050/9349 chars, 02d ran fine on both, 02e produced 7 EN/ES/NL translations; stale audit confirmed three "code follow-ups" already shipped — AOC Wikipedia override consumption live in scripts/02b_fetch_aoc_lexicon.py:64-66,322-373,388-390 (cache carries `override_source=curator`), ES grape lexicon already iterates raw/es/pliegos-extracted/ via collect_grape_slugs in scripts/02b_fetch_grape_lexicon.py:76-95, DOCUMENTO ÚNICO anchor regex matches both Toro + Ribera del Guadiana (RDG's "0 grapes principal" was role-routing, not anchor); earlier same day — Wikipedia AOC override merge — fr 44→101, es 0→29; ES national-pliego URL research merged 12 entries into raw/es/national-pliegos/manual_overrides.json + stage 02f override-priority read wired in scripts/es/02f_extract_national_pliegos.py + parser tightened in scripts/_lib/es/national_pliego.py → 138 new variety-DOP additions, zero regressions; 6 stale research prompts under scripts/_lib/ deleted after their batches closed; ES consejo regulador URL merge earlier same day — 56 new entries to appellation_urls.json, by_slug now 205)

---

## France

### Cahier des charges — ✅ complete

All 459 parents and 1079 DGCs now extract. Zero stubs after two curator URL rounds (38 + 12 ids) plus parser fixes. Detail tables below preserved as reference for the patterns we encountered.

#### BO Agri (19 — fetch today; verified)

Single-AOC PDFs:

| id | Name | Status |
|---:|---|---|
| 1 | Alsace ou Vin d'Alsace | ✅ extracted |
| 217 | Pouilly-Loché | ✅ extracted (via extranet.inao fallback after 01 fall-through fix) |
| 218 | Pouilly-Vinzelles | ✅ extracted (extranet.inao fallback) |
| 333 | Cornouaille | ✅ extracted (cidre `1) DENOMINATION` regex fix) |
| 494 | Cidre de Normandie / Cidre normand | ✅ extracted |
| 553 | Cidre de Bretagne / Cidre breton | ✅ extracted |
| 843 | Gros Plant du Pays Nantais | ✅ extracted |
| 848 | Cidre Cotentin / Cotentin | ✅ extracted |
| 1074 | Marc du Jura | ✅ extracted |
| 1089 | Fine de Bourgogne | ✅ extracted |
| 1092 | Marc de Bourgogne | ✅ extracted |
| 1246 | Lorraine (IGP) | ❌ stage 01 grabbed a 23-IGP bundle that doesn't contain it. Need a new BO Agri URL targeting Lorraine's actual cahier; or refresh via Légifrance. |

Multi-AOC bundles (stage 02 cross-bundle rescue picks per-AOC by header):

| id | Name | Bundle UUID | Status |
|---:|---|---|---|
| 44 | Lalande-de-Pomerol | 302391de (~19 AOCs, 24-10-2011) | ✅ extracted |
| 171 | Côte de Nuits-Villages | n/a | ✅ extracted (2026-05-14) via CAVB mirror + stage 02 OCR fallback — see PNOCDC section below |
| 198 | Maranges | n/a | ✅ extracted (2026-05-14) via CAVB mirror + stage 02 OCR fallback — `https://www.cavb.fr/wp-content/uploads/2021/11/CDC-Maranges-03-11-2011.pdf`. 9 entries (parent + 8 climats). |
| 225 | Rully | n/a | ✅ extracted (2026-05-14) via CAVB mirror + stage 02 OCR fallback — `https://www.cavb.fr/wp-content/uploads/2021/11/CdC-Rully-02-12-2011.pdf`. 26 entries (parent + Rully premier cru + 24 individual climats). |
| 290 | Pierrevert | 6e35031f (7 AOCs) | ✅ extracted |

#### Légifrance LODA URLs (19 — fetcher works; cookie expires every ~30 min)

`scripts/01b_solve_legifrance.py` shipped (cookie-injection workflow; creds saved to `~/.config/openwinemap/legifrance.json`). 8 ids fetched cleanly. The remaining 5 retry attempts hit cookie-expiry. **Open question**: even when the fetch works, the LODA-rendered PDF often contains only the décret preamble + cahier annex; stage 02 sometimes can't isolate a usable segment (4 of 8 fetches extracted; 4 returned "no-segment").

| id | Name | DGCs unlocked | Status |
|---:|---|---:|---|
| 71 | Saint-Julien | 0 | ✅ extracted (LODA contains cahier annex) |
| 130 | Bâtard-Montrachet | 0 | ❌ LODA décret-only, no cahier annex — needs BO Agri URL |
| 134 | Beaune | **+43** | ✅ extracted (2026-05-14) via CAVB mirror + stage 02 OCR fallback |
| 135 | Bienvenues-Bâtard-Montrachet | 0 | ❌ stage 01 grabbed wrong bundle; LODA décret-only |
| 144 | Bourgogne Passe-tout-grains | 0 | ✅ extracted (LODA contains cahier) |
| 154 | Chassagne-Montrachet | **+56** | ✅ extracted (2026-05-14) via CAVB mirror + stage 02 OCR fallback |
| 159 | Chorey-lès-Beaune | +1 | ❌ stage 01 wrong bundle; LODA décret-only |
| 170 | Côte roannaise | 0 | ✅ extracted |
| 206 | Monthélie | +16 | ❌ stage 01 wrong bundle; LODA décret-only |
| 211 | Musigny | 0 | ❌ LODA décret-only |
| 230 | Santenay | +14 | ✅ extracted (2026-05-14) via CAVB mirror + stage 02 OCR fallback |
| 231 | Savigny-lès-Beaune | +24 | ✅ extracted (rescued from id=198's bundle) |
| 247 | Irancy | 0 | ✅ extracted |
| 251 | Limoux (still) | 0 | ✅ extracted |
| 312 | Muscat du Cap Corse | 0 | ✅ extracted |
| 319 | Floc de Gascogne | 0 | ✅ extracted |
| 944 | Haute-Marne (IGP) | 0 | ❌ stage 01 grabbed 23-IGP bundle that doesn't contain it |
| 945 | Coteaux de Coiffy (IGP) | 0 | ❌ same wrong bundle |
| 951 | Puy-de-Dôme (IGP) | 0 | ❌ same wrong bundle |
| 1091 | Marc d'Alsace Gewurztraminer | 0 | ✅ extracted (LODA bundle Décret 2009-1350 split correctly by name) |
| 1240 | Cidre du Perche | 0 | ✅ extracted |

**All 12 round-2 stubs resolved on 2026-05-10** via the curator's INAO extranet PNOCDC research:

- 9 Burgundy 2011 grand-cru cluster (130, 134, 135, 154, 159, 171, 206, 211, 230) → INAO extranet `PNOCDC<Name>.pdf` standalone PDFs (with the casing/hyphen quirks the curator catalogued).
- 944, 945 → BO Agri bundle `b7f52a62-c149-453a-b8bb-49a28ba8db16` (4-IGP bundle covering Lavilledieu, Saint-Guilhem-le-Désert, Coteaux de Coiffy, Haute-Marne).
- 951 → BO Agri bundle `aa2da598-a45b-478e-96d9-f607cda07cf8` (~13 département IGPs incl. Puy-de-Dôme).

DGC cascading unlock realised in this round: **+106 DGCs** (Beaune climats, Chassagne climats, Savigny premier-crus, Santenay premier-crus, Monthélie climats, Côte de Nuits-Villages localités, etc.).

**To retry the cookie-expired ones:** refresh `cf_clearance` in your browser (open <https://www.legifrance.gouv.fr/loda/id/JORFTEXT000024923948>, copy fresh cookie), update `~/.config/openwinemap/legifrance.json`, then `.venv/bin/python scripts/01b_solve_legifrance.py --refresh --only 71 --only 134 --only 211 --only 230 --only 247`.

### Geometry — Comté Tolosan cluster

❌ id=861 + 6 DGCs (Bigorre, Cantal, Coteaux et Terrasses de Montauban, Haute-Garonne, Pyrénées-Atlantiques, Tarn-et-Garonne) silently dropped from `wiki/map-data/appellations.geojson` despite having clean cahier extraction. Not a curator data task — investigate stage 04 in [scripts/04_build_maps.py](scripts/04_build_maps.py) (likely an aires-CSV match miss; potential `dgc_village_overrides.json` add).

### Wikipedia AOC pages — 99 missing/error parents

✅ Stage 02b override-priority read shipped 2026-05-14 in [scripts/02b_fetch_aoc_lexicon.py](scripts/02b_fetch_aoc_lexicon.py). Override file `raw/wikipedia/aoc_overrides.json` is now consumed for both `fr` and `es`. Re-run with `--refresh` to invalidate previously-cached cascade-derived `missing` / `not_aoc_topic` records for slugs the curator has since pinned.

Curator research baked in (data file: [raw/wikipedia/aoc_overrides.json](raw/wikipedia/aoc_overrides.json), schema in the sibling README):

- ✅ **fr (101 entries)** — 88 pinned, 7 `missing`, 6 `not_aoc_topic`. Covers the Alsace grand-cru cluster (44, researched 2026-05-10) + the non-Alsace batch (51, researched 2026-05-14: Bourgogne, Loire, LR, Rhône, Sud-Ouest, cidres/eaux-de-vie, `-ou-` multi-name AOCs) + 5 `not_aoc_topic` stubs tidied in 2026-05-14 + 1 single-slug top-up (`vin-de-savoie-ou-savoie`).
- ✅ **es (29 entries)** — 8 pinned, 11 `missing`, 10 `not_aoc_topic`. First-pass ES batch (20, researched 2026-05-14: txakolinas, Jerez, IGPs) + 9 `not_aoc_topic` stubs tidied in 2026-05-14.
- Loose end: per-entry `verification_quote` not captured for the 16 total `not_aoc_topic` stubs — re-research to upgrade if a downstream consumer ever needs it (current consumer doesn't).

Run `.venv/bin/python scripts/02b_fetch_aoc_lexicon.py --lang fr --refresh` (then `--lang es --refresh`) to apply the curator pins; positive pins emit `lead_extract` + `sections` + `full_text` records (`looks_like_aoc` keyword filter is bypassed since the curator already validated via `verification_quote`); negative findings emit `missing: True` or `error: "not_aoc_topic"` with `override_source: "curator"`. After refresh, re-run 02d / 02e / 04 to surface the Wikipedia hints downstream.

### Terroir-fact extraction — 8 parents producing zero bullets

⏳ Stage 02d ran but the fuzzy-coverage filter (≥0.6) dropped every candidate. Re-run [scripts/02d_extract_terroir_facts.py](scripts/02d_extract_terroir_facts.py) on these slugs with `--verbose` to diagnose:

cotes-de-thau · calvados-vin · cotes-catalanes · thezac-perricard · vicomte-d-aumelas · vallee-du-torgan · pays-d-herault · cote-vermeille

### PNOCDC draft PDFs — section X missing or template-only — ✅ complete

✅ **2026-05-14 resolution**: all 27 originally-flagged entries now extract with full section X. 18 resolved in earlier curator passes via BO Agri arrêtés modifiants (Auxey-Duresses, Pernand-Vergelesses, Chorey-lès-Beaune, Bâtard-Montrachet, Bienvenues-Bâtard-Montrachet, Musigny, Monthélie, Pouilly-Loché, Saint-Véran, Vicomté d'Aumelas, Banyuls grand cru, Coulée de Serrant, Lavilledieu, Maury, Muscat de Rivesaltes, Muscat de Saint-Jean-de-Minervois, Sainte-Marie-la-Blanche, Yonne). The remaining 9 (Chassagne-Montrachet, Beaune, Santenay, Côte de Nuits-Villages, Irancy, Grand Roussillon, Muscat de Frontignan, Saint-Julien, Touraine Noble Joué) resolved via **professional-organisation mirrors** of the homologated cahier:

- **CAVB** (`cavb.fr`) — 5 Burgundy 2011 cluster cahiers (Chassagne, Beaune, Santenay, Côte de Nuits-Villages, Irancy)
- **FGVB** (Fédération des Grands Vins de Bordeaux) — Saint-Julien
- **lr-origine.com** — Muscat de Frontignan
- **maisondesvignerons66.fr** — Grand Roussillon
- **musee-boissons.com** — Touraine Noble Joué (JORF rendering with cahier as annex)

The CAVB / lr-origine / maisondesvignerons66 PDFs are mirrors of the original INAO SOMM49 source — they embed Type 1C subset fonts without a ToUnicode CMap, so `pdftotext` returns glyph-code junk. Stage 02 ships with an **OCR fallback** that auto-triggers on this case: pdftoppm at 300 DPI + `tesseract -l fra` , with `fra.traineddata` auto-downloaded to `raw/_tools/tessdata/` on first use. The fallback detection is a French-function-word density heuristic (`_looks_like_glyph_junk` in [scripts/02_extract_cahiers.py](scripts/02_extract_cahiers.py)).

**Total unlock**: 122 slugs (9 parents + 113 DGCs — Chassagne +56, Beaune +43, Santenay +14). Re-run `02d` → `02e` → `03` → `04` to surface the new content downstream.


---

### Original ❌ finding (resolved 2026-05-14, kept for historical context)

27 distinct `extranet.inao.gouv.fr/fichier/PNOCDC*.pdf` URLs in `manual_overrides.json` were **public-opposition draft cahiers**, not the final post-homologation cahier. They included sections I–IX + XI–XII but section X ("Lien à l'origine") was either empty or held only the sub-section scaffolding (`1° Informations sur la zone géographique`, `a) Description des facteurs naturels`...) without bodies. Stage 02 extracted what's there correctly — the bodies were genuinely empty in these PDFs.

Confirmed via PDF body-scan: no other draft pattern hides in the corpus (4 BO Agri PDFs contain "procédure d'opposition" in body text but all are valid working cahiers; the marker is incidental). Draft problem is fully contained in the PNOCDC URL prefix.

Each PDF needs a replacement: the final BO Agri publication (with the filled-in section X). The corresponding `manual_overrides.json` entry should be updated, then stage 01 → 02 re-runs.

Sorted by impact (parents + DGCs unlocked):

| Parent | Slugs | Max lien (chars) | PNOCDC URL |
|---|---:|---:|---|
| chassagne-montrachet | **57** (1 + 56 DGCs) | 0 | `PNOCDC-Chassagne-Montrachet.pdf` |
| beaune | **44** (1 + 43 DGCs) | 0 | `PNOCDC-Beaune.pdf` |
| monthelie | **17** (1 + 16) | 0 | `PNOCDC-Monthelie.pdf` |
| santenay | **15** (1 + 14) | 0 | `PNOCDCSantenay.pdf` |
| auxey-duresses | **12** (1 + 11) | 0 | `PNOCDC-Auxey-Duresses.pdf` |
| pernand-vergelesses | **10** (1 + 9) | 0 | `PNOCDCPernand-Vergelesses.pdf` |
| pouilly-loche | 3 | 255 | `PNOCDC-Pouilly-Loché.pdf` |
| chorey-les-beaune | 2 | 0 | `PNOCDCChorey-les-Beaune.pdf` |
| saint-veran | 2 | 255 | `PNOCDC-Saint-Véran.pdf` |
| vicomte-d-aumelas | 2 | 393 | `PNOCDCIGPVicomtedDAumelas.pdf` |
| banyuls-grand-cru | 1 | 257 | `PNOCDCBanyulsgrandCru.pdf` |
| batard-montrachet | 1 | 0 | `PNOCDCBatard-Montrachet.pdf` |
| bienvenues-batard-montrachet | 1 | 383 | `PNOCDCBienvenues-Batard-Montrachet.pdf` |
| cote-de-nuits-villages | 1 | 0 | `PNOCDCCotedeNuits-Villages.pdf` |
| coulee-de-serrant | 1 | 0 | `CDCSAVENNIERESCOULEEDESERRANT.pdf` |
| grand-roussillon | 1 | 257 | `PNOCDC-Grand-Roussillon.pdf` |
| irancy | 1 | 0 | `PNOCDC-Irancy.pdf` |
| lavilledieu | 1 | 390 | `PNOCDCIGPLavilledieu.pdf` |
| maury | 1 | 0 | `PNOCDC-Maury.pdf` |
| muscat-de-frontignan | 1 | 0 | `PNOCDC-Muscat-de-Frontignan.pdf` |
| muscat-de-rivesaltes | 1 | 257 | `PNOCDC-Muscat-de-Rivesaltes.pdf` |
| muscat-de-saint-jean-de-minervois | 1 | 257 | `PNOCDC-Muscat-de-St-Jean-de-Minervois.pdf` |
| musigny | 1 | 0 | `PNOCDCMusigny.pdf` |
| saint-julien | 1 | 0 | `PNOCDCSaintJulien.pdf` |
| sainte-marie-la-blanche | 1 | 485 | `PNOCDCIGPSainteMarielaBlanche.pdf` |
| touraine-noble-joue | 1 | 255 | `pnocdc-touraine.pdf` |
| yonne | 1 | 700 | `PNOCDCYonne.pdf` |

**Total: 27 PDFs, 181 slugs (27 parents + 154 DGCs).**

Workflow per entry: search BO Agri for the canonical post-publication cahier of the parent appellation, confirm section X has a substantial "Lien" narrative (use `pdftotext -layout <pdf> - | grep -A40 'X.*Lien'`), then replace the URL in `raw/inao/cahiers/manual_overrides.json`. Re-run stage 01 → 02 → 02d for affected slugs.

_(Historical: research prompt for this batch existed at `scripts/_lib/pnocdc_research_prompt.md`; deleted 2026-05-14 after all 27 entries resolved. Resurface from git history if a similar batch ever recurs.)_

For the high-impact parents (Chassagne, Beaune, Monthélie, Santenay, Auxey-Duresses, Pernand-Vergelesses) the BO Agri canonical was previously catalogued as `❌ LODA décret-only` and the curator opted for the PNOCDC fallback — these may still need to come via a different INAO route (e.g. the post-2014 modification arrêté annex that ships the full cahier).

### Terroir-fact erosion — 3 FR Burgundy parents blocked on PNOCDC drafts — ✅ unblocked

✅ auxey-duresses, pernand-vergelesses, saint-veran sourced from PNOCDC draft PDFs which had empty section X. All resolved in earlier curator passes via BO Agri arrêtés modifiants — `02d --refresh` against the current cahiers should produce real bullets.

### Terroir-fact extraction — IGP parser fixes shipped (2026-05-12)

✅ Stage 02 IGP extractor patched with two fixes:

1. **Orphan sub-section absorption** in `extract_igp_sections`: when a parent section's title matches the lien-narrative keyword and its body is short (<800 chars), absorb every following sub-numbered section into it — handles `agenais` (parent "8 – Lien" + children "8.7-1"/"8.7-2"), `maures` (parent "7 – Lien" + "7-1"/"7-2"), `haute-vallee-de-l-orb` (parent "7 – Lien" + mis-numbered "8-1"/"8-2"/"8-3").
2. **Title-aware lien routing** in `extract_one`: pick the IGP lien by title-keyword match (`"lien avec"`, `"lien au terroir"`), not the positional fallback `("8", "7", "9")` — `maures` has section 8 = labelling and section 7 = lien content.
3. **Page-break regex tightening** in `IGP_SECTION_HDR_RE`: replaced intra-header `\s*` with `[ \t]*` so the 2025 BO Agri MAASA template (every page ends with a centered page number followed by a form-feed + "Publié au BO Agri du MAASA le 11 décembre 2025" header) no longer binds the trailing page number to the next page's header as a phantom section title. Unblocked `mediterranee`.

**Coverage**: 80/87 IGPs working → **85/87 (98%)** after these fixes. Refreshed terroir facts for `agenais`, `maures`, `haute-vallee-de-l-orb`, `mediterranee`, `pays-d-oc` with 02d + 02e.

4. **`lien au territoire` keyword variant** (2026-05-12): the regulator writes "Lien au territoire" (with 'i') for Pays d'Oc IGP. Added to both `SECTION_ROLE_KEYWORDS["lien"]` and `_IGP_LIEN_KEYWORDS`. Unblocked `pays-d-oc` (602 → 11546 chars).

### Terroir-fact extraction — 2 residual broken IGPs (post-fix)

| Slug | lien (chars) | Cause |
|---|---:|---|
| `euskal-sagardoa-ou-sidra-del-pais-vasco-…` | 0 | Section parser mis-matches numeric table columns as section headers (`sections` dict has keys like "11010", "64220", "29", "30"…). Edge case — Basque cider IGP with multi-page analytical tables. |
| `yonne` | 759 | PNOCDC draft — resolved 2026-05-14 in earlier curator pass; re-run 02d. |

---

## Spain

### Pliego URLs — ✅ complete (2026-05-10)

**All 149 Spanish DOPs/IGPs now extract.** Two curator URL rounds (61 from MAPA + 1 euskadi.eus + 7 already-cached fixes via OJ C/L heuristic) plus three parser additions (PDF dispatch in stage 01, Spanish national-format section parser in stage 02, precedence dispatch on prefix style) closed every stub.

Detail tables below preserved as reference. Workflow notes:

```
.venv/bin/python scripts/es/regen_manual_overrides_template.py
# edit raw/es/oj-pages/manual_overrides.json
.venv/bin/python scripts/es/01_fetch_pliegos.py
.venv/bin/python scripts/es/02_extract_pliegos.py
.venv/bin/python scripts/04_build_maps.py
```

#### IGP stubs (35) — all eAmbrosia `no-publication`

3 Riberas · Altiplano de Sierra Nevada · Bailén · Bajo Aragón · Betanzos · Campo de Cartagena · Castelló · Castilla y León · Costa de Cantabria · Cumbres del Guadalfeo · Cádiz · Córdoba · Desierto de Almería · Ibiza · Illes Balears · Laderas del Genil · Laujar-Alpujarra · Liébana · Los Palacios · Murcia · Norte de Almería · Ribera del Andarax · Ribera del Gállego–Cinco Villas · Ribera del Jiloca · Ribera del Queiles · Serra de Tramuntana–Costa Nord · Sierra Norte de Sevilla · Sierra Sur de Jaén · Sierras de Las Estancias y Los Filabres · Torreperogil · Valdejalón · Valle del Cinca · Valle del Miño-Ourense · Valles de Sadacia · Villaviciosa de Córdoba

#### DOP stubs (33)

`no-publication` (26): Abona, Bullas, Calzadilla, Campo de La Guardia, Cangas, Dominio de Valdepusa, El Hierro, El Terrerazo, Getariako Txakolina, Guijoso, La Gomera, La Palma, Lebrija, Mondéjar, Málaga, Pago Florentino, Pago de Otazu, Sierra de Salamanca, Somontano, Terra Alta, Tierra del Vino de Zamora, Valle de Güímar, Valle de la Orotava, Valles de Benavente, Valtiendas, Ycoden-Daute-Isora

`not-single-document` (5 — URL exists but template not parseable): Chozas Carrascal, El Vicario, Rosalejo, Tharsys, Urbezo

`no-documento-unico-anchor` (✅ resolved — flag was stale): Toro + Ribera del Guadiana both anchor-match cleanly against `DOC_UNICO_ANCHOR_RE` in [scripts/es/02_extract_pliegos.py:212](scripts/es/02_extract_pliegos.py#L212) (re-verified 2026-05-14). Toro extracts 7 principal grapes; Ribera del Guadiana extracts polygon (`figshare-pdo`). RDG's "0 principal grapes" trace is a separate role-routing issue — its older `ti-grseq-1` template puts grapes at section 7 (not 6) with non-standard numbering, so the grape parser misses them. See `ES role-routing coverage` in code follow-ups.

### Geometry — visibility ✅; precision ⏳ for 4 wines

**Visibility check (2026-05-14)**: zero ES `stub-no-geometry` features in `wiki/map-data/appellations.geojson`. The 6 entries in [raw/es/geometry_research.json](raw/es/geometry_research.json) all resolve to `geometry-research-municipios` (whole-municipio union of GISCO communes by INE code) via [scripts/04_build_maps.py:836-848](scripts/04_build_maps.py#L836-L848). So every ES record has a polygon.

What remains is **precision** — for 4 wines the pliego specifies sub-municipio inclusions (SIGPAC parcels for vinos de pago, parroquias for Terras do Navia, a single parcel cut inside Ciudad Real for Campo de Calatrava) that we don't yet honour. The current polygons overcount the actual production zone:

| Wine | Current resolution | Precision gap (needs code-side data fetcher + resolver) |
|---|---|---|
| Abadía Retuerta (DOP, Vino de Pago) | `geometry-research-municipios` (Sardón de Duero whole, 12.5 km²) | Pliego limits to polígono 2, parcelas 1/4/5/6/8/9/10/13/14/9000 (560 ha total). Needs Castilla y León SIGPAC source — outside current Catalonia-only `SIGPAC_COMARCA_CODIS` scope. |
| Bolandin (DOP, Vino de Pago, Navarra) | `geometry-research-municipios` (Ablitas whole) | Pliego limits to polígono 5 + 8 specific parcelas + partial-recinto cut for parcela 1885 (`recinto A parcial, E, F, G, H`). Needs Navarra SIGPAC + recinto-level handling. |
| Campo de Calatrava (DOP, Ciudad Real) | `geometry-research-municipios` (17 whole municipios) | 16 of 17 should be whole (already correct); Ciudad Real should be just polígono 22 parcela 74. Needs Castilla-La Mancha SIGPAC for the cut. |
| Terras do Navia (IGP, Galicia) | `geometry-research-municipios` (3 whole municipios, ~1500 km²) | Pliego limits to specific parroquias in 2 of 3 municipios. Needs Xunta de Galicia parroquia cartography fetch + new resolver step in stage 04. |

The data-side facts are all captured in `geometry_research.json` (INE codes, SIGPAC enumerations, parroquia lists, verbatim "Demarcación de la zona geográfica" quotes). Each precision fix is a non-trivial new-source code task (per-CCAA SIGPAC schemas differ; parroquia layer doesn't currently exist in our `raw/`).

### Interprofession / consejo regulador URLs — ✅ closed (2026-05-14)

Sidepanel "Site officiel de l'interprofession" row is driven by [scripts/_lib/appellation_urls.json](scripts/_lib/appellation_urls.json). _(Research prompt previously at `scripts/_lib/es_crdo_research_prompt.md`, deleted 2026-05-14 after all batches closed.)_

2026-05-14 round merged 56 entries (54 URLs + 2 explicit nulls). `by_slug` grew from 149 → 205. Smoke-tested against Montsant + Priorat (unchanged). Re-run stage 04 to surface the new "Site officiel" rows.

#### Vinos de Pago — ✅ 27 merged

- **2026-05-12 + 2026-05-13** (23): ayles · bolandin · calzadilla · campo-de-la-guardia · chozas-carrascal · dehesa-del-carrizal · dehesa-penalba · dominio-de-valdepusa · el-terrerazo · el-vicario · la-jaraba · los-balagueses · los-cerrillos · pago-de-arinzano · pago-de-otazu · pago-florentino · prado-de-irache · rio-negro · tharsys · urbezo · uruena · vallegarcia · vera-de-estenas
- Plus **abadia-retuerta** ✅ (DOP, single-estate Vino de Pago by status though listed as standalone DOP).
- **2026-05-14** (4): casa-del-blanco (pagocasadelblanco.es) · finca-elez (pagofincaelez.com) · guijoso (campoyalma.com/guijoso_4) · rosalejo (eldoze.com — Bodegas Eldoze, sole producer; site still labels "Vino de Tierra de Castilla" pending Pago wiring).

#### Top-20 majors — ✅ 20 merged

rioja · cava · ribera-del-duero · priorat · montsant · rias-baixas · jerez-xeres-sherry · manzanilla-de-sanlucar · penedes · toro · rueda · bierzo · navarra · somontano · la-mancha · utiel-requena · valencia · alicante · jumilla (2026-05-13). Plus **valdepenas** ✅ (2026-05-14, campoyalma.com/valdepenas — JCCM marca-de-garantía portal, no autonomous consejo exists). Sherry+Manzanilla share `sherry.wine`.

Txakoli trio (arabako-txakolina, bizkaiko-txakolina, getariako-txakolina) — each got its own dedicated site (txakolidealava.eus / bizkaikotxakolina.eus / getariakotxakolina.eus), no common órgano de gestión exists.

#### Alphabetical DOP sweep — ✅ 45+8 merged

- **2026-05-13** (~38): calatayud · campo-de-borja · carinena · cigales · conca-de-barbera · condado-de-huelva · costers-del-segre · emporda · ribeira-sacra · ribeiro · valdeorras · monterrei · malaga · sierras-de-malaga · montilla-moriles · manchuela · mentrida · yecla · vinos-de-madrid · bullas · tacoronte-acentejo · valle-de-guimar · valle-de-la-orotava · ycoden-daute-isora · abona · la-palma · el-hierro · la-gomera · gran-canaria · lanzarote · islas-canarias · cataluna · terra-alta · pla-de-bages · binissalem · pla-i-llevant · leon · arlanza · arribes · granada · cebreros · ribera-del-guadiana · ribera-del-jucar · ucles · valles-de-benavente.
- **2026-05-14** (8): tarragona (INCAVI) · alella (INCAVI) · mondejar (domondejar.es) · cangas (docangas.es) · sierra-de-salamanca (dosierradesalamanca.es — splash + contact only) · tierra-del-vino-de-zamora (tierradelvino.net) · valtiendas (dopvaltiendas.com) · lebrija (Junta de Andalucía DOP/IGP catalogue — corpus says DOP, not IGP).

#### IGPs (Vinos de la Tierra) — ✅ 41 merged, 2 nulls (2026-05-14)

Second-batch redo against regional Junta fallbacks (per prompt step 4). Andalucía cluster (16) → Junta de Andalucía DOP/IGP catalogue. Aragón (6) → aragon.es IGP page. Galicia (4) → AGACAL. Illes Balears (5) → IQUA (HTTP-only on iqua subdomain). Castilla y León / Castilla → tierradesabor.es / campoyalma.com. La Rioja → larioja.org. Cantabria → ODECA. Extremadura → juntaex.es. Mallorca got its own consejo site `vtmallorca.com`.

Judgement notes:
- `3-riberas` → Navarra (not Comunitat Valenciana — prompt hint map had it wrong; corpus geo_area_brief confirms Comunidad Foral de Navarra).
- `ribera-del-queiles` (supra-autonómica Aragón/Navarra) → routed to aragon.es.
- `castello` → GVA Portal Agrari (only navigable GVA catalogue page).
- `valdepenas` + `guijoso` → JCCM-backed `campoyalma.com` (no autonomous consejo; consejería's marca-de-garantía portal).

2 explicit nulls:

| slug | Note |
|---|---|
| campo-de-cartagena | ❌ null — CARM (carm.es) has no navigable DOP/IGP catalogue page naming this IGP. Only news + BORM publications. Curator may revisit; current `null` is honest. |
| murcia | ❌ null — same as campo-de-cartagena. CARM agriculture homepage works as a stub but doesn't satisfy the "names the IGP + pliego" test. |

Smoke-test against Montsant + Priorat after each major batch lands.

### Grape lexicon — ES varieties already iterated

✅ [scripts/02b_fetch_grape_lexicon.py:76-95](scripts/02b_fetch_grape_lexicon.py#L76-L95) (`collect_grape_slugs`) already iterates both `raw/inao/cahier-extracted/` and `raw/es/pliegos-extracted/`. ES-only Iberian varieties (Canary, Galicia, Catalan) flow into the cache automatically on next 02b run. The remaining work is curator-side: per-locale title overrides for varieties whose `es.wikipedia.org` page lives at a non-canonical title (e.g. `(uva)` disambiguator) — surface candidates via [scripts/audit_es_grape_aliases.py](scripts/audit_es_grape_aliases.py).

### Wikipedia ES pages — 29 missing/error parents

⏳ Same situation as FR — no override mechanism. 5 IGP + 24 DOP. 9 are `not_aoc_topic` (urueña, ayles, campo-de-calatrava, bolandin, dehesa-penalba, abadia-retuerta, rio-negro, rosalejo, islas-canarias).

### National-pliego variety augmentation — 12 records (data ready, code wiring pending)

🟢 New stage `scripts/es/02f_extract_national_pliegos.py` parses the section-6 ("Variedades…") block of each ES national pliego PDF (linked from doc-único section 9) and merges its varieties into the map as accessory entries via [scripts/_lib/es/national_pliego.py](scripts/_lib/es/national_pliego.py). Sweep `--all` on 2026-05-12 enriched 39 records (300+ new variety-DOP additions including Méntrida's 16 secondary varieties).

✅ **All 12 URL gaps closed 2026-05-14** — curator research located every replacement on the MAPA archive (`mapa.gob.es/dam/.../pliegos-de-condiciones/pliego-condiciones-vinos/{dops,igps}/`); merged into [raw/es/national-pliegos/manual_overrides.json](raw/es/national-pliegos/manual_overrides.json) (slug-keyed `{pliego_url, source_org, verification_note}`). Stage 02f override-priority read shipped same day in [scripts/es/02f_extract_national_pliegos.py](scripts/es/02f_extract_national_pliegos.py); `--all` re-run produced 12 new sidecars under `raw/es/national-pliegos-extracted/` with **138 new variety-DOP additions** (most impactful: valencia +57, ribera-del-guadiana +45, terras-do-navia +12, vinos-de-madrid +4, rueda +4, bierzo +4, chozas-carrascal +5, campo-de-borja +6, rioja +1). Zero regressions across the 43 baseline pliegos.

Parser improvements that landed alongside the wire-up in [scripts/_lib/es/national_pliego.py](scripts/_lib/es/national_pliego.py) to handle the newly-unblocked MAPA-archive PDFs:
- `_PREFIX` relaxed to accept whitespace separator between digit and title (ribera-del-guadiana's `6 VARIEDADES DE VID.`)
- Digit count bounded to 1-2 so postal codes (`06200 Almendralejo`) don't masquerade as section headers
- Leading-whitespace bound (0-16 same-line chars) so deeply-indented revision-history table cells (rueda's col-23 `6) Variedades autorizadas:`) lose to the real header further down
- `_TRAILER` gained a bare `VITIS\s+VIN[IÍ]FERA[S]?` alternative (penedes's `6.-Variedades Vitis viníferas` drops the `DE` linker)
- `_TOC_LINE_RE` filter rejects TOC entries with dot-leader or trailing standalone page number (when both TOC and body share the full trailer string)
- `_NEXT_SECTION_RE` separator tightened to non-newline whitespace (`[^\S\n]+`) so a standalone page number between section header and wrapped variety list (penedes: `…\n10\n\nMacabeo,…`) no longer reads as "section 10. Macabeo" and truncates the body. Fixes penedes (0 → 23 varieties, +20 new slugs). Zero regressions on the other 54 sidecars.

Re-run `.venv/bin/python scripts/04_build_maps.py` to surface the 158 new variety-DOP additions on the map.

### Terroir-fact extraction — ✅ complete (2026-05-10)

✅ All 80 extracted ES parents have terroir-fact bullets (1,019 cahier-grounded + wiki bullets total). Stage 02e produced 239 ES → en/fr/nl translations (80 wines × 3 locales, minus 1 stub-only). Audit re-run (after `audit_terroir_facts.py` country-dispatch fix) shows **0 ES erosions**. Smoke-tested against Priorat (`llicorell` preserved across en/fr/nl) and Montsant (`Ull de llebre` preserved; pliego covers grape-tradition rather than geology, no factual hallucinations).

---

## Code-side follow-ups (not curator data tasks)

These surfaced in the audit but require code changes, not lookups:

- ✅ **[scripts/01b_solve_legifrance.py](scripts/01b_solve_legifrance.py)** — cookie-injection fetcher with `--reauth` flag for stale cookies; persistent creds at `~/.config/openwinemap/legifrance.json` (chmod 600). Detects Cloudflare interstitial and aborts batch with clear error.
- ✅ **Stage 01 fall-through** — walks `pdf_urls` until one yields a real PDF, so .docx primaries fall through to PDF fallbacks. Unlocked Pouilly-Vinzelles.
- ✅ **Stage 02 alias-aware matching** — `candidate_keys()` splits parent names on " ou ", " et ", "," and the cross-bundle rescue index keys every alias. `find_segment` matches on shared components rather than naive substring (avoids "Bourgogne" matching "Bourgogne Passe-tout-grains").
- ✅ **Stage 02 IGP regex** — accepts `1) DENOMINATION`, `1. Nom`, `4-1- Obligations`, `4-1-1- Déclaration` heading patterns + trailing `:`. Plus `IGP_CHAPITRE_RE` recognises `CHAPITRE 1 –` (em-dash, uppercase) alongside the legacy `Chapitre 1 :`.
- ✅ **Stage 02 split_bundle heuristic** — when a normalized cahier name appears ≥3 times in a PDF (page-footer repetition in BO Agri "Avis" annexes), key the segment to the FIRST occurrence instead of the LAST. Unlocked Cidre de Bretagne / Normandie / Cotentin etc.
- ✅ **Stage 01 override-priority** — override URLs now prepend (replacing whatever show_texte resolved); cache check tightened to only fire when prior URL == current canonical. Unlocked the 7 round-2 entries where show_texte's resolution disagreed with the curator's verified URL.
- ✅ **Stage 02 rescue-without-filename** — manifest entries with empty `filename` (e.g. Légifrance-canonical AOCs whose 01b render got wiped by a later stage-01 re-process) now still try cross-bundle rescue. Restored Savigny-lès-Beaune from the ad444512 bundle without re-fetching from Légifrance.
- ✅ **All FR cahiers extracted** as of 2026-05-10. No data-curation tasks remaining for FR cahier coverage.
- ✅ **ES commune-list parser — MAPA Spanish-national-format prose** (2026-05-11). [scripts/_lib/es/commune_list.py](scripts/_lib/es/commune_list.py) extended with lead-ins for "engloba/comprende/incluye/constituida por los siguientes términos municipales:", province-prefix-segment cleanup ("Provincia de Teruel: …; Provincia de Zaragoza: …"), parenthetical-aside stripping, footnote-marker handling, and MAPA-style end markers (`(*).—`, `Incluye las siguientes parcelas`, `MUNICIPIO\nPOLÍGONO`). `parse_ccaa_wide` / `parse_province_wide_list` gained the `totalidad de los municipios de la Comunidad Autónoma de X`, `es la provincia de X, incluyendo todos sus municipios`, and `\A`-anchored "Comunidad Autónoma de X" forms. Stage 04's `_resolve_es_igp_fallback` now tries `sections["9"]` when `geo_area_brief` yields nothing (covers wines where stage 02's title-keyword router picked the wrong section, e.g. Mallorca, Ribeiras do Morrazo), plus a `gisco-province-by-name` last-resort fallback (wine `name` → `PROVINCE_TO_INE`) for province-named IGPs whose pliego has no commune list anywhere (Castelló). **Unlocked all 15 of 15 previously-stub IGPs.**
- ✅ **AOC Wikipedia override file** (2026-05-14) — [scripts/02b_fetch_aoc_lexicon.py](scripts/02b_fetch_aoc_lexicon.py) now loads [raw/wikipedia/aoc_overrides.json](raw/wikipedia/aoc_overrides.json) (101 fr + 29 es entries) at import time into `LANG_OVERRIDES`; `fetch_aoc()` short-circuits to `_record_from_override()` when an override exists for `(lang, slug)`. Three branches: positive pin fetches `wiki_title` directly (bypasses `looks_like_aoc` keyword filter — curator validated via `verification_quote`), enriches with sections + full_text, and stamps `override_source: "curator"` + the verification quote into the cache; `missing` and `not_aoc_topic` emit cascade-compatible record shapes (`missing: True` / `error: "not_aoc_topic"`) without hitting the network. Override file edits invalidate via `--refresh`.
- ✅ **Stage 02f override wire-up** (2026-05-14) — [scripts/es/02f_extract_national_pliegos.py](scripts/es/02f_extract_national_pliegos.py) reads [raw/es/national-pliegos/manual_overrides.json](raw/es/national-pliegos/manual_overrides.json) before falling back to the section-9 URL; override-driven URL change auto-invalidates the slug-keyed PDF cache (compares sidecar `source.url` against override). Plus parser tightening in [scripts/_lib/es/national_pliego.py](scripts/_lib/es/national_pliego.py) to handle the MAPA-archive PDFs (see "National-pliego variety augmentation" section above).
- **ES pliego parser — BOE PDF / regional-gazette templates** — current parser only handles EU-OJ documento único; closing IGP no-publication wines requires per-source parsers.
- ✅ **ES pliego parser — `no-documento-unico-anchor` regex** (2026-05-14) — investigation showed the existing `DOC_UNICO_ANCHOR_RE` matches both Toro and Ribera del Guadiana. RDG's actual gap (0 principal grapes) traces to non-standard section numbering in its older `ti-grseq-1` template — see the role-routing follow-up below.
- **Stage 04 — Comté Tolosan (id=861) silently dropped** from FR appellations.geojson despite clean cahier; investigate.
- ✅ **Stage 02 IGP — absorb orphan sub-numbered sections** (2026-05-12). `_absorb_lien_orphans` + title-keyword routing in `extract_igp_sections`/`extract_one`. Fixed `agenais` (146→9190), `maures` (335→8523), `haute-vallee-de-l-orb` (174→4978). Plus regex tightening for 2025 MAASA template page-break footgun: unblocked `mediterranee`.
- **Stage 02 IGP — residual broken IGPs** — `euskal-sagardoa` (section parser mis-matches numeric table columns as section headers, e.g. "11010", "64220"). Needs targeted diagnosis. `yonne` is a PNOCDC draft — fixes via the curator queue.
- **02d IGP slicing** — `slice_section_x` in [scripts/02d_extract_terroir_facts.py](scripts/02d_extract_terroir_facts.py) looks for FR canonical `1° / 2° / 3°` markers (AOC-style). IGP cahiers use `Spécificité de la zone / du produit / Lien causal` instead, so the slicer fails and the whole lien goes into the `facteurs_naturels` bucket — producing thin coverage (5 facts in a single sub-section instead of 10–15 spread across 4). Add an IGP-aware fallback that recognizes the `Spécificité…` / `Lien causal…` sub-headings.
- **Stage 02 — detect empty/template section X** — when `extract_sections` (AOC) produces section X with `<800` chars while sections I–IX and XI–XII are present and substantial, that's a PNOCDC draft signature. Emit a warning to stderr + flag the record (`source.draft_lien: true`) so `audit_coverage.py` can surface it without manual scanning. Would have caught the 181-slug PNOCDC gap automatically at extraction time.
- **ES SIGPAC — extend beyond Catalonia** (precision improvement, not visibility unlock). Current SIGPAC source is Catalonia-only via `analisi.transparenciacatalunya.cat` (Socrata API, comarca-keyed gpkgs). Per-CCAA Spanish SIGPAC publication formats differ — Castilla y León (JCyL), Navarra (own portal), Castilla-La Mancha (JCCM) each expose SIGPAC via separate APIs with different schemas. To honour the SIGPAC parcel enumeration in `geometry_research.json` for Abadía Retuerta (Valladolid), Bolandin (Navarra), Campo de Calatrava (Ciudad Real cut), and the existing Tharsys + Urbezo entries (Valencia, Zaragoza), need either (a) a national SIGPAC source like the FEGA web service, or (b) per-CCAA fetchers with schema-adaptation layers. Currently these wines render with whole-municipio polygons (overcounted production zone but visible).
- **ES SIGPAC partial-recinto handling** — Bolandin parcela 1885 is `recinto A parcial, E, F, G y H` rather than a whole parcel. Either subset the SIGPAC geometry by recinto, or accept the whole-parcela polygon as an approximation (note in `geom_source` metadata). Only relevant after the Navarra SIGPAC source above is wired up.
- **ES JCCM apliagri PDF parser branch** — Campo de Calatrava's pliego is hosted on apliagri.castillalamancha.es, not EU-OJ. Currently the wine renders via `geometry-research-municipios` (17 whole municipios from the curator's verbatim quote in `geometry_research.json`). The precision gap is the Ciudad Real cut (polígono 22, parcela 74) which would shrink the polygon by 1 large municipio's footprint. Visible polygon already correct in 16/17.
- **ES Xunta parroquia data source** — Terras do Navia delimits by Galician parroquias (sub-municipal civil parishes). Currently renders 3 whole municipios; pliego limits 2 of them to specific parroquias. Needs a Xunta / IGN parroquia cartography fetch in stage 00 plus a new `xunta-parroquia-list` step in the stage-04 ES geometry chain. Whole-municipio polygon overcounts but is visible.
- **ES role-routing coverage** — 74 parents have an unrouted `name` role, 14 unrouted `geo_area`, 9 unrouted `link_to_terroir`, 4 each for `description` / `grape_varieties`. Section bodies are present, just not labelled with the canonical role. A handful more keyword additions to the stage-02 router would close most of these. Worth a separate pass when stage-04 rendering surfaces specific gaps.
- **ES stage-01 `--refresh` manifest footgun** — `--refresh --only X` wipes manifest entries for wines outside the `--only` filter. Doesn't block extraction (stage 02 dispatches by file existence) but the manifest stats audit reports incorrect counts. Cosmetic.

## Style taxonomy follow-ups

- **Sweet/oxidative cross-cut** — `generoso` (sherry-family) sits under `oxidative` because most sherries are dry; PX cream sherries and dulces are nominally oxidative *and* sweet. Currently they only emit `oxidative + generoso + (sub-tag)`; the `sweet` bucket is *not* added. Decide whether to surface dual-tagging (record carries both `oxidative` and `sweet`) when the pliego describes a PX / cream / sweet-oloroso style. Currently affects ~5 sherry pliegos. Defer to v2.
- **Grape display — surface the more common term** — chip labels currently render the verbatim pliego name (e.g. "MAZUELA", "VIURA"). For cross-border discoverability, surface the international/canonical synonym ("Carignan", "Macabeo") as a tooltip or secondary chip when the canonical slug differs from the verbatim local name. Slug already canonicalises (`carignan`, `macabeu`) so filtering works; this is purely a display enhancement. Defer to v2.
- ✅ **ES grape Wikipedia tooltips** (shipped earlier) — `collect_grape_slugs` in [scripts/02b_fetch_grape_lexicon.py:76-95](scripts/02b_fetch_grape_lexicon.py#L76-L95) iterates both FR cahiers and ES pliegos. ES-only Iberian varieties flow through. Curator pass for non-canonical `es.wikipedia.org` titles still open (`(uva)` disambiguator etc.).
- **ES grape alias gaps** — [scripts/audit_es_grape_aliases.py](scripts/audit_es_grape_aliases.py) lists tokens that don't resolve through `GRAPE_ALIAS` / `DEFAULT_COLOUR`. ~250 distinct tokens after current seeding; biggest residual classes are Canary Islands varieties (Bermejuela, Marmajuelo, Vijariego, Listán Negro, …) and Galician varieties (Brancellao, Sousón, Loureira, Caíño…). Most are genuine ES-only varieties — register their canonical slug in `DEFAULT_COLOUR` rather than aliasing.
- **Parenthesised synonyms in ES variety lists** — pliegos like 3-riberas write "Albillo Mayor (Turruntés)" where the parenthetical is the regional synonym. Parser currently keeps the parenthesis in the name → 3-token slug. Extract the parenthesised tail as a synonym (route through `GRAPE_ALIAS`) and slug from the primary token only.
