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

### SIQO referentiel — 2 wines missing (eAmbrosia has them, INAO doesn't)

❌ Surfaced by 2026-05-17 eAmbrosia FR-wine reconciliation in [VERIFICATION.md](VERIFICATION.md). Both exist in the EU register but not in `raw/inao/siqo-referentiel.csv` — likely retired/merged on the INAO side without flowing through to the EU register.

| eAmbrosia file_number | Name | Verification needed |
|---|---|---|
| PDO-FR-A0257 | Cabernet de Saumur | Confirm via INAO product page <https://www.inao.gouv.fr/produit/8125> or Légifrance whether still in force; if active, pin via `manual_overrides.json` |
| PDO-FR-A0271 | Côtes de Blaye | Often considered merged into the Blaye / Premières Côtes de Blaye family. Verify status. |

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

### Geometry — official MAPA zones harvested 🟢 (2026-05-22)

ES geometry now uses the **official MAPA national wine-zone layer**
("Zonas de Calidad Diferenciada: Vinos", 96 DOP-side figures) as the
primary source — `geom_source = mapa-zone`, ahead of the Bétard
`figshare-pdo` fallback. ~90 of 106 ES DOPs resolve to an official
zone polygon; the 16 misses are newer Vinos de Pago that post-date
the layer (Abadía Retuerta, Cebreros, Río Negro, Tharsys, Urbezo, …)
→ they keep Bétard. The 43 IGPs aren't in the MAPA DOP-side layer and
keep the existing GISCO commune-union chain.

⏳ **Licence note** — the MAPA IDE *metadata record* declares CC-BY 4.0
("Sin limitaciones al acceso público"); the *download landing page*
carries softer non-commercial wording. The machine-readable metadata
is the citable licence and the project is non-commercial regardless,
so it's used with `© MAPA` attribution — but if the project ever
monetises, get this clarified with MAPA. Source: `_lib/es/zones.py`.

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

🟢 Browser-extension research prompt at [tmp/es-grape-wikipedia-research-prompt.md](tmp/es-grape-wikipedia-research-prompt.md): 39 ES-corpus grape slugs with no `es.wikipedia.org` card (25 `missing` + 14 `not_grape_topic`). Regenerate the list against the post-fetch state before use — the synonym-aware 02b re-fetch may recover some.

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

### OJ synonym pairs where VIVC contradicts the regulator — ✅ resolved (2026-05-19)

✅ Stage 02 emits `A - B` lines in section 7 as ` - `-split synonym tokens. 35 distinct pairs surveyed: 27 trivially folded (same VIVC ID on both sides); 8 disputed pairs resolved via Chrome-extension research against VIVC, EU DG-AGRI List 8, MAPA TOP de variedades, Canary Wine consejo regulador, ICIA, Marsal et al. (OENO One 2019), and Wine Grapes. Prompt preserved at [tmp/synonym-pairs-research-prompt.md](tmp/synonym-pairs-research-prompt.md) for future audits. All folds applied in [scripts/_lib/grape_lexicon.py](scripts/_lib/grape_lexicon.py) (37 new aliases + 1 update).

| Pair | Verdict | Fold |
|---|---|---|
| `almuneco` ↔ `listan-negro` | SAME (Canarian variety; #6860 Listán Prieto is the South American Mission/País, distinct) | almuneco → listan-negro |
| `agudelo` ↔ `chenin` | DIFFERENT (pliego is wrong; Agudelo is Galician Godello, not Chenin) | agudelo → godello; chenin stays |
| `tinto-velasco` ↔ `alicante-bouschet` (via "BLASCO") | DIFFERENT (VIVC carries BLASCO on both #17353 and #304; pliego's `TINTO VELASCO - BLASCO` refers to #17353) | blasco → tinto-velasco (vocab override via GRAPE_ALIAS Step 2 precedence) |
| `bastardo-negro` ↔ `baboso-negro` | DIFFERENT (Cabello 2011, Marsal 2019; both DOPs say `BASTARDO NEGRO - BABOSO NEGRO` but DNA says distinct) | bastardo-negro → trousseau; baboso-negro → alfrocheiro |
| `crudijera` ↔ `moravia-dulce` | SAME ("Crudijera" is a d↔j metathesis of CRUJIDERA, VIVC #23166 synonym) | crudijera → moravia-dulce |
| `merseguera` ↔ `sumoll-blanco` | DIFFERENT (no DNA relationship; pliego's identity claim is the regulator's own error) | none — keep split |
| `tintilla` ↔ `merenzao` (Canarian) | SAME in Canarian context only; 10/10 corpus uses of bare `tintilla` are Canarian DOPs, so global fold is safe | tintilla → trousseau (with peninsular `tintilla-de-rota` kept separate) |
| `negro-sauri` ↔ `merenzao` | SAME (EU DG-AGRI List 8 and MAPA both register NEGRO SAURÍ as a synonym of MERENZAO = Trousseau Noir #12668) | negro-sauri → trousseau |

Cross-canonical implication: all six Iberian names for VIVC #12668 (Trousseau Noir) now fold to `trousseau` — merenzao, maturana-tinta, bastardo-negro, negro-sauri, tintilla (Canarian), plus the existing FR `trousseau`. Map shows one slug per VIVC variety across countries.

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

## Portugal

### CVR / DO-organisation URLs — ✅ complete (2026-05-22)

Research run (`research-gaps` skill, 3 web-research agents) resolved the
official DO-organisation website for all 44 PT appellations — 14 distinct
bodies (12 Comissões Vitivinícolas Regionais + IVDP + IVBAM), cross-checked
against the IVV (`ivv.gov.pt`) entidades-certificadoras list. All 44 merged
into [scripts/_lib/appellation_urls.json](scripts/_lib/appellation_urls.json)
`by_slug`. 44/44 FOUND — no backlog. Findings:
[tmp/pt-cvr-urls-research-results.md](tmp/pt-cvr-urls-research-results.md).
Three cross-agent conflicts resolved at staging: Azores → IVVA (the old CVR
Açores domain lapsed); Beira Interior → `vinhosdabeirainterior.pt` (the
`cvrbi.pt` redirect target); CVR Lisboa → `http://www.vinhosdelisboa.com/`
(HTTP only — HTTPS cert-name mismatch).

### Cadernos — ✅ complete (2026-05-16, v1 land)

All 44 PT wine GIs (30 DOP + 14 IGP) auto-matched against the IVV master indexes ([www.ivv.gov.pt/np4/8617.html](https://www.ivv.gov.pt/np4/8617.html) for DOP, /8616 for IGP) and downloaded as sha-pinned PDFs. Zero stubs at first run.

### Extraction — ✅ structure / ✅ grape-list polish

- 44 parents + 32 sub-regiões extracted (76 records total).
- Sub-região detection: **Pattern A** (`Sub-região NAME`) covers Vinho Verde (9) + Alentejo (8) + 6 others = 23. **Pattern B** (Douro/Trás-os-Montes-style colon prefix) covers 9 (Douro 3 + Porto 3 + Trás-os-Montes 3). Dão, Beira Interior, Lafões, Távora-Varosa, Algarve don't enumerate sub-regiões in machine-parseable prose — those stay parent-only in v1 (sub-regiões exist in regulatory documents but aren't in the IVV caderno text).
- ✅ **Grape-list polish** (2026-05-16): [scripts/pt/02_extract_cadernos.py](scripts/pt/02_extract_cadernos.py) rewritten to handle all four IVV layouts cleanly:
  - **B/N/R/G/T colour-code stripping** — trailing single-letter IVV colour codes (`Boal Branco B` → `boal-branco`, `Bastardo N` → `bastardo`) are now removed before slugification, killing the entire family of `-b` / `-n` / `-r` / `-g` / `-t` suffix slugs.
  - **PRT tabular dispatch** — Bairrada-style (`PRT52003 Alfrocheiro Tinta-Bastardinha T`) and Pico-style (`PRT50218 Arinto dos Açores Terrantez da Terceira Branco`) rows take a dedicated path that peels off the IVV code, strips the colour column (single letter OR full-word `Branco`/`Tinto`), and extracts the canonical name via an article-pattern regex (`<Cap> de/do/da/dos/das <Cap>`). Pico now yields the correct 3 varieties (was 2); Bairrada's 28 are all clean single-name canonicals (no more `aragonez-tinta-roriz`).
  - **Sub-região block break** — `Sub-região de/do …` lines stop parent-list parsing. Vinho Verde no longer hoovers up the sub-region tables (was 60 incl. `seguinte` + `sub-regiao-de-amarante`+…, now 46 clean varieties).
  - **Page-footer / file-number / letter-header filter** — `PDO-PT-A\d+`, `Caderno de Especificações`, `a.` / `b.` / `c. Outras castas` letter-prefix headers are now dropped. Trás-os-Montes was 31 incl. `pdo-pt-a1466`, now 33 clean.
  - **Prose filter expanded** — `_PROSE_RE` now catches `seguinte` (singular), `vinhos`, `produtos`, `indicação`, `obtidos`, `replantac/plantac`, `efectuad/efetuad`, `ultrapass`, `vinificaç`, `consider`, `cento`, `conjunto`, `partir`. Tightened `_GRAPE_HEADER_KEYWORDS` to anchor `\s*$` so `Tinto Cão N` is no longer eaten by the `tinto` header alternative.
  - **Slug-level noise blocklist** — `_NOISE_SLUGS` + `_NOISE_SLUG_RES` catch residual `os-vinhos`, `ivv`, `ip-pagina-2`, `castas-indicadas-em-X`, etc.
  - **PT cross-country canonicalisation** ([scripts/_lib/grape_lexicon.py](scripts/_lib/grape_lexicon.py) GRAPE_ALIAS): `aragonez`/`aragones` → `tempranillo` (PT canonical of Tinta Roriz / Tempranillo); `gouveio` → `godello` (Galician canonical); `trajadura` → `treixadura`; `trincadeira-preta`/`tinta-amarela` → `trincadeira`; `esgana-cao` → `sercial`; `boal`/`bual` → `malvasia-fina` (Madeira DNA-confirmed); `brancelho` → `alvarelhao`; `alvaraca` → `batoca`; `maria-gomes` → `fernao-pires`; `trebbiano-toscano`/`talia` → `ugni-blanc`.
  - **Verified**: zero residual `-b`/`-n`/`-r`/`-g`/`-t` suffix slugs across all 44 parents; zero residual `pdo-pt-*`, `prt*`, `sub-regiao*`, `caderno-de-*`, `castas-indicadas-em-*`. 464 unique grape slugs across the PT corpus.

### Wikipedia grape lexicon — ✅ run completed (2026-05-17)

`scripts/02b_fetch_grape_lexicon.py` invoked across all 4 site locales (en/fr/es/nl) against the merged FR+ES+PT slug set. PT-only contribution: 407 new slugs (of 974 total). Per-locale outcome on the new PT slugs:

| locale | ok | err (not-grape) | miss |
|---|---:|---:|---:|
| en | 53 | 39 | 315 |
| fr | 35 | 22 | 350 |
| es | 19 | 45 | 343 |
| nl | 19 | 23 | 365 |

53 PT grapes now have an EN Wikipedia card (Touriga, Encruzado, Bical, Baga, Arinto, Alfrocheiro, Trincadeira, Avesso, Castelão, Sercial, Viosinho, Ramisco, plus international varieties Aglianico/Dolcetto/Sangiovese/Zinfandel/Bacchus/Dornfelder/Lemberger/Rotgipfler/Acolon). ~290 obscure-PT-only varieties (Antão Vaz, Folha de Figueira, Donzelinho Tinto, Verdelho do Pico, Terrantez do Pico, Castelão Branco, etc.) have **no** card in en/fr/es/nl because they only exist on pt.wikipedia.org. Two follow-ups in the Code section: (a) pt.wikipedia.org-source + translate sidecar pattern (mirroring stage 02b/styles-translate), (b) extraction-noise blocklist additions.

### Geometry — ✅ DOPs / ⏳ IGPs

- **30 DOPs** resolved via `figshare-pdo` (Bétard 2022 EU_PDO.gpkg).
- **32 sub-regiões** inherit parent's polygon (`parent-appellation`).
- **14 IGPs** have no Figshare row by design (Bétard is PDO-only). For v1 they appear in the sidebar with no polygon. Follow-up: parse the IGP cadernos' commune lists and union via `PTPolygonIndex.union_concelhos` against the CAOP 2025 GPKGs already on disk at `raw/pt/caop/`. The CAOP layer is loaded (305 concelhos in v1; full CAOP has ~308) — only the IGP commune-list parser needs writing. See [scripts/_lib/pt/geometry.py](scripts/_lib/pt/geometry.py).

### Translation cache — ⏳ awaiting manual round-trip

- PT records emit 76 translation jobs per locale via `02c_translate_summaries.py --source-lang pt --emit-todo`. Pipeline target locales for PT: en/fr/es/nl.
- Round-trip flow (matches user's existing FR/ES workflow):
  ```
  .venv/bin/python scripts/02c_translate_summaries.py --source-lang pt --emit-todo /tmp/pt-todo-en.json --lang en
  # external translator fills the items[].summary fields
  .venv/bin/python scripts/02c_translate_summaries.py --source-lang pt --import /tmp/pt-todo-en.json --translator-id <id> --translator-kind manual
  ```

### Terroir-fact extraction — ✅ siblings shipped (2026-05-16), ⏳ awaiting first run

PT now flows through 02d/02e via [scripts/pt/02d_extract_terroir_facts.py](scripts/pt/02d_extract_terroir_facts.py) + [scripts/pt/02e_translate_terroir_facts.py](scripts/pt/02e_translate_terroir_facts.py). Same dual-source grounding (caderno section 7 + pt.wikipedia.org/wiki/<DOP>), same manual round-trip support, same shared `raw/terroir-facts/` cache directory disambiguated by `country: "pt"` field, same fuzzy-coverage filter (≥0.6) and per-bullet provenance (`cahier` / `wiki` / `both`). Targets en/fr/es/nl (FR/ES are translation targets, not sources). Skips sub-regiões — they inherit the parent's bullets at the rendering layer (stage 02 already copies the parent's caderno text into each sub-região's `link_to_terroir`).

Smoke-tested manually (emit-todo + import round-trip, `acores`): cache writes with correct country tag, fuzzy-grounding produces `cahier`-provenance bullet with coverage 1.0 on a verbatim quote, all 4 target locales import cleanly. Cache-hit re-run produces 0-item todo (idempotent).

Runs to perform (matches user's existing FR/ES Ollama workflow):
```
.venv/bin/python scripts/02b_fetch_aoc_lexicon.py --lang pt           # one-time, ~44 wines
.venv/bin/python scripts/pt/02d_extract_terroir_facts.py --provider ollama
.venv/bin/python scripts/pt/02e_translate_terroir_facts.py --provider ollama
.venv/bin/python scripts/04_build_maps.py
```

Or via the manual round-trip flow (PT facts → external human translator → import):
```
.venv/bin/python scripts/pt/02d_extract_terroir_facts.py --provider manual --emit-todo /tmp/pt-02d-todo.json
# external worker fills items[].facts[]
.venv/bin/python scripts/pt/02d_extract_terroir_facts.py --provider manual --import /tmp/pt-02d-todo.json --translator-id <id> --translator-kind manual
.venv/bin/python scripts/pt/02e_translate_terroir_facts.py --provider manual --emit-todo /tmp/pt-02e-todo.json
# external worker fills items[].translated_bullets
.venv/bin/python scripts/pt/02e_translate_terroir_facts.py --provider manual --import /tmp/pt-02e-todo.json --translator-id <id> --translator-kind manual
```

Caveat: stage 04 currently merges FR + ES terroir-fact caches; the PT branch in [scripts/04_build_maps.py](scripts/04_build_maps.py) reads the same shared dir (cache files are country-keyed via the `country` field), but verify the rendering surface honours PT records on first full pipeline rerun — track under "COUNTRY_CONFIG refactor" in the Code follow-ups section.

### Wikipedia PT lexicon — ⏳ not yet run

`scripts/02b_fetch_aoc_lexicon.py --lang pt --source raw/pt/cadernos-extracted/` is wired through `LANG_CONFIG` but hasn't been run. Will fetch pt.wikipedia.org pages for 44 PT entries with disambiguator cascade `(vinho)` → `(DOP)` → `(denominação de origem protegida)`. Per-DOP override file analogous to `raw/wikipedia/aocs/manual_overrides.json` can land alongside if any pages need pinning.

### Code follow-ups

- ✅ **PT national-pliego (Cad.Esp.) tabular grape parser** (2026-05-16) — see grape-list polish above. The PRT-tabular dispatch + colour-code stripping + sub-região break shipped in [scripts/pt/02_extract_cadernos.py](scripts/pt/02_extract_cadernos.py).
- ✅ **PT grape extraction residual noise** (2026-05-17) — shipped: extended `_NOISE_SLUGS` (12 literals: section-heading boilerplate + Portuguese months) and `_NOISE_SLUG_RES` (4 new regex patterns: `^pgi-?pt-?a\d+$`, `^b-?prt\d+`, `^pagina-?\d+(-(?:de-)?\d+)?$` covering both `N` and `N/M` page footers, `^de-\d+-de(-[a-z]+)?$` for date strings, `^no?-\d+-\d+$` for EU/Portuguese regulation citations, `^descricao-`, `^nome-do-processo`, Roman-numeral-prefixed section headings) in [scripts/pt/02_extract_cadernos.py](scripts/pt/02_extract_cadernos.py). `_is_noise_slug` now also consults the shared `GRAPE_BLOCKLIST` so cross-country noise (place names `palmela` / `setubal` / `terras-de-lafoes` / `s-mamede`, FR phrase fragments, ES headers) is filtered uniformly. Dropped ~70 noise slugs from the corpus; coverage went from 56% → 100% resolved.
- ❌ **PT principal/accessory role classification — won't fix** (2026-05-18) — investigated and closed out. Hypothesis was that the national IVV regulamento PDFs (Portarias / Decreto-Leis on `dre.pt`) carry a principal/acessória split missing from the documento-único. Full pipeline was built (auto-ref extraction + curator-pinned URLs + parser + stage-04 overlay). Audit of 33 curator-pinned PDFs found **zero** with a structured role split. The PDFs fall into four buckets: amendment Portarias that modify articles without enumerating castas; administrative recognition decrees (e.g. Alenquer's pinned DL 116/1999 is a pure IPR→DOC elevation); wrong documents (one pinned as `vinho-verde` is Portaria 332/2016 about an Évora property reversion); and flat PRT-tabular castas annexes without role markers (Bairrada, Algarve, Beira Interior, Alentejano, Península de Setúbal — at most a `*` footnote for sub-classifications like "Clássico"). The role distinction the user wanted to surface **isn't published** at the PT regulator level for the wines in our corpus. 02f pipeline (`scripts/pt/02f_extract_regulamentos.py`, `scripts/pt/regen_regulamento_overrides_template.py`, `scripts/audit_pt_grape_roles.py`, `scripts/_lib/pt/national_regulamento.py`) + the stage-04 overlay hook have been removed; the PT detail card carries an inline disclaimer about the limitation. The cached PDF set at `raw/pt/national-regulamentos/` is kept locally (gitignored) as a record of the curator effort but isn't consumed anywhere. **Reopen only if a new structured source surfaces** — e.g. consejo-regulador-side per-DOP "castas recomendadas / autorizadas" tables on CVRA / CVR Bairrada / IVDP / CVRVV websites (bespoke scraping, ~5-10 hours per DOP, ~14 DOPs total).
- **PT grape Wikipedia source — pt.wikipedia.org + translate sidecar** — current 02b only queries en/fr/es/nl Wikipedias, but the bulk of obscure Portuguese varieties (~290 unmatched slugs after the 2026-05-17 run) only exist on pt.wikipedia.org. Mirror the stage 02b/styles-translate pattern: add a pt-source fetch path, then translate the resulting extract into the four site locales with the same `--emit-todo`/`--import` round-trip the user already uses for 02c/02e. Cache attribution must record `source_lang=pt`, `source_page_url`, `source_wikipedia_title`, `source_sha`, `translator`, `translator_kind` per the CLAUDE.md narrative-layer rule. UI tooltip renders "Traduit de Wikipédia en portugais · CC BY-SA 4.0" in place of the `(français)` fallback marker.
- **CAOP commune-list IGP fallback** — `_resolve_pt_igp_fallback(...)` mirroring ES's `_resolve_es_igp_fallback`. Walk the area section for "todos os concelhos do distrito de X" / commune lists, union with `PTPolygonIndex.union_concelhos`.
- **Stage 04 `COUNTRY_CONFIG` refactor** — the v1 PT integration adds `elif country == "pt"` branches alongside the existing `== "es"` ones (~6 spots: line 869, 1148, 1200, 1565, 1724, 1865). Folding to a dispatch table when country #4 lands would be cleaner; deferred to keep v1 risk-bounded.
- **02b_fetch_aoc_lexicon `--lang pt` smoke test** — confirm the disambiguator cascade resolves the common cases (Vinho Verde, Douro, Madeira, Dão, Alentejo).

---

## Italy

### Documento unico coverage — ✅ initial drop landed 2026-05-19

531 IT wines (412 DOP + 119 IGP) from eAmbrosia. After stage 01 +
stage 01b WAF bootstrap: 129 wines have full extraction. Of those,
408 wines (76 %) have a Bétard 2022 Figshare polygon and render on the
map — including the 314 DOPs whose documento unico isn't accessible
(stub records still get a figshare polygon via file_number lookup).

| Bucket | Count | Notes |
|---|---:|---|
| Extracted (full record) | 129 | 115 DOPs + 14 IGPs with documento unico HTML |
| Stub: no-publication | 392 | eAmbrosia has no `publications[].uri` |
| Stub: not-single-document | 9 | EUR-Lex URL leads to a non-documento-unico page |
| Stub: no-documento-unico-anchor | 1 | `ortrugo-dei-colli-piacentini` (parser miss) |

### MASAF disciplinare fallback for no-publication DOPs — ✅ landed 2026-05-19

Stage 02f-MASAF ([scripts/it/02f_extract_masaf.py](scripts/it/02f_extract_masaf.py))
augments IT stub records by parsing the consolidated disciplinare PDFs
that MASAF (Ministero dell'agricoltura) publishes as 4 7-Zip archives
under [IDPagina/4625](https://www.masaf.gov.it/flex/cm/pages/ServeBLOB.php/L/IT/IDPagina/4625):

| Bundle | Coverage |
|---|---:|
| Disciplinari DOP (A-D) | 154 PDFs |
| Disciplinari DOP (E-N) | 113 PDFs |
| Disciplinari DOP (O-Z) | 143 PDFs |
| Disciplinari IGP / IGT | 111 PDFs |

Stage 00 downloads the bundles (~100 MB total, cache-keyed by sha256).
Stage 02f indexes each bundle's PDFs, matches eAmbrosia wines to PDFs
(exact > substring > rapidfuzz ≥ 90 on alt-name slugs from "X o Y o Z"
splits — 521 / 531 wines = 98 % auto-matched), extracts the PDF
on-demand from the archive, runs `pdftotext -layout`, and parses
articles 1 (summary), 2 (grapes via `match_variety` + vitigno-regex
scan), 3 (geo area), 9 (terroir link). Sidecars land under
[raw/it/masaf-disciplinari-extracted/](raw/it/masaf-disciplinari-extracted/);
stage 04's `augment_it_records_with_masaf()` merges them into stubs
in-memory (provenance in `record["masaf"]`, surfaced by `_sources_for`
as `masaf_*` fields for panel attribution).

Sweep result (2026-05-19):

| Bucket | Count |
|---|---:|
| Sidecar written | 387 |
| Skip: not-a-stub (already doc-unico extracted) | 129 |
| Skip: no-bundle-match (curator override needed) | 9 |
| No "Articolo N" anchors in PDF | 6 |

The 6 no-anchors slugs (`colli-trevigiani`, `conselvano`,
`gambellara`, `marca-trevigiana`, `veneto`, `veneto-orientale`)
all live in the IGT bundle and use a non-standard DM template
(no "Articolo N" headers — likely older Decreto Ministeriale or
RV-style formatting). Curator follow-up: extend the article-anchor
regex or pin via `raw/it/masaf-disciplinari/manual_overrides.json`.

🟢 **Disciplinare URL hunt — 15 wines.** The 6 no-anchor slugs above
plus the 9 `not-single-document` no-bundle-match wines (`colli-aprutini`,
`colli-del-sangro`, `colline-frentane`, `colline-pescaresi`,
`colline-teatine`, `del-vastese`, `salemi`, `terre-di-chieti`,
`valtenesi`) have no usable source document. Browser-extension research
prompt at [tmp/it-masaf-disciplinare-research-prompt.md](tmp/it-masaf-disciplinare-research-prompt.md):
find a public disciplinare PDF for each and merge into
`raw/it/masaf-disciplinari/manual_overrides.json`, then re-run 02f → 04.

### MASAF grape-extraction fix — ✅ landed 2026-05-20

The earlier note here called the 108 `grapes=0` MASAF records a pure
vocab gap. A 2026-05-20 audit found that was a mis-diagnosis: most
were a **parser** defect — the disciplinare's Article-2 text never
reached `match_variety` as a clean candidate. Fixed in
[scripts/_lib/it/masaf.py](scripts/_lib/it/masaf.py): `vitigno NAME:`
colon terminator, dash-bullet + parenthetical-gloss handling,
connective-aware percentage-tail strip, word-boundary drop-list
(was discarding "Corvinone" on the `vino` substring), smart-quote /
line-break-hyphen / one-variety-per-line layout handling, leading
wine-type-word strip, and false-positive guards (self-name two-pass,
fuzzy floor ≥ 90 + min length 7).

The genuine vocab gap was real too but smaller: ~73 registro-listed
Italian varieties (Barbera, Corvina, Teroldego, Negroamaro, Frappato,
Schiava, …) were absent from the VIVC-seeded vocabulary because the
broken extraction never seeded them. Added to `GRAPE_ALIAS` +
`DEFAULT_COLOUR` in [scripts/_lib/grape_lexicon.py](scripts/_lib/grape_lexicon.py).

Result: MASAF records with grapes 280 → 354 of 387. Remaining 33
`grapes=0`: 4 with an empty Article 2, ~24 genuinely-generic IGTs
("da uno o più vitigni idonei alla coltivazione" — 0 is correct),
~5 stubborn layout misses (`erbaluce-di-caluso`,
`colli-euganei-fior-d-arancio`, `primitivo-di-manduria-dolce-naturale`,
`quistello`, `rotae`).

Curator follow-up: the 73 added varieties' Wikipedia grape-lexicon
entries are handled — `grape_corpus.py` now walks the MASAF sidecars,
so `02b_fetch_grape_lexicon.py` + `02b_translate_grapes.py` cover them
(2026-05-21). Two bugs were fixed in passing: `wiki.py` `GRAPE_KEYWORDS`
had no `it` entry (every it.wikipedia page was rejected
`not_grape_topic`); `02b_translate_grapes.py` `LOCALE_NAME` had no `it`
(every it-sourced translation raised `KeyError: 'it'`).

The unknowns queue at
[raw/it/extraction-unknowns-masaf.json](raw/it/extraction-unknowns-masaf.json)
still lists the residual unmatched candidates.

### IT new-grape VIVC pins — ⏳ ready to apply

Browser-research (2026-05-21) resolved VIVC variety numbers for the
new IT varieties whose slug-derived Wikipedia search missed (article
filed under a synonym, or no article). Apply via
`raw/vivc/slug_overrides.json` after extending stage 02g to walk
`raw/it/masaf-disciplinari-extracted/` (mirror the `grape_corpus.py`
`_SOURCES` change — 02g uses its own walk, `IT_EXTRACTED` at
[scripts/02g_fetch_vivc.py](scripts/02g_fetch_vivc.py)).

| slug | VIVC # | note |
|---|---|---|
| monica | 7928 | prime MONICA NERA |
| nuragus | 8623 | |
| schiava-grossa | 10823 | en/es wiki = "Trollinger", fr = "Frankenthal" |
| schiava-grigia | 10822 | VIVC colour NOIR despite "grigia" trade name |
| uva-rara | 12830 | distinct variety; "Uva Rara" is also a Vespolina synonym |
| pelaverga-piccolo | 16938 | |
| nero-di-troia | 12819 | prime UVA DI TROIA — it/en wiki article "Uva di Troia" |
| cesanese-comune | 2398 | |
| cesanese-di-affile | 2399 | |
| gamba-rossa | 4385 | en wiki = "Gamba di Pernice" |
| invernenga | 5536 | no Wikipedia article in any of en/fr/es/nl/it |
| semidano | 11479 | no Wikipedia article |
| groppello-gentile | 5078 | |
| oseleta | 16537 | |
| rossignola | 10219 | |
| moscatello-selvatico | 8043 | no Wikipedia article |
| francavilla | 4217 | prime ZLATARICA VRGORSKA (Dalmatian) — pill canonical-bracket will read "Francavilla (Zlatarica Vrgorska)" |

Curator decisions:
- **bianchello** — NOT pinned. VIVC folds it into Trebbiano Toscano
  (#12628), but the Bianchello del Metauro disciplinare names it as
  its own variety and it.wiki treats "Biancame" as distinct. Keep the
  standalone `bianchello` slug — regulator authority over VIVC for
  identity; VIVC is a citation layer only.
- bare **cesanese** / bare **groppello** — left unpinned (genuinely
  ambiguous family names); only the sub-variety slugs are pinned.

Re-run after pinning: `02g_fetch_vivc.py` → `02b_fetch_grape_lexicon.py`
→ `02b_translate_grapes.py` → `04_build_maps.py`. Surfaces VIVC# +
canonical-bracket on the pills, and the synonym-aware Wikipedia search
recovers the articles filed under a synonym (nero-di-troia,
schiava-grossa, gamba-rossa). The no-Wikipedia varieties (invernenga,
semidano, moscatello-selvatico, schiava-grigia, francavilla,
pelaverga-piccolo) gain only the VIVC# citation — no tooltip text
exists to fetch.

### `ortrugo-dei-colli-piacentini` — ❌ no DOCUMENTO UNICO anchor

One wine (PDO-IT-A0350) whose EUR-Lex HTML doesn't have the standard
`<p class="ti-grseq-1">DOCUMENTO UNICO</p>` anchor — likely an older
template. Investigate the raw HTML at
`raw/it/oj-pages/ortrugo-dei-colli-piacentini.html` and either extend
the anchor regex or pin a working override URL.

### Italian-name VIVC slug overrides — ✅ done (2026-05-19)

The original 5 cases (Sangiovese / Nebbiolo / Vermentino / Trebbiano
cluster / Grechetto) were all already resolving correctly: the trade-
name synonyms (Brunello, Prugnolo Gentile, Morellino, Chiavennasca,
Spanna, Pigato, Favorita) don't appear in the IT disciplinari's
section-7 grape lists — the regulator uses the canonical name there.

But the spot-check uncovered a much bigger over-fold problem in
`scripts/_lib/grape_entity.py`: the vocabulary loader takes every
VIVC synonym verbatim, and several umbrella VIVC entries (NIELLUCCIO,
TREBBIANO TOSCANO, MUSCAT D'ALEXANDRIE) list dozens of distinct
Italian regional varieties as historical synonyms. Result: across
532 IT records, the `sangiovese` slug pulled in 17 Lambrusco /
Lacrima / Corinto Nero mentions, the `ugni-blanc` slug pulled in
21 Trebbiano spp. / Coda di Volpe / Falanghina / Passerina /
Biancame / Montonico / Rossola Nera entries, `pinot-noir` pulled
Pinot Bianco/Grigio + Pignola/Pignolo, `riesling` folded the
unrelated Welschriesling, `glera` pulled Garganega, etc. Also
`cabernet` was a bare-slug parser artefact swallowing both Franc
and Sauvignon.

Fixes shipped:

1. **`scripts/_lib/grape_entity.py:match_variety`** — patched the
   hyphen-split path to strip the trailing colour-letter (`B`/`N`/
   `G`/`Rs`) from each piece before vocab lookup. Without this, the
   IT format `"Pinot bianco B. - Pinot"` skipped the head piece (no
   match for the colour-suffixed key) and fell through to the
   trade-name synonym `"Pinot"`, which mapped to `pinot-noir`.
2. **`scripts/02g_fetch_vivc.py:slug_to_query`** — patched to strip
   trailing colour-letter markers and dash-suffix synonyms when
   building the VIVC search query. IT records store `"Lacrima N."`
   as the display name; VIVC's `cultivarname-search` rejected
   colour-suffixed queries and returned 0 candidates.
3. **`scripts/_lib/grape_lexicon.py:GRAPE_ALIAS`** — added ~155 IT
   variety pins minting (or routing) distinct slugs for: Lambrusco
   family (×6 cultivars), Trebbiano cluster (×6 regional siblings),
   Pinot Bianco/Grigio/Nero, Welschriesling vs. Riesling Renano,
   Moscato bianco/giallo/scanzo, Garganega, Pignoletto, Friulano,
   Refosco, Marzemino, Ciliegiolo, all the Malvasias, plus 40+
   minor Italian varieties. DEFAULT_COLOUR extended in parallel.
4. **DNA-confirmed cross-canonical folds**: `tocai-rosso → grenache`,
   `calabrese → nero-davola`, `cococciola` stays its own slug
   distinct from `bombino-bianco → pagadebiti`, etc.
5. **`raw/vivc/slug_overrides.json`** — added 39 curator pins for
   the new slugs (Albana, Avana, Biancame, Bonarda Piemontese,
   Ciliegiolo, Cococciola, Corinto Nero, Falanghina Flegrea,
   Fortana Nera, Friulano, Garganega, Greco Bianco di Tufo, Greco
   Nero, Grillo, Lacrima, Malvasia spp., Manzoni-Bianco,
   Minutolo, Montù, Negrara Trentina, Negretto, Neretta Cuneese,
   Passerina, Piedirosso, Pignola Valtellinese, Pignolo, Rossola
   Nera, Spergola, Termarina, Tintilia del Molise, Trebbiano
   Giallo, Verdea, Vernaccia Nera, Welschriesling, Moscato Rosa,
   Pugnitello), plus a fix for the pre-existing miss-pin
   `gruner-veltliner` (was 4878 GOLDEN GRAIN → now 12930
   GRUENER VELTLINER).

Final 02g manifest: `{exact-cultivar: 579, override: 341, ambiguous: 8}`
across 928 distinct slugs (was 815 before the IT split). The 8
remaining ambiguous entries are all ES/PT cases pre-existing
before this task.

IT corpus distinct slugs: 160 (was ~80). Stage 02 still surfaces
~441 unknown variety candidates per
`raw/it/extraction-unknowns.json` — those are mostly text fragments
and unmatched obscure varieties, separate follow-up.

### IT regione fallback — ⏳ low priority

353 of 408 IT polygons render with `region="Italia"` because their
records are stubs (no documento unico → no section-6 text to scan
for regione name). Stage 02d-MASAF would populate this, or a curated
`scripts/_lib/it/regione_by_file_number.json` keyed on `PDO-IT-A*`
could fill in the well-known DOPs (Barolo→Piemonte, Brunello→Toscana,
Lambrusco→Emilia-Romagna, …) immediately.

🟢 Browser-extension research prompt at [tmp/it-regione-research-prompt.md](tmp/it-regione-research-prompt.md):
159 DOPs with an empty `regione` field listed by file number — research
each to its administrative regione and emit
`scripts/_lib/it/regione_by_file_number.json`.

### IT geometry — regional-geoportal zone harvest 🟢 in progress

Strategy (decided 2026-05-22): use official regional production-zone
polygons where a region publishes a licence-clear GIS layer; Bétard
2022 is the fallback. Registry + per-region status live in
[scripts/_lib/it/zone_sources.py](scripts/_lib/it/zone_sources.py);
stage 00 fetches the `active` ones, stage 04 resolves `geoportal-zone`
in front of `figshare-pdo`.

Region tracker:

| Region | Status | Licence | Note |
|---|---|---|---|
| Piemonte | ✅ active | CC-BY 4.0 | 64 zones; 57 wines matched |
| Veneto | ✅ active | IODL 2.0 / CC-BY | WFS, DOC+DOCG+IGT; 41 wines matched |
| Toscana | ✅ active | CC-BY 4.0 (GEOscopio; download page links CC-BY) | direct zip, `zo_vin_nom_zon` layer; 55 wines |
| Lazio | ✅ active | CC-BY 4.0 | GeoServer WFS, DOC+DOCG+IGT; 29 wines |
| Lombardia | ✅ active | CC-BY 4.0 | ArcGIS MapServer, DOC+DOCG+IGT; 34 wines |
| Umbria | ⏳ todo | CC-BY 4.0 | needs a bespoke fetch — ~23 separate per-appellation `.7z` shapefiles via the dati.regione.umbria.it CKAN API |
| Puglia | ⏳ todo | IODL 2.0 | endpoint not reachable (SIT Puglia WFS/ArcGIS hosts 404 / login-gated) — needs the live WFS layer name |

**5 of 7 regions harvested → 218 IT wines on official zone polygons**
(`geoportal-zone`); the rest fall back to Bétard. Umbria + Puglia are
real to-dos, not skips — see the per-region notes and
[scripts/_lib/it/zone_sources.py](scripts/_lib/it/zone_sources.py).
| Abruzzo | ❌ fallback | custom, unconfirmed | portal SSL cert expired; stays on Bétard |
| Campania | ❌ fallback | unconfirmed | dataset page 404s; stays on Bétard |
| FVG, Sicilia, Sardegna, Emilia-R., Marche, Liguria, Basilicata, Calabria, Molise, Valle d'Aosta, Trento | ❌ fallback | — | no open zone layer found in the 2026-05-22 audit; stay on Bétard |

Wines in fallback regions keep Bétard's whole-municipality polygon
(approximate, may overlap). 119 IGPs not in Bétard remain
polygon-less in those regions.

### Sottozone detection — ⏳ low coverage

0 sottozone detected so far. The explicit `Sottozona NAME:` pattern
and the preamble-list pattern in
[scripts/_lib/it/sottozona.py](scripts/_lib/it/sottozona.py) match
nothing across the 129 extracted records, because Italian
documenti unici typically embed sottozone as section-1 wine type
qualifiers rather than as explicit enumerations. Audit the
section-1 text of known sottozona-bearing wines (Chianti parent,
Valpolicella, Soave, Bardolino) to derive a new pattern.

### Consorzio / DO-organisation URLs — 🟡 344/531 merged (2026-05-21)

Research run (`research-gaps` skill, 17 web-research agents) resolved the
official consorzio di tutela / DO-organisation website per IT appellation,
giving the map cards FR/ES parity. 344 of 531 merged into
[scripts/_lib/appellation_urls.json](scripts/_lib/appellation_urls.json)
`by_slug` (117 of 131 eAmbrosia-named consorzi + 60 of 224 wines eAmbrosia
left consorzio-less). Findings:
[tmp/it-consorzio-urls-research-results.md](tmp/it-consorzio-urls-research-results.md);
no-link list: [tmp/it-consorzio-no-link.json](tmp/it-consorzio-no-link.json).

🟡 Re-check periodically — consorzio exists but runs no public website
(becomes a card link once a site appears): Amelia, Valdinoto (Avola /
Eloro / Noto / Siracusa), vini di Cagliari (Cagliari / Girò di Cagliari /
Nasco di Cagliari / Nuragus di Cagliari), Campidano di Terralba, Carignano
del Sulcis, Colli di Luni / Cinque Terre / Colline di Levanto / Liguria di
Levante, Cori, Marino, Monica di Sardegna, Nardò, Pomino, Tintilia del
Molise, Valdadige Terradeiforti, Vernaccia di Oristano; plus nameless-wine
cases — Est! Est!! Est!!! di Montefiascone, Cesanese di Olevano Romano,
Colli Lanuvini, Contea di Sclafani, Ortona, Penisola Sorrentina, Terratico
di Bibbona, Terre Siciliane, Matera, Leverano, Lizzano, San Severo,
Moscato di Trani, Cannonau di Sardegna, Vermentino di Sardegna, Mandrolisai.

🟡 `montecarlo` — Consorzio Vini DOC Montecarlo (Lucca) page at
http://www.promontecarlo.it/consorzio_vini_doc.html returned HTTP 403 to
the research agent; re-fetch from a browser to confirm and add.

❌ ~150 IT appellations have genuinely no consorzio di tutela (small IGTs,
older southern / island DOCs, region-wide umbrella IGTs) — permanent NONE,
not actionable. Full enumerated list in `tmp/it-consorzio-no-link.json` so
the lookup is not retried blindly.

## Austria

Country #5 (added 2026-05-21). 32 wine GIs (29 DOP + 3 IGP), all with
an OJ-C publication URL — extraction is complete out of the box.

### Einziges Dokument — ✅ 30 / 32 extracted

❌ `neusiedlersee-hugelland` (PDO-AT-A0220) and `sudburgenland`
(PDO-AT-A0227) — both content-stubs. eAmbrosia still lists them
`registered`, but their only OJ-C publication is a *Löschungsantrag*
(cancellation request) — these are superseded names from the Austrian
DAC reform (Neusiedlersee-Hügelland → Leithaberg + Rosalia;
Südburgenland → Eisenberg). No single document exists to extract. A
curator could pin an alternate pliego URL in
`raw/at/oj-pages/manual_overrides.json` if one surfaces, or these may
genuinely be in delisting. Low priority.

### Geometry — ✅ 30 / 32 mapped, commune-precise

AT geometry is resolved commune-precise from each Einziges Dokument's
Bezirk/Gemeinde description (`scripts/_lib/at/gemeinde.py`, GISCO LAU +
Statistik Austria registry) — the 16 proper DACs are verified disjoint
(the Bétard whole-municipality overlap is gone). The 2 *Löschungsantrag*
content-stubs (Neusiedlersee-Hügelland, Südburgenland) have no Einziges
Dokument → no geo-area → `stub-no-geometry`; they'd be unblocked if a
curator pins a pliego URL (see above).

⏳ Two known precision gaps, both minor, both documented in
`scripts/_lib/at/gemeinde.py`:
- `leithaberg` — its doc adds 4 named *Rieden* inside the Gemeinde
  Neusiedl am See; Rieden are sub-commune and can't resolve at GISCO
  Gemeinde precision, so they're dropped (slight under-coverage rather
  than swallowing the whole commune, which would overlap Neusiedlersee).
- `carnuntum` — its doc adds the *Gerichtsbezirk* Schwechat (a judicial
  district); approximated by the Gemeinde Schwechat.
- New municipal mergers / renames surface as a Gemeinde the parser
  skips silently — extend `_GEMEINDE_ALIAS` when an appellation's
  commune count looks short.

### AOC Wikipedia hints — ⏳ 5 / 32 resolved

`scripts/02b_fetch_aoc_lexicon.py --lang de --source raw/at/dokumente-extracted`
resolves only 5 of 32 — de.wikipedia's Austrian wine-region articles
are general region pages (valley / Bundesland) whose REST summary
doesn't trip the wine-keyword `looks_like_aoc` filter (`not_aoc_topic`).
This is a salience hint for stage 02d only — terroir facts still
extract from the Einziges Dokument regardless. Curator pass: pin the
correct de.wikipedia titles via the AOC-override mechanism (e.g.
`Weinbau in der Wachau`, `Weinbaugebiet Kamptal`) so the dual-source
grounding gets a `wiki` arm. Low priority.

### Summary translation (02c) — ⏳ 1 residual record

29 / 30 AT records carry stage-02d terroir facts, so the fallback
summary is needed for just **1** record — `oberosterreich` (its
section-8 text is < 400 chars, below the 02d extraction threshold).
Per the manual-round-trip workflow, run
`scripts/02c_translate_summaries.py --source-lang de --emit-todo
todo.json`, have the FR→EN/FR/ES/NL strings translated externally,
then `--import todo.json --translator-id <id>`. Until then
`oberosterreich` shows its German summary on the localized pages.

### Grape vocabulary — ✅ seeded

Austrian-only varieties folded into `GRAPE_ALIAS` / `DEFAULT_COLOUR`
in [scripts/_lib/grape_lexicon.py](scripts/_lib/grape_lexicon.py):
Zweigelt, Sankt Laurent, Neuburger, Scheurebe, Blauer Wildbacher,
Bouvier, Goldburger, Rathay, Blütenmuskateller (+ Grauburgunder →
Pinot Gris). Re-run `scripts/at/02_extract_pliegos.py` →
`scripts/02g_fetch_vivc.py` after any edit. One residual junk token
(`"4"`) in `raw/at/extraction-unknowns.json` — ignorable.

### Appellation organisation URLs — ✅ 32 / 32 curated (2026-05-22)

All 32 AT wine GIs given an org link in
[scripts/_lib/appellation_urls.json](scripts/_lib/appellation_urls.json)
`by_slug` via `/research-gaps` (prompt + results kept at
`tmp/at-weinkomitee-url-research-{prompt,results}.md`). Two caveats:

❌ `traisental` → `Verein Traisentaler Wein` is **HTTP-only** —
`traisentalwein.at` resolves but serves no working TLS (HTTPS handshake
fails), so the entry uses `http://`. Switch to `https://` if the site
adds a certificate.

❌ `neusiedlersee-hugelland` has no organisation site of its own
(superseded name, area now Leithaberg DAC); the entry falls back to
`Wein Burgenland`, the Bundesland board. Re-point to a dedicated body
only if the name is revived.

ÖWM (`Austrian Wine`, `austrianwine.com`) covers the 5 generic-region
slugs with no Regionales Weinkomitee — `bergland`, `weinland`,
`salzburg`, `vorarlberg`, `oberosterreich`.

## Slovenia

Country #6 (added 2026-05-22). 17 wine GIs (14 DOP + 3 IGP). Structurally
an Austria clone, but only 1 wine has a fetchable EU single document.

### ENOTNI DOKUMENT — ⏳ 1 / 17 extracted

✅ `cvicek` (PDO-SI-A1561) — full extract from its EUR-Lex ENOTNI
DOKUMENT (OJ C/2026/256), 17 grape varieties.

❌ 16 content-stubs (`no-publication`). 13 grandfathered DOPs + the 3
region IGPs have no public single-document URL in eAmbrosia — only a
non-fetchable `Ares(...)` summary-sheet. The canonical source is the
Slovenian national specification (*specifikacija proizvoda*, MKGP).
**Phase 2**: research a public, licence-clear URL pattern for the MKGP
specifications (fits `/research-gaps`), fill
`raw/si/oj-pages/manual_overrides.json` via
`scripts/si/regen_manual_overrides_template.py`, and add a national-spec
parser branch to stage 02 (mirrors ES MAPA / IT MASAF). This also
unlocks the podokoliš (sub-district) sub-denominations.

**2026-05-23** — active EUR-Lex search via `/research-gaps` (prompt +
results at
[tmp/si-enotni-dokument-research-prompt.md](tmp/si-enotni-dokument-research-prompt.md)
and [-results.md](tmp/si-enotni-dokument-research-results.md)) returned
**0 / 16 FOUND**: every grandfathered name has only an
`Ares(2011|2013)` summary-sheet id, no consolidated single-document
publication on EUR-Lex. Closest false hits ruled out: *Belokranjska
pogača* (food PDO ≠ Bela krajina wine), *Kraška panceta* (≠ Kras wine),
*Nanoški sir* (≠ Vipavska dolina); Reg. (EU) 2017/1353 for Teran is the
SI/HR labelling regulation, not a single document. **Re-check in 3–6
months for `belokranjec` (PDO-SI-A1576) + `metliska-crnina`
(PDO-SI-A1579)** — both had a national *standardna sprememba* approved
2026-Q1 (MKGP consultation 7 Jan – 9 Feb 2026; eAmbrosia
`amendmentsInProgressFlag: true` on A1579 corroborates). These are the
most plausible to land an OJ-C ENOTNI-DOKUMENT publication mirroring
Cviček's path (OJ C/2026/256, 16.1.2026). MKGP-national Phase 2 remains
the systematic unlock for the other 14.

### Geometry — ✅ 17 / 17 mapped

14 DOPs resolve `figshare-pdo` (Bétard 2022, even as content-stubs); the
3 IGPs resolve `region-pdo-union` (union of the member-region DOPs).
Nothing in `stub-no-geometry`.

### Sub-denominations (podokoliši) — ⏳ Phase 2

v1 ships a flat 17-wine corpus. The podokoliš (sub-district) layer —
the FR-DGC / ES-subzona analogue — is recoverable from the MKGP national
specifications and lands with the Phase-2 national-spec parser.

### Grape vocabulary — ✅ seeded

Slovenian varieties folded into `GRAPE_ALIAS` / `DEFAULT_COLOUR` in
[scripts/_lib/grape_lexicon.py](scripts/_lib/grape_lexicon.py): Žametovka,
Kraljevina, Ranfol, Rumeni plavec (+ `sentlovrenka` → Sankt Laurent,
`refošk` / `teran` → Refosco dal Peduncolo Rosso, `chardonay` typo →
Chardonnay). `raw/si/extraction-unknowns.json` is empty after seeding.

### Teran cross-border note — ✅ done

`teran` carries a curated, source-cited note in
[scripts/_lib/appellation_notes.json](scripts/_lib/appellation_notes.json)
on the SI/HR labelling distinction (Reg. (EU) 2017/1353 + GC Case
T-626/17). When Croatia (#7) is added, add the symmetric
`hrvatska-istra` entry and do **not** mint a duplicate `teran`
appellation.

## Style taxonomy follow-ups

- **Sweet/oxidative cross-cut** — `generoso` (sherry-family) sits under `oxidative` because most sherries are dry; PX cream sherries and dulces are nominally oxidative *and* sweet. Currently they only emit `oxidative + generoso + (sub-tag)`; the `sweet` bucket is *not* added. Decide whether to surface dual-tagging (record carries both `oxidative` and `sweet`) when the pliego describes a PX / cream / sweet-oloroso style. Currently affects ~5 sherry pliegos. Defer to v2.
- **Grape display — surface the more common term** — chip labels currently render the verbatim pliego name (e.g. "MAZUELA", "VIURA"). For cross-border discoverability, surface the international/canonical synonym ("Carignan", "Macabeo") as a tooltip or secondary chip when the canonical slug differs from the verbatim local name. Slug already canonicalises (`carignan`, `macabeu`) so filtering works; this is purely a display enhancement. Defer to v2.
- ✅ **ES grape Wikipedia tooltips** (shipped earlier) — `collect_grape_slugs` in [scripts/02b_fetch_grape_lexicon.py:76-95](scripts/02b_fetch_grape_lexicon.py#L76-L95) iterates both FR cahiers and ES pliegos. ES-only Iberian varieties flow through. Curator pass for non-canonical `es.wikipedia.org` titles still open (`(uva)` disambiguator etc.).
- **ES grape alias gaps** — [scripts/audit_es_grape_aliases.py](scripts/audit_es_grape_aliases.py) lists tokens that don't resolve through `GRAPE_ALIAS` / `DEFAULT_COLOUR`. ~250 distinct tokens after current seeding; biggest residual classes are Canary Islands varieties (Bermejuela, Marmajuelo, Vijariego, Listán Negro, …) and Galician varieties (Brancellao, Sousón, Loureira, Caíño…). Most are genuine ES-only varieties — register their canonical slug in `DEFAULT_COLOUR` rather than aliasing.
- **Parenthesised synonyms in ES variety lists** — pliegos like 3-riberas write "Albillo Mayor (Turruntés)" where the parenthetical is the regional synonym. Parser currently keeps the parenthesis in the name → 3-token slug. Extract the parenthesised tail as a synonym (route through `GRAPE_ALIAS`) and slug from the primary token only.

## VIVC grape resolution — open queue (2026-05-22)

Curator action: for each row below, open the VIVC search URL, pick the variety number that best matches the slug's actual identity, and add `{"vivc_id": <id>}` to [raw/vivc/slug_overrides.json](raw/vivc/slug_overrides.json). Then `./.venv/bin/python scripts/02g_fetch_vivc.py` re-runs the passport fetch for the pinned slugs.

Latest `scripts/02g_fetch_vivc.py` run (2026-05-22, after the AT corpus
landed): `buckets = {exact-cultivar: 625, override: 363, ambiguous: 11,
miss: 5}`.

**11 ambiguous slugs — curator queue at
[raw/vivc/slug_overrides.example.json](raw/vivc/slug_overrides.example.json)**
(`[02g] 11 ambiguous slug(s)`). Each has multiple candidate VIVC
entries; copy the file to `raw/vivc/slug_overrides.json` and pin the
right `vivc_id`:

| slug | query | candidate VIVC ids |
|---|---|---|
| `sankt-laurent` | St. Laurent | 10470, 8252 — **AT** (Austrian red Sankt Laurent) |
| `groppello` | Groppello | 16969, 5076, 6698, … (23) |
| `inzolia` | Insolia | 122, 492, 5533 |
| `loureiro-tinto` | loureiro tinto | 17346, 7623 |
| `maresco` | Maresco | 1660, 4019 |
| `moscatel-negra` | moscatel negra | 25847, 24609 |
| `moscatel-negro` | moscatel negro | 6860, 40043, 23166, … (12) |
| `schiava` | Schiava | 10821–10826, 22368, … (19) |
| `siria` | doña blanca | 2742, 17676 |
| `tempranillo-blanco` | tempranillo blanco | 25057, 10690 |
| `verdejo-negro` | verdejo negro | 15678, 12668, 9694 |

**5 misses** (no VIVC candidate at all): `blutenmuskateller` (**AT** —
Blütenmuskateller, an Austrian Muscat selection that VIVC may not
carry under that name), plus pre-existing `bianco-di-alessano`,
`incrocio-manzoni`, `nerello-cappuccio`, `siria`-class IT/ES varieties.
JKI publishes no data licence, so unresolved slugs simply ship without
a VIVC bracket — not blocking.

