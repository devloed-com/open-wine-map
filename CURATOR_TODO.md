# Curator todo

Actionable manual lookups across the corpus. One section per country. Reconcile against [scripts/audit_coverage.py](scripts/audit_coverage.py) (FR) and [scripts/audit_es_coverage.py](scripts/audit_es_coverage.py) (ES) after each run.

Legend: ✅ done · 🟡 URL queued, awaiting pipeline rerun · 🟢 in progress · ⏳ blocked on code · ❌ open

Last reconciled: 2026-08-29 — full pass history in [docs/reconciliation-log.md](docs/reconciliation-log.md).

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

### Terroir-fact source contamination — 3 parents bound to the wrong BO Agri PDF — ✅ resolved via the register (2026-09-11)

Found by the 1,000-bullet terroir-fact review (plan: `docs/plan-terroir-facts-quality.md`, W2b) — **resolved 2026-09-11** without a BO Agri lookup: the eAmbrosia register serves each appellation's own cahier ("cdc Pierrevert BO.pdf", "l-Etoile CDC homologue.pdf", "Grands-Echezeaux CDC publication BO.pdf"). The three are pinned `prefer_cahier: true` in the checked-in `scripts/_lib/fr/register_overrides.json`; stage 01 binds the register attachment ahead of BO Agri for them, stage 02 re-extracted them (liens now name the appellation), and the audit's FR name guard (`audit_terroir_facts.py`) catches any recurrence.

| id | slug | was bound to | now |
|---:|---|---|---|
| 290 | `pierrevert` | Saint-Pourçain's cahier | register attachment 2952, `eambrosia-register` |
| 187 | `l-etoile` | Bourgogne Passe-tout-grains' cahier | register attachment 2083, `eambrosia-register` |
| 184 | `grands-echezeaux` | Bourgogne Passe-tout-grains' cahier | register attachment 4206, `eambrosia-register` |


### Terroir-fact source contamination — Bourgogne Passe-tout-grains + a shared PDF — ✅ resolved (2026-09-13)

Found by the full-corpus review (`docs/review-terroir-facts-2026-09-12.md`, R4).

| id | slug | problem | resolution |
|---:|---|---|---|
| 144 | `bourgogne-passe-tout-grains` | bound to PDF `49acff22…` (BO Agri `e89b7ce3…`) whose extracted lien is the **AOC Beaujolais** cahier | `prefer_cahier` pin in `scripts/_lib/fr/register_overrides.json` → register attachment `CDC_Bourgogne_Passe-tout-grains.pdf` (`3ace5ac0…`); re-extracted: lien names Passe-tout-grains 6×, grapes gamay + pinot noir (+ chardonnay / pinot blanc / pinot gris accessory), styles red + rosé; 02d re-run in the R1 batch |
| 870 / 980 | `hautes-alpes` / `haute-vienne` | both manifest entries carry BO Agri `22caf075…` / PDF `1106c71b…` | **not a misattribution**: the PDF is the arrêté of 2 Nov 2011 bundling ~20 IGP cahiers (Agenais, Comté Tolosan, Coteaux de Glanes, …); stage 02's cross-bundle rescue carved each record's own cahier (Hautes-Alpes 3× / Haute-Vienne 16× own name, 0× the other), and the shared `boagri_url` is the document that contains both. No change. |

The audit's name guard now requires the whole folded name or the stem of its longest token (≥ 6 letters) — "tout" / "grains" no longer pass a Beaujolais cahier — and stays strict for FR (`name_guard`), report-only for the other 20 countries (`name_guard_other`: CZ region-wide texts never name the wine by design).

### SIQO referentiel — 2 wines missing (eAmbrosia has them, INAO doesn't) — ✅ both RETIRED (2026-08-26)

✅ Web-research pass confirmed both are intentionally absent — no pinning needed;
the eAmbrosia `registered` rows are stale-register artifacts (Austrian-PDO precedent).
Full evidence in [VERIFICATION.md](VERIFICATION.md) (2026-05-17 entry, finding #4).

| eAmbrosia file_number | Name | Verdict |
|---|---|---|
| PDO-FR-A0257 | Cabernet de Saumur | RETIRED-MERGED into AOC Saumur (rosé) — Arrêté du 19 juillet 2016, art. 2 abrogates Décret 2011-1360 |
| PDO-FR-A0271 | Côtes de Blaye | RETIRED — not claimed since 2015, off INAO's list; EU cancellation PDO-FR-A0271-CANCEL filed 13/01/2026 ("Applied") |

🟡 Loose end: confirm the OJ cancellation notice (likely C/2026/2994) in a
browser once the EU procedure terminates — purely for the provenance note.

### Geometry — Comté Tolosan cluster — ✅ resolved

✅ (verified 2026-08-26) id=861 + 6 DGCs are back on the map: the parent resolves `geom_source=aires-csv`, the 6 DGCs (Bigorre, Cantal, Coteaux et Terrasses de Montauban, Haute-Garonne, Pyrénées-Atlantiques, Tarn-et-Garonne) resolve `parent-appellation`. All 7 present in the startup data bundle.

### Wikipedia AOC pages — 99 missing/error parents

✅ Stage 02b override-priority read shipped 2026-05-14 in [scripts/02b_fetch_aoc_lexicon.py](scripts/02b_fetch_aoc_lexicon.py). Override file `raw/wikipedia/aoc_overrides.json` is now consumed for both `fr` and `es`. Re-run with `--refresh` to invalidate previously-cached cascade-derived `missing` / `not_aoc_topic` records for slugs the curator has since pinned.

Curator research baked in (data file: [raw/wikipedia/aoc_overrides.json](raw/wikipedia/aoc_overrides.json), schema in the sibling README):

- ✅ **fr (101 entries)** — 88 pinned, 7 `missing`, 6 `not_aoc_topic`. Covers the Alsace grand-cru cluster (44, researched 2026-05-10) + the non-Alsace batch (51, researched 2026-05-14: Bourgogne, Loire, LR, Rhône, Sud-Ouest, cidres/eaux-de-vie, `-ou-` multi-name AOCs) + 5 `not_aoc_topic` stubs tidied in 2026-05-14 + 1 single-slug top-up (`vin-de-savoie-ou-savoie`).
- ✅ **es (29 entries)** — 8 pinned, 11 `missing`, 10 `not_aoc_topic`. First-pass ES batch (20, researched 2026-05-14: txakolinas, Jerez, IGPs) + 9 `not_aoc_topic` stubs tidied in 2026-05-14.
- Loose end: per-entry `verification_quote` not captured for the 16 total `not_aoc_topic` stubs — re-research to upgrade if a downstream consumer ever needs it (current consumer doesn't).

Run `.venv/bin/python scripts/02b_fetch_aoc_lexicon.py --lang fr --refresh` (then `--lang es --refresh`) to apply the curator pins; positive pins emit `lead_extract` + `sections` + `full_text` records (`looks_like_aoc` keyword filter is bypassed since the curator already validated via `verification_quote`); negative findings emit `missing: True` or `error: "not_aoc_topic"` with `override_source: "curator"`. After refresh, re-run 02d / 02e / 04 to surface the Wikipedia hints downstream.

### Terroir-fact extraction — 8 parents producing zero bullets — 7 resolved, 1 open

Reconciled 2026-08-26 against `raw/terroir-facts/`: 7 of the 8 now carry bullets
(cotes-de-thau 4 · calvados-vin 2 · cotes-catalanes 5 · thezac-perricard 5 ·
vicomte-d-aumelas 4 · vallee-du-torgan 3 · pays-d-herault 2).

✅ **`cote-vermeille` fixed later the same day — 8/8 closed.** Root cause was
upstream of 02d: its cahier's lien heading is `10- lien avec la zone
géographique` with a **lowercase** title start, which `IGP_SECTION_HDR_RE`
rejected (the uppercase requirement that keeps "125 mg/l …" lines from
becoming phantom titles), so section 10 was never sliced and 02d grounded on
the 1,141-char section 8 (élevage rules) — every candidate failed the fuzzy
filter. Fix: a `lien\b` lowercase carve-out in the title class
([scripts/02_extract_cahiers.py](scripts/02_extract_cahiers.py)); full FR
re-extraction verified byte-identical lien lengths corpus-wide (agenais 9190
· maures 8523 · pays-d-oc 11546) with cote-vermeille going 0 → **7,110
chars** → 5 terroir facts, translated en/es/nl.

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

### Terroir-fact extraction — 2 residual broken IGPs (post-fix) — ✅ both resolved

Reconciled 2026-08-26 against `raw/terroir-facts/`:

| Slug | Facts | Note |
|---|---:|---|
| `euskal-sagardoa-ou-sidra-del-pais-vasco-…` | 5 | ✅ extracts (the numeric-table-column section-parser edge case no longer blocks it) |
| `yonne` | 3 | ✅ 02d re-ran on the post-PNOCDC cahier |

---

### `extract_aire` regex backtracks pathologically on JORF-issue layouts — ✅ fixed 2026-10-04

Fixed with the verification pass this entry asked for: the `after` group is
now `(?:[^:\n]*\n){0,4}?[^:\n]*` (each line ends on its newline), the full
stage-02 re-run + snapshot diff over the 1,541 FR records changed no grape
and only the aire fields the same day's table / proximity rules changed
(see « stage 02 homologation dates … » below). The in-build trigger was
Saint-Chinian's proximity zone (centred "Département de l'Aude" headers, no
colon): 40 s on a 4 KB section, now 0.3 s. The Pouilly-Fumé reproducer below
(`--extract-timeout 0`, unbounded) ran the same day in 0.5 s, verdict
`differs` as for every other register vintage. Original note kept for the
record:

Found while running the register shadow sweep (2026-08-29). Not a register
bug and not new — a **pre-existing latent defect in the FR extractor** that no
document in the current build happens to trigger.

`_DEPT_HEADER_PATTERN` in [scripts/02_extract_cahiers.py](scripts/02_extract_cahiers.py)
contains `(?P<after>(?:[^:\n]*\n?){0,4}?):` — a nested quantifier whose inner
branch can match the empty string. On an area section that carries a
`Département du Cher` heading followed by commune lines with **no colon**, the
engine explores exponentially many ways to split those lines before failing.

Reproducer (register attachment `joe_20110630_0060.pdf` for `PDO-FR-A0824`
Pouilly-Fumé — the register serves the whole *Journal officiel* issue for this
GI rather than a standalone `CDC_*.pdf`):

```
.venv/bin/python scripts/audit_fr_register_shadow.py --only "Pouilly-Fumé" --extract-timeout 0
# hangs; `extract_aire` on a 2,044-char section runs for minutes
```

Impact today: none — the affected document only reaches the extractor through
the shadow audit, which now bounds it (`--extract-timeout`, default 20 s,
verdict `register-extract-timeout`). Impact if the register tier ever wins for
such an appellation: **stage 02 hangs the whole build**, and the same shape
could arrive from BO Agri.

Fix deliberately NOT bundled with the register change: `extract_aire` feeds
the commune list of all 1,540 FR records, so rewriting the pattern needs its
own verification pass (full stage-02 re-run + `fr-cahier-extracted` diff
against the baseline), not a drive-by edit. Candidate rewrite:
`(?P<after>[^:\n]*(?:\n[^:\n]*){0,4}?)` — same language, but every
repetition consumes at least the newline, so the empty-loop ambiguity goes
away. Confirm match-by-match equivalence over the corpus before shipping.

### Interprofession / syndicat URLs — 🟡 1537 / 1540 (2026-08-26)

Was 1244/1540. The 296 gaps were two distinct populations:

**110 AOC records in 7 bassins that had no `by_bassin` fallback.** 96 are
covered by 5 new `by_bassin` keys, all probed: BEAUJOLAIS → Inter Beaujolais (`beaujolais.com`),
SAVOIE → CIVS (`vindesavoie.fr` — note `vindesavoie.net`, which search
engines still cite, serves a broken TLS chain), JURA → CIVJ
(`jura-vins.com`), BUGEY → Syndicat des Vins du Bugey
(`vinsdubugey.net`), EAUX-DE-VIE DE CIDRE → IDAC (`idac-aoc.fr`).
The `VIN DOUX NATURELS` bassin spans three interprofessions, so its 13
AOCs got `by_slug` entries instead of one wrong fallback — CIVR for the
6 Roussillon VDNs, CIVL for the 4 Languedoc muscats, Inter Rhône for
Rasteau + Muscat de Beaumes-de-Venise. `rhum-de-la-martinique` → the
Syndicat de défense de l'AOC Rhum agricole Martinique (http-only; the
HTTPS cert is broken).

**186 IGP records with an empty `region`** — not a bug: INAO's SIQO
referentiel carries `comite_regional` for AOCs only (1245 of 1247 IGP
rows are blank), because IGPs are governed by the national committee
CNIGPVC, not a regional one. Those 186 collapse to **81 parent roots**
(the rest are sub-denominations that inherit via `parent_slug`). 73 roots
are now bound to their own page on the **Confédération des Vins IGP de
France** (`vinigp.fr`), the federation of ~30 IGP producer syndicates —
all 73 per-IGP URLs probed 200, no redirects. 8 got a more specific
body: `pays-d-oc` + `cite-de-carcassonne` + `coteaux-de-narbonne` →
Interprofession des Vins Pays d'Oc IGP (`paysdoc-vin.com`; the latter
two were formally integrated into IGP Pays d'Oc / Inter Oc by JORF
arrêté), `val-de-loire` → Syndicat des Vins IGP Val de Loire,
`muscat-du-cap-corse` + `ile-de-beaute` → CIV Corse,
`marc-d-alsace-gewurztraminer` → CIVA, the 2 IGP ciders → UNICID
(`cidresdefrance.fr`).

Open (3 records, 2 roots):

| slug | note |
|---|---|
| `correze` (+ `correze-coteaux-de-la-vezere`) | AOC since 2017. No syndicat/ODG website found — only single producers (`coteauxdusaillant.fr`) and the departmental brand `origine.correze.fr`. Neither passes the "official site of the interprofession" test. |
| `cote-roannaise` | `coteroannaise.fr` is live and speaks for "une trentaine de vignerons indépendants", but names no operating entity in its footer or legal notices — cannot confirm it is the ODG. Re-check from a browser. |

⚠️ `idac-aoc.fr` returns HTTP 403 to every non-browser client (curl and
WebFetch alike, with full browser headers) while being live and indexed.
Treated as WAF/VPN behaviour, not link rot — confirm once from a real
browser.

Side-findings for later (not URL work): `cote-roannaise` and
`muscat-du-cap-corse` carry an empty `categorie` in their cahier extract
and therefore land as `is_wine=false` on the map, despite both being
wine AOCs.

### eAmbrosia register as a second cahier source — ✅ shipped (2026-08-29)

The FR pipeline now has a self-service fallback behind BO Agri: the eAmbrosia
EU GI register serves the same INAO cahier PDF per GI
(`productSpecifications[0]`). When BO Agri surfaces **no PDF at all** for an
appellation, that gap can now be closed without a hand-curated BO Agri URL, a
Légifrance cookie, or OCR over a professional-org mirror. (An appellation
whose INAO product page links the *wrong* arrêté still needs curation — that
PDF downloads fine, so stage 01 never reaches the register tier. Re-sourcing
on a stage-02 stub is a separate change.) This is the **first landing of the
cross-country Phase-2 register retrofit** (see that section below) —
plumbing, not a data fix: FR was already at 1,540 records / 0 stubs, and the
tier runs strictly *after* BO Agri, so it wins nothing today.

The tier is additionally gated on the appellation having **no cahier PDF on
disk**: `resolve_cahier` and `_download_first_pdf` both return None for a 5xx,
a timeout or an empty Drupal body exactly as they do for a genuinely absent
cahier, so without that gate one INAO outage would re-source working
appellations and churn every downstream surface with no upstream change behind
it.

- `scripts/01d_resolve_register.py` writes the name → `fileNumber` map
  (`raw/inao/register/resolved.json`) + curator queue
  (`raw/inao/register/unresolved.json`). **466 / 466 parents resolved, queue
  empty** (444 full-name, 20 alias, 2 pinned).
- `scripts/audit_fr_register_shadow.py` is the read-only comparison against the
  in-build record (`raw/inao/register/shadow-report.md`).
- Pins live in `scripts/_lib/fr/register_overrides.json` (checked in).

Curator actions when the queue is non-empty: look the name up at
`https://ec.europa.eu/geographical-indications-register/`, add
`{"<id_appellation>": {"file_number": "PDO-FR-…", "register_name": "…",
"note": "…"}}`, re-run `01d`. An empty `file_number` records a verified
absence. The resolver deliberately refuses to fuzzy-match, so every residue is
a curator decision.

Shadow-report findings (`raw/inao/register/shadow-report.md`, 466 parents):

- **464 / 466 resolve**, 361 (77.5 %) get a cahier attachment, 352 extract.
- **92 byte-identical** to the build, 45 cosmetically different, 215
  substantively different — and in **199 of those 215 the newer text is BO
  Agri's**. The register is systematically behind (Anjou Villages: BO Agri
  "43 communes … 3 communes" vs register "24 … 2"; Anjou and Arbois carry
  2022–2023 republications). **Do not promote the register to a primary
  source.** Determinism control: 356/356 re-extractions byte-identical, so
  these are real document differences.
- 🟡 **3 records where the register is materially richer than the build** — a
  targeted re-source is a genuine quality win. Collioure and Pouilly-Loché are
  two of only six parents whose build `lien` is under 1 000 chars (the other
  four are eaux-de-vie, which carry no lien section by design), so this closes
  the tail of the PNOCDC short-lien backlog above. Needs a stub-driven
  re-source path — stage 01 only reaches the register when there is *no* PDF,
  and these have one:

  | id | appellation | build lien | register lien |
  |---:|---|---:|---:|
  | 254 | Collioure | 315 | 14 412 |
  | 217 | Pouilly-Loché | 255 | 8 261 |

  **2026-09-11 (Pouilly-Loché aire)** — the analytics surfaced a 0.4 km²
  AOC drawn across all of Burgundy in simple mode: the 2024 PNOCDC writes
  `1 - Aire géographique` (no degree sign) and defines the aire as a
  sentence ("territoire de la commune de Mâcon"), so stage 02 scanned the
  whole section and recorded the *aire de proximité* (366 communes) as the
  aire. Fixed in `extract_aire` (degree-less block headers + sentence-form
  aires; corpus-wide, 58 single-commune AOCs — Meursault, Pommard, the
  Vosne-Romanée and Gevrey grands crus, Barsac, Cornas, Gigondas … — gained
  a previously empty aire) and guarded
  in stage 04 (`[villages-guard]`). The short `lien` (255 chars) is still
  the register re-source candidate above.
  | 959 | Franche-Comté | 4 062 | 7 583 |

- ❌ **103 appellations (22 %) have no register cahier attachment** — a bare
  `Ares(…)` reference in `productSpecifications`. The brief's 15 % estimate
  came from an n=80 sample; the true figure is higher. Not actionable (BO
  Agri covers them all today).
- ❌ **6 register documents time out in `extract_aire`** and 3 fail to
  extract — see the regex defect logged above.

Open queue — ❌ **2 appellations INAO still publishes but the EU register has
struck off.** The resolver refuses to bind a `Cancelled` GI on its own (a
withdrawn registration cannot be an appellation's current specification), so
both sit in `raw/inao/register/unresolved.json` awaiting a curator call. Both
already have a working BO Agri cahier, so nothing is missing from the corpus —
what needs deciding is whether SIQO is stale (the mirror image of the
2026-08-26 "eAmbrosia has them, INAO doesn't" retirement above):

| id | appellation | file number | register state |
|---:|---|---|---|
| 877 | Cité de Carcassonne (IGP) | `PGI-FR-A1203` | `Cancelled`; registered 17/03/1978; no successor row in the register |
| 881 | Coteaux de Narbonne (IGP) | `PGI-FR-A1202` | `Cancelled`; registered 09/12/1983; no successor row in the register |

Verify against the OJ-L cancellation regulation, then either pin the file
number in `register_overrides.json` (if the attachment is still the right
cahier) or retire the appellation the way the two SIQO ghosts were.

Known register-side negatives (not actionable — BO Agri already covers them):

| appellation | file number | gap |
|---|---|---|
| Musigny | `PDO-FR-A0582` | single-document only; `productSpecifications` is a bare `Ares(2013)3755890` reference |

Two pins were needed:

| id | appellation | file number | why |
|---:|---|---|---|
| 335 | Calvados Domfontais | `PGI-FR-01837` | SIQO spelling; register + cahier both say *Domfrontais* |
| 1091 | Marc d'Alsace Gewurztraminer | `PGI-FR-01836` | SIQO carries no `categorie`, so the product-type partition cannot be picked (same root cause as the `cote-roannaise` / `muscat-du-cap-corse` `is_wine` side-finding above; those two resolve on the all-partition fallback) |

## Cross-country — terroir-facts audit findings after the 2026-09-13 re-run

Report-only checks added by review R9 (`scripts/audit_terroir_facts.py`,
run `tmp/terroir-facts-review/audit-r1-2026-09-13.json`). Each needs a
human look; none blocks the strict gate.

### `wiki_binding` — 23 records whose Wikipedia article title shares no token with the name
Pin the right article or `missing` in `raw/wikipedia/aoc_overrides.json`,
then `02b_fetch_aoc_lexicon.py --lang <l> --source <dir> --only <slug> --refresh`
(a changed revision re-triggers 02d for the record). Probably wrong:
`frusinate` → *Provincia di Frosinone* (the province), `lisboa` → *Lista
de vinhos* (a list), `lesvos` → *Λευκό κρασί* (white wine in general),
`regensburger-landwein` → *Baierwein*, `starkenburger-landwein` →
*Hessische Bergstraße*, the 7 HR records bound to *Vinogradarska
područja Republike Hrvatske* (the umbrella article — legitimate as a
hint, like LU / MT, but pin it explicitly so the check stops firing).
Probably right (a naming-only mismatch): `ahr`, `eger` / `mor`
(*borvidék*), `saint-mont`, `var`, `coteaux-de-die`, `english-wine` /
`welsh-wine` (*Wine from the United Kingdom*), `chios` (*Αριούσιος
οίνος* is the Chios wine), `colli-etruschi-viterbesi` (*Tuscia*).

### `foreign_name` — source text names another appellation ≥ 5× and its own never
`terras-do-dao` (PT: the IGP text names Vinho Verde 21×) and
`malvasia-handakas-candia` (GR: the spec names Κρήτη 20× — check whether
the file is the Cretan umbrella spec); `sobes` / `schwabischer-landwein`
/ `cvicek` are by design (region-wide or parent text). Verified correct
bindings (2026-09-14, from the MASAF sidecars): `terre-del-colleoni`
(its own disciplinare, *bergamasca* is the adjective for the Bergamo
area, 15× in Art. 9) and `pompeiano` (its own IGT disciplinare; Napoli is
the province) — no action.

### `rewrite_rejected` / `rewrite_missing` — gate rewrites the guards refused
Since gate-v2 (2026-09-14) an empty rewrite keeps the original as
`supported` with `support.rewrite_missing` (audit check
`rewrite_missing`) and a cosmetic one as `supported` with
`support.cosmetic_rewrite`; `rewrite-rejected` is left for the guard
failures (a new number, an arrow, over 420 chars). The corpus migration
re-gates everything (GATE_VERSION bump); hand-check what the audit still
lists afterwards.

### Records without a resolvable source
`collioure` (already listed under France) — the only record the gate and
the LLM audit skip (`no_source`).

## Cross-country — records rendering with no grape list (2026-09-20)

`scripts/audit_empty_grapes.py` baseline (stage 04 prints the same one-liner). Fix upstream, then re-run stage 04 → the audit; pin a verified absence in `scripts/_lib/empty_grapes_overrides.json`.

### FLAGGED — extraction gaps (39 parents at baseline; 0 open after 2026-09-20)

| country | slug | mechanism |
|---|---|---|
| fr | costieres-de-nimes | ✅ 2026-09-20 — `encepagement_block()` starts the grape parse at the `1°- Encépagement` sub-block (6 P + 8 A + 5 obs.) |
| fr | picpoul-de-pinet | ✅ 2026-09-20 — cahier typo `IV.-Encépagement` after `IV.- Aires`; repeated numeral relabelled when the next header carries numeral+2 (piquepoul; see lexicon note on the B colour) |
| fr | saint-aubin (+32 premiers crus) | ✅ 2026-09-20 — the bound PNO PDF was a 4-page *extrait* (section X only; register PDO-FR-A0822 = no-cahier). Full cahier (décret 2011-1764, 16 pp) pinned from the BIVB mirror in `manual_overrides.json` (BO Agri unreachable at the time); chardonnay / pinot blanc / pinot noir + pinot gris, lien 9.8 k chars. |
| fr | ile-de-france (+5 sub-denominations) | ✅ 2026-09-20 — `\x0c5 Encépagement` page-top header now matched (72 varieties) |
| fr | lavilledieu | ✅ 2026-09-20 — IGP encépagement routed by keyword (section 4.1), not position (5 P + 2 A) |
| es | bajo-aragon, ibiza, illes-balears, serra-de-tramuntana-costa-nord, valdejalon, valles-de-sadacia | ✅ 2026-09-20 — curator-pinned PDF pliegos; lower-case rosters, `variedades de vid` titles, page furniture and dangling connectors now parsed (by-catch: ribera-del-gallego-cinco-villas, ribera-del-jiloca, castilla-y-leon colours) |
| es | la-gomera, pago-de-otazu, urbezo | ✅ 2026-09-20 — same PDF branch; La Gomera's nested `6. Vino espumoso` no longer wins the section-6 tie (16 P + 15 A) |
| it | catalanesca-del-monte-somma, osco, quistello, rotae | ✅ 2026-09-20 — Molise + Lombardia fed from MASAF's Registro Nazionale (catalogoviti, per province; 34 / 34 / 82); catalanesca's letter-spaced PDF re-read from `pdftotext -raw` (1) |
| it | grottino-di-roccanova, valtenesi | ✅ 2026-09-20 — Grottino: letter-spaced `Arti col o 2` header + `di`-wrapped names (5); Valtènesi: PDO cancelled (Reg. 2026/572) → `CANCELLED_GIS`, now sottozona `riviera-del-garda-classico-valtenesi` |
| pt | alentejano, algarve, beira-atlantico, minho, peninsula-de-setubal, terras-da-beira, terras-de-cister, terras-do-dao | ✅ 2026-09-20 — `6. Principais Uvas de Vinho` anchor + `Secundárias` block no longer overwrites the roster; `PRT 5xxxx` rows; wrapped lines rejoined (66–259 each; setubal 1 → 17 by-catch) |
| pt | palmela, tavora-varosa | ✅ 2026-09-20 — same fix (31 / 37) |
| at | kremstal | ✅ 2026-09-20 — EUR-Lex title typo `Keltertrauensorte(n)`; fuzzy title routing for keywords ≥ 10 chars (riesling, grüner veltliner) |
| ch | bern-berne (+2), glarus, jura, schaffhausen, solothurn, thurgau, zug, zurich | ✅ verified 2026-09-20: none of the eight acts enumerates a variety (federal list / office-kept register by reference) — pinned REVIEWED with the article cited. Open: `reglement_index.py` `zh` points at LS 916.51, repealed 01.01.2018 with no successor act — flag the entry; JU cached HTML was a PDF.js viewer shell, resolver added to stage 01 (re-run `scripts/ch/01_fetch_reglements.py`). |

### INHERIT — stage-04 gap (12 at baseline; 0 open)

| country | slugs | mechanism |
|---|---|---|
| ch | the 12 VS grands crus | ✅ 2026-09-20 — CH stage 02 now copies the `valais-wallis` roster into each grand-cru record (45) |

### PT alias gaps surfaced by the 2026-09-20 caderno parser fix (lexicon, not parser)

| surface (caderno) | should fold to | note |
|---|---|---|
| tinta-bastardinha | alfrocheiro | "Alfrocheiro (Tinta-Bastardinha)", Algarve |
| graciosa | bastardo | "Bastardo (Graciosa)" |
| molinha | tamarez | "Tamarez (Molinha)" |
| sousao | vinhao | "Vinhão (Sousão)" |
| pau-ferro, tinta-lameira | tinta-caiada | "Tinta-Caiada (Pau-Ferro/Tinta-Lameira)" |
| bastardo ↔ trousseau | one slug | same cultivar (VIVC TROUSSEAU NOIR); fold decision |
| maria | — | bare first name is an exact alias of trousseau; false-positive trap |
| pero-pinhao | own slug | PRT54023, distinct old variety; currently hyphen-split to sousao |
| moscatel-graudo ↔ muscat-d-alexandrie | one slug | same cultivar |

Also: `_prt_canonical_name` enqueues two-column "Name Synonym" strings as unknowns on every run (~110 entries) — noise, not output.

### ES alias questions surfaced by the 2026-09-20 PDF-pliego parser fix (lexicon, verify against VIVC before editing)

| surface | current fold | question |
|---|---|---|
| derechero | unmatched | "Derechero de Muniesa", Bajo Aragón native red — add own slug once VIVC-verified |
| moristell | morrastel (= Graciano) | Ribera del Jiloca writes "moristell (Juan Ibáñez)" and Juan Ibáñez folds to `moristel` — likely should fold to `moristel` |
| robal | mourisco-branco (white) | fires on Jiloca's red list "bobal, robal" — local red synonym or the Portuguese white? |
| tintilla / bastardo negro → trousseau, baboso negro → alfrocheiro | existing folds | La Gomera; fine if intended |

### IT follow-ups from the 2026-09-20 roster fixes

- **Valtènesi** (PDO-IT-A1188) cancelled by Reg. (EU) 2026/572, now a sottozona of Riviera del Garda Classico (`riviera-del-garda-classico-valtenesi` via sottozona Pattern C). After `it/00 → it/02 → 04`: remove the `Valtènesi → DOC` pin in `scripts/_lib/it/national_term_overrides.json` and the `valtenesi` entry in `raw/it/oj-pages/manual_overrides.json`.
- Regional registers now sourced from MASAF's Registro Nazionale (catalogoviti, per province, HTTP only) for Molise + Lombardia; Regione Lombardia's own elenco (d.d.u.o. 10101/2025) is WAF-blocked to non-browser clients.
- Lexicon (verify VIVC): register code 318 "Malvasia Rosa RS." exact-matches `velteliner-rouge-precoce` — wrong for Italy (pink mutation of Malvasia di Candia Aromatica); "Veltliner B." → gruner-veltliner; "Lambrusco Marani" → generic lambrusco; "Catalanesca bianca" alias. Unmatched Lombardia natives: Timorasso, Groppello di Mocasina, Lambrusco Viadanese, Incrocio Terzi N.1, Bussanello, Moradella, Erbamat, Erbanno, Mornasca, Grappello Ruberti, Bellagna, Merera; Molise: Moscato Nero di Acqui.

### FR follow-ups from the 2026-09-20 parser fix

- Lexicon: bare `piquepoul` + colour B (Picpoul de Pinet "cépage piquepoul B") resolves to slug `piquepoul`, VIVC-bound to #9298 PIQUEPOUL NOIR; needs a colour-qualified fold to `piquepoul-blanc` (#9295). Bare `piquepoul` also appears on la-clape, pierrevert, saint-chinian — check their colour codes first. `match_variety` has no colour-qualified alias mechanism today.
- ✅ 2026-09-21 Domfront (cidre/poiré IGP) no longer lists the perry pear `antricotin` as a grape (section 5.1.1 header now parsed); drop the stale `raw/vivc/by-slug/antricotin.json` + `raw/vivc/slug_overrides.json` pin. (done)

### REVIEWED — regulator names no variety (15)

vlaamse-landwijn (BGA §7 broad rule); appenzell-ausserrhoden, appenzell-innerrhoden, basel-stadt, nidwalden, schwyz (+ zurichsee), uri (règlement defers to federal OVin).

## Cross-country — visitor feedback triage (2026-09-22) — 🟡 2 fixed, 1 open design

`feedback.csv` / `scripts/feedback_report.py`, all time: 4 flags, 2 retracted. Evidence and the adversarial verification (18 agents) are summarised in the session notes; numbers below were re-derived at least twice.

| slug | aspect | verdict | action |
|---|---|---|---|
| navarra | grapes | VIVC pin "Oneca (Galvani)" | ✅ fixed 2026-09-20 (pins verified live) |
| pineau-des-charentes | grapes (fr, retracted) | roster = cahier §V (14 varieties incl. trousseau gris) — but the **fr tooltip for Trousseau Gris showed the Trousseau *noir* article** (`raw/wikipedia/grape_overrides.json` fr pin → "Trousseau": Bastardo photo, "Le trousseau N…", VIVC 14165 gris in the footer); nl was translated from that same fr card | ✅ fixed 2026-09-22: fr pin set to `null` (`override-absent`), fr + nl cards re-translated from en *Trousseau gris* |
| gres-de-montpellier | boundary (retracted) | advanced polygon = the 44 INAO parcellaire rows (Saint-Vincent-de-Barbeyrargues has a Languedoc row, none for id_denom 2917 — INAO's gap); **default (simple) mode draws the 45-commune aires-csv union: 819.8 km², 18× the 46.4 km² parcellaire, 45.9 km² of it lagoon (Étang de l'Or 29 km²), no on-screen disclosure** | 🟡 simple-mode water superseded by the footprint (branch `feat/zoom-lod`); the Saint-Vincent gap is a candidate pin — see the Côtes du Rhône Villages entry below |
| saint-estephe | boundary (open) | advanced polygon sound: 1 INAO row, 99.95 % in commune 33395, 100 % of RPG 2023/2024 vineyard parcels inside (IGN RPG via data.geopf.fr WFS), every 1855 growth + cru bourgeois inside or < 250 m; detached 1.18 km² part = Saint-Corbian / Le Boscq; **default mode draws the IGN commune: 33.05 km², of which 8.56 km² (25.9 %) is BD TOPO `Estuaire` (Gironde) and ~9 km² western forest / palus** | ❌ open — see below |

### Monterrei boundary flag (2026-09-27, en, zone view at z9.3) — ✅ fixed

The parent's polygon was the MAPA zone: six municipios whole (Castrelo do
Val, Monterrei, Oímbra, Verín, Riós, Vilardevós ≥ 98.8 % each, 674 km²).
The documento único (PDO-ES-A1114-AM03, 12 September 2025, "Ampliación de
la zona delimitada") delimits by parishes: seven mountain parishes of
Castrelo do Val (Campobecerros, Parada da Serra, Piornedo, Portocamba) and
Riós (O Navallo, Rubiós, Trasestrada) it excludes were drawn (~111 km²);
the six it added in Cualedro (San Millao, Montes, Rebordondo, A Xironda)
and Laza (Matamá, Retorta) were missing (~79 km²), so the Ladera de
Monterrei subzona — already drawn from the IET parishes — stuck out west of
its parent on screen. Fixed by the whole-municipio MAPA-zone rule in
`apply_es_parroquias` (CLAUDE.md, ES chain; `tests/test_es_parroquias.py`):
the parent is now `iet-parroquia-union`, Vilardevós plus 49 parishes, 640
km², one polygon, both subzonas inside it. Ribeiro and Ribeira Sacra keep
their whole-municipio zones — see the Galician parroquias residue section
under Spain. The post-build audits were clean (outliers 0 unreviewed,
footprints strict) except one overlap sliver unrelated to Monterrei —
Beaujolais / Coteaux Bourguignons, 41 km², the eight Mâconnais–Beaujolais
border communes both INAO rows list; the Coteaux Bourguignons row only
bound on 2026-09-26 through the "X ou Y" alias fold, so it post-dated the
09-25 review and is now whitelisted with its siblings.

### Côtes du Rhône Villages boundary flag (2026-09-29, en, footprint view at z8.8; flagged twice, retracted once) — ✅ fixed

The parent polygon is the INAO parcellaire dissolved over id_app 276 (88
of the aire's 95 communes). Seven communes of the aire géographique
(cahier section IV; aires-communes CSV IDA 1287) carry no Villages parcel
in the 2026-05-11 release: Vaison-la-Romaine, Saint-Marcellin-lès-Vaison,
Saint-Romain-en-Viennois and Mollans-sur-Ouvèze have no row for **any**
AOC (not digitised); Visan, Sérignan-du-Comtat and Sorgues have Côtes du
Rhône rows only. Six of the seven are named DGC communes (« Vaison-la-
Romaine », « Puyméras », « Massif d'Uchaux », « Sainte-Cécile », « Visan »),
so at z8.8 the footprint stopped short of Vaison with the town label on
bare basemap — what the visitor saw. Fixed by the new curator-pin layer
(CLAUDE.md "INAO parcellaire gaps";
`scripts/_lib/parcellaire_gap_fills.json`, `scripts/_lib/parcellaire_gaps.py`,
`scripts/audit_parcellaire_gaps.py`): six pins — Côtes du Rhône Villages
(7 communes, 426 → 538 km²; Sérignan, Sorgues and Visan from the Côtes du
Rhône parcels of the commune, the four undigitised ones whole), Côtes du
Rhône (5 whole, incl. Saint-Laurent-des-Arbres — a Lirac commune with no
row for any AOC; 1,323 → 1,377 km²), and the Vaison-la-Romaine (2.2 → 35
km²), Massif d'Uchaux, Puyméras and Sainte-Cécile DGCs. Every filled card
says which communes and how. Visan's own DGC stays the whole commune
(`aires-csv-dgc`, already disclosed). Post-build audits: outliers 0 unreviewed / 0
stale, overlaps 0 suspicious, gap pins 6 APPLIED / 0 STALE; the footprint
audit's `--strict` exits 1 on 11 bridges > 5 % (pouilly-fuisse-premier-cru
20 % onto the Mâcon villages, saint-bris, gres-de-montpellier, la-clape,
the Corton / Blagny / Ladoix climats) and 7 containment findings of 0.1 %
— **byte-identical to the 2026-09-27 run** (`/tmp/owm-audit-envelopes-
monterrei.log`; the "footprints strict" wording in the Monterrei entry
above was loose), the fill only removed cotes-du-rhone from the containment
list. Those 11 bridges are a separate review item (whitelist with evidence,
or a smaller closing for the climats). Side fix: `feedback_report.py` dropped `lod` / `zoom` on
the *flagged* rows (only retractions carried them) — the CSV now shows the
zoom band a flag was raised in.

**Candidate pins the audit surfaces (verify each against the cahier before
pinning; `scripts/audit_parcellaire_gaps.py`, 167 records with ≥ 1 gap,
most of them CSV legal aires that are not production areas):**

- gres-de-montpellier — Saint-Vincent-de-Barbeyrargues (Languedoc row, no
  Grés row; the 2026-09-18 flag above) → pin with donor `languedoc`.
- rasteau-tranquille (DGC) — Cairanne, Sablet (the aire lists parts of both).
- touraine-azay-le-rideau (DGC) — Artannes-sur-Indre, Thilouze (no row for
  any AOC); touraine-amboise — Montreuil-en-Touraine, Saint-Ouen-les-Vignes.
- macon-villages (DGC) — Pruzilly, Romanèche-Thorins, Saint-Amour-Bellevue,
  Saint-Symphorien-d'Ancelles (Beaujolais rows only).
- anjou — Corzé, Louzy, Orée d'Anjou, Verrie, Verrières-en-Anjou, Antoigné;
  cotes-de-bordeaux-blaye — Donnezac, Étauliers.
- languedoc — 58 Limoux-area communes with Limoux / Blanquette rows and no
  Languedoc row (is the regional delimitation there simply not digitised?
  a single INAO question settles all 58); cotes-de-bordeaux — 22;
  vin-de-corse-ou-corse — 36 communes with no row for any AOC.
- NOT gaps (CSV legal aire ≠ production area; leave unpinned): the Corton
  and Givry premier-cru climats (three-commune CSV rows for one-commune
  crus), the Alsace grands crus (47-commune rows), Bourgogne / Bordeaux
  regional aires (vineless communes).

### Cévennes boundary flag (2026-09-29, fr, zone view at z7.2) — ✅ fixed

IGP Cévennes is a commune union from the INAO IGP aires CSV. Its 236 rows
(IDA 2217) carry `Date MAJ` 14 September 2012 and are all Gard; the cahier
des charges in the build (BO du MASA 8 August 2024, arrêté at JORF 4 August
2024) lists the same Gard communes **plus 40 Lozère communes** ("Pour le
département de la Lozère : Altier, Barre-des-Cévennes … Villefort"; section
7.1: "situé dans les départements du Gard et de la Lozère"). The latest CSV
release (2025-10-09, the one in `raw/`) has no Lozère row, so the polygon
stopped at the département border — a Cévennes without Florac, the Vallée
Française or the Tarn gorges. Fixed by a curator-pin layer (CLAUDE.md "INAO
aires-communes supplements"; `scripts/_lib/aires_supplements.json`,
`aires.apply_supplements`, `tests/test_aires_supplements.py`): 39 Lozère
communes added (3,482 → 4,952 km², 233 → 272 communes drawn). Two more
records with the same defect were found by diffing every cahier's commune
list against its CSV rows and pinned on the same evidence: Côtes de Thau
(+9 communes around the Étang de Thau — Sète, Mèze, Frontignan …; cahier BO
24 August 2023, CSV rows of 2015; 181 → 422 km²) and Maures (+3 — Besse-sur-
Issole, Cabasse, Le Thoronet; cahier BO 11 December 2025; 2,193 → 2,313 km²).
Post-build (2026-09-30, `/tmp/owm-build-aires-supplements.log`): the three
supplements applied, 0 stale; against the previous build only the three
records changed (12 entity pages, their panel JSON, the startup blobs, the
tile fingerprint in the app bundles, 12 sitemap `lastmod`); outliers 0
unreviewed / 0 stale, overlaps 0 suspicious (sliver classes unchanged),
1,043 tests pass. Not deployed.

**Open on the pinned records**

- cevennes — Massegros Causses Gorges (48094) is in the aire "pour la partie
  correspondant au territoire de la commune déléguée Les Vignes" only. Not
  drawn (`not_drawn` in the pin): IGN AdminExpress communes have no polygon
  for a commune déléguée. Le Rozier + Saint-Pierre-des-Tripiers are a
  detached lobe for that reason. A Les Vignes polygon (AdminExpress
  `COMMUNE_ASSOCIEE_OU_DELEGUEE`, Licence Ouverte) would close it.

**Candidates from the same diff (cahier names a commune the CSV lacks;
verify each against the cahier in force before pinning — the probe reads
prose, so exclusion lists, vinification zones and merged communes show up
as false candidates):**

- thezac-perricard — Mauroux, Sérignac, Saux (Lot; Saux is now a commune
  déléguée of Porte-du-Quercy). The cahier in the build is a **PNOCDC
  draft** (`extranet.inao.gouv.fr/fichier/PNOCDCIGPThezac-Perricard.pdf`);
  CSV rows of 2012 are the six Lot-et-Garonne communes. Pin once the
  amended cahier is published in the BO.
- duche-d-uzes (AOC, `aires-csv`) — 10 Gard communes the cahier (COG 2024,
  BO Agri MAASA stamp) lists and the AOC CSV lacks: Argilliers, Collias,
  Domessargues, Euzet, Mauressargues, Montagnac, Quissac,
  Saint-Hippolyte-de-Caton, Saint-Just-et-Vacquières, Vers-Pont-du-Gard.
- collines-rhodaniennes — Ambonil, Bourg-de-Péage (cahier BO Agri 11
  December 2025; CSV rows of 6 December 2024).
- lorraine — Houdemont, Neuves-Maisons (cahier COG 2020; CSV rows of 28
  July 2025 are *newer* — check which side is current).
- pays-de-brive — Astaillac, Saint-Viance, Segonzac, Ussac (cahier BO 15
  October 2020; CSV rows of 5 September 2025 are newer — likely a cahier the
  build has not picked up; register-drift check).
- haute-vallee-de-l-aude — Cassaignes (the cahier lists cadastral sections
  for some communes; partial).
- urfe — Perreux, Saint-Martin-d'Estréaux, Sail-les-Bains (PNOCDC draft in
  the build).
- ardeche — Vallées-d'Antraigues-Asperjoc (2019 commune nouvelle; the CSV
  keeps the pre-merger codes — vintage drift, not an amendment).
- ile-de-france (18 communes), comtes-rhodaniens (14) and the spirit / cider
  GIs (Calvados, Pommeau, eaux-de-vie de cidre) — not read yet.
- NOT gaps: alpilles (the 29-commune list is the vinification zone, the 19
  CSV communes are the grape zone), franche-comte (the Jura list is the
  exclusion of the AOC communes).

### Visitor flags of 2026-10-03 (`feedback_report.py --range all`: 12 flags, 5 retracted, 1 note)

**muscadet-coteaux-de-la-loire — name (fr, footprint view at z8.4, simple mode) — ❓ no defect found.**
The string on screen is the regulator's in every source the build holds:
SIQO row id_appellation 98 / id_denomination_geo 212 "Muscadet Coteaux de la
Loire" (both product rows — Vin tranquille 15239 and Vin sur lie 15240 — on
one denomination, so no sub-denomination), the cahier in the build (sections
I, III, X, XII all write « Muscadet Coteaux de la Loire », no hyphen, no
"des"), INAO product page 15239, the EU register `PDO-FR-A0495`
(`register_name` identical, matched on the full name). The fr card renders
the same name in the h1, the title ("Muscadet Coteaux de la Loire, carte du
vignoble — Val de Loire"), the sidebar and the summary; the only other names
on the card are the grape pill "Melon" (cahier "melon B", VIVC prime MELON, no
bracket) and the region "Val de Loire". Geometry is the INAO parcellaire for
id_app 98, bbox −1.525 / 47.212 / −0.994 / 47.427 — Carquefou and Thouaré in
the west, Ligné and Mésanger in the north, Saint-Florent-le-Vieil in the east,
the 22 aire communes of the aires CSV (14 Loire-Atlantique, 8 Maine-et-Loire)
— and the 2026-09-29 outlier / overlap audits were clean. Not reproducible
from the flag alone; candidates if it recurs: the 1936 decree's historical
form "Muscadet des Coteaux de la Loire", a hyphenated spelling, or a visitor
who expected "Melon de Bourgogne" on the pill. The cahier in the build is
the 2019 arrêté (`homologated_at` 2019-10-16) while `latest_known_pdf` is a
2025-11-26 publication — a register-drift re-source candidate, unrelated to
the name.

**bolgheri-sassicaia — grapes (en, zone view at z9.6 and z7.7; flagged twice, retracted once; note "Cabernet-Frank") — ✅ fixed, mechanism-wide.**
The card listed Cabernet Sauvignon alone while its own terroir fact named
the Cabernet Franc the Marchese planted in the 1940s. The MASAF disciplinare
(Art. 2) reads "Cabernet Sauvignon: almeno l'80 %; possono concorrere altri
vitigni con uve a bacca rossa … riportati nell'allegato 1", and the PDF ends
with "Allegato 1 – Elenco vitigni complementari idonei alla produzione del
vino a DOC Bolgheri Sassicaia" — 49 red varieties, Cabernet Franc tenth.
Stage 02f read an in-PDF annex only when Article 2 named no variety (the
Toscano-IGT case), so every DOC that names its principal and hands the
complement to the annex lost the complement. Fix in
[scripts/_lib/it/masaf.py](scripts/_lib/it/masaf.py) `grapes_with_annex`
(CLAUDE.md, MASAF stage 02f, "in-PDF variety annex"): wider anchor
(Allegato / Elenco headings, bounded at the next Allegato or Articolo),
cell-wise rows for the register-table, two-column and "(N)" layouts, and
the reading decided by Article 2's wording — complement → `accessory`,
"da uno o più vitigni … allegato 1" → roster → `principal`, no "allegato"
in Article 2 → annex ignored (Roero). Stage 04's non-stub backfill adds the
annex `accessory` entries to a documento-unico record without any and
records the MASAF provenance. Corpus sweep (`/tmp/owm-annex-dryrun2.log`,
58 annex records re-extracted, `it-masaf-disciplinare-v4`): 36 stubs gain
an accessory roster (Sassicaia 1 + 46; the Tuscan DOCs 25–80 each — the
regulator attaches the whole regional register for "altri vitigni idonei"),
11 documento-unico records gain one through the backfill (Chianti Classico
1 + 37, Chianti 3 + 80, Rosso di Montepulciano 1 + 82, Torgiano Rosso
Riserva, Montefalco, Vin Santo di Montepulciano, Castelfranco Emilia, delle
Venezie, Riviera del Garda Classico; Maremma Toscana and Torgiano had an
empty documento-unico roster and take the whole sidecar), 8 rosters are
promoted from the few names Article 2 singles out to the annex (Terre
Siciliane 2 → 56, Calabria 1 → 35, Basilicata 2 → 53, Isola dei Nuraghi
5 → 69, Alpi Retiche 5 → 74, Vigneti delle Dolomiti 19 → 57, Monferrato
10 → 43 — its bianco and rosso are "uno o più vitigni" of the Piedmont
list — and Mitterberg, whose documento unico already carries 40), and the
three full-roster IGTs recover "Refosco dal Peduncolo rosso" (the wine-type
stripper took its "rosso"; the name as written is now tried first).
Tests: `tests/test_it_parser.py` (Sassicaia excerpt + a synthetic
register-table fixture: complement, roster, bounded list, no-reference).
Post-build (2026-10-04 02:38 → 03:37, `/tmp/owm-stage04-2026-10-04b.log`,
shared with the concurrent FR re-extraction / Montpeyroux work of the other
session): Sassicaia 1 + 46, Chianti Classico 1 + 37, Calabria 35, Terre
Siciliane 56; `[grapes]` FLAGGED=0 / INHERIT=0, 0 stale geometry overrides,
`audit_empty_grapes --strict` and `audit_gi_terms --strict` exit 0. An
earlier build of the same night (02:09) had read `saumur.json` while stage
02 was rewriting it and shipped Saumur with no grapes — a concurrent
stage-02 run and a stage-04 build must not overlap, the same rule as two
stage-02 runs. Not deployed.

Side findings of the sweep, not acted on:

- **`riminese` / `albana` are two slugs on one VIVC passport** (#224 Albana
  bianca): the Corsican Riminèse pin was moved from 10117 to 224 on
  2026-09-20, after the MASAF sidecars were written. The matcher's
  VIVC-synonym layer now sends "Albana di Romagna" (Colli d'Imola) and
  "Ribona" (Colli Maceratesi; VIVC lists RIBONA under Albana bianca) to
  `riminese` where the 2026-09-20 sidecars had `albana`; the pill reads
  "Albana di Romagna (Albana Bianca)", correct for the reader, but the grape
  facet splits one variety over two slugs (30 FR cahiers on `riminese`).
  Fold decision for a lexicon pass. Same drift on alto-adige ("Portoghese").
  The three sidecars were rewritten in this pass (driver bug, no build
  effect for the two documento-unico records).
- **Unresolved annex names** now in
  `raw/it/extraction-unknowns-masaf.json` for the grape-colour pass:
  Catanese Nero, Lucignola, Merlese, Minnella Bianca, Orisi (Terre
  Siciliane); Bellagna, Bussanello, Erbamat, Grappello Ruberti, Incrocio
  Terzi N.1 (Alpi Retiche); Bianchetta Trevigiana, Casetta (Vigneti delle
  Dolomiti); Maceratino, Malbo Gentile (Esino); Centesimino, Cornacchia,
  Ervi, Famoso, Festasio, Lambrusco Benetti, Lambrusco Oliva, Pelagos,
  Perla dei Vivi (Castelfranco Emilia). The queue file was rewritten by the
  per-slug driver and holds this run's 1,619 candidates only; a full
  `02f --all --include-nonstub` sweep restores the corpus-wide queue.
- Lexicon quirks the annex exposes (pre-existing): "Prugnolo Gentile" →
  `nielluccio` beside "Sangiovese" → `sangiovese` (two pills for one
  variety on Sassicaia's card); "Mazzese" → `ciliegiolo`.

### Simple-mode polygons carry open water, and the panel does not say the shape is the commune — 🟡 disclosure + footprint on branch `feat/zoom-lod` (2026-09-23), water mask still open

- **Branch `feat/zoom-lod` (2026-09-23, not merged):** zoom now picks the geometry instead of the mode — below z12 the 1,259 French parcel-level records draw a generalised vineyard footprint (250 m morphological closing of the INAO parcellaire, `scripts/_lib/vineyard_envelope.py`; median 1.3× the parcels vs 5–8× for the commune union), from z12 the parcels; the commune union is no longer drawn for them, which removes the water for the 32 records whose twin is parcellaire (Saint-Estèphe 26 % estuary → 0). Every card now says what the polygon is: the zoom-reactive footprint line, a "réunion des {n} communes, plans d'eau compris" line for plain `aires-csv` / `dgc-village-override` / `communes` records (the 97 water records that no envelope can reach — every IGP, Champagne), and a zone-source line for the other countries (geoportal / MAPA / Bétard / administrative union). `Feedback *` and `Appellation Viewed` carry `lod` + `zoom`. Audit: `scripts/audit_vineyard_envelopes.py` (`--water` measures BD TOPO water, rivers included, inside the footprint's added area).
- **Still open:** the BD TOPO open-water mask for the commune-derived geometries (the 97 FR records + the non-FR lakes below) — a display decision, the design verdict below stands; and the CH `see_flaeche` exact source.

- Only France has a simple ≠ advanced split (354 of 2,952 villages features differ, all FR); everywhere else the "simple" polygon is the advanced one, so a visitor cannot escape the water by switching mode.
- FR sizing (villages layer ∩ BD TOPO v3 `surface_hydrographique` Estuaire / Lagune / Lac ≥ 0.2 km², scratch run 2026-09-22): 129 appellations carry ≥ 0.3 km² of water; ≥ 10 % of the polygon for muscat-de-mireval 29.7 %, muscat-de-frontignan 28.4 %, saint-estephe 25.9 %, sable-de-camargue 25.8 %, pauillac 23.2 %, pays-des-bouches-du-rhone-terre-de-camargue 19.6 %, aude-la-cote-revee 17.6 %, cotes-de-thau 14.2 %, medoc 12.6 %, pays-d-herault-berange 11.2 %, fitou 10.5 %, saint-julien 10.5 %. The scan excludes `Ecoulement naturel` (tidal rivers), so margaux (~4 % via OSM) and the Loire communes are under-reported. 97 FR *advanced* polygons are affected too — all aires-csv / aires-csv-dgc / parent-appellation / dgc-village-override, none parcellaire.
- Non-FR (Overpass sizing, verification only): cheyres 56 % Lac de Neuchâtel, lavaux 42 % / vully 35 % / la-cote 34 % Léman, zug 36 %, riviera-del-garda-classico 21.5 %, colli-del-trasimeno 18 %, balatonmelleki 12 %, noord-holland 14 %; the Neusiedler See sits inside neusiedlersee / leithaberg / burgenland / weinland. For CH the exact lake area is already on disk: swissBOUNDARIES3D `tlm_hoheitsgebiet.see_flaeche` per Gemeinde (851.6 km² over 205 communes; the 10 standalone lake rows are already dropped by `ch/geometry.py`).
- Design panel verdict (3 designs, 2 judges): **subtract an IGN BD TOPO open-water mask (Licence Ouverte 2.0) from the commune-derived geometries only** — fetch `BDTOPO_V3:surface_hydrographique` with `nature IN ('Estuaire','Lagune','Lac') AND persistance='Permanent'` in stage 00 (raw/manifest entry, sha-keyed cache), floor **0.2 km²** (1.0 leaves the Camargue at 4.6 %), mask simplified at `TILE_SIMPLIFY_TOLERANCE`, applied in stage 04 above the `parent_village_geom_by_slug` hand-off with an explicit source frozenset {aires-csv, communes, aires-csv-dgc, dgc-village-override, parent-appellation} (never parcellaire, never cadastre-lieu-dit), refusal on empty / > 70 % loss, `land_clipped` km² recorded on the feature and a `[geo] water` build line, 6-decimal coordinate rounding, memoised per shared geometry object, a `--no-water-clip` flag whose build must compare `identical` against a golden snapshot, and a CLAUDE.md note on the ordering against `geometry_outlier_overrides.json` (centroid-matched). The GISCO-LAU-coastline alternative is free (zip already in raw/es/gisco) but fixes only the Médoc, not the lagoons; OSM is verification-only (ODbL share-alike on the published geojson). Lakes and lagoons are legally inside the commune superficie, so this is a *display* decision — record it as such in the panel text.
- ~~Disclosure (owed regardless of the clip)~~ superseded by the branch above (the drawn shape is now a function of zoom, not of a hidden `v_source`): ~~emit `geom_source_villages` (from `v_source`) as a startup field (register it in `STARTUP_AOCS_FIELDS`), render a mode-aware `approx-line` when `viewMode === 'simple'` and it differs from `geom_source` (the label `meta_geom_approx_communal` exists in every catalogue and is unused), and re-render the open panel from `applyMode()` — today a mode switch leaves the card stale. `geom_approx_aires` fires only for `aires-csv-dgc`; plain `aires-csv` records (pineau-des-charentes) get no line either.~~
- Done 2026-09-22: `Feedback Flagged` / `Retracted` / `Note` now carry `view_mode`, and the report prints it — the flag's `geom_source` is the *advanced* provenance and was misread as "the visitor was looking at the parcellaire".

## Cross-country — delimitation sweep (2026-09-23) — 🟡 report written, nothing implemented

Full report: [docs/delimitation-sweep-2026-09-23.md](docs/delimitation-sweep-2026-09-23.md); per-record classification, overlap pairs and source texts in `tmp/delimitation-sweep-2026-09-23/`. 849 non-French records read (every record with a cadastral / exclusion / partial-municipality marker or a real same-country overlap), 135 high-rated ones re-verified against the text.

- Overlapping specifications almost never name each other (104 of 2,338 partners); where a border is resolved it is by each document's own sub-municipal line.
- Cadastral identifiers in 99 records: ES 50 (polígonos / parcelas — the Vinos de Pago estates and DO-level inclusions / exclusions; SIGPAC resolves them, the Priorat/Montsant code is the seed), IT 20 (fogli / particelle — Agenzia delle Entrate cadastral map, licence to confirm), SI 12 + SK 7 (cadastral municipalities + contour lines, open layers), DE 8 (Flurstücke, ALKIS open only in BB / SN / ST).
- Sub-municipal administrative units: PT freguesias (43, CAOP already on disk), RO sate (34, no open layer), GR / CY κοινότητες (38, GISCO LAU already at that level), BG землища.
- Italy: 278 narrative traces (roads, rivers, contours) — digitising, not parsing; 58 IT + 29 GR altitude limits could be a DEM clip of the zone, labelled as a display refinement.
- ≈ 80 records defer to an annexed map only (GR 29, PT 15, IT 11, CY 10, ES 9, DE 4): nothing to parse.
- Suggested order: ES polígonos → PT freguesias → SI/SK cadastral municipalities → IT fogli → DE Flurstücke → altitude clips. No step maps parcels the documents do not reference.

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

### Geometry — commune-list parser residue after the 2026-09-24 fixes — ✅ guarded 2026-09-25

The 2026-09-24 fixes (Quiroga-Bibei's lower-case article, the 74 compound
municipio names, the 11 Pallars mergers) were verified against the whole
corpus; the independent check found three latent gaps with **no record
affected today**. All three are guarded since 2026-09-25 (`merge_compound_
municipios` refuses a bare-article piece; `_LOWER_ARTICLE_RE` accepts
`los` / `las`; the resolver's `_reread_out_of_context` splits a compound
whose pieces bind inside the established provinces while the compound
does not — and, the same rule, re-reads "Los Corrales" as Huesca's
"Loscorrales", the one real defect the outlier audit surfaced: Ribera del
Gállego-Cinco Villas drew Sevilla's Los Corrales, 636 km away). Tests in
`tests/test_es_commune_matching.py` (2026-09-25 block). The original notes:

- `merge_compound_municipios` fuses "Vielha e Mijaran, Les y Bossòst" into
  one token because the normaliser strips a trailing article the way GISCO
  writes "Borges del Camp, Les" — `Les` (Val d'Aran, INE 25125) is the only
  municipio whose whole name is an article. Refuse a merge when a piece
  normalises to an empty string or a bare article.
- `_LOWER_ARTICLE_RE` (subzona.py) accepts a / o / as / os / el / la / els /
  les / es / sa / l' but not the Castilian plurals `los` / `las`, which the
  resolver's normaliser does strip; a pliego writing "los Villares" in lower
  case is still dropped.
- "Toril y Masegoso" (Teruel) has both halves as live municipios elsewhere
  (Cáceres, Albacete); two such names listed side by side in one list would
  fuse — no pliego lists those provinces together.

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

🟡 The browser-extension research prompt formerly at `tmp/es-grape-wikipedia-research-prompt.md`
(39 ES-corpus grape slugs with no `es.wikipedia.org` card) **no longer exists on disk**
(tmp/ cleaned; noted at reconciliation 2026-08-26). If the gap still matters, regenerate
the list against the current post-fetch state first — the synonym-aware 02b re-fetch and
the VIVC passes since then may have recovered several.

### Wikipedia ES pages — 29 missing/error parents — ✅ resolved

✅ (verified 2026-08-26) Superseded by the override mechanism shipped 2026-05-14
(see "Wikipedia AOC pages" in the France section): `raw/wikipedia/aoc_overrides.json`
carries 29 `es` entries — 8 pinned, 11 `missing`, 10 `not_aoc_topic` — covering
exactly this batch (urueña, ayles, campo-de-calatrava, bolandin, dehesa-penalba,
abadia-retuerta, rio-negro, rosalejo, islas-canarias among the negatives).

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
- **Terroir-fact quality fixes W1–W8** (2026-09-11): 02e preserve-list split, Alsace shared-cahier slicer, in-record dedupe, ellipsis-aware coverage, style normaliser, boilerplate filter, audit extension — full handoff in `docs/plan-terroir-facts-quality.md`.


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
- **Stage 04 write-time simplification is applied to the published geojson, not only the tiles** (found 2026-09-22 while verifying Saint-Estèphe) — `_simplify_for_tiles` (`TILE_SIMPLIFY_TOLERANCE` 0.0002° ≈ 22 m, 04_build_maps.py ~2660) runs before the feature is written, contrary to the comment at ~243-247; Saint-Estèphe ships 298 of 2,653 INAO vertices, Hausdorff 21.6 m, 1.13 % symmetric difference (palus lieux-dits INAO excludes appear partly inside), Grés de Montpellier −2 % area. `props.area` / `bbox` are computed *before* the pass, so they no longer describe the geometry they ship with (saint-estephe 0.0017848 vs 0.0017786 deg²). Either simplify per geom_source (parcellaire at a finer tolerance), or compute the props after, and fix the comment. Every FR parcellaire record is affected identically; ~3 px at the client's maxZoom 14.
- **`matched_via` defaults to "primary" for curator-pinned grape cards** — `scripts/_lib/lexicon_loading.py:170`; raw/wikipedia/grapes/fr/*.json written by the override path carry no `matched_via`, so an audit that trusts the field to find pinned cards misses the fr pins. Related guard worth adding to the grape audit: flag any slug whose Wikipedia card (page_url) is shared with a slug of a *different* VIVC berry colour — the fr "Trousseau" article was serving 9 slugs, one of them the gris (2026-09-22 Pineau feedback).
- **Grape-role disclaimer is PT-only** — app.js `role-disclaimer` is gated on `r.country === 'pt'`; FR records whose cahier lists no principal/accessoire split (Pineau des Charentes, all 14 shown as principal; blanc vs rosé/rouge lists and the 10 % trousseau-gris cap not surfaced) get no equivalent note.
- **SSR content block omits HU dűlők / IT menzioni** ([scripts/_lib/content_block.py](scripts/_lib/content_block.py)) — the Phase-3 server-rendered `<article id="ssr-content">` deliberately leaves out the Hungarian *dűlők* and Italian *menzioni / UGA* collapsible chip sections. They still render client-side via `renderDulok` / `renderMenzioni` in [scripts/_lib/map_template.py](scripts/_lib/map_template.py) (so users see them in the live panel; crawlers / no-JS do not). Port those two renderers to Python in `content_block.py` so the crawlable HTML matches the panel for HU/IT appellations. Low priority — niche chip data, the rest of the card is already server-rendered; left out initially because their per-record shape churns more than the stable fields.

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

### Geometry — ✅ DOPs / ✅ IGPs (reconciled 2026-08-26)

- **30 DOPs**: 23 via `caop-concelho-union` (commune-precise), 7 via `figshare-pdo`
  (Bétard 2022 EU_PDO.gpkg).
- **32 sub-regiões** inherit parent's polygon (`parent-appellation`).
- **14 IGPs**: ✅ all resolve `caop-concelho-union` — the CAOP commune-list parser
  ([scripts/_lib/pt/commune_list.py](scripts/_lib/pt/commune_list.py) +
  `PTPolygonIndex.union_from_parsed`) shipped; verified in the current build
  (e.g. `alentejano`, `tejo` → `geom_source=caop-concelho-union`). See the PT
  geometry chain in [CLAUDE.md](CLAUDE.md).

### Translation cache — ✅ moot for facts-covered records (reconciled 2026-08-26)

All 44 PT parents now carry 02d terroir facts (see below), and the 02c summary is
a fallback rendered **only** for records with no facts (facts-XOR-summary rule), so
the 02c round-trip below is only needed if a PT record ever loses its facts.

- PT records emit 76 translation jobs per locale via `02c_translate_summaries.py --source-lang pt --emit-todo`. Pipeline target locales for PT: en/fr/es/nl.
- Round-trip flow (matches user's existing FR/ES workflow):
  ```
  .venv/bin/python scripts/02c_translate_summaries.py --source-lang pt --emit-todo /tmp/pt-todo-en.json --lang en
  # external translator fills the items[].summary fields
  .venv/bin/python scripts/02c_translate_summaries.py --source-lang pt --import /tmp/pt-todo-en.json --translator-id <id> --translator-kind manual
  ```

### Terroir-fact extraction — ✅ siblings shipped (2026-05-16), ✅ run complete (44/44 PT fact files in `raw/terroir-facts/`, verified 2026-08-26)

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

### Wikipedia PT lexicon — ✅ run (44 cached pages at `raw/wikipedia/aocs/pt/`, verified 2026-08-26)

`scripts/02b_fetch_aoc_lexicon.py --lang pt --source raw/pt/cadernos-extracted/` has run;
the per-DOP pt.wikipedia cache is populated (44 files) and 27 curator override entries
exist under `raw/wikipedia/aoc_overrides.json["pt"]`.

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
use the older `Art. N` Decreto-Ministeriale header style instead
of `Articolo N`. Resolved 2026-05-27 by extending `_ARTICLE_HEAD_RE`
in [scripts/_lib/it/masaf.py](scripts/_lib/it/masaf.py) to
`(?:Articolo|Art\.)`. Verified safe (1/50 sampled existing MASAF
PDFs had line-start `Art. N`, and that one was previously failing
too). Combined with the 02f oj-pages-cache fallback, all 6 now
extract via curator-pinned PDFs.

🟡 **Disciplinare URL hunt — reconciled 2026-08-26: 9 → 1 remaining
(`salemi`).** The 2026-05-27 drop added 15 override URLs, of which 6
promoted out of stub state with clean disciplinare extraction
(colli-trevigiani, conselvano, marca-trevigiana, veneto,
veneto-orientale, valtenesi — the last one ships as a 2-article
correction-decree fragment, not a full disciplinare, but is correctly
attributed). Of the 9 bad-URL wines listed below, events since closed 8:

- **7 Abruzzo IGTs cancelled** (colli-aprutini, colli-del-sangro,
  colline-frentane, colline-pescaresi, colline-teatine, del-vastese,
  terre-di-chieti) — Commission Implementing Regulations (EU) 2026/558–708
  consolidated them into Terre Abruzzesi; filtered out of the corpus by
  the `CANCELLED_GIS` registry in
  [scripts/it/00_fetch_data.py](scripts/it/00_fetch_data.py) (531 → 524).
- **`gambellara`** — the MASAF bundle match later succeeded (sidecar
  fetched 2026-08-21 from `Disciplinari DOP (E-N)/Gambellara.pdf`,
  5 principal varieties); no override URL needed.
- **`salemi`** — still open: no parseable public source, itself pending
  cancellation; currently the only IT wine absent from the map.

Historical bad-URL table (kept for the patterns encountered):

| Slug | Bad URL pinned | Problem |
|---|---|---|
| `gambellara` | GU 2011-02-25 `caricaPdf?cdimg=11A0223000100010110005` | wrong document — the PDF at that `cdimg` is actually the *Salame Piacentino* DOP disciplinare (a cured-pork product), not Gambellara wine. Curator confused the `cdimg` page identifier |
| `colli-aprutini` | GU 2025-09-09 n.209 (consolidated) | not in the GU's TOC at all; consolidated GU is 40 pp of unrelated decrees |
| `colline-frentane` | GU 2025-09-09 n.209 | only mentioned in a *consortium-recognition* decree (25A04880), not a disciplinare |
| `colline-pescaresi` | GU 2025-09-09 n.209 | same — recognition decree only |
| `colline-teatine` | GU 2025-09-09 n.209 | same |
| `del-vastese` | GU 2025-09-09 n.209 | same |
| `terre-di-chieti` | GU 2025-09-09 n.209 | same |
| `salemi` | GU `caricaArticolo?...flagTipoArticolo=0` | returns HTML, not PDF. Try `flagTipoArticolo=1` (the same fix that worked for marca-trevigiana) |
| `colli-del-sangro` | MASAF detail HTML page | index page, not a disciplinare PDF. The Sept-2025 GU decree (25A04880) explicitly notes that the Consorzio tutela vini d'Abruzzo *failed* representativeness for this IGT — may be deregistered / dormant |

For `salemi` (the sole survivor): find a public, licence-clear
disciplinare URL and merge it into both
`raw/it/oj-pages/manual_overrides.json` and (if the URL is a PDF)
`raw/it/masaf-disciplinari/manual_overrides.json`. **Verify before
pinning** that the URL's content is the actual disciplinare di
produzione of the named wine (not a recognition / amendment /
consortium-management decree, and not a different product entirely) —
or wait out its expected cancellation. (The research prompt formerly at
`tmp/it-masaf-disciplinare-research-prompt.md` was cleaned from tmp/;
resurface from git history if needed.)

### MASAF article carver takes the last sottozona annex — ✅ fixed (2026-09-13)

`extract_articles` kept the **last** occurrence of each article number, so a consolidated disciplinare whose sottozona annexes restart at *Art. 1* yielded the last annex's summary / grapes / area / Art. 9 for the whole DOP (review 2026-09-12, R4). `extract_article_runs` in `scripts/_lib/it/masaf.py` now splits the header sequence into runs at every restart, drops a TOC run (all bodies < 200 chars) and a decree preamble bound in front of the disciplinare (Veneto IGT: five transitional articles whose Art. 1 never *reserves* the name), keeps the parent's own run and stores the later runs as the sidecar's `annexes` (`{title, article_bodies}` — "ALLEGATO 3 «MONTEPULCIANO D'ABRUZZO» SOTTOZONA «ALTO TIRINO»"). `parse_grapes_with` also lets a genuine roster phrase vouch for a slug first hit via the DOC name (Trebbiano d'Abruzzo → trebbiano-abruzzese was lost). Parser template bumped to `it-masaf-disciplinare-v2`; 02f re-run for all 522.

Result: 20 parents structurally corrected (Abruzzo grapes 2→17, Trentino 4→28, Colli Tortonesi 1→24, Langhe 1→14, Romagna 1→15, Terre di Cosenza 9→17, Friuli Colli Orientali 2→19; Montepulciano / Cerasuolo / Trebbiano d'Abruzzo + Abruzzo get the parent's Art. 9 lien) and, because the parent's real Art. 1 now names the sottozone, the stage-04 detector emits **77 sottozone in 17 parents** (was 38 in 10 — Romagna 16, Terre di Cosenza 7, Friuli Colli Orientali 5, Riviera Ligure di Ponente 5, Asti / Barbera d'Asti / Colli Tortonesi 2 each).

Open follow-ups:
- Sottozone whose parent Art. 1 does not enumerate them but whose annex titles do (Montepulciano d'Abruzzo 9, Abruzzo 4, Trentino 5 + Titolo II Trentino Superiore) — feed the `annexes[].title` roster to `extract_it_sottozone`, and ground each synthesized sottozona on its own annex Art. 9 (the Alsace `terroir_chapters` pattern) instead of inheriting the parent's bullets.
- `friuli-colli-orientali`: the detector merges «Schioppettino di Prepotto» and «Savorgnano» into one slug (`schioppettino-di-prepotto-savorgnano`) — a quote-splitting quirk in `_split_pattern_b_list`.

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

### IT new-grape VIVC pins — ✅ applied (verified 2026-08-26)

All 17 slugs below resolve in `raw/vivc/by-slug/` with exactly the listed
VIVC ids (spot-checked monica #7928, nuragus #8623, nero-di-troia #12819,
schiava-grossa #10823, oseleta #16537, francavilla #4217, invernenga #5536,
semidano #11479). See also the "VIVC grape resolution — ✅ closed
2026-06-03" section further down. Original research notes kept below.

Browser-research (2026-05-21) resolved VIVC variety numbers for the
new IT varieties whose slug-derived Wikipedia search missed (article
filed under a synonym, or no article).

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

### `ortrugo-dei-colli-piacentini` — ◑ investigated 2026-08-26: old table-template; content covered by MASAF

Investigation result: the cached EUR-Lex HTML is the **pre-2016
table-based OJ layout** (958 `class="table"`/`tbl-txt` cells, a single
`ti-grseq-1` occurrence) — a different parser family entirely, not an
anchor-regex tweak. Meanwhile the wine is content-complete through the
MASAF sidecar (grapes, articles 1/2/3/9, regione Emilia-Romagna,
`figshare-pdo` polygon), so nothing is missing on the map. Remaining
value of a real EU-OJ extraction is provenance polish only. Two Phase-2
options if ever wanted: (a) add IT to
[scripts/extract_register_fiches.py](scripts/extract_register_fiches.py)
`COUNTRY_CONFIG` and pull its register fiche (uniform template), or
(b) write a table-template slicer. Low priority.

### Complete-coverage pass residuals — ⏳ (2026-05-30; re-verified still open 2026-08-26)

The 2026-05-30 pass closed source-docs / map / grapes / terroir /
sub-denominations for IT. Residual curator items (all re-checked
2026-08-26: `catalanesca-del-monte-somma`, `grottino-di-roccanova`,
`valtenesi`, `osco`, `rotae`, `quistello` still carry 0 grapes in the
current build):

- **Regional registers — Molise + Lombardia not yet pinned.** 3 annex-
  reference IGTs draw from registers not yet sourced: `osco` + `rotae`
  (Molise) and `quistello` (Lombardia). Add their region register URL +
  template to `raw/it/regional-variety-registers/sources.json` (+ `igts`
  list) and re-run `02h_extract_regional_registers.py` → `04`. Lombardia's
  register is the BURL Serie Ordinaria n.27/2019 ZIP (manual download per
  the manual-downloads-ok convention); Molise needs a Regione Molise DGR.
- **Varietal / parse-quirk IGTs with no grapes** — `catalanesca-del-monte-
  somma` (single-variety IGP "Catalanesca"; its MASAF article 2 isn't
  detected so add Catalanesca to the lexicon + pin), `grottino-di-
  roccanova` (grapes under Article 1, no Articolo 2 in the PDF),
  `valtenesi` (modification-decree PDF, only articles 1+9 parsed). Each is
  a one-off MASAF-PDF structural quirk; recover by hand or a per-PDF tweak.
- **Salemi** (IGP, Sicily) — no parseable public source (1995 GU umbrella
  decree only; being absorbed into DOC Sicilia as a UGA, under a 2025
  cancellation request). Stays `stub-no-geometry`. If/when the EU formally
  cancels it, add to `CANCELLED_GIS` in `scripts/it/00_fetch_data.py`.
- **MGA/UGA cru polygons** — name-chips only (Barolo 169, Barbaresco 66,
  Soave 29, Chianti Classico 11, …). No licence-clear public GIS layer
  exists for the cru boundaries (researched 2026-05-30: all Consorzio-held
  / Masnaghetti-proprietary). Geoportale Piemonte's open layer is
  appellation-level only. Revisit if a Region publishes an open MGA layer.
- **New IT grape slugs** — the regional registers + Tuscan-natives pass
  added varieties (abrusco, barsaglina, foglia-tonda, orpicchio, …) that
  need a VIVC pass (`02g`) + grape-Wikipedia (`02b --only`) to gain pill
  tooltips. Fold any new unknowns from `raw/it/extraction-unknowns-masaf.json`.

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

### IT regione fallback — ✅ resolved (verified 2026-08-26)

The curated fallback shipped: `scripts/_lib/it/regione_by_file_number.json`
carries 165 entries and `derive_regione`
([scripts/_lib/it/region.py](scripts/_lib/it/region.py)) resolves the rest
from province/commune signals. Only **3** IT records in the current build
still render `region="Italia"` (was 353 of 408).
[scripts/audit_it_regions.py](scripts/audit_it_regions.py) cross-checks every
regione against the polygon. (The research prompt formerly at
`tmp/it-regione-research-prompt.md` is gone with the tmp/ cleanup.)

### Geometry — comune-list parser residue after the 2026-09-24 whole-province fix — ✅ fixed 2026-09-25

- ❌ **Island names are not expanded (found 2026-09-25 by the overlap audit).**
  Epomeo IGT delimits "l'intero territorio amministrativo dei comuni
  ricadenti nell'isola d'Ischia in provincia di Napoli" and is drawn as the
  whole province of Napoli (`gisco-provincia-union`); Pompeiano IGT is the
  province "esclusi quelli ricadenti nell'isola d'Ischia" and keeps Ischia.
  Fix: a small island → comuni table in `scripts/_lib/it/comune.py`
  ("isola d'Ischia" → Barano d'Ischia, Casamicciola Terme, Forio, Ischia,
  Lacco Ameno, Serrara Fontana; "isola d'Elba" is already a comune list in
  the Elba DOC) applied both as an inclusion and inside an exclusion
  clause. Until then the two Terre del Volturno pairs are whitelisted in
  `geometry_overlap_overrides.json` as the regulator's own IGT overlap.

`parse_geo_area` now keeps a whole province named beside a comune list as a
member (Rubicone 10 → 85 comuni, Daunia 3 → 64, Murgia 6 → 47;
`gisco-comune-provincia-union`). The three gaps below were fixed on
2026-09-25 together with two the outlier audit exposed — **Valle Belice**
drawn as the provinces of Agrigento + Palermo (Pantelleria, Lampedusa,
Ustica included) because one unresolvable three-word name ("Santa
Margherita Belice", ISTAT "… di Belice") burnt four misses and closed the
comune bucket, and the list not resuming after "in provincia di Agrigento
e Contessa Entellina". Exclusions subtract only whole units (a partial
marker in the clause — isole amministrative, fondi valle, area interna al
GRA, la parte — keeps everything; "esclusivamente" is not an exclusion; a
bracketed clause ends at its ")"); a bare "Provincia di X:" header opens
the list; an unresolved multi-word name is one miss; "art." / "n." do not
end the winemaking lookback; connector-less and j → i folds recover
"Concordia sul Secchia", "Santa Teresa di Gallura", "Gioiosa Jonica". 129
of 524 parses changed, 16 build-affected (Valle Belice 125 → 4 comuni,
Casauria 46 → 17, Roccamonfina 104 → 25, Tharros 87 → 78, Emilia-Romagna
IGT 120 → 77, Locride 13 → 22, Terre del Volturno 2 → 78, Provincia di
Nuoro 52 → 96 …); an Explore agent read the 16 texts against the new
lists: 15 better, 1 same-with-a-caveat (Arghillà's frazione "Archi"
matches Archi CH in the parse and is dropped by the regione filter),
none worse. Still missing there, recall not regressions: "Carpaneto P.no"
(abbreviated Piacentino), "Gallo" for Gallo Matese, "Baia Latina" /
"Cancello Arnone" (dropped "e"/"ed"), "Giugliano" for Giugliano in
Campania, Pecorara (merged into Alta Val Tidone, no GISCO row); Colline
del Genovesato is drawn from the comuni its boundary prose names (the
Tigullio coast comuni it never lists are still missing). Tests in
`tests/test_it_parser.py` (2026-09-25 block). The original notes:

- An **excluded** province is promoted: "ad esclusione dell'intero territorio
  della provincia di Ravenna" → member. Stop the quantifier lookback at
  esclus- / eccett- / ad eccezione. Related, pre-existing: exclusions are read
  as inclusions everywhere in this parser (Marsala "esclusi i comuni di
  Pantelleria, Favignana ed Alcamo", Rimini "ad esclusione dei comuni di") —
  both records are Bétard-resolved today, so nothing shows.
- The "territorio provinciale" branch has no winemaking-clause guard, and an
  "art." token ends the guard's lookback window early (only Costa Toscana uses
  the form, and it is geoportal-resolved).
- A comune list after a bare "provincia di X:" header with no `comuni`
  keyword is parsed into the province bucket and lost (Costa Toscana, Carso,
  Asolo Prosecco, Alta Langa shapes) — Costa Toscana therefore resolves as
  five whole provinces when the geoportal does not win.

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
| Umbria | ✅ active | CC-BY 4.0 | CKAN `package_search` → 19 per-appellation `.zip`/`.7z` shapefiles (`fetch_type: ckan_shapefiles`); 20 wines matched (all but Narni, which publishes no shapefile) |
| Puglia | ⏳ todo | IODL 2.0 | endpoint not reachable (SIT Puglia WFS/ArcGIS hosts 404 / login-gated) — needs the live WFS layer name |
| Abruzzo | ❌ fallback | custom, unconfirmed | portal SSL cert expired; stays on Bétard |
| Campania | ❌ fallback | unconfirmed | dataset page 404s; stays on Bétard |
| FVG, Sicilia, Sardegna, Emilia-R., Marche, Liguria, Basilicata, Calabria, Molise, Valle d'Aosta, Trento | ❌ fallback | — | no open zone layer found in the 2026-05-22 audit; stay on Bétard |

**6 of 7 tracked regions harvested → ~237 IT wines on official zone
polygons** (`geoportal-zone`); the rest fall back to Bétard. Puglia is
the one remaining to-do, not a skip — see the per-region notes and
[scripts/_lib/it/zone_sources.py](scripts/_lib/it/zone_sources.py).

Wines in fallback regions keep Bétard's whole-municipality polygon
(approximate, may overlap). The IGT polygon gap this section used to
note is closed: IGTs now resolve via the `gisco-comune/provincia/
regione-union` chain (2026-05-30 pass; 523 / 524 IT wines carry a
polygon — only `salemi` remains off-map).

### Sottozone detection — ✅ resolved via MASAF Article 1 (verified 2026-08-26)

The documento-unico scan indeed yields ~0 (sottozone live in the MASAF
disciplinare, not the EU doc). `synthesize_it_sottozone_records()` in
stage 04 now runs the [scripts/_lib/it/sottozona.py](scripts/_lib/it/sottozona.py)
detector over the MASAF sidecar `article_bodies` instead — **38 sottozone
across 10 DOPs** in the current build (Chianti 7, Vin Santo del Chianti 7,
Valtellina Superiore 5, Bardolino 3, Costa d'Amalfi 3, Cannonau di
Sardegna 3, Penisola Sorrentina 3, Cinque Terre, Lambrusco Mantovano,
Lago di Caldaro), each a first-class sub-denomination record.

### Consorzio / DO-organisation URLs — 🟡 417/523 merged (recounted 2026-08-26)

Research run (`research-gaps` skill, 17 web-research agents) resolved the
official consorzio di tutela / DO-organisation website per IT appellation,
giving the map cards FR/ES parity. Current `by_slug` coverage: **417 of
523** IT parents (initial 2026-05-21 drop was 344/531 pre-cancellations;
later merges + the Abruzzo-IGT cancellations moved both numbers). Merged
into [scripts/_lib/appellation_urls.json](scripts/_lib/appellation_urls.json)
`by_slug` (117 of 131 eAmbrosia-named consorzi + wines eAmbrosia
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

🟡 `montecarlo` — the promontecarlo.it 403 was re-checked on 2026-08-26
and **resolved as do-not-add** (domain repurposed); see the re-check
outcomes below.

❌ ~150 IT appellations have genuinely no consorzio di tutela (small IGTs,
older southern / island DOCs, region-wide umbrella IGTs) — permanent NONE,
not actionable. ⚠️ The enumerated list previously kept at
`tmp/it-consorzio-no-link.json` was **lost to a tmp clean** and none of it
was ever merged into `appellation_urls.json` as explicit nulls — so all 109
current gaps read as "unchecked" rather than "checked, none exists".
Re-deriving it (or recording the verified subset as `null`) is the
remaining IT task.


#### 🟡 re-check outcomes (2026-08-26)

- `montecarlo` — **resolved, do not add.** `promontecarlo.it` now
  answers 200 (the earlier 403 was UA-related), but the domain has been
  repurposed into a generic wine-content blog; the Consorzio Vini DOC
  Montecarlo page is gone. The existing `viavinariamontecarlo.it` entry
  stands.
- Molise cluster (`biferno`, `molise`, `pentro-di-isernia`, `osco`,
  `rotae`) — recorded as explicit `null`: recognition of the Consorzio
  di tutela e valorizzazione dei vini DOP/IGP del Molise was **revoked**
  (GURI n. 93, Apr 2022), so no consorzio exists. `tintilia-del-molise`
  keeps its own separate consorzio (`tintilia.it`).
- Umbria gaps (Assisi, Todi, Colli Perugini, Colli Altotiberini, Amelia,
  Lago di Corbara, Spello, Bettona, Cannara, Narni, Allerona) — the
  regional producers' body `umbriatopwines.it` names consorzi only for
  Montefalco, Orvieto, Torgiano and Todi (the last as "c/o Cantina
  Tudernum", no site). Confirms NONE; left unrecorded rather than nulled.
- `barbera-del-monferrato`, `calosso`, `cisterna-d-asti` — **not**
  covered by the Consorzio Barbera d'Asti e Vini del Monferrato: its own
  site lists 12 denominazioni and none of these three. Search snippets
  claiming otherwise are wrong.
- `penisola-sorrentina` (+ Gragnano / Lettere / Sorrento) — the
  Consorzio Produttori Penisola Sorrentina DOP was founded Nov 2023 (HQ
  Palazzo de Marini, Gragnano) but publishes no website. Stays 🟡.
- Federdoc (`federdoc.com/consorzi-aderenti/`, the national confederation
  of consorzi) was checked as a bulk source: its membership list is only
  ~90 consorzi, all of them already-covered flagships, and it publishes
  addresses + emails but no websites. **Not a useful bulk source for the
  remaining gaps.**

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

### AOC Wikipedia hints — ✅ closed: researched, rest pinned `missing` (verified 2026-08-26)

`scripts/02b_fetch_aoc_lexicon.py --lang de --source raw/at/dokumente-extracted`
resolves only 5 of 32 — de.wikipedia's Austrian wine-region articles
are general region pages (valley / Bundesland). The curator pass ran
(2026-05): the remaining AT slugs are pinned `missing` in
`raw/wikipedia/aoc_overrides.json["de"]` with per-slug research notes
(e.g. Wachau → the UNESCO-landscape article, Kamptal → the river
article, Leithaberg → the mountain-range article — none are DAC/wine
pages, so there is genuinely no `wiki` arm to pin). Same outcome as
CH/LU: terroir facts extract from the Einziges Dokument alone. Re-open
only if de.wikipedia gains dedicated DAC articles.

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

### ENOTNI DOKUMENT — ✅ 1 EU-OJ + 16 national-spec augmented (header reconciled 2026-08-26)

✅ `cvicek` (PDO-SI-A1561) — full extract from its EUR-Lex ENOTNI
DOKUMENT (OJ C/2026/256), 17 grape varieties.

✅ **Promoted 2026-08-26: `belokranjec` + `metliska-crnina` are now full
EU-OJ extractions — SI is 3 EU-OJ + 14 national-spec.** The due re-check
found both OJ-C publications (the Cviček path, exactly as predicted):
Belokranjec **OJ C/2026/3572** (6.7.2026, PDO-SI-A1576-AM01 approved
20.4.2026) and Metliška črnina **OJ C/2026/3598** (13.7.2026,
PDO-SI-A1579-AM01 approved 17.4.2026) — modernised consolidated ENOTNI
DOKUMENT texts. EUR-Lex URLs pinned in the overrides (WAF-free mirror:
Publications Office Cellar, `publications.europa.eu/resource/oj/C_2026035xx`
with `Accept: application/xhtml+xml` + `Accept-Language: slv`); fetched
via si/01 + the 01b Chromium bootstrap; si/02 extracted both (18 + 10
grapes, 2.7/2.4 KB lien); 02d re-grounded their terroir on the EU-OJ text
(10 + 8 facts) and 02e translated en/fr/es/nl. NB the two override
entries keep `specifikacija_url` for the old national-spec source — do
NOT run `si/01c --refresh` for these slugs (it would clobber the spec
cache with the EU-OJ page).

The remaining 14 content-stubs stay augmented by the MKGP/Uradni-list
national-spec layer (stage 01c/02f, shipped 2026-05-29 — see below);
`bela-krajina` additionally carries per-DOP terroir from the eAmbrosia
register fiche (2026-06-02 pass).

Historical detail (13 grandfathered DOPs + the 3 region IGPs had no
public single-document URL in eAmbrosia — only a non-fetchable
`Ares(...)` summary-sheet; the canonical source is the Slovenian
national specification, *specifikacija proizvoda*, MKGP).
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

**2026-05-29** — MKGP-national URL research via `/research-gaps`
(prompt + results at
[tmp/si-specification-research-prompt.md](tmp/si-specification-research-prompt.md)
and [-results.md](tmp/si-specification-research-results.md)) returned
**16 / 16 FOUND**, two source patterns: (a) 11 per-wine MKGP `.doc`
files at `gov.si/assets/ministrstva/MKGP/DOKUMENTI/HRANA/VINO/ZOP/S_<slug>.doc`
— `bizeljcan`, `bizeljsko-sremic`, `dolenjska`, `goriska-brda`, `kras`,
`metliska-crnina`, `prekmurje`, `slovenska-istra`, `stajerska-slovenija`,
`teran`, `vipavska-dolina`; (b) 5 HTML pravilniki on `uradni-list.si`
— `bela-krajina` (consolidated Pravilnik UL RS 49/2007, predpis 2634),
`belokranjec` (PTP Pravilnik UL RS 112/2022, predpis 2690), and the 3
PGIs `podravje` / `posavje` / `primorska` (all share the 2007 Pravilnik).
URLs + provenance notes pinned in
[raw/si/oj-pages/manual_overrides.json](raw/si/oj-pages/manual_overrides.json).

✅ **2026-05-29 — Phase 2 stage 02f shipped.** Stage 01c
([scripts/si/01c_fetch_specifikacije.py](scripts/si/01c_fetch_specifikacije.py))
fetches the 16 specs into `raw/si/specifikacije/<slug>.{doc,html}`
keyed by Content-Type (msword → .doc, html → .html); stage 02f
([scripts/si/02f_extract_specifikacije.py](scripts/si/02f_extract_specifikacije.py))
dispatches to one of two parser branches in
[scripts/_lib/si/specifikacija.py](scripts/_lib/si/specifikacija.py):
- **`mkgp-doc-v1`** — MS Word .doc converted via `antiword` running
  in a one-off Docker image
  ([scripts/si/Dockerfile.doc-converter](scripts/si/Dockerfile.doc-converter):
  ~120 KB on top of `debian:bookworm-slim`, build with
  `docker build -t owm-antiword:latest -f scripts/si/Dockerfile.doc-converter scripts/si/`),
  then a 9-section parser keyed on the SPECIFIKACIJA PROIZVODA
  template's numbered headers (1 Ime / 2 Opis vin / 3 Posebni
  enološki / 4 Opredelitev geografskega območja / 5 Največji donos /
  6 Sorte / 7 Povezava z geografskim območjem / 8 Veljavne zahteve /
  9 Pregledi). Section 6 splits `bele:` / `rdeče:` for the colour-
  hinted variety roster (all-principal, mirroring the EU template's
  flat shape). Style detection truncates at the `Tradicionalna
  imena` boilerplate so it doesn't over-tag with every predikat tier
  authorised in Slovenian wine law.
- **`uradni-list-pravilnik-2007`** — 4 wines (bela-krajina + 3 PGIs)
  share the consolidated Pravilnik o seznamu geografskih označb za
  vina in trsnem izboru. Parser walks the `5. člen` paragraphs to
  identify the wine region's okoliši, then walks Priloga 2 to
  extract per-okoliš `priporočene sorte` (→ principal) + `dovoljene
  sorte` (→ accessory). The PGI variant rolls every okoliš inside
  its wine region into one combined roster.
- **`uradni-list-pravilnik-2022-ptp`** — 1 wine (belokranjec) parsed
  from the shared Metliška črnina + Belokranjec PTP Pravilnik. Walks
  `\b\d+\. člen\b` (strict word boundary so genitive references
  don't false-positive) for Article 2 (značilnosti — paragraph 2 is
  Belokranjec), Article 4 (področje pridelave — shared area), and
  Article 5 paragraph 2 (enumerated 10-variety Belokranjec list).

`augment_si_records_with_specifikacija()` in
[scripts/04_build_maps.py](scripts/04_build_maps.py) merges the
sidecars into the in-memory stub records at load time; `_sources_for`
surfaces `specifikacija_*` provenance for the panel. Result: 16/16
SI stubs augmented; 11 MKGP-doc + 4 UL-2007 + 1 UL-2022-PTP;
**236 principal + 54 accessory** variety slugs across the corpus.
Per-wine principal min=1 (Teran) max=25 (Bizeljčan / Bizeljsko
Sremič). Every SI wine now carries a real variety roster + summary +
geo-area + (for the 11 MKGP wines) link-to-terroir on the map panel.

Re-runnable:
```
.venv/bin/python scripts/si/01c_fetch_specifikacije.py
.venv/bin/python scripts/si/02f_extract_specifikacije.py --all
.venv/bin/python scripts/04_build_maps.py
```

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

## Croatia

Country #7. 18 wine PDOs (no IGPs). Only Muškat momjanski + Ponikve
carry a fetchable EU-OJ JEDINSTVENI DOKUMENT; the other 16 are
grandfathered names.

### JEDINSTVENI DOKUMENT — 2 / 18 EU-OJ extracted

✅ `muskat-momjanski`, `ponikve` — full EU-OJ extracts.

### MPS national specifikacija — ✅ Phase 2 shipped (2026-05-29)

MPS-national URL research via `/research-gaps` (prompt + results at
[tmp/hr-specification-research-prompt.md](tmp/hr-specification-research-prompt.md)
and [-results.md](tmp/hr-specification-research-results.md)) returned
**16 / 16 FOUND** — every grandfathered PDO has its canonical
*specifikacija proizvoda* (per Reg. 1308/2013 čl. 94) published by the
Ministarstvo poljoprivrede at
`poljoprivreda.gov.hr/UserDocsImages/dokumenti/hrana/zastita_oznaka_izvrsnosti_vina/na_razini_EU/`
(listing page `/istaknute-teme/hrana-111/oznake-kvalitete/oznake-izvornosti-vina/229`).
14 `.doc`, 1 `.docx` (Primorska Hrvatska), 1 PDF (Dingač). No EUR-Lex
single document exists for any of them. URLs + provenance pinned in
[raw/hr/specifikacije/manual_overrides.json](raw/hr/specifikacije/manual_overrides.json)
(kept out of `raw/hr/oj-pages/manual_overrides.json` so the Dingač PDF
doesn't pollute the EU-OJ stage 01/02 path).

✅ Stage 01c
([scripts/hr/01c_fetch_specifikacije.py](scripts/hr/01c_fetch_specifikacije.py))
fetches the 16 specs; stage 02f
([scripts/hr/02f_extract_specifikacije.py](scripts/hr/02f_extract_specifikacije.py))
converts (.doc → antiword Docker `owm-antiword`, .docx → stdlib zip,
.pdf → pdftotext) and parses via
[scripts/_lib/hr/specifikacija.py](scripts/_lib/hr/specifikacija.py)
(lettered-section slicer a–j; grape colour markers Bijele/Crne sorte;
section g terroir). Stage 04
`augment_hr_records_with_specifikacija()` merges into the 16 stubs
in-memory. Result: **601 principal varieties** + **16 / 16 with
terroir source text** (the Primorska docx loses its lettered a–j
prefixes to Word auto-numbering → a keyword-title slicer recovers its
terroir + grapes). Effective extraction = **18 / 18**.

### Terroir-fact extraction (02d/02e) — ✅ done (2026-05-29)

HR 02d's `_resolve_lien_and_source` reads the specifikacija sidecar's
section-g text. Anthropic batch run (msgbatch_…ER6m / …Gtzt) produced
**213 bullets across all 18 wines** (6–15 each, incl. Primorska 7),
translated into en/fr/es/nl (18 × 4). Per-DOP `hr.wikipedia.org` pages
were already cached (18/18) for dual-source grounding.

### Grape vocabulary — ✅ 44 added + VIVC/Wikipedia wired (2026-05-29)

44 autochthonous HR varieties added to `GRAPE_ALIAS` / `DEFAULT_COLOUR`
in [scripts/_lib/grape_lexicon.py](scripts/_lib/grape_lexicon.py) with
regulator-assigned colours (from the Bijele/Crne sorte grouping) and a
research-agent VIVC/identity pass. 4 folds (Crljenak viški→tribidrag,
Brajda crna + Plavčina→plavina, Kavčina crna→zametovka). Grapes rose
**601 → 689**. `raw/hr/extraction-unknowns-specifikacije.json` is now
**empty** — `Bilan bijeli` + `Pošip crni` added as distinct slugs,
`croatina-crna`/`carmenere-crni` pinned to their base so they no longer
double-log.

✅ **VIVC + Wikipedia enrichment wired** — `grape_corpus.py` and
`02g_fetch_vivc.py` now also scan `raw/{hr,si}/specifikacije-extracted/`
(mirrors the IT-MASAF sidecar precedent), so spec-only varieties feed
the corpus. 02g resolved **12 HR VIVC IDs** (11 curator-pinned in
`raw/vivc/slug_overrides.json` — Plavina 9557, Blatina 1454, Cetinka
2407, Dobričić 3608, Gegić 4493, Glavinuša/Okatac 8728, Kujundžuša
6545, Lasina 6761, Smudna Belina 24912, Trnjak/Rudežuša 10327, Vranac
13179 — plus Sansigot→Suščan 12107 auto-resolved); Crljenak viški rides
Tribidrag 17636. 02b grape-Wikipedia landed tooltips for 6 varieties
from the en/fr/es/nl/pt/it locales (Plavina, Blatina, Dobričić, Gegić,
Vranac, Drnekuša).

✅ **hr-sourced grape tooltips wired (2026-05-30)** — `hr` added as a
source-only locale to `02b_fetch_grape_lexicon` LOCALES (alongside
pt/it), to `02b_translate_grapes` SOURCE_LOCALES + LOCALE_NAME, and a
`wiki_lang_hr` = "Wikipédia en croate" gettext label (filled in all 4
catalogs). The ASCII slug doesn't match the diacritic hr.wikipedia
title, so the correct titles are pinned in
`raw/wikipedia/grape_overrides.json["hr"]` (Blatina, Cetinka, Dobričić,
Kujundžuša, Lasina, Plavina, Pošip, Trnjak — found by probing
hr.wikipedia, only real grape articles kept). After the hr fetch +
`02b_translate_grapes --provider anthropic` (83 pairs), the
autochthonous varieties with an hr.wikipedia article — Kujundžuša,
Trnjak, Lasina (fully hr-sourced into en/fr/es/nl), plus Dobričić /
Plavina / Blatina (native + translated) — render tooltips in all 4
panel locales with a "Traduit de Wikipédia en croate · CC BY-SA 4.0"
attribution. The remaining autochthonous varieties genuinely have no
hr.wikipedia grape article (verified by probe); their pills render with
name + colour + VIVC canonical bracket, no tooltip. NB: `hr` is now in
the default grape-fetch LOCALES, so a future unfiltered 02b sweep
fetches hr for the whole corpus (mostly unused — the tooltip uses the
dominant-lang source) — use `--only` for surgical reruns.
`02b_translate_grapes` gained a `--batch` flag (2026-05-30, sidecar
`raw/.batch/02b-grapes.json`) so grape-tooltip translation runs via the
Anthropic/Mistral Batch API like 02c/02d/02e; `--batch` loads `.env`
(the sync `--provider anthropic` path needs ANTHROPIC_API_KEY exported).

### Teran cross-border note — ✅ done

`hrvatska-istra` carries the symmetric note to SI `teran` in
[scripts/_lib/appellation_notes.json](scripts/_lib/appellation_notes.json)
(Reg. (EU) 2017/1353 + GC Case T-626/17). No duplicate `teran`
appellation minted on the HR side.

## Hungary

Country #8 (added 2026-05-23; complete-coverage pass 2026-05-30). 41 wine
GIs (35 DOP + 6 PGI), **41 / 41 on the map (100 %)**, **41 / 41 with grapes**
(1292 slugs; 16 via the national termékleírás layer), **41 / 41 with terroir
facts** (368 bullets, translated en/fr/es/nl). Complete coverage on all
four axes: source documents, map, grapes, terroir.

### EGYSÉGES DOKUMENTUM + national termékleírás — ✅ 41 / 41 sourced

26 wines carry a fetchable EUR-Lex EGYSÉGES DOKUMENTUM (stage 02). The 15
grandfathered flagships (Tokaj, Villány, Sopron, Szekszárd, Pannonhalma,
Pécs, Bükk, Somlói, Nagy-Somló, Balatonfüred-Csopak, Csongrád,
Balatonboglár, Káli, + the Balatonmelléki and Zemplén PGIs) are now
backed by the **Agrárminisztérium national termékleírás PDF** via the
stage 01c/02f national-spec layer (`hu-termekleiras-v1` parser):

- Source: `boraszat.kormany.hu/termekleirasok2` (the leaf pages are JS
  shells; the real PDFs are opaque-token `/download/...` URLs — pinned in
  [raw/hu/national-specs/manual_overrides.json](raw/hu/national-specs/manual_overrides.json)).
  Tokaj uses the `tokajiborvidek.hu` council mirror. Public official act
  (Szjt. 1999. évi LXXVI. tv. §1(4) — úrhivatalos exemption).
- The PDF is the EU single-document template in Hungarian: Roman-numeral
  outline (IV. KÖRÜLHATÁROLT TERÜLET → communes, VI. ENGEDÉLYEZETT
  SZŐLŐFAJTÁK → grapes, VII. KAPCSOLAT A FÖLDRAJZI TERÜLETTEL → terroir).
  15/15 extracted with grapes + communes + terroir text.
- Fetch caveat: `boraszat.kormany.hu` serves an incomplete TLS chain that
  Python `requests`/`ssl` rejects; stage 01c shells out to `curl` (the
  codebase already shells out to pdftotext). If a download token rotates
  and a fetch 404s, re-pull from the leaf page `…/termekleirasok2/<slug>`.

✅ `soltvadkerti` (PDO-HU-02171) — was a routing miss, now fixed. Its EU
EGYSÉGES DOKUMENTUM uses the older template variant where section 8 is
titled "Kapcsolat a földrajzi területtel" (vs. the standard "A
kapcsolat(ok) leírása"); that title wasn't in the `link_to_terroir`
keyword table, so 5.7 KB of terroir text was dropped. Fixed in
[scripts/_lib/hu/egyseges_dokumentum.py](scripts/_lib/hu/egyseges_dokumentum.py)
(keyword added + blocklisted from geo_area). It now has 8 terroir facts.
Its single grape (Ezerjó) is **correct** — Soltvadkerti is a single-variety
Ezerjó appellation (section 7 is just `Ezerjó – <synonym>` lines).

### Geometry — ✅ 41 / 41 mapped

33 PDOs + the Balaton PGI resolve `figshare-pdo` (Bétard 2022, with
PGI-HU-A1507 bridged via the upstream mis-label PDO-HU-A1507). The 5 PGIs
(Balatonmelléki, Duna-Tisza-közi, Dunántúli, Felső-Magyarország, Zemplén)
resolve `region-pdo-union`. The 3 newer PDOs (`etyeki-pezsgo`, `koszeg`,
`fured`) that post-date Bétard now resolve **`gisco-commune-union`** —
[scripts/_lib/hu/commune.py](scripts/_lib/hu/commune.py) parses the
Egységes Dokumentum / termékleírás settlement list and unions the matching
Eurostat GISCO LAU `HU_*` polygons (0 unmatched: Etyek 1, Kőszeg 4,
Füred 10 communes). HU stage 02 now emits `geo_communes` per record.

### Dűlő / cru layer — ✅ Tokaj shipped (427); other formats Phase-2

The dűlő (named single-vineyard) layer is harvested from the termékleírás
MELLÉKLET by [scripts/_lib/hu/dulo.py](scripts/_lib/hu/dulo.py) (stage
02f → `dulok` in the sidecar → stage-04 augment → `dulok` in the aocs
blob). Following the IT menzioni/UGA decision, dűlők are a flat,
source-attributed **chip list** grouped by település (no per-dűlő
polygons — none exist publicly; Tokaj alone has 427), surfaced as a
collapsible "Dűlők (named vineyards): N" block on the map panel +
a `## Dűlők` wiki section.

✅ **Tokaj** — 427 dűlők across 27 települések (incl. aldűlők), parsed
cleanly from the canonical 3-column `… megnevezése` table.

⏳ **Phase-2 format variants** — only Tokaj uses the canonical 3-column
table. The other dűlő-bearing specs use layouts the v1 parser does not
attempt (a fragile parse that mis-attributes a dűlő to the wrong village
is worse than none):
- **Villány** — a "2-up" table (two `Borvidéki település | Dűlőnév`
  column-pairs per row, with carry-forward down empty cells + page-wrapped
  aldűlők). Needs column-offset slicing per half.
- **Szekszárd / Somló / Nagy-Somló / Balatonboglár / Eger / Csopak** —
  define dűlőnév *rules* (95 %-származás, yield caps) but either don't
  enumerate a list, or enumerate it in prose / a non-tabular form.
All 36 specs are now fetched (`raw/hu/national-specs/`), so the Phase-2
work is parser-only — no new fetches.

### AOC Wikipedia hints — ✅ cached (41 / 41 attempted)

`scripts/02b_fetch_aoc_lexicon.py --lang hu --source raw/hu/dokumentumok-extracted`
has been run; the per-borvidék hu.wikipedia cache is populated and feeds
02d salience.

### Grape vocabulary — ✅ seeded

Hungarian native varieties + crossings folded into `GRAPE_ALIAS` /
`DEFAULT_COLOUR` in [scripts/_lib/grape_lexicon.py](scripts/_lib/grape_lexicon.py):
Furmint, Hárslevelű, Olaszrizling (→ welschriesling), Kékfrankos (→
blaufrankisch), Kadarka, Kékoportó (→ blauer-portugieser), Cserszegi
fűszeres, Irsai Olivér, Királyleányka, Leányka, Juhfark, Ezerjó,
Tramini (→ gewurztraminer), Szürkebarát (→ pinot-gris), Csókaszőlő,
Kövérszőlő, Kövidinka, plus the native crossings Zefír, Ezerfürtű,
Zengő, Kabar, Bíborkadarka, Generosa, Rubintos, Csabagyöngye,
Zalagyöngye, Kunleány, Aletta, Medina, Zenit, Zéta, Patria, Domina,
Cirfandli (Zierfandler), Bakator family, Odysseus / Orpheus / Zeus,
Pannon Frankos (→ blaufrankisch), and ~20 others. Re-run
`scripts/hu/02_extract_pliegos.py` → `scripts/02g_fetch_vivc.py` after
any edit. The Monor doc's `**` bold-marker leakage + `(FONTOSABB)` /
`(EGYÉB)` role suffixes are now stripped in `parse_grapes` (and the role
markers drive a real principal/accessory split: Monor → 13 principal +
8 accessory). `badacsony` (PDO-HU-A1506) has an awkward EU doc where the
wine-type subsections (Késői szüretelésű / Jégbor / Töppedt) are numbered
as top-level sections 5–7, leaving its grape section unrouted; it is
backfilled (21 varieties) from its national termékleírás via the
fill-if-empty branch of `augment_hu_records_with_national_specs` (the
augment now enriches empty fields on non-stub HU records too, never
clobbering good EUR-Lex data).

The national-spec extraction (`raw/hu/extraction-unknowns-national.json`,
2026-05-30) added `sargamuskotaly` (one-word Sárgamuskotály →
muscat-blanc-a-petits-grains, fixes flagship Tokaj), `korai-piros-veltelini`
(→ `fruhroter-veltliner`, now VIVC #16157 + colour gris; Wikipedia tooltip
still a **miss** — the article is under the German title "Frühroter
Veltliner", curator-pinnable via `raw/wikipedia/grape_overrides.json`),
`goher` (Gohér — heritage white, Zemplén + Balatonboglár; VIVC *ambiguous*
→ curator pin pending in `slug_overrides.example.json`) and `banati-rizling`
(Bánáti rizling = Banat Riesling, VIVC #6501 KREACA; Somló + Nagy-Somló).
⏳ Still in the unknowns queue for a curator: `Zervin` (Badacsony —
uncertain identity/colour) and `Messiás` (Zala — EU-extracted, not
displayed). VIVC by-slug coverage of displayed HU grape slugs is now
113/113 (files; `goher` carries a null id pending the ambiguity pin).
The 3 newly-added slugs' Wikipedia tooltips miss (rare/German-titled) —
the same hu-native tooltip long-tail noted below. Residual unknowns there
are mostly **product-type labels** correctly excluded as non-grapes
(Classicus/Premium/Super Premium/Bikavér/Főbor/Jégbor/Késői szüretelésű/
Narancsbor/Gyöngyözőbor) plus a tail of rare HU natives and pdftotext
column-gluing artefacts (`Dornfelder Ezerfürtű`, `Syrah Szürkebarát`,
`Cabernet Francfranc`, `Cot (Malbec`, bare `Gohér` / `Bánáti rizling` /
`Csomorika`). Fold the genuine natives via `GRAPE_ALIAS` as the curator
confirms colours; the glued artefacts need no action.

### Wikipedia grape lexicon — 🟡 11 / 49 FOUND (2026-05-24)

49 HU-corpus grape slugs were never attempted in any of en/fr/es/nl
Wikipedia. After `/research-gaps grape-wikipedia`: 11 resolved
(22 per-locale overrides merged into
[raw/wikipedia/grape_overrides.json](raw/wikipedia/grape_overrides.json)
— `blaufrankisch`, `cserszegi-fuszeres`, `ezerjo`, `juhfark`, `kabar`,
`koverszolo`, `kovidinka`, `muscat-hambourg`, `sagrantino`, `zeta`,
`zierfandler`); 38 have no en/fr/es/nl article — most carry a
hu.wikipedia.org page that the project does not currently fetch.

⏳ **Phase 2 unlock** — mirror the PT pt.wikipedia translate-sidecar
pattern (CURATOR_TODO line 482) for hu. Without it the following stay
tooltip-less:

Native on hu.wikipedia (would fetch + translate cleanly):
`arany-sarfeher` · `bakator` · `biborkadarka` · `budai-zold` ·
`csokaszolo` · `ezerfurtu` · `jubileum-75` · `kunleany` · `medina` ·
`menoire` · `nektar` · `poloskei-muskotaly` · `pozsonyi-feher` ·
`rubintos` · `viktoria-gyongye` · `zalagyongye` · `zefir` · `zengo` ·
`zenit` · `zeus`

No Wikipedia article anywhere (VIVC-only — tooltip would stay blank):
`aletta` · `alibernet` · `csillam` · `csomor` · `duna-gyongye` ·
`gyongyrizling` · `meszikadar` · `odysseus` · `orpheus` · `patria` ·
`pintes` · `refren` · `rozalia` · `rozsako` · `turan` ·
`vertes-csillaga` · `vulcanus` · `zold-szagos`

Provenance: [tmp/hu-grape-wikipedia-research-prompt.md](tmp/hu-grape-wikipedia-research-prompt.md)
+ [tmp/hu-grape-wikipedia-research-results.md](tmp/hu-grape-wikipedia-research-results.md).

## Romania

### Complete coverage — DONE (2026-05-30)

**46 wine GIs (34 DOP + 12 IGP)** from eAmbrosia (de-duplicated;
earlier docs said 54 — that counted administrative re-registrations).
**v1 coverage is now 46 / 46 on the map, 0 stubs.** 32 wines extracted
from the EU-OJ DOCUMENT UNIC; the 14 grandfathered names (`Ares(…)`
only) are fully covered by the new **ONVPV national-spec layer**:

- ✅ **National-spec layer** (stages 01c/02f + [scripts/_lib/ro/caiet.py](scripts/_lib/ro/caiet.py)):
  14 ONVPV caiete de sarcini (PDF, `onvpv.ro`, WAF-free) pinned in
  `raw/ro/national-specs/manual_overrides.json`, parsed into sidecars,
  merged in stage 04 (`augment_ro_records_with_national_specs`). Each
  augmented wine carries 9–18 grapes, commune geometry, 7–10 terroir
  facts. See the RO national-spec section in [CLAUDE.md](CLAUDE.md).
- ✅ **Geometry**: 33 figshare-pdo + 13 gisco-commune-list = 46/46.
  The 2 grandfathered IGPs (Dealurile Transilvaniei, Viile Caraşului)
  resolve from the caiet's commune list. Section-routing for the newer
  Reg. 2024/1143 template + a density-based commune fallback fixed the
  3 IGPs (Dealurile Moldovei/Vrancei, Terasele Dunării) that previously
  failed to parse communes.
- ✅ **Terroir facts 46/46** (02d/02e Anthropic batch); ro.wikipedia is
  thin (43/46 curator-pinned `missing` — see CLAUDE.md), so RO grounds
  on the cahier/caiet text.

### Region facet — incremental file_number map (still open, low priority)

[scripts/_lib/ro/region.py](scripts/_lib/ro/region.py) carries the 8
Romanian wine macro regions. `_REGION_BY_FILE_NUMBER` is empty — every
wine resolves via the in-text scan or falls back to "România" (the
distribution looks correct in the audit). Optional curator pass:
hand-pin each wine's file_number → region for stable facet labels
(matches the AT / HR / HU pattern).

### Extraction-unknowns triage (2026-05-23)

98 unknown grape candidates curated into [scripts/_lib/grape_lexicon.py](scripts/_lib/grape_lexicon.py)
GRAPE_ALIAS / DEFAULT_COLOUR — 15 new canonical slugs (Alutus,
Arcaș, Aromat de Iași, Balada, Bătută Neagră, Codană, Columna,
Donaris, Golia, Miorița, Negru Aromat, Ozana, Unirea, Băbească Gri,
Rkatsiteli) pinned in [raw/vivc/slug_overrides.json](raw/vivc/slug_overrides.json).
After re-extraction one survivor remains, needing a curator look at
the source EU-OJ HTML:

- ✅ **Colinele Dobrogei — `Cristina N` — real variety (2026-08-26).**
  The brand suspicion is refuted: VIVC **#21045 CRISTINA** is a
  registered Romanian wine grape (noir, Chardonnay × Băbească Neagră
  marker-confirmed, bred at SCDVV Murfatlar by Ionescu/Oslobeanu,
  European Catalogue), and the citing document lists "Cristina N"
  inside its variety roster beside the sibling Murfatlar crossings
  Columna and Mamaia, plus in a per-variety yield row. Slug existed
  (`cristina`, noir, self-map); VIVC pin added in the 2026-08-26
  `/research-gaps vivc-ambiguous` pass.
- 🟡 **Dealurile Moldovei — `Zghihară neagră`**. VIVC's Zghihară de
  Huși #20281 is firmly white; no documented red biotype in
  wein.plus, Indigene, or Crameromania. Likely a typo for plain
  `Zghihară` (de Huși) or for a different red variety. Verify the
  source HTML; if a typo, fold via `GRAPE_ALIAS` to the correct
  canonical.

### Caiet-de-sarcini grape unknowns (2026-05-30, national-spec layer)

Surfaced by stage 02f over the ONVPV caiete
([raw/ro/extraction-unknowns-national.json](raw/ro/extraction-unknowns-national.json)).
The affected wines already carry their other 9–18 varieties + geometry
+ facts, so these are accessory-variety gaps, not blockers. Same
SCDVV-crossing pattern as the 2026-05-23 batch (uneven VIVC coverage;
wein.plus is the upstream-of-VIVC secondary source):

- 🟡 **Majarcă (albă)** — fuzzy-near `majarca-alba` (73). A real Banat
  white; add a `GRAPE_ALIAS` pin `majarca → majarca-alba` (the bare
  form drops the colour suffix).
- 🟡 **Astra / Blasius / Radames** — Romanian SCDVV breeding-station
  crossings, no current lexicon entry. Research VIVC/wein.plus IDs and
  mint slugs + `DEFAULT_COLOUR` like the prior 15.
- ⚪ **`Sortiment alb` / `Sortiment roşu`** — blend pseudo-varieties
  ("white/red assemblage"), correctly unmatched; add to a grape
  blocklist if the noise is bothersome (no false positive today).

---

## Bulgaria

Country #10. First Cyrillic-script country. 54 wine GIs total — 52 PDOs
+ 2 macro PGIs (Дунавска равнина / Тракийска низина = north / south
country halves). Only **3 of 54** wines carry a fetchable EUR-Lex
ЕДИНЕН ДОКУМЕНТ (melnik, nova-zagora, dunavska-ravnina); the other 51
are Art.107 / Reg.1308/2013 grandfathered names with no public
single-document URL — they ship as content-stubs that nonetheless
appear on the map because Bétard 2022 covers every BG PDO. Geometry
coverage is 100 % at v1 (52 figshare-pdo + 2 region-pdo-union).

### Cyrillic-handling infrastructure (2026-05-23, shipped)

- `unidecode>=1.3` added to [pyproject.toml](pyproject.toml).
- [scripts/_lib/grape_lexicon.py](scripts/_lib/grape_lexicon.py) `slugify`
  pre-`unidecode()`s Cyrillic input → Latin slug; Latin-script input
  invariant (verified against the FR/ES/PT/IT/AT/SI/HR/HU/RO corpora).
- [scripts/_lib/grape_entity.py](scripts/_lib/grape_entity.py)
  `_normalise` does the same — `match_variety` works on Cyrillic
  variety names (Мавруд / Гъмза / Широка мелнишка лоза…) by folding to
  Latin VIVC primes.
- BG-specific helpers preserve Cyrillic via `.casefold()` rather than
  ASCII-fold (see [scripts/_lib/bg/commune.py](scripts/_lib/bg/commune.py)
  + [scripts/_lib/bg/region.py](scripts/_lib/bg/region.py)).

### National-spec layer (ИАЛВ / IAVV) — ✅ shipped 2026-05-30

The 51 grandfathered stubs are now augmented from the ИАЛВ per-wine
продуктова спецификация PDF (eavw.com), resolved via `/research-gaps`.
Stages 01c (fetch) + 02f (extract) + stage-04 augment + 02d/02e
terroir. Result: **51/51 stubs augmented; all 54 BG wines carry grapes
(418 principal slugs) + 544 terroir bullets** (translated en/fr/es/nl).
URLs pinned in `raw/bg/national-specs/manual_overrides.json`. See the
"BG national specifikacija layer" section in CLAUDE.md. If an IAVV
UUID/CVID token rotates and a fetch 404s, re-pull the listing page and
refresh the URL, then re-run 01c → 02f → 04.

### Per-PDO Wikipedia AOC tooltips — ✅ researched, 54/54 NONE

`02b_fetch_aoc_lexicon.py --lang bg` resolves **0 of 54** because
bg.wikipedia covers Bulgarian wine GIs as town / landform articles, not
dedicated wine-region articles (wine is a marginal sub-topic). Confirmed
twice: a 2026-05 bulk pass pinned 52, and a 2026-05-30 `/research-gaps
aoc-wikipedia` delta pass verified the 2 macro PGIs (Дунавска равнина →
Danube-Plain landform; Тракийска низина → Тракия/Thrace) plus the 3
flagships (Мелник, Поморие, Сухиндол) — all NONE. All 54 are now pinned
`missing` in `raw/wikipedia/aoc_overrides.json["bg"]` so 02b stops
retrying. 02d therefore grounds on the IAVV spec text alone (no
Wikipedia salience); terroir bullets are unaffected (544 already
produced). Same pattern as el/de/it/pt/ro. Re-open only if bg.wikipedia
later gains dedicated wine-region articles.

### Grape vocab — 1 residual source typo (cosmetic)

`raw/bg/extraction-unknowns-specifikacije.json` carries one entry:
`Шардоне Димят` (liaskovets) — the IAVV PDF omits the comma between
two grapes. The 02f parser's whitespace-split fallback already
recovers both (chardonnay + dimyat), so this is logged-but-handled; no
alias needed. All other BG spec varieties resolve (18 natives + 9
international folds added to `grape_lexicon.py` on 2026-05-30).

### Per-PDO appellation_urls.json entries — ✅ closed + correctness fix (2026-08-26)

**54 / 54 resolve.** The earlier background sweep (`/tmp/bg-appellation-urls.json`,
since lost to a tmp clean) had merged 31 `by_slug` entries pointing at
**bg.wikipedia.org articles about the town** the PDO is named after
(Асеновград, Видин, Плевен, Ямбол, …) plus one winery article. The
sidepanel row those feed is literally *"Site officiel de
l'interprofession"* — a town encyclopedia article is the wrong kind of
thing there, so all 31 were **removed**, along with 4 entries pointing
at the state regulator ИАЛВ (already surfaced separately as the
national-spec source) and 2 pointing at `rlvk-burgas.com`, whose domain
**no longer resolves in DNS** (genuine link rot).

They are replaced at region level: the 5 `by_bassin` винарски район
entries now point at **НЛВК — Национална лозаро-винарска камара**
(`bulgarianwines.org`), Bulgaria's actual interprofessional body
(founded 2000, 5 regional chambers). `karlovo` keeps its РЛВК Тракия
(`rlvktrakia.com`) entry — a real regional chamber.

Not actionable: РЛВК Мизия (Pleven), РЛВК Черно море (Varna) and РЛВК
Пирин (Sandanski) have no discoverable websites; РЛВК Югоизточна
Тракийска (`rlvk-sliven.com`) is live but its per-PDO membership is not
published, so no per-slug binding is defensible.

### Cross-cutting: align IGP geometry patterns across countries — ✅ substantially closed (reconciled 2026-08-26)

Both formerly-unaligned buckets landed:

- **PT** — the 14 IGPs resolve `caop-concelho-union` (CAOP commune-list
  parser, [scripts/_lib/pt/commune_list.py](scripts/_lib/pt/commune_list.py)).
- **IT** — IGTs resolve via `gisco-comune-union` / `gisco-provincia-union`
  / `gisco-regione-union` (~81 IGTs; 523/524 IT wines carry a polygon,
  2026-05-30 pass).

Current per-country IGP strategies (all countries now reach a polygon;
no `none`/stub bucket remains):

| Country | IGPs | IGP strategy                 |
| ------- | ---: | ---------------------------- |
| FR      | many | INAO aires CSV (parcel)      |
| ES      |   43 | `gisco-commune-list` / ccaa  |
| PT      |   14 | `caop-concelho-union`        |
| IT      |  119 | `gisco-comune/provincia/regione-union` |
| AT      |    3 | `gisco-bundesland-union`     |
| SI      |    3 | `region-pdo-union`           |
| HU      |    5 | `region-pdo-union` (+1 Bétard-bridged) |
| RO      |   12 | `gisco-commune-list`         |
| BG      |    2 | `region-pdo-union`           |
| GR      |  114 | `gisco-nuts-region` (112) + commune-list (2) |
| DE      |   27 | `region-pdo-union` + `gisco-commune-union` |
| NL      |   12 | `nuts2-province`             |

Residual: this is now a naming/consistency nicety, not a coverage gap —
strategies differ by what each regulator's text legally delimits
(commune list vs region vs NUTS unit), which is intentional honest
precision, not drift.

## Greece

Country #11. 147 wine GIs (33 PDO + 114 PGI). Wikipedia tooltip
coverage is the thinnest of any country.

### Per-PDO Wikipedia AOC tooltips — research pass complete (2026-05-25)

31 PDOs researched via Wikipedia agent sweep: **4 FOUND**
(`nemea` → "Κρασί Νεμέας", `robola-kefallinias` → "Ρομπόλα Κεφαλονιάς",
`santorini` → "Βινσάντο Σαντορίνης" (caveat: covers only the Vinsanto
sub-style of the broader PDO), `monemvasia-malvasia` → "Μαλβαζία").
**27 PDOs pinned `missing`** — el.wiki has only locality articles for
flagships like Naoussa / Mantinia / Rapsani / Limnos / Paros etc.

### Per-IGP Wikipedia AOC tooltips — bulk-pinned NONE, revisit pending

114 GR PGIs (the Art.107/Reg.1308/2013 grandfathered VdP / Vins de Pays
names) were bulk-pinned as `missing` in
[raw/wikipedia/aoc_overrides.json](raw/wikipedia/aoc_overrides.json)
on 2026-05-25 without per-slug research — pattern confirmed by the
adjacent BG result (52/52 NONE) + GR PDO 27/31 NONE rate. Curator
todo: a future per-slug verification pass might recover ~5–10 % of
these (a handful of well-known PGIs like Πελοπόννησος / Μακεδονία /
Θεσσαλία / Κρήτη umbrellas could have el.wiki articles even when the
individual sub-area IGPs don't).

### Interprofession / consortium URLs — ✅ closed (2026-08-26)

**147 / 147 resolved.** 129 were already merged by the 2026-06 sweep
(114 → ΕΔΟΑΟ's `winesofgreece.org`, 15 per-PDO producer/consortium sites
such as `limnoswines.gr`, `kefaloniawinemakers.gr`, `cair.gr`,
`easamyntaiou.gr`, `monemvasiawinery.gr`). The residual 18 PDOs
(Μαντινεία, Ραψάνη, Σητεία, Πάτρα, Ζίτσα, Γουμένισσα, Αρχάνες, Δαφνές,
Πάρος, Αγχίαλος, Μεσενικόλα, Μαυροδάφνη Πατρών, Μοσχάτο Πατρών,
Μοσχάτος Ρίου Πάτρας, Χάνδακας-Candia, the 3 Malvasia PDOs) are closed
by adding **`by_bassin` entries for all 10 GR αμπελουργικές ζώνες** →
ΕΔΟΑΟ (Εθνική Διεπαγγελματική Οργάνωση Αμπέλου & Οίνου,
`winesofgreece.org` — confirmed operator). Region-level fallback also
covers any future GR wine; the 15 per-PDO `by_slug` entries keep
priority.

### National product specification (ΥΠΑΑΤ) — ✅ complete (2026-05-30)

`/research-gaps gr stubs` swept all 138 grandfathered stubs: **all 138
resolved**, **0 EUR-Lex** single documents. Pinned in
`raw/gr/national-specs/manual_overrides.json`; fetched by stage 01c; parsed
by stage 02f (`scripts/_lib/gr/specifikacija.py`) → 138 sidecars (all with
grapes), augmented into the map by stage 04.

- **132** found 2026-05-29 as national προδιαγραφή / τεχνικός φάκελος on the
  minagric four-w host `http://wwww.minagric.gr/greek/data/pop-pge/` (the
  `https://www.minagric.gr` host is Akamai-WAF-blocked; a VPN re-triggers it).
- **6** resolved 2026-05-30 via the **eAmbrosia public-API attachments**
  (`https://ec.europa.eu/geographical-indications-register/eambrosia-public-api/api/v1/attachments/<id>`,
  served HTTP 202 + a valid PDF). The minagric filenames weren't enumerable
  behind the 403 directory listing, but the EU Commission serves the same
  ΥΠΑΑΤ spec as a PDF attachment per GI. Browser-extension research pass.

| slug | file_number | eAmbrosia attachment |
|---|---|---|
| `rodos` | PDO-GR-A1612 | 9524 (EUGI00000007423) |
| `malvasia-handakas-candia` | PDO-GR-A1617 | 15926 (EUGI00000007481) |
| `malvasia-paros` | PDO-GR-A1607 | 9420 (EUGI00000007426) |
| `arkadia` | PGI-GR-A1331 | 16131 (EUGI00000007126) |
| `kos` | PGI-GR-A0981 | 3990 (EUGI00000005509) |
| `retsina-of-viotia` | PGI-GR-A1572 | 9132 (EUGI00000007281) |

**Reusable finding (all countries):** the eAmbrosia public-API
`/attachments/<id>` endpoint serves the "Product specification file" PDF
per GI directly from `ec.europa.eu` — a cleaner, WAF-free, licence-clear
(© EU) source than scraping national regulator sites. The attachment id is
on each GI's eAmbrosia detail page under Documents. Candidate to generalise
into stage 00/01 for any country whose national specs are hard to fetch.

### Geometry — the area-units layer (2026-09-24) — 🟡 residue listed

Since 2026-09-24 the resolver reads the ΥΠΑΑΤ spec's delimitation prose
(`scripts/_lib/gr/commune.py` `parse_area_units`, `scripts/_lib/gr/geometry.py`
`units_union`; CLAUDE.md "GR geometry resolution chain"). After the second
pass of the same day (the single-town records, the former επαρχίες, the
whole-prefecture texts): **60 PGIs** draw a GISCO LAU union (`how:
area-units`), **14** a curated prefix pin (`_GR_PGI_PREFIX`), 33 PDOs stay on
Bétard, **40 PGIs stay at NUTS level** — 31 by the spec's own NUTS line and
9 by the curated NUTS pin. Every GR record now carries a real region facet
(a LAU-union record reads it from the NUTS unit the spec cites, else from
the NUTS-3 units its polygon lies in — 43 records had fallen to "Ελλάδα"
when the first pass moved them off the NUTS step). Every flipped record was reviewed by independent
agents against the spec text and the GISCO table (packets under the session
scratchpad); the pin file `scripts/_lib/gr/commune_overrides.json` carries
57 record pins in 28 records plus the `eparchies` table (Θηβών, Μεγάρων,
Χαλκίδας, Καρυστίας — each from the el.wikipedia eparchy article and the
δήμος articles, refuted twice; the 1991 ΕΣΥΕ census settled the one
community, Μετόχι Διρφύων, that the Kymi unit carries for Χαλκίδας but not
Καρυστίας). What is left for a curator:

- **Source defect — `retsina-koropiou`**: the ΥΠΑΑΤ τεχνικός φάκελος of
  Ρετσίνα Κορωπίου pastes Ρετσίνα Καρύστου's delimitation ("τέως επαρχίας
  Καρυστίας" — southern Euboea, 60 km from Koropi). An empty pin keyed
  "επαρχία Καρυστίας" keeps the record on the curated NUTS pin (all of
  Αττική). The honest polygon is Δ.Κ. Κρωπίας (EL_49040000, 114 km²) — pin it
  only once a public text says so (Π.Δ. 514/1979, ΦΕΚ 157/Α, defines the
  zone; not fetched: et.gr is a JS gate).
- **Named units the commune layer does not carry (drawn without them,
  disclosed on the card as "not drawn")**: `gerania` — "όρους Γεράνεια" is
  the mountain, not a unit (the two Megara communities are drawn);
  `playies-egialias` — "Γουμένισσας (Βρυσαρίου)" is an alias in brackets,
  nothing missing; `playies-paikou` — Δ.Δ. Γερακώνας has no GISCO row (a
  settlement inside the Goumenissa unit, already drawn);
  `retsina-mesogion-attikis` — Σταυρού: no Attic community of that name in
  LAU 2024 (a locality of Παλλήνη / Γέρακας; EL_49090101 Γέρακα would be the
  container, not pinned); `tegea` — Δεμιρίου (the review could not confirm a
  rename to Λιθοβούνια; left out) and "Τεγέας" (the umbrella phrase);
  `playies-pentelikou` — Κουκουνάρι, Σταματοβούνι (unlocated vertices of
  the boundary line, see below). All harmless; pin only with a public
  source.
- **Approximate by design — `playies-pentelikou`**: the spec traces the
  boundary as a line through named places ("Δροσιά- Άνοιξη- Άγιος Στέφανος-
  Λίμνη Μαραθώνα – Αγ. Γεώργιος Βρανά – Κουκουνάρι – Σταματοβούνι –
  Διόνυσος – Δροσιά"); the record draws the polygon those places outline
  (`scripts/_lib/gr/landmarks.json`, six vertices from Wikidata items —
  village centre points, the reservoir's centre for Λίμνη Μαραθώνα, the
  village Βρανάς for its church; 34 km²), so the enclosed slopes with
  Σταμάτα and Ροδόπολη are inside. Two vertices are not located by any
  licence-clear gazetteer (Κουκουνάρι, a locality, and Σταματοβούνι, the
  hill above Σταμάτα — neither in Wikidata nor the GeoNames GR dump cached
  under `raw/geonames/`): the line runs straight from Βρανάς to Διόνυσος,
  which under-draws the south-eastern bulge, and the card lists both as not
  drawn. To finish it: add their coordinates to `landmarks.json` from a
  public source (GeoNames once added, or the map attached to ΥΑ
  443785/22.12.1993, ΦΕΚ 946/Β) and rebuild. Vertex precision is the
  settlement centre, not the decree's line through it.
- **Umbrella PGIs still at region level — `ipiros`, `sterea-ellada`,
  `peloponnisos`** ("όλες τις περιοχές της Ηπείρου για τις οποίες έχουν
  αναγνωρισθεί οίνοι ΠΓΕ και ΠΟΠ …"): the text is a cross-reference — the
  union of the member GIs' zones — not the whole region. The honest polygon
  is a region-union of the member records (the SI / HU PGI pattern) once a
  member table is curated per umbrella; today the NUTS-2 region is drawn.
  `thessalia`, `thraki`, `makedonia`, `kriti` use similar wording but were
  read as whole-region by two reviews (their sentences add "που
  περιγράφονται επακριβώς", i.e. every unit is already recognised).
- **Whole-prefecture texts whose NUTS-3 unit pairs two prefectures** are
  now prefix pins (Αργολίδα EL_41, Αρκαδία EL_40, Καρδίτσα EL_23, Κοζάνη
  EL_14, Λακωνία EL_43, Μεσσηνία EL_44, Θάσος EL_0401, Ικαρία EL_5401, the
  island of Euboea for `retsina-evias`); `mantzavinata` ("Διοικητικής
  περιοχής καταγωγής Κεφαλλονιάς") stays on EL623 Ιθάκη-Κεφαλληνία — the
  review read "administrative area" as the 1996 prefecture, which held
  Ithaca. A future spec naming Πρέβεζα, Άρτα, Τρίκαλα, Σάμος or Λήμνος alone
  needs the same pin (the pairs are EL541, EL611, EL412, EL411).
- **Accepted whole-unit precision, worth knowing**: `anavyssos` draws all of
  Δήμος Σαρωνικού for "στα νότια του Δήμου Σαρωνικού" (plus the Keratea unit
  for "the western side of Λαυρεωτική"); `klimenti` is one community (the
  spec's own section Γ: Δ.Δ. Κλημεντίου, 700–1000 m); `elassona` is the nine
  Δ.Δ. its section Γ lists, not the Kapodistrian unit; `lilantio-pedio` draws
  Δ.Κ. Χαλκιδέων whole for the locality Δοκός; `ilion` draws Δ.Κ. Ιλίου
  (8 km²) for the toponym «Πύργος Βασιλίσσης»; `metaxaton` draws Δ.Κ.
  Μεταξάτων for "Μοναστήρια Μεταξάτων"; `retsina-karistou` draws Skyros,
  which the former eparchy held; every altitude band (">200 m") is drawn as
  the whole unit. `paggeo` = the five former δήμοι = today's Δήμος Παγγαίου
  (EL_0503).
- **Review method to reuse**: the scratch probe resolves all 147 records in
  memory against the current build and diffs GISCO id sets; each flipped
  record gets a packet (text + matched rows + unmatched names) that an Explore
  agent reviews against `gisco-el-lau.json` (one row per line, grep by stem)
  and a second agent tries to refute per proposal; a completeness screen over
  the records still at NUTS level (six readers, a refuter per positive) found
  the whole-prefecture and eparchy cases above. Former δήμοι whose seat has
  another name are identified from the el.wikipedia article of the former unit
  (seat + community list matched one-to-one against the prefix's rows); a
  former επαρχία from the eparchy article plus each δήμος article, with the
  1991 ΕΣΥΕ census as the tie-breaker. Never pin from memory; a pin only for
  the container of a list widens the record (Δαφνουσίων, Δερβενοχωρίων were
  removed for that reason).

### Grape lexicon — GR natives needing aliases (recall gap)

Stage 02f logs unknown-variety candidates to
`raw/gr/extraction-unknowns-national.json`. Real Greek natives missing exact
lexicon aliases (so they only fuzzy-match, e.g. genitive `Σταυρωτού`) should
be folded into `GRAPE_ALIAS` / `DEFAULT_COLOUR` in
[scripts/_lib/grape_lexicon.py](scripts/_lib/grape_lexicon.py) — sieve the
unknowns file against real GR varieties (Αηδάνι/Aidani, Γαϊδουριά, Κατσανό,
Πλατάνι, Ποταμίσι, Ασπρούδες, …), distinct from the place-name prose noise.

---

## Slovakia

Country #13 (added 2026-05-24). 10 wine GIs (9 DOP + 1 PGI), all 10 on
the map.

### JEDNOTNÝ DOKUMENT — ✅ 4 / 10 extracted

6 content-stubs (`no-publication`): Východoslovenská, Južnoslovenská,
Nitrianska, Malokarpatská, Karpatská perla, Slovenská (PGI). Art. 107 /
Reg. 1308/2013 grandfathered names with only `Ares(...)` references in
eAmbrosia.

### National-spec layer — ✅ shipped (2026-05-30/31, stage 01c/02f)

All **6 / 6** stubs augmented. 5 from the **ÚPV SR** (Úrad
priemyselného vlastníctva SR / Slovak Industrial Property Office,
indprop.gov.sk) per-wine **špecifikácia výrobku** PDF (modern lettered
a–i template, `upv-sr-specifikacia-v1`) — researched + verified
2026-05-30 via `/research-gaps national-spec sk` (national-source +
EUR-Lex negative-check; 0/6 have an EU-OJ single document). The Phase-2
MPRV SR / slov-lex.sk lead was the WAF-blocked mirror; the WAF-free
register is ÚPV SR. Listing `…/OPVAZOV/specifikacie-op-zo/vina-a-liehoviny`,
URL pattern `…/swift_data/source/pdf/specifikacie_op_oz/<slug>.pdf`.
Result: 41–42 principal varieties each, 2.8–14.8 KB §g terroir each.

The 6th, **Karpatská perla** (`PDO-SK-A1598`), has NO spec on the ÚPV
register — but its canonical spec IS public on the **mpsr.sk** mirror
(`https://www.mpsr.sk/download.php?fID=15089`): the old 1996 ÚPV
*Prihláška označenia pôvodu* (application 0005-96), an OCR-scanned PDF
with the numbered `03.N` template + a flat §03.5 variety list. A second
parser branch `upv-sr-prihlaska-v1` handles it (numbered slicer + flat
list + targeted OCR repairs). mpsr.sk WAF-blocks bot UAs, so SK 01c uses
a browser UA. Result: **31 varieties + 6.9 KB §03.2/03.3/03.4 terroir
narrative → 4 terroir bullets**. Stage 04 augments all 6.

### Geometry — ✅ 10 / 10 mapped

8 of 9 SK DOPs resolve `figshare-pdo` (Bétard 2022). The 9th
(`PDO-SK-02856` TOKAJSKÉ VÍNO) resolves `figshare-pdo-alias` to the
Vinohradnícka oblasť Tokaj polygon (same Tokaj zone, different brand
registration). The single PGI `Slovenská` resolves `region-pdo-union`
(union of all 8 SK DOPs).

### Terroir facts — ✅ 10 / 10 extracted + translated

The 4 non-stub SK wines (Vinohradnícka oblasť Tokaj, Stredoslovenská,
Skalický rubín, TOKAJSKÉ VÍNO zo slovenskej oblasti) got 9–10 terroir
bullets each via Anthropic Batch API (2026-05-24). The 5 modern-spec
stubs (Malokarpatská, Nitrianska, Južnoslovenská, Východoslovenská,
Slovenská) got 9–10 bullets each grounded on the ÚPV §g narrative, and
Karpatská perla got 4 grounded on its 1996-prihláška §03.2/03.4 granite-
soil narrative (2026-05-30/31). **91 SK source bullets across all 10
wines**, translated en/fr/es/nl.

### Grape vocabulary — ✅ seeded (2026-05-24)

Slovak native varieties + crossings folded into `GRAPE_ALIAS` /
`DEFAULT_COLOUR`: Frankovka modrá (→ blaufrankisch), Svätovavrinecké
(→ sankt-laurent), Veltlínske zelené (→ gruner-veltliner), Tramín
červený (→ gewurztraminer), Müller Thurgau, Rizling rýnsky/vlašský,
Rulandské biele/šedé/modré, Modrý Portugal, Pesecká leánka (→ leanyka,
the SK name for HU Leányka — distinct from feteasca-regala despite
literature confusion), plus the VÚVV Bratislava crossings Devín,
Dunaj, Hron, Rimava, Váh, Nitria, Hetera. `karpatska-perla` carries
its own slug for the namesake PDO. **2026-05-30 national-spec pass**
added 6 more VÚVV/Pospíšilová crossings from the ÚPV §f tables, each
VIVC-anchored and distinct (own slug): Breslava (#1671, blanc), Mília
(#22818, filed blanc — VIVC berry-skin rose, Traminer-inherited),
Noria (#22819, blanc), Nitranka (#17282, noir), Rudava (#17283, noir),
Torysa (#22419, noir). The parser takes only the left **Odroda**
column, never the synonym column, so the Pesecká leánka ↔ Feteasca
regala confusion never reaches the matcher.

### Interprofession / consortium URLs — ✅ closed (2026-08-26)

**10 / 10 resolved.** 9 were already merged (ZVHV `zvvs.sk` per
vinohradnícka oblasť, `vcz.sk` for Skalický rubín, `tokajregion.sk` for
the Tokaj oblasť). The last gap, `tokajske-vino-zo-slovenskej-oblasti`,
now points at the same **Tokaj Wine Road Association** entry as
`vinohradnicka-oblast-tokaj` — the two PDOs are the same physical Tokaj
oblasť under different brand registrations.

### ΥΠΑΑΤ specs with sections pasted from another PGI — ❌ open (2026-09-12)

The national technical files reuse text across PGIs; the terroir facts inherit it (`docs/review-terroir-facts-2026-09-12.md`, R4):

| slug | pasted from | affected |
|---|---|---|
| `fthiotida` | ΠΓΕ Παρνασσός (names it; delimits Gravia / Elateia / Parnassos / Amfikleia above 350 m) | naturels facts #0–#4 |
| `peloponnisos` | ΠΓΕ Αχαΐα / Πλαγιές Αιγιαλείας / Αρκαδία (semi-sparkling section) | #0, #3–#6 |
| `retsina-evias` | Retsina Attikis (Mesogia, Markopoulo, MARKO cooperative) | human-factors facts |
| `ipiros` | Ioannina sparkling section; #5's 1972 recognition is Zitsa's | #5, #7, #8 |

Route: a foreign-name guard in 02d / the audit (source names another GI of the same country ≥ 3 × and its own 0 ×) so these sections are refused; curator note to ΥΠΑΑΤ optional.

## Czech Republic

Country #14 (added 2026-05-24). 13 wine GIs (11 DOP + 2 PGI), all 13
on the map.

### Register-fiche variety `Ryzlink buketový` — ✅ resolved 2026-08-26 (own slug, no fold, no VIVC)

Verification ran both checks: **absent** from Vyhláška 88/2017 Sb.
Příloha 2 (confirmed against the local cache — 67 varieties, no buket-*)
and **absent** from the ÚKZÚZ Státní odrůdová kniha (Přehled odrůd révy
2020: zero hits; eAGRI/trade sources cite it as the canonical example of
a *non-registered* zemské-víno variety). It IS a real legacy variety —
item ~20 of the old Vyhláška 323/2004 Příloha 15 list, **dropped by the
2017 decree** — surviving only in the register fiche §6 `**`/OTHER
legacy block (ceske + moravske). Identity is contested (cs.wikipedia →
Goldriesling VIVC #4884; the German Bukettriesling synonym chain →
Bukettraube VIVC #1611; NEITHER passport carries the Czech name), so per
the Cornalin/Humagne precedent it got its **own slug**
`ryzlink-buketovy` (blanc) in `grape_lexicon.py`, a `vivc_id: false`
pin in `raw/vivc/slug_overrides.json`, and the CZ register-fiche
re-extraction now resolves it (unknowns queue cleared). Note: CZ fiche
grapes feed only the terroir-text layer, not the map roster, so this is
queue hygiene + future-proofing, not a visible-pill change.

### JEDNOTNÝ DOKUMENT — ❌ 0 / 13 extracted

All 13 CZ wines are Art. 107 / Reg. 1308/2013 grandfathered names with
only `Ares(...)` references in eAmbrosia — **the worst single-document
coverage of any country in the corpus**. The structural alternative
shipped 2026-05-24: stage 02f extracts data from the Czech national
implementing decrees (Vyhláška 88/2017 + 254/2010 Sb.). See
"National-spec extraction" below.

### National-spec extraction — ✅ shipped (2026-05-24, stage 02f)

Two Czech wine-law decrees fetched, cached, and parsed by
[scripts/cz/02f_extract_national_specs.py](scripts/cz/02f_extract_national_specs.py):

- **Vyhláška č. 88/2017 Sb. Příloha č. 2** → national variety roster
  (35 white + 26 red + 6 zemské-víno = **67 varieties**, all 67
  resolved in the lexicon). Applied to all 13 CZ wines (Czech wine
  law does not restrict varieties per podoblast). Sidecar:
  `raw/cz/national-specs/varieties.json`.
- **Vyhláška č. 254/2010 Sb. Příloha** → per-podoblast obec lists
  (50/35/119/90/71/30 obce across the 6 podoblasti =
  **395 obce total**, 392 matched to GISCO LAU = **99.2 %**).
  Sidecars: `raw/cz/national-specs/communes/<slug>.json`.

Fetch source: zakonyprolidi.cz (eSbírka is a JS SPA, Sbírka scan-PDFs
are image-only). Canonical attribution: Sbírka zákonů částka 32/2017 +
částka 92/2010. Czech law text is public per §3(d) of the Czech
Copyright Act (úřední dílo).

### Geometry — ✅ 13 / 13 mapped, 6 at commune precision

- **6 podoblasti** (Litoměřická / Mělnická / Slovácká / Znojemská /
  Velkopavlovická / Mikulovská) resolve `gisco-commune-union-podoblast`
  — commune-precision via the Vyhláška 254/2010 obec list. More
  honest than Bétard's macro-region-aggregated polygon for these
  sub-regions.
- **2 macro DOPs** (Čechy / Morava) resolve `figshare-pdo` (Bétard
  2022).
- **2 macro PGIs** (české / moravské) resolve `region-pdo-union` (each
  = the macro PDO polygon of the same name, single-member union).
- **3 single-vineyard / single-varietal PDOs** (Znojmo, Šobes,
  Novosedelské Slámové víno) resolve `figshare-pdo` (Bétard 2022).

### Per-podoblast variety + terroir restriction — ⏳ Phase 2

The current shipped state attaches the same 67-variety national list
to all 10 wines that authorise jakostní víno (every PDO/PGI). Czech
wine law makes no per-podoblast restriction, so this is factually
correct — but the panel UX wins less than a per-AOC list would. A
future ÚKZÚZ or per-consortium "registered Leitsorten" per
sub-region could give a more useful principal split (much like the
DE BLE Produktspezifikation §3.2 split). Not blocking.

### Terroir text + styles — ✅ solved via SZPI CHZO specs (2026-05-31)

The earlier "structurally unavailable" verdict held only for the CHOP
(PDO) tier + the EU register. The **SZPI** publishes the two **CHZO
(PGI) product specifications** as licence-clear PDFs (úřední dílo) —
full EU-template specs whose section-1 region description (climate +
per-bioregion geology/soils) is the regulator's terroir narrative for
the Morava / Čechy wine region. Every CZ wine sits in one of the two
regions, so all 13 now ground their terroir on a regulator source:
`scripts/_lib/cz/chzo_spec.py` + stage 02f fetch
(`szpi.gov.cz/soubor/specifikace-chzo-{moravske,ceske}.aspx`) →
`cz/02d` grounds on `region_terroir_text` → **7–10 terroir facts on
all 13 CZ wines** (en/fr/es/nl). Styles: the 2 PGIs get the real CHZO
roster (sparkling / semi-sparkling / vin-de-liqueur); the CHOPs +
podoblasti get grape-colour-inferred white/red/rose (+ vin-de-paille
for Novosedelské Slámové víno). Phase-2 polish: per-podoblast
terroir text (split section 1.2's bioregion prose by podoblast) to
de-duplicate the macro/PGI shared bullets.

### Grape vocabulary — ✅ seeded (2026-05-24)

All 67 varieties in Vyhláška 88/2017 Sb. Příloha č. 2 resolve:
shared international varieties (Müller Thurgau, Chardonnay, Sauvignon,
Cabernet Sauvignon, Cabernet Moravia, Hibernal, Solaris, Zweigeltrebe
→ zweigelt, …) folded to canonical slugs; Czech registry-only
crossings (Děvín, Erilon, Florianka, Lena, Malverina, Medea, Mery,
Muškát moravský, Rulenka, Svojsen, Tristar, Veritas, Vesna, Vrboska,
Agni, Fratava, Jakubské, Kofranka, Nativa, Sevar, Pálava, Aurelius,
André, Neronet) get own slugs in
[scripts/_lib/grape_lexicon.py](scripts/_lib/grape_lexicon.py).
Zemské-víno-only varieties (Bílý Portugal, Modrý Janek, Ranuše
muškátová, Šedý Portugal, Tramín žlutý, Veltlínské červenobílé) also
seeded.

### AOC Wikipedia hints — ✅ fetched (2026-05-24)

`scripts/02b_fetch_aoc_lexicon.py --lang cs --source raw/cz/dokumenty-extracted`
shipped 8 of 13 cs.wikipedia.org pages on first run; 4 errors + 1
missing — likely title-disambiguation drift (curator pass to pin the
correct `(víno)` / `(vinařská oblast)` titles via the AOC-override
mechanism is open but not blocking).

Provenance: [tmp/cz-specification-research-prompt.md](tmp/cz-specification-research-prompt.md)
+ [tmp/cz-specification-research-results.md](tmp/cz-specification-research-results.md).

### Interprofession / consortium URLs — ✅ closed

**13 / 13 resolved** (merged in the 2026-06 sweep, verified 2026-08-26).
Národní vinařský fond's `vinazmoravyvinazcech.cz` per-region /
per-podoblast encyclopedia pages cover the macro names and the six
podoblasti; VOC bodies (`vocznojmo.cz`, `vocmikulovsko.cz`) cover the
Znojmo / Mikulovsko denominations.

## Switzerland

Country added 2026-05. 63 AOC entries across 26 cantons.

### Interprofession / cantonal-association URLs — ✅ closed

**75 / 75 resolved** (merged in the 2026-06 sweep, verified 2026-08-26)
via `by_bassin` entries for all 6 Swiss wine regions: Valais → IVV
(`lesvinsduvalais.ch`), Vaud → OVV (`ovv.ch`), Genève → OPAGE
(`geneveterroir.ch`), Ticino → Ticinowine, Trois-Lacs → Neuchâtel Vins
et Terroir, Deutschschweiz → BDW. Every Swiss AOC — including the 22
Geneva premier crus and the VS Grand Cru commune sub-records — resolves
through its region. Per-AOC `by_slug` overrides remain possible if a
premier-cru or Lavaux/Dézaley/Calamin body publishes its own site.

## Germany

Country #12. 46 wine GIs (19 PDO + 27 PGI).

### BLE Produktspezifikation — Anbaugebiete ✅ + Landwein ✅ Phase 2 shipped (2026-05-30)

Stage 02f parses two BLE Produktspezifikation categories (both
*Amtliches Werk §5 UrhG*, fetched in stage 00 into the shared
`raw/de/produktspezifikationen/`, tagged `category` in the manifest):
- **13 Anbaugebiete** (quality-wine PDOs) — principal/accessory role
  split from §3.2 Mindestmostgewicht (9 of 13 split, 4 flat).
- **15 Landwein g.g.A.** (the stub PGIs with no fetchable EU Einziges
  Dokument) — `landwein_spezifikation.py` lexicon-scan parser.
  **15 / 15 augmented**: 38-160 varieties + 1.3-4.3 KB Zusammenhang
  terroir text each; 185 terroir bullets (4-10/wine) extracted via
  02d-batch + translated en/fr/es/nl via 02e-batch (2026-05-30).
  Geometry already resolved via `region-pdo-union` (DE_PGI_MEMBER_PDOS).

### Großlagen sub-denominations — ⏳ Phase 2

The Weingesetz Großlagen (Bocksbeutel, Niersteiner Gutes Domtal, …)
are conceptually sub-denominations of their Anbaugebiet but live only
in the Weinverordnung Anhang 1 + BLE Weinlagen-Verzeichnis (not
eAmbrosia). Phase 2: per-source parser to emit them as parent/sub
records (mirrors the IT MASAF / ES MAPA pattern).

### Multi-Bundesland Landwein geometry — ◑ partially shipped (2026-05-30)

`gisco-commune-union` step added to the DE geometry chain: curated
`DE_LANDWEIN_AREA` (BLE Produktspezifikation §3) → whole-Kreis union by
AGS prefix + named-Gemeinde match against GISCO LAU.
- ✅ **Brandenburger Landwein** (PGI-DE-A1281) — 188 communes, 13,093 km²
  (6 Landkreise + 4 kreisfreie Städte + 7 Gemeinden; Meseberg→Gransee).
- ⏳ **Mecklenburger / Schleswig-Holsteinischer Landwein** (+ any future
  multi-Bundesland Landwein still on `stub-no-geometry`): transcribe
  their §3 area into `DE_LANDWEIN_AREA` and add the Land's Kreis-AGS
  rows to `_DE_KREIS_AGS` (currently only Brandenburg's 18 Kreise).
  Mitteldeutscher is already covered via `region-pdo-union`.

### Landwein grape vocabulary — ✅ pass done (2026-05-30)

5 genuine varieties the Landwein/Anbaugebiet BLE specs name were folded
into [grape_lexicon.py](scripts/_lib/grape_lexicon.py) + VIVC-resolved
(02g, all `exact-cultivar`): **Serena** (VIVC #4739, white PIWI),
**Reberger** (#19999, Regent × Lemberger, red), **Blauer Affenthaler**
(#79 AFFENTHALER, old Württemberg red); **Roter Müller Thurgau** →
`muller-thurgau` and **Roter Räuschling** → `raeuschling` (colour
mutations of existing cultivars). Wikipedia tooltips mostly absent for
these (obscure) — VIVC link is the citation surface.
- ⏳ Still raw (correct per v1 policy — anonymous breeder codes, no
  VIVC/Wikipedia): `Gf-Ga 52-42`, `VB Cal 1-22`, `B i`. Queue in
  `raw/de/extraction-unknowns-produktspezifikation.json`.

### 19 grandfathered names without an EU single document — ⏳ Phase 2

Grapes + terroir for the grandfathered Anbaugebiete are covered by the
BLE Produktspezifikation layer; what's still missing is the EU-OJ
narrative-section data. Curator path: `regen_manual_overrides_template.py`
→ pin a EUR-Lex OJ-C URL if one is published.

## Malta

Country #18, added 2026-05-31. 3 wine GIs (2 DOP + 1 IGP); all 3 on the
map. First English-source corpus (`source_lang="en"`).

### Coverage — ✅ complete

- Malta `PDO-MT-A1630` + Gozo `PDO-MT-A1629` — EU-OJ English SINGLE
  DOCUMENT extracted (sections 1–9, ~30 varieties each).
- Maltese Islands `PGI-MT-A1631` — `no-publication` content-stub;
  resolves geometry via `region-pdo-union` (Malta ∪ Gozo). 1-entry
  curator queue; pin a EUR-Lex OJ-C English SINGLE-DOCUMENT URL in
  `raw/mt/oj-pages/manual_overrides.json` only if the Commission ever
  publishes one (no action required for v1 — it is on the map).

### Terroir narrative — ✅ closed: Wikipedia-only (no regulator source exists)

Investigated 2026-05-31. The two PDO publications are STANDARD AMENDMENT
communications whose section 8 reads "No amendments are to be carried
out in this section." — and this is **not** a language artifact: the
Maltese-language version says the same ("Ma għandha ssir l-ebda emenda
f'din it-taqsima"). The full national specs **are** publicly fetchable
(clean PDFs via `legislation.mt/getpdf/<id>`, no Playwright needed):
- **S.L. 436.07** "D.O.K. Wines Production Protocols" — varieties /
  yields / winemaking practices; **no terroir narrative**.
- **S.L. 436.05** "Denomination of Origin & Geographic Indications" —
  GI framework regulation; soil/climate appear only as a generic legal
  definition, not a Malta/Gozo-specific description.

So the Maltese regulator publishes **no appellation-specific terroir
prose** anywhere (the CH situation). The EU single-document section 8
was never populated (Malta's 2009 protection predates the EU
single-document regime; AM01 is the first one and deferred section 8).
**Decision:** terroir stays Wikipedia-grounded (CH/LU pattern); this is
the honest narrative surface, not a fixable gap.

Optional future enhancement (NOT a terroir fix): a national-spec layer
(stage 01c/02f, `legislation.mt/getpdf`) could pull S.L. 436.07's wine-
style descriptions + variety/yield rules to replace the amendment-
boilerplate summary and add regulator-grounded data. Licence: Maltese
legislation © Govt of Malta — verify reuse terms before ingesting.

### Indigenous varieties — ✅ fully enriched (2026-08-26)

Ġellewża (red) + Girgentina (white) folded into `grape_lexicon.py`
(`DEFAULT_COLOUR` + `GRAPE_ALIAS`). Enrichment ran 2026-08-26: VIVC
resolved exact-cultivar for both — **Ġellewża #14174**, **Girgentina
#17787** — en.wikipedia cards fetched (both exist) and translated into
fr/es/nl via the 02b translate sidecar. Pills now carry colour, VIVC
bracket/link, and tooltip in all four locales after the next stage-04
rebuild. (Prerequisite fix: `raw/mt/dokumente-extracted` was missing
from the 02g corpus walk — see the cross-country corpus-walk note.)

## Cyprus

### Coverage — ✅ complete (2026-05-31)

11 wine GIs (7 PDO + 4 PGI). All 11 are Art.107 grandfathered names with
no fetchable EU-OJ Ενιαίο Έγγραφο; all augmented from the moa.gov.cy
Department-of-Agriculture τεχνικός φάκελος (stage 01c scrapes the
«Αμπελουργία / Οινολογία» listing + name-matches; stage 02f parses the
Greek single-document PDF, OCR'ing the image-only ones). 11/11 on the map
(7 Bétard PDO + 4 GISCO district-union), 11/11 with grapes (226 slugs),
8/11 with terroir facts.

### Terroir text — ✅ closed (2026-05-31, browser-research)

The 3 image-only moa.gov.cy scans (`pitsilia`, `larnaka`, `lefkosia`)
were replaced by the **text-layer τεχνικός φάκελος on the EU eAmbrosia
public attachments API** (Ares(2011)1411840 / 1411809 / 1411819), pinned
in `raw/cy/national-specs/manual_overrides.json` (eAmbrosia serves these
under HTTP 202 + body — `cy/01c.fetch_one` accepts 200/202). All 3 now
parse as text-layer with a selectable §7 ΔΕΣΜΟΣ section; **11/11 CY wines
now carry terroir facts (73 bullets)**. The OCR fallback in
`_lib/cy/specifikacija` remains for any future image-only spec.

### Indigenous varieties — ✅ (2026-05-31, VIVC/wein.plus research pass)

Cypriot natives folded into `grape_lexicon.py` (`DEFAULT_COLOUR` +
`GRAPE_ALIAS`, Greek-script + Latin-spec spellings): xynisteri, mavro,
maratheftiko (+ vamvakada/pampakada synonyms), giannoudi, ofthalmo,
promara, morokanella, spourtiko, vlouriko, kanella, vasilissa, vertzami
(lefkada folds here), mavrotragano, mavrathiro. Synonym folds: malaga →
muscat-d-alexandrie, μοσχάτο-κύπρου → muscat-a-petits-grains. Residual
flags: `vlouriko` colour (sources split white/red — shipped noir per
wineriesofcyprus); `mavrathiro` identity weak (likely Santorini, low
conf); VIVC IDs not yet pinned for giannoudi/ofthalmo/promara/kanella/
vasilissa (not catalogued under searchable Latin names) — optional 02g
enrichment, pills render with colour but no VIVC bracket.

### Interprofession / consortium URLs — ❌ none exists (recorded 2026-08-26)

All 11 CY wines are now **explicit `null`** in `by_slug` (the ES
`campo-de-cartagena` / `murcia` precedent) so the lookup is not retried
blindly. Cyprus abolished the Συμβούλιο Αμπελοοινικών Προϊόντων (Vine
Products Council) and has no interprofessional body — per-PDO or
national. The competent authority is the Department of Agriculture's
Αμπελουργία/Οινολογία branch, which the panel already links as the
national-spec source, so pointing the "interprofession" row at it would
be duplicative and mislabelled. `cypruswines.com` is a private
commercial guide; WINECORE is a 17-winery project consortium; the Cyprus
Oenophile Association is a consumer club. Re-open if a producers'
interprofession is constituted.

⚠️ Related link rot: `moa.gov.cy` now 301-redirects to `gov.cy/moa/`
(and `gov.cy` 403s to bots). 8 of the 11 CY national-spec source URLs
still point at `moa.gov.cy`; the PDFs are cached, so nothing is broken
today, but a `--refresh` would fail. The other 3 already moved to
eAmbrosia attachments.

## United Kingdom

Added 2026-09-06 (country #19). The UK is the corpus's cleanest register:
**6 / 6 registered wine GIs extract**, all with a public product
specification, all on the map. There is no missing-document queue.

### Open — pending application

| name | kind | applied | status |
|---|---|---|---|
| The Crouch Valley | PDO | 2023-03-06 | ❌ still in assessment on the GOV.UK register |

When it is granted: re-run `scripts/gb/00_fetch_data.py` (it picks the
name up automatically), then add its file number to
`_FILE_NUMBER_BY_SLUG` in [scripts/gb/00_fetch_data.py](scripts/gb/00_fetch_data.py)
and a geometry entry to `GB_COUNTY_TERRITORY` in
[scripts/_lib/gb/geometry.py](scripts/_lib/gb/geometry.py) (the Crouch
Valley is in Essex). Stage 00 warns when a registered wine has no file
number, because region + geometry both key on it.

### Open — Darnibole boundary (approximate by construction)

`PDO-GB-N1636` renders as the convex hull of the seven parcel centroids
decoded from its specification's own plan — 6.1 ha against a declared
5 ha, correctly sited on the verified south-facing slope, and disclosed
in the panel as approximate. It interpolates between centroids rather
than tracing the red boundary line, so its edges sit inside the true
boundary by up to ~half a field. To improve it, a curator would need
either (a) the RPA/OS parcel polygons for those seven ids, or (b) a
georeferenced trace of the plan's red line. Neither is currently
available under a public licence. Full derivation + the three-way anchor
check: [scripts/_lib/gb/darnibole.py](scripts/_lib/gb/darnibole.py).

### Curator inputs recorded 2026-09-06 (files under `raw/` are gitignored)

VIVC pins added to `raw/vivc/slug_overrides.json` for the seven varieties the
UK rosters introduced (3 resolved automatically — cascade #2139,
roter-veltliner #12931, fruehgipfler #4269):

```
madeleine-angevine -> 7062     madeleine-sylvaner -> 7070
triomphe-dalsace  -> 12650     gagarin-blue -> false
```

`madeleine-angevine` and `madeleine-sylvaner` are ambiguous in VIVC's
cultivarname search (Oberlin / 4N forms, and GEILWEILERHOF 3-28-51
respectively); `triomphe-dalsace` never auto-matches because the slug strips
the apostrophe from TRIOMPHE D'ALSACE, and VIVC also binds the bare surface
"Triomphe" to DODRELYABI #3616; `gagarin-blue` is a verified absence (no VIVC
accession — a black Russian/Caucasus cultivar documented by the RHS plant
register).

Wikipedia grape-tooltip pin in `raw/wikipedia/grape_overrides.json`:
`triomphe-dalsace` -> "Triomphe d'Alsace" (en + fr), same apostrophe cause.
5 of the 7 now have tooltips; `madeleine-sylvaner` and `gagarin-blue` have no
article in any locale (verified) and are deliberately left as misses.

Wikidata suppressions in `raw/wikidata/slug_overrides.json`: `english-wine`
and `welsh-wine`. en.wikipedia redirects both "English wine" and "Welsh wine"
to the umbrella article *Wine from the United Kingdom* (Q1467810), so the
sitelink path resolved BOTH PDOs to that one QID. Q1467810 is the topic, not
either PDO, and `sameAs` asserts identity — so it is suppressed until Wikidata
has per-PDO items. Sussex keeps its own Q39056976 ("Sussex wine").

Geometry-outlier whitelist (checked in, `scripts/_lib/geometry_outlier_overrides.json`):
all four national GB records, whose detached parts are the Isles of Scilly
(England) and the Anglesey islands (Wales) in the ONS country polygons.

### Open — "Findling" binds to Bouvier via VIVC

The English + Welsh rosters list *Findling*, which `match_variety`
resolves to `bouvier` on an **exact** VIVC synonym (VIVC #1625 BOUVIER
carries FINDLING). In a UK context Findling is far more likely the
Müller-Thurgau seedling grown in England. VIVC is the project's taxonomy
authority so the current binding stands, but it wants a curator ruling —
and, if VIVC is wrong for the UK reading, a `GRAPE_ALIAS` pin.

---

## Italy — two Wikipedia articles were bound to the wrong appellation ✅ fixed

Found 2026-09-06 by grouping the emitted JSON-LD `sameAs` links (see the
cross-country section below). The `02b_fetch_aoc_lexicon` title cascade bound
two IT records to a *different* appellation's article on name similarity:

| slug | appellation | was bound to | distance |
|---|---|---|---|
| `tarantino` | IGP Tarantino (Puglia) | `Trentino (vino)` — the Trentino DOC | ~900 km north |
| `rotae` | IGT Rotae (Molise) | `Roma (vino)` — the Roma DOC | different region (Lazio) |

This was not only an SEO/identity problem. `rotae` had shipped a
**wiki-provenance terroir bullet about the wrong appellation** — "La DOC Roma
è stata approvata con DM 02.08.2011; la versione vigente del disciplinare
risale al DM 07.03.2014." — translated into all four locales. It passed the
≥ 0.6 fuzzy-coverage filter precisely *because* it is a faithful verbatim
quote; the filter checks that a bullet is grounded in its source, not that the
source is the right document. `tarantino` escaped content contamination (all 5
of its bullets were `cahier`-provenance) but carried the wrong `sameAs`.

Fixed: both pinned `{"missing": true}` in `raw/wikipedia/aoc_overrides.json`
under `it` with the reason, their cached article files replaced with a
`missing` marker recording the suppressed title, then IT 02d + 02e re-run for
the two slugs. Both are now 100 % `cahier`-grounded with `wiki_source_url:
null` (tarantino 6 facts, rotae 7).

**The general lesson**: a `wiki`-provenance bullet is only as trustworthy as
the article-title match, and nothing downstream re-checks that match. A cheap
standing guard is to group the corpus by bound article title and look at any
title claimed by more than one appellation — which is exactly how these two
surfaced. Worth running after each `02b_fetch_aoc_lexicon` sweep.

---

## Cross-country — terroir-fact full-corpus review (2026-09-12) — ❌ open

Report: `docs/review-terroir-facts-2026-09-12.md`; evidence `tmp/terroir-facts-review/full-review-2026-09-12/`. Data-side items not covered by the country sections above:

- Wikipedia bindings: `tirol` → de.wikipedia *Toro (Weinbaugebiet)* (the Spanish DO); `montecastelli` → the village article (its wiki-only bullet #4 describes the village hill). Pin both `missing` in `raw/wikipedia/aoc_overrides.json`.
- `sobes` fact #1 (Mikulov bioregion, Pavlov Hills limestone) is the Mikulovská podoblast 50 km east; Šobes sits on Bohemian Massif crystalline rock — the region-wide CHZO grounding plus the podoblast wiki hint.
- `montana` (BG): the IAVV spec has the Danube "to the south" and Stara Planina "to the north"; bullet #0 silently corrects it — a source typo worth a note.
- Re-run scope: `rerun-slugs.txt` (346 records with a verified misleading bullet) and the 730 records with "Label:" bullets (`det_checks.json` → `rows.label_prefix`), all but one extracted before the 2026-09-11 style block.

## Cross-country — grape pills show another country's spelling ✅ fixed 2026-09-06

Found 2026-09-06 from a GB spot-check: the English PDO's pill reads **"Optima
113"**, but the UK product specification says plain "Optima" (and the GB
record stores it correctly). "Optima 113" is Germany's official
Bundessortenamt name, from the Geilweilerhof breeding selection 33-13-113 —
a real name for the variety, just not the British one.

Root cause is one guard in `emit_html` (`scripts/04_build_maps.py`, the
`grape_names` loop):

```python
if s_slug and s_name and s_name.lower() != s_slug:
    grape_names[s_slug] = s_name
```

The comment directly above it states the intent — *"drives the pill label so
the rendered name matches what the regulator actually published"* — but
`s_name.lower() != s_slug` drops the record's own spelling precisely when it
is already clean ("Optima".lower() == "optima"), presumably as a payload-size
saving on the assumption the client can re-derive it. The client does not
re-derive it from the slug: it falls back to the corpus-wide `GRAPES_INFO`
display name, which is the **most frequent spelling across all countries** —
frequently another language's.

Blast radius (whole corpus, 50,757 (record, grape) pairs): **6,792 displaced
labels, of which 1,047 are substantive** — a different word or number, not
just casing. Worst offenders:

| records | record's own name | label actually shown |
|---:|---|---|
| 97 | Müller Thurgau / müller-thurgau | **Rizlingszilváni** (Hungarian) |
| 76 | muscat à petits grains | muscat à petits grains blancs |
| 71 | Alicante Bouschet | alicante henri bouschet |
| 35 | albariño (ES) | **alvarinho** (Portuguese) |
| 30 | godello (ES) | **Gouveio** (Portuguese) |
| 18 | Blauer Portugieser (DE/AT) | **Kékoportó** (Hungarian) |
| 17 | plantet (FR) | seibel 5455 |
| 4 | Optima (GB) | Optima 113 (German) |

By country: it=228, fr=220, de=149, es=94, ro=67, pt=67, hr=48, hu=31, ch=26,
sk=23. So German and Austrian pages label Müller-Thurgau with its Hungarian
name, and Spanish pages label Albariño and Godello with their Portuguese ones
— directly contradicting the stated rule in CLAUDE.md that the pill shows
"the cahier's spelling ... verbatim with the VIVC prime name in brackets when
distinct".

**Fixed 2026-09-06**: the guard was removed so `emit_html` carries the
record's own spelling unconditionally, with a comment recording why it must
not be re-added as an optimisation. Verified in the rendered panel — the
English PDO's pills now read *Optima*, *Regent*, *Kerner*, *Albarino
(Alvarinho)* instead of *Optima 113*, *Regent N.*, *Kerner B.*, *Alvarinho*;
Mosel keeps its own *Optima 113* and *Müller Thurgau*, Valdeorras its
*godello*. Each country now shows its regulator's spelling with the VIVC
canonical in brackets when distinct, which is what CLAUDE.md specifies.

Cost: `grape_names` rides the lazily-fetched panel payload, not the startup
bundle. Panel payloads total 42.4 MB over 11,656 files (mean 3.6 KB); the
startup bundle is unchanged at 3.51 MB. Per-record name counts rose as
expected (english-wine 30→81, mosel 64→126, sussex 10→28).

---

## Cross-country — one Wikidata QID claimed by several appellations (pre-existing)

Found 2026-09-06 while wiring GB's `sameAs`. **18 QIDs are currently claimed
by 50 appellation records**, and — counting only the 1,659 pages that actually
emit JSON-LD — **15 Wikipedia articles are claimed as `sameAs` by 44 of
them**. Either way it is an identity error in the JSON-LD:
schema.org `sameAs` asserts *this page is about that entity*, so two
appellations cannot legitimately share one QID. Group
`raw/wikidata/qids-by-slug.json` by `qid` to reproduce.

Two distinct causes, needing different fixes:

- **Umbrella article shared by a whole country's corpus** — clearly wrong.
  `Q582745` "Maltese wine" is claimed by all three MT records (malta, gozo,
  maltese-islands); `Q9198993` "Vinarska oblast Cechy" by cz cechy + ceske.
  GB hit exactly this and is already suppressed (see the United Kingdom
  section).
- **Parent article inherited by sub-denominations / sibling names** —
  `Q1067753` Vinho Verde across 10 records and `Q191034` Porto across 4 (both
  via the P9854 eAmbrosia join, which returns the parent's GI), plus
  `Q1058259` chablis + petit-chablis, `Q21427011` the three Calvados records,
  `Q551484` the three Anjou records, `Q3288502` the two Marc d'Alsace.

The suppression mechanism already exists (`raw/wikidata/slug_overrides.json`,
`{suppress: true}`), so the QID half of the fix is curation, not code — but it
touches 6 countries, so it wants its own pass rather than riding a country
addition.

**The Wikipedia half is not yet fixable by curation.** `_entity_same_as` in
`scripts/_lib/map_template.py` takes its Wikipedia URL from
`terroir_facts.wiki_source_url`, which no override reaches, so suppressing a
QID leaves the shared article link in place — GB's two PDOs still both point
at *Wine from the United Kingdom*. The worst instance is HR: 14 records all
claim `Vinogradarska područja Republike Hrvatske`.

Suggested fix, self-maintaining and covering all 44 at once: drop a Wikipedia
`sameAs` whenever the same article URL is claimed by more than one *indexable*
record. An article claimed by two appellations cannot identify either, so the
invariant is sound without per-record curation. It changes output for ~44
records across several countries, so it belongs in its own change with a
before/after diff.

---

## Cross-country — audit_terroir_facts covers only FR / ES / GB (pre-existing)

`scripts/audit_terroir_facts.py` re-derives fuzzy coverage from each
country's own source documents, so it needs a per-country dispatch entry
(extracted dir, wiki cache dir, lien field, Wikipedia heading map, hint
char-cap, and the right hint *builder* — FR-style vs ES-style). Only `fr` and
`es` were ever wired; every country added since (PT, IT, AT, SI, HR, HU, RO,
BG, GR, DE, SK, CH, CZ, LU, BE, NL, MT, CY) was silently skipped — a
`KeyError` swallowed by the loop's broad `except` and printed as
`err <slug>: '<cc>'`, indistinguishable from a corrupt cache.

The 2026-09-06 GB pass wired `gb` in and made the skip explicit: unsupported
countries are now counted and reported instead of masquerading as errors. The
full-corpus run quantifies the gap — **1,030 fact-carrying records across 18
countries are unaudited**:

```
[skipped] countries with no source dispatch entry: at=30, be=10, bg=54,
ch=3, cy=11, cz=13, de=39, gr=147, hr=18, hu=41, it=522, lu=1, mt=3,
nl=21, pt=44, ro=46, si=17, sk=10
```

against 4,470 bullets actually audited (FR + ES + GB). Italy alone is 522
records, so it is the highest-value single entry to wire. Wiring the remaining 18 is a bounded, mechanical
job — each needs the 5 dispatch entries above, and getting the hint builder
or char-cap wrong produces *false* drift / erosion flags (both were hit while
wiring GB, and both are documented inline there), so each country's entry
should be validated against a record with a known-good `wiki`-provenance
bullet.

---

## Cross-country — two slugs for one VIVC variety (pre-existing; surfaced by GB)

Not introduced by the UK pipeline — GB is simply the first country whose
*single* variety roster names both spellings, which puts the same grape on
one panel twice.

**`blaufrankisch` and `lemberger` are both VIVC #1459 BLAUFRAENKISCH.**
The project's own cache agrees: `raw/vivc/by-slug/blaufrankisch.json` and
`raw/vivc/by-slug/lemberger.json` both read `vivc_id: 1459`, and each
lists the other as a synonym. The split is an alias-chain artefact —
`kekfrankos → blaufrankisch` and `limberger → lemberger` are both
one-hop, and nothing folds the two heads together.

Usage across the corpus (229 records, 11 countries):

| slug | records | countries |
|---|---:|---|
| `blaufrankisch` | 124 | hu 72, hr 24, sk 14, cz 10, gb 4 |
| `lemberger` | 105 | ro 43, si 21, de 15, at 9, hu 8, gb 4, be 2, pt 2, es 1 |

Folding them is the established policy (commit `a7570f2` "fold
VIVC-collision slug dupes … unify facet by variety"), but it moves the
grape facet for 11 countries, so it belongs in its own change with its
own before/after diff — not in a country addition.

**`csabagyongye` / `zalagyongye` are mis-named.** The slug
`csabagyongye` is bound to VIVC #13374, whose prime name is **ZALA
GYOENGYE** — so the *binding* is right for the surface "Zala gyöngye"
but the slug name says Csaba. Meanwhile `zalagyongye` exists as a
separate slug with no VIVC binding at all (7 HU records), and
`perle-von-zala → csabagyongye` is commented "alternate German name for
Csabagyöngye" when Perle von Zala is the German name of *Zala*gyöngye.
Needs a curator pass over the pair; renaming a slug ripples into the
VIVC cache, the wiki pages and the translations, so likewise its own
change.

## Cross-country — eAmbrosia register attachment endpoint (spike ✅; CZ + SI live; Phase-2 retrofit planned)

The EU GI register public API
(`ec.europa.eu/geographical-indications-register/eambrosia-public-api`,
OpenAPI at `/v3/api-docs`) exposes, per GI, BOTH the EU **single document
/ fiche technique** (`singleDocTechFile[].uri`) and the **full national
cahier des charges** (`productSpecifications[].uri`) as
`/api/v1/attachments/<uri>` PDFs — reachable for the grandfathered
`Ares(...)`-only population that currently rides bespoke national-spec
parsers.

**Resolver recipe (verified):**
1. `fileNumber → id`: `POST /api/gi-applications/filter`
   `{"first":0,"rows":5000,"showTSGs":"false","filters":[]}` → map row
   `fileName`→`id` (one ~4 MB response, cache it). **Do NOT use
   `int(giIdentifier[4:])`** — it 500s for ~1/3 of GIs (PDO-CZ-A0888 =
   appUniqueId EUGI…2821 but real id 8225).
2. `GET /api/gi-applications/id/<id>` (**no `/v1/`**) → read the two `*.uri`.
3. `GET /api/v1/attachments/<uri>` — browser-gated (real browser UA +
   `Accept` WITHOUT `application/pdf`), answers HTTP 202 + PDF body.

**Spike result (`tmp/eambrosia-spike-findings.md`):** 47/47 sampled
grandfathered/stub wines across ES/IT/SI/HR/BG/GR/HU/RO/CZ/SK/LU resolved
to a fetchable `singleDocTechFile`; all inspected (10 across 9 langs/scripts)
text-layer, uniform EU template, with terroir + variety sections. **Viable
as the primary stub fallback behind one per-language fiche-technique parser**
(role keywords already exist in the per-country parsers); keep bespoke
scrapers secondary. Proven in use: **BE** (4 Walloon → fiche) + **CY** (3
image-only specs).

### Implementation status (2026-06-02)

Shared infra shipped: `scripts/_lib/eambrosia_register.py` (resolver +
browser/202 fetch), `scripts/_lib/fiche_technique.py` (2-family parser),
`scripts/extract_register_fiches.py` (config-driven, 8 countries),
`scripts/_lib/register_fiche.py` (sidecar accessor for stage-04 / 02d).
66 fiche-surfaced natives folded into `grape_lexicon.py` (queues drained).

Applied **where there was an actual terroir gap** — not as a rip-and-replace:
- ✅ **CZ** — per-DOP terroir now live (was shared-region SZPI CHZO for all
  Morava/Čechy wines); `cz/02d` grounds on the fiche §7.
- ✅ **SI** — bela-krajina + belokranjec get their OWN per-DOP terroir from
  the fiche (`si/02d` fill-if-empty), replacing the "inherited from Posavje"
  `appellation_notes` workaround.
- **No action needed for HR/HU/SK/BG/GR/RO** — they were already terroir- +
  grape-covered by their own national-spec/EU-OJ layers (hu 41/41, gr 147/147,
  bg 54/54, ro 46/46 already had per-DOP facts). Re-sourcing them via the
  fiche would be churn + regression risk for no gain.

### Phase 2 — unify source-fetch on the register API (elegance retrofit, NON-URGENT)

🟢 **First landing: France (2026-08-29).** FR now carries the register as a
last-resort cahier tier behind BO Agri, with a name → `fileNumber` resolver
(FR is the one INAO-sourced country, so it has no `id_eambrosia` join key) and
a read-only shadow report. See the France section above. What it proves for
the rest of the retrofit: the register's `productSpecifications` attachment is
the **full national spec**, not the thinner single document, and it parses with
the country's existing extractor unchanged. What it does NOT yet do: retire BO
Agri, `01b_solve_legifrance.py` or the OCR mirror path — those come out only
once the shadow report proves the register covers them, as a separate change.

Forward-looking cleanup, not user-visible: make the register API the
**canonical first-fetch** for the source document, so the codebase is more
uniform and sheds fragile dependencies. The register single-document is
reachable even for grandfathered `Ares`-only wines, needs **no AWS-WAF /
Playwright** (unlike the EUR-Lex `01`/`01b` path), and follows one uniform
template. Candidate wins, in priority order:
1. Retire the per-country EUR-Lex WAF + `01b_solve_waf.py` Playwright
   bootstrap where the register fiche carries the same single document.
2. Replace the most fragile bespoke national-spec scrapers (rotating tokens,
   WAF-blocked hosts) with the register fetch.
3. Fold `extract_register_fiches.py` + the per-country 02d hook into a
   single shared stage so new countries are config-only.
Keep the bespoke scrapers as fallback (the register lacks the *full national
cahier*'s richer per-variety detail for some countries). Caveats: polite
low-rate client (202 + UA gate is deliberate anti-bot); PDF size/text-layer
guard for image-scan long tail; the resolver's bulk filter-list is ~4 MB
(cache it). Do this as a deliberate refactor pass, not piecemeal.

## Style taxonomy follow-ups

- **Sweet/oxidative cross-cut** — `generoso` (sherry-family) sits under `oxidative` because most sherries are dry; PX cream sherries and dulces are nominally oxidative *and* sweet. Currently they only emit `oxidative + generoso + (sub-tag)`; the `sweet` bucket is *not* added. Decide whether to surface dual-tagging (record carries both `oxidative` and `sweet`) when the pliego describes a PX / cream / sweet-oloroso style. Currently affects ~5 sherry pliegos. Defer to v2.
- **Grape display — surface the more common term** — chip labels currently render the verbatim pliego name (e.g. "MAZUELA", "VIURA"). For cross-border discoverability, surface the international/canonical synonym ("Carignan", "Macabeo") as a tooltip or secondary chip when the canonical slug differs from the verbatim local name. Slug already canonicalises (`carignan`, `macabeu`) so filtering works; this is purely a display enhancement. Defer to v2.
- ✅ **ES grape Wikipedia tooltips** (shipped earlier) — `collect_grape_slugs` in [scripts/02b_fetch_grape_lexicon.py:76-95](scripts/02b_fetch_grape_lexicon.py#L76-L95) iterates both FR cahiers and ES pliegos. ES-only Iberian varieties flow through. Curator pass for non-canonical `es.wikipedia.org` titles still open (`(uva)` disambiguator etc.).
- **ES grape alias gaps** — [scripts/audit_es_grape_aliases.py](scripts/audit_es_grape_aliases.py) lists tokens that don't resolve through `GRAPE_ALIAS` / `DEFAULT_COLOUR`. ~250 distinct tokens after current seeding; biggest residual classes are Canary Islands varieties (Bermejuela, Marmajuelo, Vijariego, Listán Negro, …) and Galician varieties (Brancellao, Sousón, Loureira, Caíño…). Most are genuine ES-only varieties — register their canonical slug in `DEFAULT_COLOUR` rather than aliasing.
- **Parenthesised synonyms in ES variety lists** — pliegos like 3-riberas write "Albillo Mayor (Turruntés)" where the parenthetical is the regional synonym. Parser currently keeps the parenthesis in the name → 3-token slug. Extract the parenthesised tail as a synonym (route through `GRAPE_ALIAS`) and slug from the primary token only.

## Cross-country — VIVC curator pins that pointed at the wrong passport ✅ fixed 2026-09-20

Visitor feedback (Plausible `Feedback Flagged`, navarra / grapes, 2026-09-20):
the Navarra card rendered the pill **"Oneca (Galvani)"** — VIVC 4359 is the
Italian table grape Pirovano 86, not the Navarra white recovered by EVENA
(registered in Spain 2023, no VIVC entry). The Navarra roster itself was
correct (16 varieties = the 2025 documento único, C/2025/297).

`audit_vivc_coverage.py --strict` (new `check_pins`) found the pin was one of
**33** in `raw/vivc/slug_overrides.json` written from memory: 22 landed on an
unrelated passport, 11 on ids VIVC serves blank. All re-pinned against the live
passport (each entry records `_previous_vivc_id` + the verification date);
`02g --refresh --only …`, `02b_fetch_grape_lexicon --refresh --only …` re-run
for them (the wrong passports had steered three Wikipedia tooltips: riminese →
Sangiovese, muscadin → Muscadine, antricotin → Aramon blanc).

| slug | was | now | basis |
|---|---:|---:|---|
| oneca | 4359 GALVANI | absent | no VIVC entry (search 2026-09-20) |
| diagalves | 3551 DIANA HAMBURG | 2520 MONTUA | JKI DNA: Diagalves = Chelva / Montúa |
| espadeiro | 3998 EUGENE DURET | 24552 ESPADEIRO TINTO | VIVC prime |
| riminese | 10117 RKATSITELI 4N | 224 ALBANA BIANCA | Corsican riminèse B; VIVC synonym |
| mayorquin | 7541 MAXATAWNEY | 9542 PLANTA FINA | VIVC synonym |
| muresconu | 8095 MOVSESI | 8959 PASCALE DI CAGLIARI | MASAF registro scheda 180 |
| bouteillan | 1632 BOWMAN | 14834 COLOMBAUD | corpus is bouteillan B; VIVC synonym |
| caino-tinto | 2002 CALLO | 1564 BORRACAL | VIVC + Wine Grapes |
| camaralet-de-lasseube | 2014 CAMACHA | 24189 CAMARALET | VIVC prime |
| oberlin | 8678 OBITKI | 8652 OBERLIN NOIR | Oberlin 595 |
| ratino-gallega | 9942 RAVAZ 1 | 24127 RATINO | VIVC Spain, blanc |
| terret | 12397 TERZI 97-41 | 12384 TERRET NOIR | as the note intended |
| crujidera, crudijera | 23167 MAVROTHIRIKO | 23166 MORAVIA DULCE | VIVC synonym |
| negro-sauri, bastardillo-chico | 17252 / 1029 | 12668 TROUSSEAU NOIR | = Merenzao (DO León / Arribes) |
| ferraudou | 4112 FERTILIA | 24201 FERRADOU | Gers spelling |
| giro-negre | 5005 AMERIKANIKO | 4811 GIRO NERO | VIVC Spain; syn. Giró de Baleares |
| jaen-blanca | 5651 JAEN GARCIA | 5648 CAYETANA BLANCA | VIVC synonym |
| meslier-saint-francais | 7676 MESLIER ROSE | 7677 | prime |
| franc-noir-de-haute-saone | 4253 blank | 4916 | prime |
| soreli-blanc, soleri | 22841 blank | 24892 SORELI | prime |
| saborinho | 10395 blank | 15678 MOLAR | VIVC synonym |
| izkiriota | 5070 blank | 7338 MANSENG GROS BLANC | Basque name of Gros Manseng |
| muscadin, pirene, antricotin, plant-de-brunet, mourvedre-blanc | wrong / blank | absent | no VIVC entry |
| torrontes, alvarelhao-branco, caino-longo | blank | absent | VIVC folds the name under several primes / two accessions |

Open follow-ups:

- ✅ 2026-09-21 `petit-grains-blancs-muscat-ottonel` (haute-marne): the cahier
  itself drops the comma ("muscat à petit grains blancs muscat ottonel B"), so
  it is a source typo, folded by `GRAPE_ALIAS` to `muscat-ottonel`; the slug is
  gone from the corpus and its override / caches were removed.
- ✅ 2026-09-21 `izkiriota` (Getariako Txakolina): the pliego names the variety
  twice, in Basque and Castilian; `GRAPE_ALIAS` now folds izkiriota /
  izkiriota-handia → gros-manseng and izkiriota-ttipia → petit-manseng, so the
  card shows one pill.
- ✅ 2026-09-21 `espadeiro` pt: pt.wikipedia has no Espadeiro article (the title
  redirects to Trincadeira), so the pair is pinned `null` in
  `raw/wikipedia/grape_overrides.json`; the nl translation was pruned.
- ✅ 2026-09-21 `antricotin` (Domfront perry pear, no longer extracted as a
  grape): pin and caches removed.
- ✅ 2026-09-21 `albarin-blanco` (19 records: Cangas, Tierra de León, …): the
  en / es Wikipedia caches were the Albariño article (Wine Grapes: distinct
  varieties, a classic confusion), and Zerratia inherited it through the
  same-VIVC donor chain. es now pins the "Albarín blanco" article, en is
  pinned absent; fr / nl / en tooltips re-translated from es.
- ✅ 2026-09-21 `ondarrabi-zuri-zerratia` (Txakoli pliegos) folds to
  **Petit Courbu** (#3213): the Bizkaiko Txakolina documento único states
  "la variedad recomendada Hondarrabi Zuri Zerratia (Petit Courbu)", and
  Getariako lists both names the way it lists Izkiriota beside Gros Manseng.
  The earlier "DNA-confirmed = Albarín Blanco" pin was unsupported (VIVC
  #22838 carries only Galician synonyms; the Wine Grapes Albarín Blanco entry
  names no Basque synonym). Conflicting third-party reading, not followed:
  VIVC #651 Arrufiac lists ZURIZERRATIA and Wine Grapes gives "Zurizerratia
  (Pays Basque)" under Arrufiac — the French-Basque use of the name. If a
  Basque-government act ever names Arrufiac, revisit.
- ❌ `hondarrabi-zuri` binds to Courbu blanc #3211 (VIVC flags HONDARRABI ZURI
  as the official Spanish name there), but Wine Grapes notes the Basque name
  covers three varieties in the vineyards — Courbu blanc, Crouchen and the
  hybrid Noah — and the pliegos cannot tell them apart. Bracket kept on
  VIVC's authority; a regulator statement naming the variety per DO would
  settle it.
- ❌ `torrontes` (39 ES records) stays bracket-less by decision: one slug covers
  at least three varieties. Galicia (Ribeiro, Rías Baixas, Ribeira Sacra,
  Valdeorras …) = the Spanish register's Torrontés, DNA-identical to Alarije
  (VIVC #213 lists TORRONTES as a synonym; OEVV "dual legal status");
  "Turruntés" of Rioja / Madrid = Albillo Mayor (Hebén × unknown, 2015);
  Torrontés de Montilla = Puerto Alto / Zalema; Canarias unverified. Binding
  any one of them corpus-wide would be wrong for the others, and a
  record-scoped alias (surface → slug per record / region) does not exist —
  the same gap as the colour-qualified piquepoul fold above. Build that
  mechanism first, then split the slug per region with the pliego as evidence.

## VIVC grape resolution — ✅ closed 2026-06-03

All 11 ambiguous slugs + all 17 IT VIVC pins from the earlier pass are now
resolved. Passports re-fetched; 02b run for synonym-recovered slugs.

**9 ambiguous slugs — ✅ pinned 2026-06-03** via VIVC + grape-colour-researcher:

| slug | vivc_id | prime | colour | note |
|---|---|---|---|---|
| `sanktt-laurent` | 10470 | SAINT LAURENT | NOIR | AT red; candidate 8252 ruled out |
| `inzolia` | 492 | ANSONICA | BLANC | Sicilian white; #122 = unrelated table grape AFUS ALI |
| `siria` | 2742 | SIRIA | BLANC | Same variety as `dona-blanca`; 55 ES uses (Galicia, Castile) |
| `maresco` | 1660 | BRATKOVINA BIJELA | BLANC | Valle d'Itria; #4019 ESCURSAC is NOIR (wrong colour) |
| `moscatel-negro` | 8226 | MUSCAT HAMBURG | NOIR | Official Spanish name MOSCATEL NEGRO; 9 Canary IS. DOPs |
| `moscatel-negra` | 8226 | MUSCAT HAMBURG | NOIR | Feminine gender variant of moscatel-negro; 1 use (Ycoden) |
| `loureiro-tinto` | 17346 | LOUREIRO TINTO | NOIR | Galician red; distinct from white Loureiro #7623 |
| `tempranillo-blanco` | 25057 | TEMPRANILLO BLANCO | BLANC | White Tempranillo mutation; #10690 is NOIR parent |
| `verdejo-negro` | 12668 | TROUSSEAU NOIR | NOIR | Cangas (Asturias); VIVC lists VERDEJO NEGRO as explicit synonym |

**2 family names — left unpinned** (genuinely ambiguous, curator intent per 2026-05-22 note):
- `groppello` — 23+ VIVC sub-variety candidates; `groppello-gentile` (#5078) already pinned
- `schiava` — 19+ VIVC sub-variety candidates; `schiava-grossa` (#10823) + `schiava-grigia` (#10822) already pinned

**5 misses** (no VIVC candidate at all): `blutenmuskateller` (**AT** —
Blütenmuskateller, an Austrian Muscat selection that VIVC may not
carry under that name), plus pre-existing `bianco-di-alessano`,
`incrocio-manzoni`, `nerello-cappuccio`, `siria`-class IT/ES varieties.
JKI publishes no data licence, so unresolved slugs simply ship without
a VIVC bracket — not blocking.

## Cross-country — SEO / structured-data (JSON-LD on entity pages)

### `additionalType` — minimal shipped ✅ / kind-aware variant ⏳

Shipped (2026-06-05): every indexable entity page's `Place` carries
`additionalType = https://www.wikidata.org/wiki/Q2140699` ("wine-producing
region") — the universal, EU-and-non-EU-safe place-class. Constant
`_WIKIDATA_GI_TYPE` in [scripts/_lib/map_template.py](scripts/_lib/map_template.py).

⏳ **Kind-aware regulatory class** (richer typing, optional, NON-URGENT):
emit `additionalType` as an array `[Q2140699, <regulatory-class>]` keyed on
`rec["kind"]`:
- DOP / AOP → `Q13439060` (EU "Protected designation of origin")
- IGP / PGI → `Q3104453` (EU "protected geographical indication")
- **must exclude `country=="ch"`** (Swiss AOCs are NOT EU PDOs) and any other
  non-EU — fall back to `Q325668` ("designation of origin") or just `Q2140699`
  alone.

Caveat to weigh before doing it: a PDO/PGI is the *designation / legal
protection*, not the *area* — so tagging the `Place` with it is a mild
"protected-as" vs "is-a" blur (the reason it wasn't shipped in v1). Turns the
single constant into a small kind+country→QID helper + the array-emit branch in
`_build_entity_jsonld`. Low value (KG/LLM typing hint only; `Place` isn't
rich-result-eligible), so deferred.

### Wikidata QID coverage (stage 02i) — long-tail unlock ⏳

`02i_fetch_wikidata_qids.py` resolves 1,230 / 2,886 slugs to a QID (167 via
P9854 eAmbrosia-ID join, 1,063 via Wikipedia sitelink). The ~1,656 misses are
records with neither an eAmbrosia P9854 match nor a validated Wikipedia
article. Two levers to raise coverage: (a) re-run `02b_fetch_aoc_lexicon.py`
for the locales where AOC articles are pinned `missing` (each new article a
sitelink can resolve); (b) curator pins in `raw/wikidata/slug_overrides.json`
(`{slug: {qid}}`) for notable misses — e.g. `crozes-hermitage` resolved to no
QID despite having a fr.wikipedia article + Wikidata item.

### Page weight — 13 MB `aocs.<lang>.*.js` data blob — ✅ resolved via the two-tier split (verified 2026-08-26)

Lever 3 below shipped: the startup bundle now carries only
`STARTUP_AOCS_FIELDS` (**3.3 MB** on disk, was ~13.25 MB) and the panel
payload lazy-loads per slug from `wiki/data/d/<locale>/<slug>.json`
(2,908 files per locale) on first panel open. See "Data bundle: startup
blob + lazy panel detail" in [CLAUDE.md](CLAUDE.md). Original analysis
kept below for context.

#### Original finding (historical)

Bing URL-inspection flags a low-severity Notice "Html size is too long" on
entity pages. The HTML itself is tiny (~20 KB / ~180 lines) — the trigger is
the **`/data/aocs.<lang>.*.js` corpus blob: ~13.25 MB uncompressed** (3,823
records × ~3.5 KB), loaded as a render-blocking `<script src>` (no `defer`/
`async`) on **every** page because each page boots the full map. Bunny serves
it Brotli (`content-encoding: br`, ~2–3 MB on the wire), but the uncompressed
payload is what the page-weight heuristic counts. **Non-blocking for indexing**
(`URL can be indexed ✓`); this is a real-performance / LCP / mobile / crawl-
budget improvement, not an SEO fix.

Levers, by effort/payoff:
1. **`defer` the data `<script>`** — stops it blocking parse/render; quick, no
   size change. (`aocs_data_src` slot in [scripts/_lib/map_template.py](scripts/_lib/map_template.py).)
2. **Lazy-load on first paint / interaction** (best effort:payoff) — the entity
   page's SSR card + the map polygons (pmtiles) don't need the blob; only
   sidebar search/filter does. Fetch it after first paint or on first sidebar
   interaction so the initial load (and the crawler) never pulls 13 MB.
   App-side change in `_APP_JS`.
3. **Split the blob** (biggest win) — ship a light search/facet index
   (slug + name + facets, ~hundreds of KB) eagerly + fetch per-appellation
   detail on panel open. Stage-04 data-emit + `_APP_JS` refactor; QA the
   search/filter parity.


## Cross-country — VIVC synonym collisions (ranking rule shipped; 2 open questions)

VIVC keeps every name a variety has ever borne, so one surface is routinely
claimed by several records. `_load_vocabulary` used to walk those in file
order, so a legacy synonym could outrank another record's prime name. It now
ranks claims — prime name > synonym flagged "official name in <country>" >
plain synonym — which re-bound 8 surfaces the corpora actually use.
[scripts/audit_ambiguous_synonyms.py](scripts/audit_ambiguous_synonyms.py)
lists what the ranking cannot decide (51 RISKY at time of writing).

Reported by José Vouillamoz (co-author of *Wine Grapes*, Valais) via Reinier
Broeks: `Bianca` was folded into Biancolella and `Hermitage` into Cinsaut.

### Open question 1 — bare `Sárfehér` (HU, 3 records)

Pinned to `arany-sarfeher` (status quo) pending a curator ruling.

- Sárfehér (VIVC #5417, = Honigler / Mézes fehér / Précoce de Bousquet) and
  Arany sárfehér (VIVC #5600, the 1873 Izsák selection) are **distinct**
  cultivars — Fazekas et al., *Kertgazdaság* 54 (2022) 1-2, Table 1 lists both
  as separate register rows (2 ha vs 288 ha).
- VIVC flags `SARFEHER` official-in-Hungary on #5417, which argues for the
  flip. But plantgrape gives #5417's Hungarian official name as *Honigler*,
  not Sárfehér, and a ~2 ha relic appearing in regional PGI rosters is
  implausible. The source text says "izsáki sárfehér - 1873" and a PDO named
  *Izsáki Arany Sárfehér* exists, so the bare form reads as shorthand.
- To settle: check the Nemzeti Fajtajegyzék entry each of the 3 records
  (etyek-buda, dunantuli, balaton) intends. If they mean the relic, re-pin to
  the #5417 slug; if shorthand, keep as is and the pin is correct.

### Open question 2 — `Moschato Samou` is country-dependent

Bound to `muscat-ottonel`, correct for the 3 **Cypriot** records: the Cyprus
Dept. of Agriculture annex prints "MUSCAT OTTONEL (ΜΟΣΧΑΤΟ ΣΑΜΟΥ)", and
Cyprus uses Μοσχάτο άσπρο for Muscat blanc. A **Greek** Μοσχάτο Σάμου would
be Muscat Blanc à Petits Grains (Samos) — the opposite. No Greek record uses
the surface today; if one appears, the matcher needs a country-aware pin
rather than the current global binding.

### Upstream-flag caveat

VIVC's official-name flag is a claim, not a fact, and is not unique per
country: Sauvignon Blanc (#10790) carries **both** `SAUVIGNON` and
`ZELENI SAUVIGNON` as Slovenian official names, which cannot both hold. That
bad flag re-bound Slovenian Zeleni sauvignon (= Sauvignonasse / Friulano) to
Sauvignon Blanc until a hard pin reverted it. When an official-name flag
would flip an existing binding, corroborate against a second register
(plantgrape.fr is a fetchable proxy) before trusting it.

### Open question 3 — slug groups sharing one vivc_id — ENUMERATED + TRIAGED 2026-08-21

The full enumeration the 2026-08-20 note called for ran on 2026-08-21: 117
live slug groups shared a single VIVC id (116 on the audit's corpus view,
which misses HU — see the loose end below). Three classes fell out, two of
them now closed:

**Class 1 — spelling / bare-vs-qualified dupes: FOLDED (22 groups
dissolved).** The corpus-slug tier already applies GRAPE_ALIAS
(`_corpus_slug_frequency` folds on read — the pagadebiti/bombino
precedent), so the 2026-08-20 "not fixable with an alias alone" note was
stale: a slug→slug alias + re-extraction retires the minority slug. Folds
applied (see the "VIVC-collision folds" block in `grape_lexicon.py`):
sauvignon-blanc + sauvignon-blanco → sauvignon, gewurz-traminer,
nero-d-avola → nero-davola, maccabeu, lledonner-pelut, castet → castets,
godelho → godello, ottonel → muscat-ottonel, monastrel → mourvedre,
moscatel-negra, muscat-a-petit-grains-blancs, mauzac-blanc → mauzac,
fer-servadou → fer, henri-bouschet → alicante-bouschet, braquet → brachet,
tinta-lisboa → tinta-de-lisboa, ramisco-tinto → ramisco, soleri →
soreli-blanc, pinot-d-aunis → pineau-d-aunis, vijiriego →
vijariego-blanco, cao → tinto-cao, fernao → fernao-pires, muscat-hambourg
→ muscat-de-hambourg (HU aliases re-pointed), mario-feld → pinot-noir
(Mariafeld is a Pinot noir clone). Per-record display names keep the
source spelling — only the facet key unifies.

**Class 3 — mis-resolved VIVC ids: FIXED (research-verified against live
vivc.de, 2026-08-21).** Beyond the suspected list, a colour-mismatch sweep
(corpus colour letter vs VIVC berry colour) surfaced several more:

| slug / surface | was | now | evidence |
|---|---|---|---|
| `bia` (fr 22, Savoie/Isère, blanc) | 8768 ONDARRABI BELTZA (pin note claimed Basque Txakoli — false premise) | **1319 BIA BLANC** | VIVC passport; en.wiki |
| `mollard` (fr 34, Hautes-Alpes) | 7900 = MOLINERA (id typo in the pin) | **7903 MOLLARD** | VIVC; Wikidata P3904; pl@ntgrape |
| `picardan` (fr 54, Languedoc IGPs) | 1612 BOURBOULENC | **527 ARAIGNAN** — the FR Catalogue officiel's Picardan B ("can officially be called Araignan", pl@ntgrape); pill bracket now "Picardan (Araignan)" | VIVC; pl@ntgrape |
| bare `jurançon N` (Côtes du Tarn, noir) | slug `jurancon` pinned 5861 JURANCON *BLANC* ("Jurançon AOC is white" — the pin conflated appellation with grape) | alias → **`jurancon-noir`**, pinned **5862** | VIVC; pl@ntgrape |
| bare `manseng N` (Béarn/Saint-Mont, noir) | slug `manseng` → MANSENG GROS BLANC | alias → **`manseng-noir`** (#7340) | colour letters in both cahiers |
| bare `couderc N` (Landes, noir) | slug `couderc` (own pill) | alias → **`couderc-noir`** (#3206) | Landes hybrid context |
| surface "Nasco" (it 16, Sardinia) | bound to `valenci-blanco` = BEBA #22710 (ES table grape) via BEBA's legacy "NASCO" synonym | self-minted **`nasco`**, pinned **8354 NASCO** | VIVC passport |
| surface "Brachetto" (Brachetto d'Acqui, Ruchè, Piemonte) | bound to `brachet` = BRAQUET NOIR #1657 (Nice) via its legacy "BRACHETTO" synonym | self-minted **`brachetto`**, pinned **15630 BRACHETTO** | VIVC candidate list |
| `terrantez` (pt 3, Dão/Duriense/Tejo/Algarve — mainland) | 26140 TERRANTEZ DO PICO (Azores) | **24589 TERRANTEZ** (VIVC's standalone mainland prime) | VIVC search (6-way homonym) |
| `rufete-serrano-blanco` (es 1, white) | 10331 RUFETE (the red) | **`vivc_id: false`** — VIVC has no entry; distinct white per the CyL regulator | VIVC search empty |
| `pugnitello` (it, Tuscan) | 7949 MONTEPULCIANO (VIVC folds it; identity contested) | **`vivc_id: false`** — Registro Nazionale codice 371 keeps it distinct; no Montepulciano bracket | VIVC + Registro + wein.plus disagree |
| surface "Italia" (Cirò, Rossese di Dolceacqua, Nebbiolo d'Alba, Spoleto) | EUR-Lex table country column matched as a grape (stale bind, then fuzzy→rossese@92) | banned in `_BANNED_SURFACES`; IT stage 02 strips the `Italia -` column prefix so display names show the variety again | source table text |

Confirmed *correct* after the same research (VIVC-faithful, no change):
`hibou-noir` = Avanà #793 (2011 DNA; FR catalogue keeps the name, VIVC
keeps only an accession), `s-saul` = Cinsaut (VIVC carries S. SAUL / SAO
SAUL), `valente` = Heunisch weiss, and the Douro PRT-passport folds
santareno = Etraire de l'Aduï and moscadet = Meslier Saint-François
(verified live); mondet = Durif and rodo = Mondeuse noire are the same
PRT-passport family, accepted on VIVC's authority. `gajo-arroba` keeps
its CASTELOA pin: the Arribes pliego lists it in the *tinto* roster (the
CyL "blanc" colour tag was a parser artifact), though VIVC lets
CORNIFESTO #2846 claim the same name — noted in the pin.

**Class 2 — per-country / per-regulator names for one variety: RESOLVED
2026-08-21 (facet-tier unification, user-approved).** ~70 groups remain
after the folds and fixes, all deliberate or VIVC-faithful: cot/malbec,
rolle/vermentino, nielluccio/sangiovese, jaen/mencia,
bastardo/trousseau(+verdejo-negro), lemberger/franconia/blaufrankisch,
muscat/muscat-a-petits-grains,
morrastel/graciano/tinta-miuda/tintilla-de-rota,
listan/palomino/palomino-fino/listan-blanco-de-canarias/malvasia-rei,
muscat-d-alexandrie/moscatel-graudo/…, portugais-bleu/blauer-portugieser/
portugues-azul, sousao/souson/vinhao, alvarelhao/brancellao,
verdelho/verdello, avana/hibou-noir, cinsault/s-saul, heunisch/valente,
durif/mondet, araignan/picardan, and the long tail of pinned PT/ES
synonym pairs. Decision: keep the slugs (regulator-spelling fidelity,
matching the malbec/bastardo pin notes); the facet tier unifies them —
already live in `map_template.py` + `app.js` via `VIVC_SIBLINGS`
(filter-predicate expansion: toggling Côt matches Malbec records),
`SLUG_TO_CANONICAL` (facet rows + counts roll up to the highest-usage
member, locale-home-country preferred) and `GRAPE_SYNONYMS`
(parenthesised synonym labels on the canonical row, searchable).
Verified against the 2026-08-21 rebuild: cot↔malbec, picardan↔araignan,
s-saul↔cinsault, valente↔heunisch all roll up; the re-pinned
bia / brachetto / nasco / terrantez and the unpinned pugnitello are
correctly siblingless. No per-slug folding needed for this class —
future same-id pairs inherit the behaviour automatically once both
members carry a by-slug VIVC record.

Deferred (per-record or parser-level, not slug-level):
- Calabrian "Greco bianco" (Cirò, Melissa) is **Guardavalle #5096** per
  VIVC/wein.plus — a different variety from Campania/Puglia/Basilicata's
  Greco (di Tufo) #4970 that the shared `greco-bianco` slug is pinned to.
  Same per-record-context problem as Scavigna's Magliocco. (The *other*
  Calabrian Greco bianco — Greco di Bianco DOC passito, Gerace — is
  Malvasia Dubrovačka #7266 per Crespan et al. 2006; not in the corpus.)
- Bare "Cesanese" (Cesanese del Piglio, Castelli Romani) is an Affile
  e/o comune group designation — needs the MASAF-parser group expansion
  the bare-Cabernet fix used, not a fold.
- Bare "Raboso" (Veneto IGTs) is a Piave/Veronese group; VIVC hands it
  to Piave. Left as-is.
- Bare "piquepoul" is colour-mixed (Saint-Chinian N vs La Clape B) —
  a plain alias can't split it; needs colour-aware alias support.
- Bare "korithi" (GR) is the same case (2026-08-26): Zakynthos "Korithi
  B" = #6414 KORITHI ASPRO vs Mantzavinata "Korithi N" = #6415 KORITHI
  MAVRO; pinned `vivc_id: false` until colour-aware aliasing lands —
  then split B→6414 / N→6415.

Loose ends:
- ✅ **Corpus-walk gap closed 2026-08-26.** `grape_corpus._SOURCES` gained
  hu / nl / be / lu / cy (+ cy national-specs) and the BG/GR/SK/RO
  national-specs-extracted sidecar dirs; `02g_fetch_vivc.py`'s own walk
  gained ch / mt / cy / nl / be / lu + the same sidecar dirs. The
  cz/sk/gr/ro **register-fiches-extracted dirs stay deliberately
  excluded** — stage 04 reads only their terroir text, so their rosters
  must not weigh the corpus-slug frequency tiers (comments at both
  sites). As predicted this surfaced **141 corpus slugs without a VIVC
  by-slug record** (GR/CY/BG native tails, CZ registry crossings…); a
  full incremental 02g sweep was run over them 2026-08-26 — final
  buckets: 852 exact-cultivar + 5 exact-prime + 387 override, 120 miss
  (no VIVC candidate — obscure natives, ship without bracket, by
  design), and 42 `ambiguous-cultivar` slugs queued — **✅ all 42
  resolved the same day** via a `/research-gaps vivc-ambiguous` pass
  (5 parallel research agents; evidence table in
  [tmp/vivc-ambiguous-research-results.md](tmp/vivc-ambiguous-research-results.md)):
  40 pinned against live VIVC passports + national registers (NN
  25/2020 + NN 81/2022 for HR, NFJ 2024 for HU, Bundessortenamt-class
  evidence for DE, Genes 2020 DNA anchors), 2 pinned `vivc_id: false`
  (korithi — a two-variety colour-split case; schiava — the standing
  bare-family-name ruling). Three new pins join existing same-id
  groups, handled by the facet tier: tribidrag → primitivo+zinfandel
  (#9703), muskat-zuti → moscato-giallo (#8056), bratkovina → maresco
  (#1660). Notable: `cristina` (RO) was NOT a brand — it is the SCDVV
  Murfatlar crossing VIVC #21045 (closes the 2026-05-23 🟡 below).
  Residual
  cosmetic muddle: the `_SOURCES` lang column mixes country codes and
  locales (gr/at/si/cz where el/de/sl/cs would be locale-correct);
  unknown codes fall through the 02b-translate source chain harmlessly,
  but normalising them (+ invalidating the dominant-lang cache) is a
  clean-up candidate.
- **Stage-02 runs across countries must not run concurrently.** The
  vocabulary scans the FR/ES/PT extracted dirs and silently skips
  mid-write files (`json.JSONDecodeError → continue`), so a parallel
  re-extraction can drop a corpus slug from tier 1 and let a VIVC synonym
  claim steal its surface (observed: CH bare "muscat" →
  muscat-d-alexandrie while FR was mid-rewrite; fixed by a sequential
  re-run). A snapshot/lock in `_corpus_slug_frequency` would remove the
  trap.
- The suspiciously-named `suivie-de-la-manseng` (fr 1) and
  `listan-prieto-moscatel-negro` (es 1) are prose-artifact slugs kept
  alive by deliberate pins; they belong to the ARTIFACT cleanup, not the
  collision family.

One member of this family was folded on 2026-08-20: `bombino-bianco` vs
`pagadebiti` (both = VIVC #1483 BOMBINO BIANCO). The `bombino-bianco` slug
only ever existed via the bare-"Bombino" alias (10 IT records), while
`pagadebiti` was the incumbent for the spelled-out surfaces (21 IT + 25 FR),
so the alias now points at `pagadebiti` and the parallel slug is gone after
re-extraction — no facet split remains for this pair.

### Open question 4 — bare names guessed to a specific cultivar — RESOLVED 2026-08-20

Researched per-record against the source documents plus the Italian Registro
Nazionale, VIVC, regional authorized-variety lists, the Croatian national
cultivar list and DNA literature; full per-record evidence in
[tmp/bare-grape-surfaces-research-2026-08-20.md](tmp/bare-grape-surfaces-research-2026-08-20.md).
Audit flags dropped 168 → 98; every remaining bare-name flag is a
verified-correct binding. Verdicts and what was applied:

| surface | verdict | applied |
|---|---|---|
| `Cabernet` | group designation ("da Cabernet franc e/o Cabernet Sauvignon e/o Carmenère") or a line-wrap of one of the two; never reliably franc | surface banned in grape_entity; MASAF parser wrap-joins, expands the `(da …)` parenthetical, and defaults bare heads to franc+sauvignon; HU Balatonmelléki + PT Açores re-extracted |
| `Verduzzo` | HR correct (NN 25/2020 entry 233 = "Verduzzo Friulano"); IT is a friulano/trevigiano group per each disciplinare's parenthetical | `verduzzo-trevigiano` slug minted (Registro 257, VIVC 12977, SSR-distinct); parenthetical expansion emits both members |
| `Budai` | CORRECT — bare "Budai" IS the official HU register name (Balaton PDO synonym table; VIVC #881) | VIVC pin budai-zold → 881 |
| `Bombino` | bianco everywhere except Lizzano (line-wrapped "Bombino ⏎ nero"); Frusinate = the local Ottonese = bianco | wrap-join repairs Lizzano; bare alias re-pointed to the incumbent `pagadebiti` slug (see OQ3 note) |
| `Pinot` | mostly line-wraps of Pinot bianco/grigio; two genuine group designations (Colli di Scandiano, Friuli Isonzo spumante); HU Duna = wrapped Pinot noir (correct) | wrap-join + 3-way bare-head expansion in the MASAF parser |
| `Malvasia nera` | di **Brindisi** in Puglia (Lizzano's own gloss), Toscana (1960s Puglia imports; Sant'Antimo/Montecarlo annexes) AND Calabria (only Brindisi authorized, DGR 557/2019); Brindisi ≡ Lecce (SSR; DM 30/05/2018 synonyms); di Basilicata is a distinct half-sibling kept only where literally named (Terra d'Otranto) | GRAPE_ALIAS pins malvasia-nera + di-lecce → di-brindisi |
| `Alicante` | Grenache — Registro code 010 (syn. CANNONAU/GRENACHE); Bouschet is a separate entry 011; Emilia-Romagna IGTs admit only 010; Menfi lists both | alias → `grenache`; Menfi's real Alicante Bouschet recovered (wrap-join + "da soli" noise fix); FR unaffected (cahiers spell "Alicante Henri Bouschet") |
| `Canaiolo` | CORRECT — nero in all 7 (red-blend contexts; Maremma's own gloss) | none needed |

Loose ends:
- HU Duna's pill label still reads bare "Pinot" (column-mangled "Pinot ⏎
  küvéborok ⏎ noir"); binding correct, label cosmetic.
- audit_grape_surfaces' TRUNCATED heuristic (label words < slug words) is
  blind to colour-suffixed surfaces: "Alicante N." counts as two words, so
  the stale alicante-bouschet bindings in the Rimini/Rubicone EUR-Lex
  records were invisible to it (found by hand; fixed by re-running
  it/02_extract_pliegos.py after the alias change). A surface-word count
  that drops the trailing colour code would close the gap.
- Bare "Pinot"/"Verduzzo" remain globally bound (pinot-noir /
  verduzzo-friulano) via VIVC for the sake of HU Duna / the HR register
  name; a future country writing bare "Pinot" meaning something else will
  re-surface in this audit.
- Verify the two new VIVC pins against live vivc.de (it returned 500s on
  2026-08-20): budai-zold → 881, verduzzo-trevigiano → 12977 (corroborated
  via Wikidata Q371448).

Run the audit after any stage-02 change; `--strict` fails on anything
flagged.

### Second-tier ambiguous-synonym pass — RESOLVED 2026-08-21

Follow-up sweep over `audit_ambiguous_synonyms.py`'s RISKY list (44 → 35)
plus corpus cross-checks; six research agents, all verdicts implemented.
Full evidence table in
[tmp/bare-grape-surfaces-research-2026-08-20.md](tmp/bare-grape-surfaces-research-2026-08-20.md)
(second-tier section). Re-bound: GR "Grenache Rouge N" → grenache (45
entries were painted gris), RO "Saint Emilion" → ugni-blanc, IT Colli
Martani "Vernaccia (Nera)" → vernaccia-nera (bare "vernaccia" banned), San
Severo "Trebbiano bianco" → ugni-blanc, HR "Ružica crvena" → kovidinka (NN
25/2020), CH "Vernatsch" → schiava-grossa, BG "Немски ризлинг" → riesling
(un-shadowing the real Силванер row), HU bare "muskotály" banned
(wine-type term; Pécs + Hajós-Baja lose a false Muscat), HU "Mátrai
muskotály" → own slug. New slugs minted: forastera (VIVC 4189),
refosco-di-faedis (9989), magliocco-dolce (8478), magliocco-canino (7092),
biancone (1335), matrai-muskotaly; forastera-blanca's VIVC pin corrected
4189 → 24859. Confirmed correct as-is: GR Refosco (VIVC #9987 carries
"REFOSKO (PELEPONNES/ARKADIEN)"), HR Verdić → glera, DE Petite Syrah →
durif, BG bare Ризлинг → riesling, and the Weißer-Riesling / Grenache-Noir
/ Burgund-mare / Oporto / red-Traminer / Roter-Gutedel / Petite-Arvine /
Malvazija / Bianchetta-Genovese families.

Remaining loose ends:
- Scavigna's "Magliocco" renders as magliocco-dolce; its annex table (per
  disciplinare.it, not in the MASAF consolidated text) says Magliocco
  Canino — needs a per-record mechanism or an upstream text source to fix.
- ~~The 6 new VIVC pins need verification against live vivc.de~~ — DONE
  2026-08-21: all six (plus budai-zold 881, verduzzo-trevigiano 12977 and
  the corrected forastera-blanca 24859) re-fetched against live vivc.de
  via `02g --refresh --only`; every prime/colour matches the pin.
- 38 RISKY ambiguous synonyms after the 2026-08-26 corpus-walk widening
  (was 36 on 2026-08-21; +2 from the newly-walked dirs) — none known to
  bind a wrong cultivar (Brachetto, the worst offender found since, now
  has its own slug), but re-run the audit after any vocab change.

### Note — recently added VIVC pins live only in gitignored `raw/`

`raw/vivc/slug_overrides.json` is covered by the blanket `raw/*` ignore, so
these are not in version control. Recorded here so a fresh checkout can
restore them (stage 02g reports them as `ambiguous-cultivar` — or resolves
them to the wrong homonym — without a pin):

```json
"bianca": {"vivc_id": 1321, "_prime": "BIANCA"},
"freisa": {"vivc_id": 4256, "_prime": "FREISA"},
"budai-zold": {"vivc_id": 881, "_prime": "BUDAI ZOELD"},
"verduzzo-trevigiano": {"vivc_id": 12977, "_prime": "VERDUZZO TREVIGIANO"}
```

Added in the 2026-08-21 collision pass (see OQ3 above for the evidence):

```json
"bia": {"vivc_id": 1319, "_prime": "BIA BLANC"},
"mollard": {"vivc_id": 7903, "_prime": "MOLLARD"},
"picardan": {"vivc_id": 527, "_prime": "ARAIGNAN"},
"jurancon-noir": {"vivc_id": 5862, "_prime": "JURANCON NOIR"},
"nasco": {"vivc_id": 8354, "_prime": "NASCO"},
"brachetto": {"vivc_id": 15630, "_prime": "BRACHETTO"},
"terrantez": {"vivc_id": 24589, "_prime": "TERRANTEZ"},
"gajo-arroba": {"vivc_id": 23126, "_prime": "CASTELOA"},
"rufete-serrano-blanco": {"vivc_id": false},
"pugnitello": {"vivc_id": false}
```

(the `jurancon` pin was *removed* — the bare surface now folds to
`jurancon-noir` via GRAPE_ALIAS; `vivc_id: false` = deliberately absent
from VIVC, the bianchello mechanism.)

Added in the 2026-08-26 pass:

```json
"ryzlink-buketovy": {"vivc_id": false}
```

(CZ legacy zemské-víno white from the fiche §6 `**`/OTHER block; identity
contested Goldriesling #4884 vs Bukettraube #1611, neither VIVC-grounded —
see the CZ section for the evidence. The MT natives resolved WITHOUT pins:
gellewza #14174 + girgentina #17787 are plain `exact-cultivar` by-slug
records, no override needed.)

Added in the 2026-08-26 `/research-gaps vivc-ambiguous` pass (42 entries;
full evidence in [tmp/vivc-ambiguous-research-results.md](tmp/vivc-ambiguous-research-results.md)):

```
avgoustiatis→801 kanella→16124 kontokladi→6395 kotsifali→6446
koutsoubeli→6463 mavrotragano→40210 skiadopoulo→11849 thrapsathiri→12428
vertzami-lefko→13013 bratkovina→1660 debit→10423 draganela→21070
grk→5066 vugava→13184 zadarka→13365 zlahtina→22843 modra-kosovina→24493
muskat-zuti→8056 svrdlovina-crna→15638 trbljan→8075 zumic→24915
zametovka→6047 vitovska-grganja→16017 harslevelu→5314 goher→767
csomor→3281 nektar→16179 rozalia→23930 zierfandler→13443 tribidrag→9703
negroamaro→8456 andre→456 helios→17133 juwel→13212 orion→8802
orangentraube→16645 tauberschwarz→16156 weisser-lagler→24537
busuioaca-de-bohotin→8248 cristina→21045 korithi→false schiava→false
```

Same applies to the other ~450 pins already in that file; the deployed site
is built from the curator's machine, so production is unaffected.

## Traditional terms — curator pin passes (scripts/_lib/traditional_terms.json)

Empty renders scheme-only (never wrong); each pin needs the founding act cited.

- GR — ΟΠΑΠ / ΟΠΕ per PDO (33): pin from the founding ministerial decisions (ΦΕΚ), not the ΥΠΑΑΤ specs (only 1 of 132 cached specs names ΟΠΕ). ΟΠΕ = Samos, Mavrodaphne Patras / Kefallinias, Moschatos Patron / Riou Patron / Kefallinias / Limnou / Rodou; the rest ΟΠΑΠ.
- CZ — VOC (Víno originální certifikace) for `znojmo` only (zákon 321/2004 §23); the other 12 stay empty.
- CH — Grand Cru (12 Valais communal records, roster from Vinum Montis, 2 `to-verify`) and Premier Cru (22 Geneva records, GE règlement) as sub-tier terms; needs the communal / cantonal règlement cited per record before it can enter the table.
- NL — Landwijn (Annex XII PGI term) vs the BGA-labelled provincie PGIs: decide whether the 12 PGIs carry it.
- SI — vino PTP (GI-wide, Uradni list 49/2007); HU — Tájbor; BG — Регионално вино; CY — ΟΕΟΠ / Τοπικός Οίνος: confirm GI-wide use in the regulator specs, then pin.
- IT — re-scrape MASAF IDPagina/4625 when a new DOCG is recognised (the dated `ServeAttachment` elenco; the static URL is the 2014 build). ES — refresh the MAPA listado (dated header) when a new VP is registered; Urbezo is pinned until the listado catches up.
- Tooltip Wikipedia extracts for the terms (02b style-lexicon pattern): en has articles for DOCG, AOC, DOCa, DAC, IGT, Vinho regional, Landwein, PDO; fr/es/nl gaps via 02b-translate.

## Pipeline — grape canonical ranking depends on the corpus on disk

**2026-09-11** — `_vivc_canonical_by_id` (scripts/_lib/grape_entity.py)
picks, among VIVC by-slug files sharing a vivc_id, the slug present in the
extracted corpora on disk (then the most frequent). That makes
`raw/inao/cahier-extracted/` an implicit input of every stage-02 / stage-04
run and the ranking self-reinforcing: a stage-02 run started on a damaged
FR corpus wrote `corvo` for aubun, `rodo` for mondeuse, `araignan` for
picardan, `livornese-bianca` for rolle, `graciano` for morrastel … across
190 FR records, and later runs kept them. Recovered by seeding the FR
records' grape lists from the last good build and re-running (see the
session memory). To do: pin the FR-canonical slugs explicitly (a checked-in
vivc_id → canonical table, or make `GRAPE_ALIAS` the first tiebreaker) so
the choice no longer depends on what happens to be on disk, and add a
stage-04 assertion comparing the principal-slug set against the previous
build's blob.

## Cross-country — register drift check (2026-09-20) — ❌ open

Full report: [docs/register-drift-2026-09-20.md](docs/register-drift-2026-09-20.md).

| Country | Item | Action |
|---|---|---|
| FR | Cité de Carcassonne (877), Coteaux de Narbonne (881) — IGPs cancelled (arrêté 31-03-2025; Reg. (EU) 2025/2538 / 2025/2536) | ✅ kept and marked *Cancelled* via `scripts/_lib/cancelled_gis.json` (2026-09-20) |
| FR | 22 appellations with a newer homologation arrêté on INAO (Beaujolais 05-08-2026, Mâcon 07-08-2026, Meursault / Bordeaux supérieur 04-06-2026, Coteaux du Giennois / Côte de Nuits-Villages / Côtes de Toul / Entre-deux-Mers / L'Etoile / Marc d'Alsace 02-09-2026, Blagny / Coteaux varois / Crémant de Loire / Moselle / Muscat de Frontignan / Pineau des Charentes / Rosé de Loire / Saint-Bris / Vinsobres 08-06-2026, Viré-Clessé 27-07-2026, Côtes de Provence 27-04-2026, Coteaux de l'Auxois 20-09-2022) | ✅ 2026-10-01 stage 01 through a French VPN (BO Agri is geo-fenced — see CLAUDE.md): 38 fetched / 407 cached / 7 register / 14 missed; 24 canonical cahiers replaced (the 22 minus Muscat de Frontignan, whose page now links nothing newer, plus Languedoc 11-08-2026 and Bandol 11-08-2026) + 4 pinned in `manual_overrides.json` because the product page lags INAO's own Textes JO index (Crémant de Bordeaux 04-06-2026, Mâcon 07-08-2026, Côte de Nuits-Villages and L'Etoile 02-09-2026; L'Etoile's `prefer_cahier` register pin released). Stage 02 re-extracted the 28 parents + 142 DGCs (0 stubs); 02d/02e chain run `cahiers-2026-10-01` (358 facts, gate 335 supported / 23 rewritten / 0 dropped / 2 moved, audit `--strict` 0, $3.51; the gate batch sat 7.7 h in Anthropic's queue) + `cahiers-2026-10-01b` for Muscat de Frontignan; stage 03 regenerated |
| FR | Crémant de Bordeaux (31) — INAO now links the 2021 arrêté, we hold 25-11-2025 | ✅ neither: the arrêté du 4 juin 2026 (JORF 10-06-2026) is in force — INAO's Textes JO index lists it, the product page still links 2021; pinned 2026-10-01 |
| FR | 11 in PNO (Bordeaux, Chinon, Clos de Vougeot, Cognac, Coteaux d'Aix, Grés de Montpellier, Ladoix, Muscat de Lunel, Premières Côtes de Bordeaux, Périgord, Saumur) + Alsace | re-check after the opposition period |
| FR | Marc d'Alsace (1091) — the 02-09-2026 cahier is an eau-de-vie template (sections A / B / C, "1. Description des facteurs du lien au terroir"); the FR section parser extracts no lien and no grapes from it | ✅ 2026-10-04 — INAO's 2026 eau-de-vie template ("Chapitre Ier : Conditions de production et lien à l'origine", Arabic "N. - Title" sections; the A / B / C were the Chapitre III control-plan rows the EU letter-template branch took): `is_spiritueux_2026_template` branch in stage 02, `kind: EDV`, aire 53 Haut-Rhin + 64 Bas-Rhin communes, lien 5.9 KB (section 5), grape gewurztraminer Rs from "4.1° Matière première" (grapes are parsed for a grape-derived spirit only). The 2026-10-01 refresh had also renamed the record `marc-d-alsace` (the manifest re-read SIQO's `appellation` column) — the registered name *Marc d'Alsace Gewurztraminer* (SIQO `produit`, INAO product 13046, PGI-FR-01836, cahier §2) is pinned in `siqo_supplements.json` `name_overrides`, stage 02 takes names from the referentiel, slug and URL restored. 02d/02e chain run `marc-d-alsace-2026-10-04` (the old 3 facts came from the 2009 décret text). Expect Cognac / Armagnac / Calvados republications in the same template |
| FR | Limoux (251), Savigny-lès-Beaune (231), Floc de Gascogne (319) — never had a manifest cahier (rescued from sibling bundles); the register tier bound their own `CDC_*.pdf` on 2026-10-01, lien byte-identical to the rescue | ✅ no action |
| FR | stage 01 regexes miss `boagri/rectificatif-…` and `legifrance.gouv.fr/eli/…` links | ✅ fixed 2026-09-20 (`BOAGRI_RECTIFICATIF_RE`, `LEGIFRANCE_ELI_RE`; a page with only those links keeps its prior cahier) |
| IT | Salemi (PGI-IT-A0807) cancelled Reg. (EU) 2026/1043 | ✅ in `cancelled_gis.json` (marked, not dropped); the record is a no-geometry stub, so it is not in the blob until it gets a polygon |
| NL | Ambt Delden (PDO-NL-02169) cancelled Reg. (EU) 2026/1068 | ✅ in `cancelled_gis.json` (kept and marked) |
| HU | Mura / Murai (PDO-HU-02817) registered Reg. (EU) 2026/1792, single doc C/2026/1833 | ✅ added 2026-09-20 (Balaton; `gisco-commune-union` 8/8; 12 facts) |
| ES/HU/IT/RO/SI/DE/GR | 38 GIs with a new OJ C / OJ L publication after our fetch (list in the report) | re-fetch 01 → 02 for those slugs |
| all | earlier cancellations (pre-2023) are not in `cancelled_gis.json` — out of scope for now | ❌ open |

## France — INAO parcellaire release 2026-09-28 (checked 2026-09-30) — ✅ adopted 2026-10-04

data.gouv.fr: only the parcellaire moved (2026-05-11 → 2026-09-28, sha1
`e671f920…`, 11,773 → 11,751 rows, 357 → 356 `app` values); SIQO CSV
(2025-12-31) and both aires CSVs (2025-10-09) are byte-identical to `raw/`.
Adopted 2026-10-04: `raw/inao/parcellaire.zip` + `raw/manifest.json` now name
the 2026-09-28 resource (sha256 `82cb533d…`), the shapefile sits beside the
2026-05-11 one under `raw/inao/parcellaire/` (`resolve_shapefile` takes the
newest), the 2026-05-05 URL is gone from data.gouv.fr (404 — the dataset keeps
the latest resource only, which is why dropped rows have to be checked in).
All 11 rows of `inao-shapefile-patch.csv` match exactly once in the new
release. Rows the release dropped and nothing retires are carried forward
from the 2026-05-11 extract — `scripts/_lib/parcellaire_carry_forward.json`,
see CLAUDE.md « Rows carried forward from an earlier release »; the gap audit
and `tests/test_parcellaire_carry_forward.py` turn STALE the day the rows
return. Re-check each weekly export.

| Change in the layer | Verified cause | Action |
|---|---|---|
| Languedoc Montpeyroux (id_denom 1313) removed — Arboras, Montpeyroux, 9.6 km² | **AOC Montpeyroux recognised**: arrêté du 11 août 2026 (NOR AGRT2607509A, JORF 15-08-2026, INAO show_texte 8608, product 23354, red only; national transitional protection, EU application not yet on eAmbrosia). Draft cahier (PNO June 2025): Arboras, Montpeyroux, Lagamas, Saint-Jean-de-Fos. Its parcels are not in the layer yet | ✅ 2026-10-04 `montpeyroux` parent added through `scripts/_lib/fr/siqo_supplements.json` (provisional id `p23354`; stage 01 fetched the cahier through a French VPN; stage 02 extracts 4 principal + 3 accessory grapes, 4-commune aire, 7.6 KB lien; region pinned LANGUEDOC; register absence pinned); the old DGC rows of id_denom 1313 stay the only parcels until INAO ships the new aire parcellaire. Cahier fetched 2026-10-01 (BO Agri `2128d40f-f2c2-436a-8d1c-cd993626aa30`, sha `a6c640d1…`, 10 pp.: red only; aire Arboras, Montpeyroux, Lagamas, Saint-Jean-de-Fos; principals grenache N, mourvèdre N, syrah N, carignan N; accessories cinsaut N, counoise N, morrastel N); until INAO ships the parcels, keep the 2026-05-11 rows of id_denom 1313 as an approximation (the arrêté's art. 2 lists DGC parcels not retained in the new aire parcellaire, and the draft aire adds two communes) |
| — | **Languedoc re-homologated the same day** (arrêté du 11 août 2026, NOR AGRT2607507A, abrogates the arrêté of 18-11-2024; show_texte 8607, BO Agri `ec0fa131-4766-401d-9f09-aa0f942d6504`, fetched 2026-10-01 sha `f3344ab2…`). **Section II lists nine DGCs — Montpeyroux is dropped**; it survives only in the commune list and a stale sentence of the Saint-Saturnin lien | ✅ 2026-10-04 `languedoc-montpeyroux` kept and marked through the new `scripts/_lib/promoted_gis.json` (green *Promoted* badge + dated line linking the successor, the arrêté and the new cahier); when the SIQO export drops row 1313, the stage-02 drop guard refuses the run until a `retained` supplement row keeps it |
| Saint-Sardos (id_app 686) removed — 23 communes, 36.4 km² | **no legal act**: nothing in JORF 11-05 → 30-09-2026 (DILA dumps swept), nothing new in INAO's Textes JO, eAmbrosia PDO-FR-A0408 `registered`; product pages 8380 / 8381 still serve (updated 17-06-2026) but INAO's product search returns nothing for "Sardos". Upstream data state, not a withdrawal | ✅ 2026-10-04 carried forward: the 23 rows of the 2026-05-11 release are a checked-in extract (`parcellaire_carry_forward/saint-sardos-2026-05-11.geojson.gz`, INAO's coordinates unchanged) appended by `build_aoc_polygons` and the coverage index; `geom_source` stays `parcellaire`, the card says "Parcel delimitation from the INAO release of 2026-05-11; the release of 2026-09-28 carries no rows for this denomination". Still 2026-09-28 on data.gouv.fr on 2026-10-04; drop the entry when the rows return (the audit says STALE) |
| Côtes de Provence la Londe (id_denom 1839) added — 4 communes, 33.4 km², `insee` null (`insee2011` filled) | cahier of 27-04-2026 (show_texte 8412, already in the newer-arrêté list); product records re-created 13-05-2026 (25202–25204) | ✅ 2026-10-04 `load_coverage` reads a code only from a string field (the null `insee` is a float NaN and had become a commune "nan"), and splits the few two-code fields ("49078,49115"); the record's four codes come from `insee2011` (83019, 83047, 83069, 83071) |
| Blaye cluster (Bordeaux, Bordeaux supérieur, Crémant de Bordeaux, Côtes de Bordeaux + Blaye) ~20 communes, +8 to +17 ha; Languedoc 34 communes, −6.9 ha; Val-de-Livenne's two Blaye rows merged; Vinsobres CVI + `1B540S`; nomcom typo `SAINT-CHRISTOLY-DE-BLAYEE` | routine re-digitising | footprint cache invalidates for those records only |

## France — stage 02 homologation dates and the 2024 Saumur layout (2026-10-04)

| Finding | Fix |
|---|---|
| 266 of 467 parents had no `source.homologated_at`: the date regex required "par le décret / par l'arrêté" (150 cahiers say "par arrêté"), missed "du 1er …" and INAO's own typo "homologué pa l'arrêté" (Montpeyroux), and never looked at the BO Agri cover line above the title the splitter cuts at | ✅ `homologation_date(segment, before)` — 583 → 1,479 dated records, none lost; `tests/test_fr_cahier_parser.py` |
| Saumur (110) was served the superseded 2019 cahier through the rescue: its own PDF is the arrêté du 12 janvier 2024, whose headings carry no numeral (pdftotext drops the list numbering), so the Roman splitter found nothing. Dating the index exposed it (the 2024 segment won and the record became a stub) | ✅ `extract_unnumbered_sections` (≥ 6 canonical titles on whole lines); Saumur + Saumur Puy-Notre-Dame now read the 2024 cahier (lien 14,937 chars, Chenin / Cabernet franc principal + 8 accessory). The aire table leak ("Doué-en-Anjou (pour le seul territoire … Vins tranquilles blancs et Fontaine …)", duplicates per wine type) ✅ 2026-10-04: `strip_table_label_column` + per-département dedupe (266 cahiers carry the table header; corpus-wide 412 leaked label tokens → 0 and 9,213 duplicate commune tokens → 0; Saumur 114 → 54 distinct aire communes, proximity 209 → 95; both the 2019 and 2024 layouts); the page-break header fold rejoined lists cut by a page (the 51 Alsace grands crus' proximity zone 45 → 79) |
| Saint-Joseph (284) rescued from the 2011 décret bundle while a 2024 cahier (`8b76129f…`, arrêté du 4 juillet 2024) was on disk undated | ✅ follows from the dates — now the 2024 text |
| Marc d'Alsace (1091) eau-de-vie template — see the drift section | ✅ 2026-10-04 (drift section) |
| `montpeyroux` drew the DGC aire "Languedoc Montpeyroux" (2 communes) because `aires._resolve_key` bound a record name sitting inside a longer CSV label | ✅ 2026-10-04 the reverse-substring step now needs the record to be an alias part of the label (Pouilly); Montpeyroux resolves from its cahier's 4 communes (`communes`). Side effect, swept over 467 parents: IGP **Côtes du Lot** now binds to IGP CSV aire "Lot" (IDA 2043, 340 communes, all département 46) instead of the 6 out-of-département communes the cahier text yielded (the parser missed "le département du Lot"); the cahier's 6 extra communes (Lot-et-Garonne: Fumel, Montayral; Tarn-et-Garonne: 4) are not in the CSV row → ✅ 2026-10-04 **no pin**: read, the six are the *zone de proximité immédiate* (a vinification derogation) and they are **cantons**, not communes — "cantons limitrophes … dans le département du Lot-et-Garonne : Fumel et Tournon-d'Agenais ; dans le département du Tarn-et-Garonne : Lauzerte, Molières, Montaigu-de-Quercy et Montpezat-de-Quercy"; the aire is "le département du Lot", exactly the CSV row. The extractor had read the proximity list as the aire: stage 02 now routes the proximity sentence to `aire_proximite_immediate` and records the whole département as `aire_departements` (29 FR records — Gard, Aude, Drôme, Isère, Pays d'Oc, Méditerranée's ten …; some forty IGPs had carried their neighbours' communes as their own aire). The wiki page says "Lot — l'ensemble du département" |
| `rerun_terroir_facts.py --scoped-02d` dropped a scoped slug that had no facts cache yet (Montpeyroux: logged "will be extracted", never passed to 02d) | ✅ fixed 2026-10-04 — the country is read from the extracted record |

Orphan rows (null `signe` / `app`) in the aires-géographiques shapefile of the
same date: Cité de Carcassonne, Coteaux de Narbonne, Saint-Sardos, Languedoc
Montpeyroux, Alsace grand cru, the two Pouilly "complété par une dénomination
de climat" rows, Pays d'Auge Cambremer, Pintadeau de la Drôme.

## Cross-country — commune-union homonym guard (2026-09-23) — ✅ audited, 1 pin open

Raised by the ΠΓΕ Άγιο Όρος geometry report (visitor mail, 2026-09-23). One
wrong bbox turned out to sit on top of three separate defects: a soft facet
used as geometry, a commune union with no homonym guard, and a detached-part
detector that could not see large outliers.

### GR — the reported record (`scripts/_lib/gr/`, `tests/test_gr_parser.py`)

| Defect | Effect |
|---|---|
| `nuts_region` accepted the `region` facet as a geometry candidate | a soft text-scanned label became a 42,000 km² polygon (Άγιο Όρος drawn as Στερεά Ελλάδα, ~93 km south of the peninsula) |
| the GR region scan read the *terroir narrative* | a passing "…η Αττική" in a comparison sentence set the facet; now geo-area + name only, the IT `derive_regione` rule |
| `_REGION_MARKER_RE` listed bare `του` / `της` / `στην` first | swallowed any genitive place name, Mount Athos included, and shadowed the `περιφερειακή ενότητα` / `νομός` branches into dead code |
| `_LAU_TIER_PREFIX_RE` did not know `Ψευδοδημοτική Κοινότητα` | all **68** Greek self-governing communities were unreachable by name in the GISCO index |
| a curated `slug → [NUTS_ID]` pin ranked *below* the commune heuristic | the Τύρναβος and Πλαγιές Παϊκού pins were silently dead |
| `_TOPIKI_BELONGS_RE` kept the δήμος over the named community | premise ("GISCO community polygons aggregate up to the δήμος") is the opposite of how the layer is built — 6,142 EL rows against 332 δήμοι. Folded into `_SUBUNIT_OF_DIMOS_RE`, which keeps the sub-unit |

Άγιο Όρος now resolves through the commune list to Άγιο Όρος + Ουρανούπολη =
**358.8 km²** at community precision. It deliberately carries **no** NUTS pin,
so a future parser regression surfaces as `stub-no-geometry` rather than a
plausible-looking coarse polygon.

### The same unguarded union, per country

| Country | Live exposure | Outcome |
|---|---|---|
| RO | 13 records | ❌ **was the worst** — 11 of 13 inflated, several to the full width of the country. Fixed with a județ mask, below |
| CH | 35 records | ✅ already canton-filtered; the filter was waived for be/vs/fr/gr as "bilingual cantons may straddle", which confuses language with territory. Waiver removed — the one genuine cross-canton area (Vully FR+VD) is curated in `PER_AOC_COMMUNE_LISTS`, which bypasses the filter. Dropped the BE règlement's German common noun "Messen" → the Solothurn commune |
| HU | 8 records | ✅ 0 ambiguous names in the corpus; guard added anyway (verified byte-identical geometry) |
| BG | 0 records | ✅ defensive fallback only; guard added |
| GB | 0 records | ✅ one geometry per name — cannot over-union |
| CZ | — | ✅ already masked by the per-podoblast Bétard polygon |

### RO — the județ mask

Romanian commune names repeat heavily: `Izvoarele` is 5 communes, `Fântânele`
7, `Ștefan cel Mare` 6. `commune_union` took every homonym, so *Colinele
Dobrogei* — a Black Sea appellation — ran from 21.35°E to 29.02°E, and
*Dealurile Vrancei* spanned 43.75°N to 48.2°N. The specs name their județe
(`judeţul X`, or `jud. X` inline in the ONVPV caiete), and Romania's 41 județe
+ Bucharest ARE the NUTS-3 units, so the GISCO NUTS-3 layer is the boundary
set. `parse_judet_list` harvests them and every matched commune is held to
them; with no declared județ, an ambiguous name contributes nothing. The mask
can only remove area, never add it.

| record | before | after |
|---|---:|---:|
| Colinele Dobrogei | 7,730 km², 21.35–29.02°E | **5,111 km², 27.86–29.02°E** |
| Dealurile Vrancei | 6,012 km², 43.75–48.2°N | **1,315 km², 45.38–46.12°N** |
| Dealurile Munteniei | 8,267 km² | **3,236 km²** |
| Dealurile Olteniei | 4,193 km² | **1,072 km²** |
| Dealurile Transilvaniei | 14,898 km² | **8,576 km²** |
| Terasele Dunării | 3,087 km² | **1,802 km²** |
| Jidvei | 567 km² | **349 km²** |

**✅ `dealurile-moldovei` — resolved 2026-09-24, no pin needed.** Its document
DOES declare six counties — Iaşi, Galaţi, Vaslui, Neamţ, Bacău, Botoşani — but
as section headers (`1. Judeţul Iaşi`, `1.1 Judeţul Galaţi`, …) that the
mangled PDF→HTML numbering turned into sub-sections, so they landed in
`section_titles` and never in any body text the harvester read.
`judet_source_text` now feeds the titles to `parse_judet_list` as well:
26,835 → 11,205 km², 26.22–28.26°E — the Moldavian region.

**✅ RO commune-parser recall — 2026-09-24.** A 13-agent diagnosis of every
name that failed to match (with an adversarially-checked synthesis) found the
misses were parser rules, not data: unstripped `Com.` / `Com` / `Loc.` /
`localităţile` / `sat` / `sate` / `cartierele` lead-ins (139 names), glued
`ComunaX` from lost spaces, descriptor tails (`- sat X`, bare `satele`, `oraşul
X cu …`, `Com. X - X`), an unanchored tail cut that emptied whole chunks
(`localităţile componente Mediaş`), county-seat / numeric / 2-letter names
rejected before lookup (Municipiul Iaşi, 23 August, Ip), eight spelling drifts
(Isacea → Isaccea, Năieni → Năeni, …, aliased on the spec side only — never
fuzzy), the cedilla `şi` the splitter did not know, typographic dashes deleted
by the ASCII fold, and PDF footers. All landed in `scripts/_lib/ro/commune.py`
+ `geometry.py`, each pinned in `tests/test_ro_parser.py`. The structural
change: **section-scoped counties** — `parse_commune_list_scoped` returns
(name, [județe]) pairs from the county header each name sits under, stage 02 /
02f store them as `geo_communes_scoped`, and `commune_union` masks each name
to its own county (record-wide mask as fallback). Griviţa is a commune in both
Galaţi and Vaslui and Dealurile Moldovei lists it under each: record-wide that
was an ambiguity, scoped it is two matches.

| | before | after |
|---|---:|---:|
| matched communes, 13 records | 556 | **719** |
| Dealurile Olteniei | 20 | **119** |
| Dealurile Moldovei | 168 | **204** (26.51–28.26°E, the Moldavian region; six counties from its section titles) |
| ambiguous names | 48 | **0** |

Still ~1,000 "unmatched" names per the diagnosis are **villages (sate)**, which
GISCO has no polygon for — an explained category, not a miss. Deferred, with
the reasons: village-role tagging with an adjacency guard (medium risk, ~0
polygons gained, needs the INS SIRUTA sat→comună gazetteer to be done
honestly); the restricted line-wrap join (cleanup only). **One per-record
exclusion is open**: `dealurile-zarandului` delimits only "Curtici (satul
Dorobanţi)" — Dorobanţi (RO_12912) is its own LAU and already matched, yet the
whole Oraş Curtici (72.6 km²) is added; a resolver rule ("X (satul Y)" with Y
an in-county LAU bordering X → use Y) or a reviewed stage-04 exclusion. Also
noted: stage 02f stamps `extracted_at` with the clock, so a no-op re-run
rewrites all 14 sidecars (pre-existing; the scripts contract says a no-op
should be byte-stable).

### The detector that should have caught all of this

`audit_geometry_outliers.py` built its "main body" by AREA RANK — the largest
parts until they held 95% of the total — and exempted every part in that set
from the test. A large *detached* part could therefore be absorbed into the
body and never checked. Saale-Unstrut's Werderaner Wachtelberg (117 km²,
87 km out) was precisely the part that tipped the accumulator past 95%: the
audit reported nothing for it, and its own whitelist entry read as stale. The
body is now built by area rank but refuses to absorb a part isolated from
every other part (one indexed STRtree pass). Pinned by
`tests/test_geometry_outliers.py`.

Effect: whitelist entries all match again (0 stale, Saale-Unstrut and the two
Welsh entries back to ACCEPTED). The newly-visible findings were triaged on
2026-09-24 — 21 records, one Explore agent each reading the finding from the
audit file, every verdict adversarially refuted by a second agent (20 of 21
upheld; the one refutation corrected a proposed fix, not the classification):

| outcome | records | what |
|---|---:|---|
| whitelisted (legitimate, source-cited) | 9 | Württemberg + Landwein Neckar + Schwäbischer Landwein (the Bodensee outpost, BLE spec §4/§7.1); Rheingau + Rheingauer Landwein (Felsberg, BLE spec §3); Viile Timişului (Podgoria Teremia, OJ C 90/2021); Marc d'Alsace Gewurztraminer + Alsace lieu-dit (the Wissembourg communes, INAO cahier + aires CSV); Μοσχάτος Κεφαλληνίας (Πόρος, Β.Δ. 386/1971) |
| clipped (Bétard cross-attribution) | 1 | Hrvatsko primorje — Skradin (184 km²) lies in the MPS spec of Dalmatinska zagora, not Hrvatsko primorje |
| upstream parser / table fix | 11 | PT: freguesia lists inside parentheses read as concelhos (Duriense → Pombal, Leiria) and an exclusion clause read as an inclusion (Beira Atlântico); IT: `S. Arcangelo di Romagna` bound to Sant'Arcangelo (PZ) by a prefix fallback; BG: Оряховица (Stara Zagora) listed under the northern PGI; DE: Taubertäler Landwein mapped to the whole Württemberg PDO; ES ×6: a first-word fallback accepted as "unambiguous" with no province check (Salinillas de Buradón → Burgos, Alcocer de Planes → Guadalajara, San Pedro de Muro → San Sadurniño), parroquia lists leaking past a case-sensitive `Así como`, hyphen and `/` normalisation, a subzona paragraph bleed (Torrevieja) |

After the RO county scoping and the nine whitelists, **unreviewed 100 → 88**;
after the eleven upstream fixes below and the final rebuild, **70**, and after the
SIGPAC-Jaén + Galician-parroquia build later that day **69**, unchanged by the
polígono-footprint build that followed (20 accepted, 11 confirmed clips, 0
pending, 0 stale; none of the 21 triaged records remains; Sierra Sur de Jaén
not flagged). Overlap audit likewise unchanged at 491 / 3 accepted, no Sierra
Sur pair.
Terasele Dunării was then whitelisted too (its seven parts are the listed
Danube communes, OJ C/2026/893 §6 — Zimnicea, Greaca, …, Însurăţei).

### The eleven upstream fixes (2026-09-24) — implemented and measured per country

Each was implemented by one agent against the verified note, with a
regression test that fails on the old code, and a corpus-wide probe of every
record of that country (parsed sets + resolved parts before/after). Stage 04
was not run by the agents; the effect was confirmed on the final rebuild.

| country | change | corpus effect | caveats left, with the reason |
|---|---|---|---|
| **PT** (`scripts/_lib/pt/commune_list.py`, `geometry.py`) | parenthetical freguesia lists stripped innermost-first before the split; the honorific `D.` no longer ends a capture (case-sensitive guard); an exception clause (`com/à exceção de …`, `exceto`, `excluindo`) routes its list to `excluded_concelhos`, which the distrito expansion leaves out member-wise; enumerated `a) O distrito de X` forms now match | Duriense 3 parts / 4,683 km² → 1 / 5,513 (Pombal-Leiria gone; Mirandela, Torre de Moncorvo, Vila Flor recovered); Beira Atlântico 4 / 3,229 → 1 / 6,747 (Aveiro + Coimbra distritos in, the six excluded concelhos out); Terras da Beira 3 → 9 concelhos; Lisboa −Azambuja, Tejo −Ourém (both excluded by their own text); 5 records lose only freguesia tokens that never matched | ❌ pre-existing, out of the findings' scope, each per the record's own text: **terras-da-beira** misses all of distrito Castelo Branco ("todas as freguesias de todos os concelhos do distrito de" — no distrito regex knows that form); **transmontano** resolves 2 of ~24 concelhos (`;`-separated concelhos with `;` inside the parentheticals end the capture); **lisboa** loses Porto de Mós to `_strip_freguesia_tail`; **minho / vinho-verde** drop "a freguesia de Ossela, do município de Oliveira de Azeméis" before the v1 freguesia-parent rule runs. The paren-aware terminator the note suggested was tried and rejected — it lost Moura from Alentejo |
| **IT** (`scripts/_lib/it/comune.py`, one stage-04 call) | fused ISTAT hagionyms indexed under their `san`-split form (84 names, zero clashes); a match is rejected when the text runs on through a name connector (di/del/della/sul/in/… — not `e`, the list conjunction); `resolve()` takes the record's regione and drops cross-regione homonyms; glued `Jonico,San` commas split; three disciplinare spellings aliased (Castelguelfo, Ozzano Emilia, Terre del Sole) | Bianco del Sillaro 20 → 37 comuni, 5 → 2 parts (Sant'Arcangelo PZ out, Santarcangelo di Romagna RN in, the 14 Forlì-Cesena comuni the Castrocaro miss had cut off back); Rubicone +2; 9 further records improve in the resolver only (their build geometry comes from a zone layer or Bétard) | 🟡 **friuli-grave**: the resolver now yields Udine + Pordenone whole-province instead of one wrong Trentino comune — not live (build uses Bétard), but the comune list itself is unparsed because the text says "territorio comunale di:", a keyword the parser does not know. The "in provincia di X" clause was not wired in: the regione filter settles every ISTAT cross-regione homonym pair (7 probed), so it would be unexercised code |
| **ES** (`scripts/_lib/es/geometry.py`, `commune_list.py`, `subzona.py`) | a first-word fallback hit is a guess, never "unambiguous": it no longer votes for the province set and is accepted only inside the provinces the exact matches established, and for a multi-word name only when the common prefix reaches past the head word (two words after san/santa/villa/val/puebla), the GISCO name is a whole-word prefix of the pliego's longer form, or the particle-stripped words agree; `/` bilingual GISCO names split before the character pass (they never matched exactly before), `-` is a word separator, curly / acute apostrophes and Catalan ` i ` folded; the abbreviation case of the class docstring ("Albelda" → Albelda de Iregua) actually implemented; parroquia enumerations stripped with their holder, `así como` ends a list case-insensitively, `- <muni>: las parroquias de …` lines keep the muni; the last subzona's capture stops at a sentence boundary (full ES stage 02 re-run: 4 records changed, only `subzona_communes`) | 29 of 78 commune-resolved records change, every name traced to its pliego token; all six flagged parts gone — Valle del Miño-Ourense 16 parts / 1,370 km² → 1 / 726 (exactly its 14 municipios), Norte de Almería one polygon of 1,145 km² (Vélez-Blanco + Vélez-Rubio recovered), Betanzos 3 → 1 part, Barbanza 8 named municipios, Rioja Alavesa +Oyón-Oion, El Comtat ends at Cocentaina; Villaviciosa de Córdoba's only polygon had been Os de Balaguer (Lleida). Montsant + Priorat wkb-identical | 🟡 whole-municipio proxies the new rules drop, each per the pliego's own wording — a curator call whether the polygon or its absence is the better proxy: ~~**Padrón**~~ (Barbanza e Iria — resolved: drawn as its two named parishes, Iria Flavia + Padrón, 12.3 km², from the IET parroquia layer), **Martos** (Sierra Sur de Jaén: numbered polígonos only; Alcaudete was never bound), **Caudete** (Valencia-Clariano: registered parcels only). ❌ **Kripan** (Rioja Alavesa) still unmatched — the pliego writes Cripán, GISCO Kripan, and an alias would not rest on the record's text. **rio-negro "San Andrés"** left unmatched rather than tie-broken between two Guadalajara San Andrés. **monterrei-ladera-de-monterrei** briefly fell to the parent polygon (its three former municipios were all parish-holder phrases) — resolved the same day by the IET parroquia layer: it is now `iet-parroquia-union` of Vilardevós + 25 named parishes, 466.8 km² |
| **BG** (`geometry.py`, `region.py`) | PDO-BG-A1344 Оряховица moved from the Дунавска равнина PGI to Тракийска низина; region facet likewise; membership tables asserted to partition the PDOs | Дунавска равнина 6 → 5 parts (−1,076 km² at 42.41 °N); Тракийска низина unchanged (the polygon was already inside its body) | 🟡 Bétard's 1,076 km² polygon for Оряховица looks like a whole obshtina where the ИАЛВ spec (§3) names four village land areas in област Стара Загора — precision, out of scope |
| **DE** (`geometry.py`) | Taubertäler Landwein no longer a union of the Württemberg PDO; `DE_LANDWEIN_AREA` transcribed from the BLE spec §4.1/§4.2 (13 Main-Tauber-Kreis Gemeinden + Bieberehren, Röttingen, Tauberrettersheim, Rothenburg o.d.T., Adelshofen for Tauberzell); `_DE_KREIS_AGS` gains 08128 / 09679 / 09571; `_de_norm` strips the Bavarian `, St` / `, GKSt` / `, M` | 2 parts / 10,757 km² (the whole Württemberg PDO incl. the Bodensee outpost) → 1 part / 1,243 km², the Tauber valley; Württemberg, Landwein Neckar and Schwäbischer Landwein unchanged | ❌ §4.1 lists 37 **Gemarkungen** flat, unbound to a Gemeinde; only the 13 named Gemeinden were transcribed. If a Gemarkung lies in one of the 5 Main-Tauber communes the spec does not name (Ahorn, Assamstadt, Freudenberg, Igersheim, Wittighausen), that commune is missing — no regulator source binds Gemarkung → Gemeinde, so none was asserted. The region facet: **decided 2026-09-24** — `REGIONS` gains "Baden-Württemberg" for a Landwein whose BLE area spans two Anbaugebiete of one Bundesland (Taubertäler = Baden + Württemberg Gemeinden, §4.1/§4.2), and Schwäbischer Landwein moves Baden → Württemberg (its §4 area is the Württemberg Anbaugebiet plus the Bodensee outpost); the rule is written into `scripts/_lib/de/region.py` and pinned by `test_landwein_region_facet_follows_the_anbaugebiet_or_bundesland_rule` |



### DE — re-extraction after the region relabel surfaced three lexicon defects (2026-09-24) — ✅ fixed

Re-running `de/02_extract_pliegos.py` for the Taubertäler / Schwäbischer
region relabel changed the grape rosters of 16 records, so every changed
surface was traced to its source line and checked against VIVC live:

| surface (DE regulator text) | bound before | bound now | why |
|---|---|---|---|
| `Roter Riesling` (16 records; BLE sidecars of Nahe, Pfalz, Franken too) | `gewurztraminer` (EU documents) / `roter-veltliner` (fuzzy 100 on Roter Veltliner's VIVC synonym "RIESLING ROTER") | **`roter-riesling`**, new slug — VIVC #10076 RIESLING ROT, berry colour rouge, Germany; colour `rose` like Roter Elbling (vinified white) | a distinct registered variety, not a Riesling spelling; the exact alias now beats the synonym |
| `Lämmerschwanz` (Franken) | `juhfark` (fuzzy) | `juhfark`, pinned in `GRAPE_ALIAS` | VIVC lists LAEMMERSCHWANZ under four primes (JUHFARK #5852, CSOMORIKA #3281, HARSLEVELUE #5314, RABO DE OVELHA #16956) — the re-extraction had drifted to `csomor`; de.wikipedia "Juhfark (deutsch: Lämmerschwanz)" settles the German usage |
| `Gm 6414-39` (Nahe, Nahegauer Landwein) | `ehrenbreitsteiner` | unbound (raw candidate) | VIVC #4726 GEISENHEIM 6414-39 is its own accession, not Ehrenbreitsteiner (#4725) — an anonymous breeder code, per the DE rule |
| `Roesler` (Pfalz, Pfälzer Landwein, Württemberg) | `riesling` (fuzzy) | `roesler` (VIVC #15438, Klosterneuburg red crossing) | lexicon catch-up from the AT pass |
| `Roter Veltliner` (8 records) | unbound | `roter-veltliner` (VIVC #12931) | lexicon catch-up from the GB pass |

`02g --only roter-riesling` resolved the passport (`exact-cultivar`). Its
only Wikipedia article is German: the en fetch had landed on the Riesling
article through a VIVC synonym, so `en` is pinned `null` in
`raw/wikipedia/grape_overrides.json` and the four locales are translated
from de. The translator then crashed on German (`LOCALE_NAME` had seven
languages), and three older cards were never read at all — Blauer
Wildbacher and Rathay (de) and Kraljevina (sl) had no tooltip in any
locale. `de` / `sl` now close the source chain (after every language
already used, so no cached translation moves; 16 pairs translated), and
the tooltip gained `wiki_lang_de` / `_sl` / `_it` — 230 Italian-sourced
tooltips read "Wikipedia IT" before. `tests/test_grape_translate_sources.py`
pins both tables. Not done, a design call: the corpus hands the chain
country codes (`at`, `si`, `ch`), so an Austrian or Slovene variety still
prefers an English article over its own-language one; mapping them would
re-translate 13 cached tooltips from a different source. Everything else in the 46 DE
records is byte-identical to the pre-relabel snapshot. Lesson recorded: a
VIVC synonym in the vocabulary can outscore a real variety name that the
lexicon does not know — after adding a variety for one country, re-extract
the countries whose rosters name its near-homonyms.

### Code review of the 2026-09-24 changes — 23 findings, adversarially verified

Five Explore reviewers read the uncommitted diff by area; a second agent per
area tried to refute each finding by reproducing it. 22 confirmed, 1
plausible (es-5, a fetch-convention remark), 0 refuted.

**Greece — the region facet (gr-bg-hu-region-1).** Taking the terroir
narrative out of the GR region fill (the Athos fix) left 102 of 147 GR
records on the generic "Ελλάδα". The live site shows why the scan had to go:
against the live facet it was wrong for 19 records (all 15 retsinas under
Κρήτη, Achaia under Θράκη, Ilia and Zakynthos under the wrong islands,
Nea Mesimvria under Θράκη) and right for 15. Stage 04 now takes the PGI
region from the NUTS unit its geometry resolved to — the unit the spec cites
("GR232 Αχαΐα") or a curated pin — through `region_for_nuts_ids` in
`scripts/_lib/gr/region.py`, after the curated map and the geo-area / name
scan. The nine facet values are Greece's geographic regions, which cut across
the administrative ones (el.wikipedia "Γεωγραφικά διαμερίσματα της
Ελλάδας": Attica, Euboea, Aitoloakarnania → Στερεά Ελλάδα; Achaia, Ilia →
Πελοπόννησος; Drama, Kavala → Μακεδονία; Kythira → Ιόνια Νησιά); units that
straddle two (EL307, EL51, EL63) resolve to nothing rather than a guess.

**Greece — commune parser (gr-2 … gr-6).** The δήμος-name sweep was compiled
IGNORECASE, so its capital anchor matched anything and ate the next list item
("… του Δήμου Τυρνάβου και Δελερίων" lost Δελερίων); names are now
case-sensitive with all-caps tails allowed, the tier words stay
case-insensitive through `(?i:…)`. A sub-unit of two or three words ("Αγίου
Παύλου", "Νίκου Καζαντζάκη") now drops its δήμος too; the genitive plural is
spelled out (κοινοτήτων — the accent moves); plural «Τοπικές Κοινότητες»,
the pre-Kallikratis «δημοτικό διαμέρισμα» and «καθώς και» are separators; a
trailing "της Λάρισας" qualifier is stripped at match time, only when the
bare head is itself a community. On the nine GR records with EU-OJ area
text, three parses changed, all gains (Tyrnavos +2 communities). The
Epanomi pin to all of Θεσσαλονίκη (EL522, 3,689 km²) is gone: its single
document names one community (79.5 km²), now drawn at that precision, with a
curated Μακεδονία facet. The Thrace PGI is pinned to Evros + Xanthi + Rodopi:
its spec says "όλες τις περιοχές της Θράκης" but cites GR11 "Ανατολική
Μακεδονία, Θράκη", which drew Drama and Kavala too.

**Independent check of the agent fixes (2026-09-24, second model).** The
Romanian fix (ro-1 … ro-6) passed its checker on the corpus (46 records,
719 communes matched, ambiguity 0, no geometry change) with three edge
cases outside the corpus; two are now guarded — a county header that runs
on into prose ("în judeţul Iaşi pe raza comunei Bohotin judeţul Vaslui, …")
no longer swallows the next marker, and "Com. Lungeşti - Lungeşti - satele
…" keeps the seat-village cut — and the third (two county lists joined by
"şi din" / "respectiv") is recorded below. The Italian fix passed (Alto
Livenza 8 → 14 comuni, Garda 27 → 43, Vallagarina 3 → 21, Colli di Luni
12 → 15; all 522 records otherwise identical); its checker notes that a
comune written with a regional qualifier ("Lugo di Romagna") is kept only
when the comune listed just before it shares the province, and that an
appellation with exactly one comune in a second regione would still lose
it — no record has that shape today. The Spanish fix passed (12 records
rebind; on the map only the subzonas Ribeira Sacra Quiroga-Bibei and
Costers del Segre Pallars change) with two notes: the new "así como los
términos municipales de …" fold would also fold a partial-municipio clause
("… el término municipal de Rialp en su parte situada …") if one ever
appeared, and three synthetic rows in `tests/test_es_commune_matching.py`
carry INE codes that are not the real ones (harmless, like older rows).

**Second-model check of the Greek changes (2026-09-24).** Four read-only
verifiers re-derived them: the region table against the cited el.wikipedia
article (every mapping quoted; the three straddling units EL307 / EL51 /
EL63 rightly unmapped), the Thrace and Macedonia pins against the texts on
file, Epanomi's community against GISCO, the parser over all 292 area
texts, the search-box change under node, the Spanish fetch code with
synthetic province-05 and manifest cases. Corrections applied: EL515
"Θάσος, Καβάλα" straddles two regions by the same article (Thasos is an
Aegean island), so it is unmapped and its three PGIs curated — Θάσος →
Νησιά Αιγαίου, Καβάλα and Παγγαίο → Μακεδονία; the umbrella Μακεδονία PGI
is curated too. The prose word "όρια" had cost ΠΓΕ Αγορά its community
Αγοράς ("στα διοικητικά όρια των οικισμών Αγοράς …"): the limits phrase
is now a list separator when a list noun follows. "Βλαχάτων" (Ρομπόλα) is
aliased to GISCO's "Βλαχάτων Εικοσιμίας". Units that straddle only by an
island (the Sporades in EL613, Samothrace in EL511, Skyros in EL642) stay
mapped to their mainland region, and the rule is written next to the
table. Two verifier notes left as they are: picking a spirit from the
search box fires "Kind Toggled spirits" even when the toggle was already
on (pre-existing), and a non-zip body served for the Galician parish zip
now stops ES stage 00 instead of being cached (arguably right).

**Bulgaria (gr-bg-hu-region-7).** Оряховица's facet still read Дунавска
равнина because stage 04 prefers the stored stage-02 region; BG stage 02 re-run,
now Тракийска низина. The re-extraction moved one grape: «Гергана» had
fuzzy-bound to glera and then vitovska-grganja; it is its own Bulgarian white
(VIVC #23144, verified live), now in the lexicon and pinned in
`raw/vivc/slug_overrides.json` (the Cyrillic query misses).

Open, with the evidence:

- ✅ **Μακεδονία PGI** (`PGI-GR-A1616`) was drawn from EL51 + EL52 + EL53,
  and EL51 carries Evros, Xanthi and Rodopi. The first write-up said no
  spec was on file; wrong — its EU single document (OJ C/2026/2625, the
  Reg. 2024/1143 template) is cached, and section 9 lists thirteen
  regional units, all Macedonian (Γρεβενών, Δράμας, Θεσσαλονίκης, Ημαθίας,
  Καβάλας, Φλώρινας, Καστοριάς, Κοζάνης, Πέλλας, Σερρών, Πιερίας,
  Χαλκιδικής, Κιλκίς in part). The GR parser had dropped that section: its
  title is genitive ("Συνοπτικός καθορισμός της οριοθετημένης γεωγραφικής
  περιοχής") and no keyword matched it, while section 3 "Χώρα στην οποία
  ανήκει η οριοθετημένη γεωγραφική περιοχή" (body: "Ελλάδα") matched the
  nominative one and became the record's area — the Greek twin of the RO
  "Țara căreia îi aparține" decoy. Fixed 2026-09-24 in
  `scripts/_lib/gr/eniaio_engrafo.py` (genitive keywords added, the decoy
  blocklisted; the eight older GR documents parse unchanged), and the pin
  is now EL514 + EL515 + EL52 + EL53 (EL515 also carries Thasos; the
  document's per-unit altitude bands are not drawn). Re-extract GR and
  rebuild to land it.
- ❌ **Sithonia PGI** is drawn as all of Χαλκιδική (EL527) although its spec
  delimits "την χερσόνησο της Σιθωνίας"; the overlap with Άγιο Όρος is no
  longer whitelisted. Community precision needs the peninsula's community
  list (δήμος Σιθωνίας), which the spec does not enumerate.
- ✅ **Outlier audit (resolved 2026-09-25: 57 unreviewed → 0).** Every
  detached part was reviewed against its source and whitelisted with the
  citation in `scripts/_lib/geometry_outlier_overrides.json` (54 new
  entries; see CLAUDE.md "Geometry-outlier overrides" for the rule per
  provenance), except four that were defects and were fixed upstream:
  Calvados Domfrontais bound to the whole Calvados aire (SIQO's
  "Domfontais" + the aires-CSV substring fallback → near-exact step in
  `_lib/aires.py`), Ribera del Gállego-Cinco Villas' "Los Corrales" bound
  to Sevilla (ES resolver re-read), Valle Belice drawn as two provinces (IT
  parser), and — not a defect after all — Πλαγιές Αίνου's "mainland" parts,
  which are the Echinades islets that GISCO carries under Δ.Κ. Αγίας
  Ευφημίας (Δήμος Πυλαρέων, Kefalonia). Bükk's part 92 km east is Barabás,
  a Bükk település per the HU termékleírás; Znojmo's is Kojetice, in the
  Znojemská list of Vyhláška 254/2010. The original 2026-09-24 finding:
  41 findings are new after the detector rewrite, 15 are
  gone (69 → 95 unreviewed on the same build; geometry unchanged). The
  body is now the largest 25 km-cluster and a smaller detached cluster is
  reported whole, so every genuine second lobe under 20 % of the area
  now shows: the Yonne lobe of the six Bourgogne regionals, the northern
  Rhône, Wissembourg for Alsace and Crémant d'Alsace, Corsica for
  Méditerranée (its cahier names Corse-du-Sud and Haute-Corse), Skyros for
  the eight Euboea PGIs, the Balearic islands, Brandenburger Landwein's
  scattered Gemeinden, the Czech Bohemian lobes, Savoie, Moselle, Sable de
  Camargue, Loire, Provence, Calvados / Pommeau / Île-de-France commune
  unions — about 40 records to whitelist with their source. One new finding
  is real: **Los Palacios** (ES) draws Villafranca in Navarra, 636 km away,
  a homonym leak of "Los Palacios y Villafranca". The 15 that vanished
  chain to the body island by island (Champagne's Montgueux, the Aeolian,
  Sporades and Dalmatian islands, the Breton coast); Salina's whole-Messina
  province polygon is among them and stays wrong (recorded under IT). The
  welsh-wine / welsh-regional-wine whitelist entries are unused now (The
  Skerries chain to Anglesey) and may be dropped.
- ❌ **Two Romanian county lists joined by a connective** ("Localităţi din
  judeţul Galaţi şi din judeţul Vaslui: …", "Judeţul Galaţi, respectiv
  judeţul Vaslui: …") open two sections, the first empty, so every name is
  scoped to the second county and the first county's communes drop as
  outside. Not in the corpus today; the old code scoped them to the first
  county only, also wrong. Fix: merge a header's counties into the next
  header when no name sits between them.
- ❌ **National-spec area texts are not parsed for communes.** Avdira names
  "τις κοινότητες Αβδήρων, Μάνδρας, Μυροδάτου και Μαγγάνων … του Ν. Ξάνθης";
  Ismaros names its δημοτικά διαμερίσματα. Both draw a whole NUTS-3 unit
  today. Parsing the national-spec geo area in GR 02f would give community
  precision to these, now that the parser handles the national-spec idioms.

### Build of 2026-09-24 19:55 — what changed, what the verifiers found (5 Explore agents)

Re-extracted RO (EU documents + ONVPV caiete) and GR, rebuilt, re-audited.
Against the previous build 108 records changed: 104 GR (102 regions, the
Epanomi / Μακεδονία / Θράκη geometries), 2 ES subzonas (Pallars drops
Palau d'Anglesola and Sant Martí de Riucorb; Quiroga-Bibei binds A Pobra
do Brollón), 2 BG (Оряховица's facet, Гергана). Romania: county scoping on
five records, no geometry change, 42 județ masks loaded. Audits on the new
build: outliers 11 confirmed / 0 stale / 18 accepted / 93 unreviewed;
overlaps 488 suspicious / 2 accepted (the Sithonia pair is suspicious by
design); empty-grapes strict passes; GI terms strict passes; the
vineyard-envelope strict audit fails on the pre-existing containment /
bridging residues. Every expectation held except the items below, all
pre-existing and now visible because the Greek facet and the detector are
no longer hiding them:

- ❌ **GR: PGIs drawn as whole NUTS units far beyond their text.** Sixteen
  Attica PGIs (Ίλιον, Ανάβυσσος, Γεράνεια, Μαρκόπουλο, Παλλήνη, Σπάτα,
  Πλαγιές Πεντελικού, the retsinas …) draw all of EL30 including Kythira,
  3,826 km²; the text of Ίλιον is one toponym, that of Πλαγιές Πάρνηθας
  three Boeotian communities plus Αφιδνών. Seven Euboea PGIs draw all of
  EL642 including Skyros; Πλαγιές Κιθαιρώνα draws all of Στερεά Ελλάδα
  (15,574 km²) for two communities. Kos = all Dodecanese, Kissamos = all
  Chania, Lesvos includes Lemnos, Zakynthos includes the Strofades, Kriti
  includes Gavdos. Fix upstream: parse the national-spec area text for
  communities (the parser now handles its idioms) and fall through to NUTS
  only when nothing resolves; the NUTS pins in `scripts/_lib/gr/nuts.py`
  then become last resorts.
- ❌ **GR Αιγαίο Πέλαγος draws only the South Aegean.** Its spec cites "GR42
  Νότιο Αιγαίο, GR41 Βόρειο Αιγαίο"; the name resolver keeps one. Pin
  `aegeo-pelagos` to `["EL41", "EL42"]` (source: its own spec on file).
- ❌ **GR Σιθωνία** is all of Chalkidiki (EL527) for a text that says "την
  χερσόνησο της Σιθωνίας"; needs the peninsula's community list.
- ❌ **GR Patras PDOs carry Bétard homonym parts**: Μοσχάτος Ρίου Πάτρας has
  Πλάτανος of Aigialeia instead of Πλατάνι of Rio; Μοσχάτο Πατρών has Άγιος
  Νικόλαος of Kalavryta; Μαυροδάφνη Πατρών both. Clip-override candidates
  (`scripts/_lib/geometry_outlier_overrides.json`, verify against the gpkg).
- ❌ **GR Θράκη** is flagged for Samothrace (EL511 carries the island); the
  spec delimits "όλες τις περιοχές της Θράκης" by regional unit. Whitelist
  with that citation, or subtract the island — a curator call.
- ❌ **GR Μακεδονία's panel summary reads "«Μακεδονία» Ελλάδα"**: the summary
  builder joins sections 1 and 3, and in the 2024/1143 template section 3
  is the country. Not rendered today (the record has 11 facts); fix the
  builder to skip the country section for that template.
- ❌ **ES Ribeira Sacra Quiroga-Bibei is still missing Pobra de Trives**: the
  pliego writes "a Pobra de Trives" with a lower-case Galician article and
  the subzona tokenizer rejects a token starting lower-case. Six of seven
  municipios bound. Fix in `scripts/_lib/es/subzona.py` `_is_commune_token`.
- ❌ **ES Costers del Segre Pallars: 10 of 21 names unmatched** — historical
  municipios merged into Tremp, Isona i Conca Dellà, Gavet de la Conca …;
  needs a merged-municipio alias table with the merger decree as source.
- ❌ **ES Los Palacios** draws Villafranca (Navarra): "Los Palacios y
  Villafranca" is split on " y ". Keep a compound name whole when the
  joined form is itself a GISCO key.
- ❌ **IT Rubicone** is drawn from its ten Bologna comuni only: the geo-area
  also says "l'intero territorio amministrativo delle province di
  Forlì-Cesena, Ravenna e Rimini", and `parse_geo_area` drops the province
  list whenever a comune list is present. Pre-existing; union both.
- ❌ **Blauer Wildbacher has no VIVC link**: the 02g query "Wildbacher"
  missed its only candidate, BLAUER WILDBACHER #13234 (in the cached
  search). Pin in `raw/vivc/slug_overrides.json` after a live passport
  check. **Гергана** has a VIVC link but no Wikipedia card yet
  (`02b_fetch_grape_lexicon.py --only gergana`).
- ✅ The `welsh-wine` / `welsh-regional-wine` outlier whitelist entries no
  longer match anything (The Skerries chain to Anglesey); dropped — the
  file carries no such keys on 2026-09-25.

### Stage-03 markdown pages stale since May (found 2026-09-24) — ❌ open, pre-existing

`wiki/<slug>.md` + `wiki/_index.json` are older than their stage-02 records
in 14 countries (ES 185/185, GR 147/147, DE 46/46, RO 46/46, CH 75/75, …;
e.g. `wiki/mosel.md` 2026-05-24, `_index.json` 2026-09-20). Nothing
deployed or rendered reads them (deploy skips `_index.json`; the map reads
raw/ + wiki/data/), so the site is unaffected, but a fresh 00→04 run would
regenerate them and the "reproducible" rule says it should. Fix: run every
`scripts/<cc>/03_generate_wiki.py` after FR `03_generate_wiki.py` (check
first that FR's run does not rewrite `_index.json` without the other
countries' entries).

### Region facet — the terroir-narrative scan, corpus-wide (2026-09-24) — ✅ closed

The Athos facet defect (a passing "…η Αττική" in the lien) was one instance of
a pattern: **10** stage-02 scripts (be / bg / cy / cz / de / hr / hu / ro / si /
sk) and **9** stage-04 region fills passed `link_to_terroir` into the region
scan. Measured before removing it: across all 267 records of those countries
the facet is identical with and without the narrative — every one is covered
by its curated `_REGION_BY_FILE_NUMBER` — so the scan was dead weight, but the
same latent class. All 19 call sites now read geo-area + name only (the IT
`derive_regione` rule); `tests/test_region_scan_wiring.py` fails if any
country passes the narrative back in.

### ES stage 02 `--only` rewrites `_index.json` from the selection alone — ❌ open

Found 2026-09-24 while re-extracting for the commune fixes: `raw/es/pliegos-
extracted/_index.json` held a single key (`getariako-txakolina`) left by an
earlier `--only` run, and the full run restored all 149. The FR stage 02 had
the same footgun (fixed 2026-09-11 by merging the selected entries into the
existing index); ES's `--only` still writes the index wholesale. Until it is
fixed, re-extract ES only with a full run, and check the index key count
afterwards.

### Geometry-overlap audit — 493 unreviewed slivers, whitelist was empty — ✅ reviewed 2026-09-25

**Verified on the rebuilt map (2026-09-25, after the parser / resolver /
radius fixes):** `audit_geometry_outliers.py --strict` → 23 confirmed
clips, 0 stale, 75 accepted, **0 unreviewed**; `audit_geometry_overlaps.py
--strict` → 77 border, 224 tier, 106 generalisation, 86 source-drawn, 28
accepted, **0 suspicious** (two pairs joined the whitelist after the
rebuild: Terre del Volturno, now drawn from its 78 comuni, against the
whole-province Pompeiano and Epomeo IGTs); `audit_empty_grapes.py
--strict` and `audit_gi_terms.py --strict` unchanged and green.

**Resolution (2026-09-25).** On the 2026-09-25 07:20 build the audit listed
520 slivers. Classified (the audit now does this itself, every class listed
in full — see CLAUDE.md "Geometry-overlap audit"): 77 BORDER (two national
layers along a state border, all ≤ 0.24 km wide), 226 TIER (a PGI / IGP or
a spirit-drink GI over a PDO / AOC), 107 GENERALISATION (same tier, thin,
two geometry sources), 86 SOURCE-DRAWN (both polygons from a geoportal /
MAPA / parcellaire / Bétard layer — Tuscany's and Veneto's DOCs, Bétard's
padded municipalities), 24 SUSPICIOUS. The 24 were checked commune by
commune against the INAO aires-communes CSV: in every French pair the
shared communes are listed in BOTH appellations' rows (Beaujolais and the
Bourgogne regionals share the eight Mâconnais–Beaujolais communes; Cheverny
/ Touraine share Monthou-sur-Bièvre; Béarn / Floc de Gascogne share Viella
and Maumusson-Laguian; Agenais / Côtes du Lot both list Fumel; the Aude and
Hérault DGC pairs share one commune each), the Blaye / Bourg band is INAO
parcels against an INAO commune list, and the three Greek pairs are LAU
1:1M vs NUTS 1:3M bands. All 24 whitelisted with that evidence
(`scripts/_lib/geometry_overlap_overrides.json`); `--strict` passes. The
original entry:

First strict run of `audit_geometry_overlaps.py` on record (2026-09-24, after
the outlier work): **493 suspicious slivers (87 cross-country, 406
same-country), 0 accepted** — the whitelist had never been populated, so
`--strict` has always failed. The visible cross-country ones are 1 km²,
0.0 km-wide border slivers between differently-generalised national layers
(CH/IT, SK/AT, AT/SI, FR/IT); a review pass is needed before `--strict` means
anything. Of the records changed this session only four appear: Άγιο Όρος ×3
(Ouranoupoli inside the Χαλκιδική / Σιθωνία / Μακεδονία NUTS PGIs — genuine
nesting per its own text, whitelisted with the OJ citation, the first entries
in that file), Duriense ↔ Castilla y León / Arribes (3 km² Douro-border
slivers, CAOP vs GISCO), Norte de Almería ↔ Bullas (1.9 km²), Bianco del
Sillaro ↔ Colli Bolognesi (1.6 km², GISCO comune vs geoportal zone) — all
generalisation-class, left with the backlog. After the Galician parroquia
layer (later the same day): **491**, with two new same-country pairs that
read as genuine shared ground, not artefacts — Valle del Miño-Ourense ↔
Ribeira Sacra (30.5 km², 8 % of Valle del Miño: its named parishes of
Nogueira de Ramuín sit inside Ribeira Sacra's MAPA zone) and Barbanza e Iria
↔ Rías Baixas (13.2 km²: the two Padrón parishes Barbanza now draws lie in
Rías Baixas' Ribeira do Ulla subzona, whose pliego also names Padrón).
Whitelist candidates once a curator confirms both pliegos.

### Vineyard-envelope audit `--strict` fails on the feat/zoom-lod footprints — 🟡 radius fixed 2026-09-25, containment residues open

**Resolution (2026-09-25).** The 78 bridging records are the small ones:
790 of the 1,259 footprint records are under 1 km² (442 under 0.05 km²),
and a 250 m closing of a climat that size laps onto the neighbouring
climat by construction. The radius now scales with the record —
`r = clamp(0.25·√area, 30 m, 250 m)` (`vineyard_envelope.adaptive_radius`;
0.05 km² → 56 m, 0.25 km² → 125 m, ≥ 1 km² → 250 m) — the record carries
`geom_lod_radius_m` and the card prints it; the 250 m cache entries stay
valid (454 records keep 250 m, 805 get 30–249 m). **After the rebuild
(audit of 2026-09-25):** inflation median 1.08× / p90 1.46× / max 2.43×
(was 1.07 / 1.48 / 3+); bridging > 5 % fell from 78 to 31 and the worst
from 65 % (Les Gaudichots) to 20 % (Pouilly-Fuissé premier cru, 60 climats
interleaved with the Mâcon village parcels). Of the 31, twenty are
micro-climats bridging under 5 ha — the closing of a concave polygon fills
a corner of the next climat, under four pixels at the last footprint zoom
— and the audit now ignores a bridge under `--bridge-min-km2` (0.05 km²)
and treats sibling DGCs like parent / children (Grés de Montpellier over
the other Languedoc DGCs is the parent's ground). What is left — **11 records
on the final run** (`--strict`: 0 missing, 0 orphan, 0 bbox, 8 containment,
11 bridge; JSON at /tmp/owm-envelopes-final.json when written) — is a
short list of records whose "neighbour" legitimately shares their communes —
Pouilly-Fuissé (and its premier cru / climat records) over the Mâcon
village AOCs of the same communes, Saint-Véran over Mâcon-Prissé,
Saint-Bris over Bourgogne Côtes d'Auxerre, La Clape over Corbières,
Ladoix / Corton-Charlemagne over Aloxe-Corton, Grés de Montpellier over
the Languedoc DGCs (not siblings in SIQO: Grés de Montpellier carries its
own id_appellation, so the sibling rule cannot see them) — an overlap the
50 % umbrella rule does not see because the neighbour covers only part of
the record; an accepted-bridges table with sources would close it, or a
"covers ≥ 25 % of the record" umbrella rule. **The 8 containment residues
are diagnosed, not fixed:** anjou, cabernet-d-anjou, rose-d-anjou,
rose-de-loire, muscadet, languedoc, cotes-du-rhone, cotes-de-provence —
each 0.0011–0.0017 km² in 11–69 slivers of 33–923 m², every one just past
the 39 m tolerance at a single vertex (`scratchpad` diagnosis, 2026-09-25):
the topology-preserving 30 m simplify plus the 8.5 m erosion sagitta
overshoot by a few metres where the closing's boundary turns sharply. Sub-
50 m on eight regional unions of 100–2,000 km²; grow the tolerance by a
documented 10 m or accept the check as informative — not a geometry
defect a reader could see. The original entry:

First strict run on record (2026-09-24, 55 min): parity 0/0, bbox 0, but
**8 containment residues** — parcels outside the footprint by ~0.001 km²
against the 39 m tolerance, all on the large regional AOCs (Anjou, Cabernet
d'Anjou, Côtes de Provence, Côtes du Rhône, Languedoc, Muscadet, …) — and
**78 records bridging > 5 %** of their footprint onto a neighbour's parcels,
almost all Burgundy premier-cru climats of 0.01–0.1 km² where a 250 m closing
inevitably laps onto the adjoining climat (Les Gaudichots 65 % onto La Tâche,
Hautes Mourottes 47 %, Pouilly-Fuissé 1er cru 20 % onto the Mâcon villages).
Inflation: median 1.07×, p90 1.48×, 3 above 3× (Volnay Le Village, Chassagne
1er cru, one more). Every build of 2026-09-24 served all 1,259 footprints from
the cache (computed = 0), so this is the state the branch shipped with on
2026-09-23, untouched by the geometry work of these two days. Decide whether
the residues are a tolerance question (bump the 39 m for the regional unions)
and whether micro-climat bridging needs a smaller radius or an accepted list;
`--bridge-max` is the knob.

### Sierra Sur de Jaén — SIGPAC parcels wired; polígono footprints — ✅ decided 2026-09-24

The pliego includes "las zonas de sierra" of Alcaudete (polígonos catastrales
1–12, 18–29) and Martos (33–42) beside six whole municipios. The parcel
mechanism now covers it: FEGA's national SIGPAC download
(sigpac-hubcloud.es, CC BY 4.0, quoted in `scripts/_lib/es/sigpac_fega_urls.json`
and `raw/es/sigpac/manifest-fega-23.json`; the 456 MB Jaén zip is sha-pinned,
a 51 MB two-municipio extract is what the loader reads), the inclusion
parser accepts "polígonos catastrales actuales del N al N", and the loader
maps the FEGA schema onto the Catalan one (Priorat + Montsant byte-identical).
The parser finds all 24 + 10 polígonos. **But SIGPAC 2026 records no `VI`
recinto in any listed polígono of Alcaudete (9,863 ha, olive groves and
pasture) and 0.14 ha in Martos (polígonos 36, 40, 41).** With Priorat's
vineyard-only semantics the map therefore draws four tiny plots for Martos
and nothing for Alcaudete. The alternative is the listed polígonos' full
footprints (≈ 98.6 km² + 33.1 km²), which is what the pliego delimits and
how every whole municipio on the ES map is drawn (administrative area, not
vineyard); it needs a loader-level polígono footprint (union of every recinto
of the polígono, any use — the extract already keeps every use) and a
per-record switch so Priorat / Montsant keep their parcel semantics.
**Decided (Boris): footprint** — the polígono is the delimited area, a plot
planted inside it qualifies. Implemented as `SIGPAC_INCLUSION_SEMANTICS`
(default `footprint`; Priorat + Montsant pinned `vineyard`, byte-identical):
Sierra Sur 730.9 → **861.8 km², one polygon** (Alcaudete 24/24 polígonos
98.7 km², Martos 10/10 33.2 km²), disclosed in the panel. **Decided the same
day: the same reading for the two anchors** — Priorat 150.9 → 167.1 km²
(354 parts → 1; Falset 13.4 km² of polígonos vs 1.5 of vines) and Montsant
297.8 → 317.8 km² (373 → 1; Falset 18/18). No record is pinned to the
vineyard reading any more. Also newly visible in Montsant's
panel line: Garcia (0/5) and Tivissa (0/9) — their polígonos are in the
Ribera d'Ebre comarca, which stage 00 does not fetch (`SIGPAC_COMARCA_CODIS`
= Priorat only); a one-line catalogue addition. And the Catalan SIGPAC
manifest records only "© Generalitat de Catalunya / DARP, SIGPAC. Free reuse
with attribution" — no licence name or URL, so the panel links the portal
without a licence label; pin the licence when a curator confirms it.

Side effects of the same change, both improvements: `_resolve_es_sigpac`
now requires at least one SIGPAC hit before labelling a result parcel-precise,
which moved **Arribes** (48-commune union, Almaraz de Duero's polígonos never
resolved — Zamora not fetched) and **Tarragona** (81-commune union, a junk
"Los municipios de" anchor) from a mislabelled `sigpac-hybrid-pliego` onto
their official MAPA zone. Campo de Borja (Mallén, Fréscano) and Rueda
(Órbita, Palacios de Goda) now parse their polígono inclusions and would
resolve at parcel precision once Zaragoza / Ávila are fetched — same
one-line addition to the FEGA catalogue. A fresh checkout's stage 00 now
downloads 456 MB for Jaén; the per-municipio extract is what ships.

### Galician parroquias — layer added 2026-09-24; residue

The IET Mapa de Parroquias de Galicia now refines the six Galician
parish-delimited records (see CLAUDE.md, ES chain). Left open: **Ourense
city** — the pliego of Valle del Miño-Ourense names Cabeza de Vaca, Santiago
das Caldas and Tras do Hospital, which the IET layer does not carry (folded
into the city parish "Ourense"); confirm with the IET before pinning. The
seven spelling pins in `scripts/_lib/es/parroquia_overrides.json`
(Sarandóns/Sarandós, Vilacoba/Vilacova, San Martiño/San Martín de Suarna, A
Pobra/A Proba de Navia, Castrelo/Castrelos de Abaixo and de Cima, San Tomé →
San Tomé das Olas, Oza dos Ríos → Oza-Cesuras) rest on name equivalence
recorded in each `_note`. The two Monterrei subzonas read their parish
block out of the parent section text the sub-record still carries; a
stage-02 change that dropped it would silently return them to the
comma-split union (the stage-04 log line would show it). Licence: the
publisher's aviso legal (Decreto 14/2017, "compatible con CC-BY 4.0 INT")
is cited as governing over the 2015 non-commercial PDF bundled in the zip
and the abertos CC BY-SA listing — a curator may want to confirm with the
IET.

Added 2026-09-27 (Monterrei boundary flag, see the visitor-feedback triage
section): a MAPA zone drawn at whole-municipio resolution whose pliego names
parishes is now redrawn from the IET parishes (Monterrei, 674 → 640 km²).
Two Galician DOs stay on their whole-municipio MAPA zone, each for a reason
the redraw cannot fix by itself:

- **Ribeiro** (564 km², 14 whole municipios) — the pliego names parishes of
  O Carballiño (3) and Boborás (5) and the parish of Alongos, but also
  *lugares* below the parish tier: Santa Cruz de Arrabaldo and Untes
  (Ourense), Puga, A Eirexa de Puga, O Olivar, Feá and Celeirón (Toén), A
  Touza (San Amaro). Drawing the parishes alone would keep Ourense and San
  Amaro whole and shrink Toén to Alongos, dropping the parishes of Puga and
  Feá. Needs a locality → parish gazetteer (the Xunta's *Nomenclátor de
  Galicia* lists lugar → parroquia → concello) so a lugar is drawn as its
  parish and reported as a proxy, the way the Greek resolver draws a
  τοπωνύμιο as its community (`geom_units_proxied`). Until then the card
  says "official MAPA zone" for five municipios drawn whole.
- **Ribeira Sacra** (2,524 km², 45 whole municipios) — the pliego says the
  five subzonas comprise "parte de los términos municipales" and names no
  part; the real zone is the valley slopes. Nothing in the public text can
  narrow it; a Xunta / consejo regulador delimitation layer would.

The MAPA layer (`raw/es/mapa-zonas/`, fetched 2026-05-22) predates the
2025 Monterrei amendment; where it is whole-municipio, a re-fetch would not
help — the pliego, not the layer, carries the parishes.
