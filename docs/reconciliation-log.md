# Reconciliation log

Dated history of corpus-reconciliation passes — what landed, what was verified,
what regressed. Split out of `CURATOR_TODO.md` (which now keeps only the
`Last reconciled:` pointer + open items) so the actionable queue stays readable.

Newest first.

---

## 2026-08-26 — /research-gaps vivc-ambiguous: 42-slug pin pass

The queue surfaced by the corpus-walk widening (same-day action pass below),
researched by 5 parallel agents against live VIVC passports + national
registers (HR NN 25/2020 + NN 81/2022, HU NFJ 2024, Genes 2020 DNA anchors,
wein.plus, Wine-Grapes-adjacent literature). User-confirmed and applied:

- **40 PINNED** into `raw/vivc/slug_overrides.json` (now 499 entries) —
  full per-slug evidence in `tmp/vivc-ambiguous-research-results.md` and
  the pin table in CURATOR_TODO's restore-note block. Highlights:
  harslevelu→5314, zierfandler→13443 (Spätrot), tribidrag→9703 (joins the
  primitivo+zinfandel same-id group), negroamaro→8456, zametovka→6047
  (Kavčina črna / Stara trta), grk→5066, debit→10423 (RUZEVINA),
  trbljan→8075 (MOSTOSA, with a caveat on VIVC's new 0-holding #27344),
  andre→456 (the Czech crossing), goher→767 (white conculta member),
  busuioaca-de-bohotin→8248 (Muscat rouge à petits grains).
- **`cristina` (RO) brand suspicion REFUTED** — VIVC #21045, a real SCDVV
  Murfatlar crossing (Chardonnay × Băbească Neagră); closes the
  2026-05-23 Colinele-Dobrogei 🟡.
- **2 × `vivc_id: false`**: `korithi` (two distinct varieties — B=#6414 /
  N=#6415; queued next to bare-piquepoul for colour-aware alias support)
  and `schiava` (standing bare-family-name ruling).
- Three new legitimate same-id groups, auto-unified by the facet tier:
  tribidrag/primitivo/zinfandel #9703, muskat-zuti/moscato-giallo #8056,
  bratkovina/maresco #1660.
- Applied via `02g --refresh --only <40 slugs>` (all resolve `override`);
  a scoped 02b sweep over the 33 card-less pins recovered **12 en
  Wikipedia cards** via the VIVC-synonym chain (Grk, Kotsifali, Debit,
  Vugava, Žlahtina, Mavrotragano, Thrapsathiri, Trbljan, Muškat žuti,
  Vitovska, Busuioacă de Bohotin, Tauberschwarz) + 29 fr/es/nl
  translations; the other 21 are genuinely article-less natives.
- Provenance: `tmp/vivc-ambiguous-research-prompt.md` +
  `tmp/vivc-ambiguous-research-results.md`.

---

## 2026-08-26 — open-todo action pass (post-reconciliation)

Worked the reconciled queue top-down; full pipeline runs, every result
verified in the rebuilt `wiki/` (stage 04 clean, 2,908 records, 0 stale
overrides). Landed:

- **FR `cote-vermeille` terroir gap closed (8/8 zero-bullet parents done).**
  Root cause was a stage-02 slicing miss, not 02d: the cahier's heading
  `10- lien avec la zone géographique` starts lowercase, which
  `IGP_SECTION_HDR_RE`'s uppercase-title requirement rejected. Added a
  `lien\b` lowercase carve-out; full FR re-extraction (466 + 1,074 DGCs, 0
  errors) verified byte-identical lien lengths corpus-wide (agenais 9190 /
  maures 8523 / pays-d-oc 11546); cote-vermeille 0 → 7,110 chars → 5 facts
  (02d anthropic) → en/es/nl (02e; exactly 3 jobs = proof nothing else
  drifted).
- **SI: belokranjec + metliska-crnina promoted to full EU-OJ extractions.**
  The due OJ-C re-check found both: C/2026/3572 (6.7.2026) + C/2026/3598
  (13.7.2026), consolidated ENOTNI DOKUMENT each (WAF-free mirror: Cellar
  XHTML). Pinned in the SI overrides (old spec URL kept as
  `specifikacija_url`; si/01c --refresh for these slugs is now forbidden),
  fetched via si/01 + 01b Chromium, extracted (18 + 10 grapes, 2.7/2.4 KB
  lien), terroir re-grounded on the EU-OJ text (10 + 8 facts, 02e ×4
  locales). SI = 3 EU-OJ + 14 national-spec.
- **FR SIQO 2 missing wines: both RETIRED (research-verified).** Cabernet
  de Saumur folded into AOC Saumur rosé (Arrêté 19.7.2016 art. 2 abrogates
  Décret 2011-1360); Côtes de Blaye unclaimed since 2015 + EU cancellation
  PDO-FR-A0271-CANCEL filed 13.1.2026. Recorded in VERIFICATION.md; no
  pinning — eAmbrosia rows are stale-register artifacts.
- **`is_wine` mis-flag fixed** for Côte roannaise + Muscat du Cap Corse:
  stage 04 now falls back to the SIQO `categories` list when the manifest
  `categorie` is empty (both records came via the mirror/override path).
  Verified True in the rebuilt blob.
- **CZ `Ryzlink buketový` resolved**: absent from Vyhláška 88/2017 Příloha
  2 (local check) AND the ÚKZÚZ Státní odrůdová kniha (web research); a
  real legacy variety from the repealed 323/2004 list with contested
  identity (Goldriesling #4884 vs Bukettraube #1611, neither VIVC-grounded)
  → own slug `ryzlink-buketovy` (blanc), `vivc_id: false` pin, CZ fiche
  re-extraction cleared the unknowns queue.
- **MT grape enrichment complete**: Ġellewża VIVC #14174 + Girgentina
  #17787 (exact-cultivar), en.wikipedia cards fetched, fr/es/nl translated
  (a 19-job corpus-wide 02b-translate pass also drained the HU/ES tail).
- **Corpus-walk gap closed (OQ3 loose end)**: 02g +
  `grape_corpus._SOURCES` now walk mt/cy/nl/be/lu/ch/hu + the BG/GR/SK/RO
  national-specs-extracted sidecars (register-fiche dirs deliberately
  excluded — terroir-only). Full incremental 02g sweep over the 141
  newly-visible slugs: 852 exact + 5 prime + 387 override / 120 miss / 42
  ambiguous → queued in `slug_overrides.example.json` for a
  `/research-gaps` pin pass (search caches already on disk).
  `audit_ambiguous_synonyms`: 36 → 38 RISKY (+2, none known-wrong).
- **ortrugo-dei-colli-piacentini investigated**: pre-2016 table-based OJ
  template (a different parser family, not an anchor tweak); wine is
  content-complete via MASAF — downgraded to low-priority with two Phase-2
  options.
- Wiki regenerated (1,540 FR + 17 SI pages); stage-04 rebuild + facet
  canonical roll-ups verified intact (malbec→cot, araignan→picardan,
  s-saul→cinsault).

---

## 2026-08-26 — interprofession / organisation URL sweep

The parallel curation the stale-audit entry below defers to. Scope: the
`appellation_urls.json` "Site officiel de l'interprofession" row across every
country. Coverage went **2 468 / 2 908 → 2 783 / 2 908** records (gap 440 →
125, of which 27 are now *decided* NONE rather than unchecked).

Per-country: **GR 129→147**, **SI 14→17**, **SK 9→10**, **FR 1 244→1 537**,
BG 54/54 kept but re-sourced (below). AT / BE / CZ / CH / DE / HR / HU / LU /
MT / NL / PT / RO were already complete — the CURATOR_TODO sections claiming
`❌ 0/147` (GR), `❌ 0/75` (CH), `❌ 0/13` (CZ), `❌ 0/10` (SK) were **stale by
one sweep**, not open work; they are now rewritten to the shipped state.

Landed:

- **FR +293** — 5 missing `by_bassin` keys (Beaujolais / Savoie / Jura / Bugey
  / eaux-de-vie de cidre) covering 96 AOC records; the 13 `VIN DOUX NATURELS`
  AOCs split per-slug across CIVR / CIVL / Inter Rhône rather than given one
  wrong regional fallback; 79 IGP entries. The 186 FR IGP records collapse to
  81 parent roots (children inherit via `parent_slug`), 73 of which bind to
  their own page on the Confédération des Vins IGP de France (`vinigp.fr`) —
  all 73 URLs probed 200, no redirects — and 8 to a more specific body
  (Inter Oc, Syndicat des Vins IGP Val de Loire, CIV Corse, CIVA, UNICID).
  Confirmed *not* a bug: FR IGPs have an empty `region` because INAO's SIQO
  referentiel carries `comite_regional` for AOCs only (IGPs sit under the
  national committee CNIGPVC).
- **GR +18** — `by_bassin` for all 10 αμπελουργικές ζώνες → ΕΔΟΑΟ
  (`winesofgreece.org`, operator confirmed), matching the 114 per-slug entries
  already pointing there.
- **SI +3 / SK +1** — `by_bassin` for the 3 vinorodne dežele; Bela krajina PTP
  pair → Društvo vinogradnikov Metlika; the second Tokaj PDO → the same Tokaj
  Wine Road Association as the first.

Corrected (not a coverage change — a correctness one):

- **BG** — 31 `by_slug` entries pointed at **bg.wikipedia articles about the
  town** the PDO is named after (Асеновград, Видин, Плевен, Ямбол …) under a
  row labelled "Site officiel de l'interprofession". Removed, together with 4
  pointing at the state regulator ИАЛВ (already surfaced as the national-spec
  source) and 2 at `rlvk-burgas.com`, whose domain no longer resolves. The 5
  `by_bassin` region entries now point at **НЛВК** (`bulgarianwines.org`),
  Bulgaria's actual interprofession. Coverage stays 54/54.

Recorded as decided-NONE (explicit `null`, the ES `murcia` precedent):

- **CY ×11** — Cyprus abolished the Vine Products Council; no interprofession
  exists, and the competent Department of Agriculture branch is already the
  national-spec source.
- **IT ×5** (Biferno, Molise, Pentro di Isernia, Osco, Rotae) — the Molise
  consorzio's recognition was revoked, GURI n. 93 / Apr 2022.

Verification: every new or changed URL was probed — **89 / 90 return 200**.
The one exception, `idac-aoc.fr`, 403s to all non-browser clients while being
live and indexed (WAF), and is flagged for a browser confirm.

Not landed, with evidence:

- **IT 109 gaps** stand. Federdoc's consorzi directory was evaluated as a bulk
  source and rejected (≈90 members, all already-covered flagships, no websites
  published). Spot re-checks: `montecarlo` resolved as *do-not-add* (the 403
  cleared but `promontecarlo.it` is now a repurposed wine blog); the Umbria
  cluster confirmed consorzio-less; `barbera-del-monferrato` / `calosso` /
  `cisterna-d-asti` confirmed **not** covered by the Asti-Monferrato consorzio
  despite search snippets saying so; Penisola Sorrentina's consorzio exists
  (founded 2023) but publishes no site.
- **FR ×3** — `correze` (+ its DGC) and `cote-roannaise` have no confirmable
  ODG site.

Side-findings logged in CURATOR_TODO, not acted on: `cote-roannaise` and
`muscat-du-cap-corse` land as `is_wine=false` (empty `categorie` in the cahier
extract) despite being wine AOCs; `moa.gov.cy` now 301s to `gov.cy/moa/`, so
8 CY national-spec source URLs would fail a `--refresh` (cached PDFs fine).
A whole-file link-rot probe (514 URLs) was inconclusive in this environment —
whole hosts (`onvpv.ro` ×32, `kormany.hu`, `juntadeandalucia.es`) reset the
connection, consistent with the known VPN/WAF behaviour — so nothing was
removed on its evidence; only the DNS-dead `rlvk-burgas.com` was actioned.

---

## 2026-08-26

Stale-audit pass over `CURATOR_TODO.md` (no pipeline runs — every change
verified against `raw/` caches, `scripts/_lib/` data files, and the current
`wiki/data/aocs.en.*.js` build). Sections updated:

- **FR Comté Tolosan cluster** ❌→✅ — parent resolves `aires-csv`, all 6 DGCs
  `parent-appellation`; present in the startup bundle.
- **FR 8 zero-bullet parents** — 7 of 8 now carry 2–5 facts; only
  `cote-vermeille` remains at 0 (left open).
- **FR residual broken IGPs** ✅ — `euskal-sagardoa…` 5 facts, `yonne` 3 facts.
- **ES Wikipedia 29 missing/error parents** ⏳→✅ — superseded by the
  2026-05-14 override mechanism (`aoc_overrides.json["es"]`, 29 entries).
- **ES grape-wiki research prompt** — tmp/ file gone; noted regenerate-if-needed.
- **PT geometry** ⏳→✅ — 14/14 IGPs resolve `caop-concelho-union` (also 23/30
  DOPs); **PT 02d** ✅ ran (44/44 fact files); **PT aoc-lexicon** ✅ ran (44
  cached pages + 27 `pt` overrides); **PT 02c round-trip** marked moot under
  the facts-XOR-summary rule.
- **IT disciplinare URL hunt** 9→1 — 7 Abruzzo IGTs cancelled (EU 2026/558–708,
  `CANCELLED_GIS`), `gambellara` MASAF-bundle-matched 2026-08-21 (5 varieties);
  only `salemi` remains (pending cancellation, off-map).
- **IT VIVC pins** ⏳→✅ — all 17 resolve in `raw/vivc/by-slug/` with the
  researched ids.
- **IT regione fallback** ⏳→✅ — `regione_by_file_number.json` has 165 entries;
  3 records render "Italia" (was 353).
- **IT sottozone** ⏳→✅ — 38 sub-denomination records across 10 DOPs via the
  MASAF Article-1 detector; also fixed the geometry-tracker table that had its
  last 3 rows orphaned below a paragraph.
- **IT consorzio URL count** refreshed 344/531 → 417/523 (post-cancellation
  denominator). NOTE: interprofession-URL curation is running in parallel
  elsewhere — statuses in those sections are intentionally NOT reconciled here.
- **IT complete-coverage residuals** re-verified still open (catalanesca,
  grottino-di-roccanova, valtenesi, osco, rotae, quistello all 0 grapes).
- **AT Wikipedia hints** ⏳→✅ closed — remaining AT slugs pinned `missing` with
  research notes (valley/landscape articles, no DAC pages exist).
- **SI ENOTNI DOKUMENT header** reconciled to the shipped state (1 EU-OJ + 16
  national-spec augmented; register-fiche per-DOP terroir for bela-krajina +
  belokranjec); flagged the belokranjec/metliska-crnina OJ-C re-check window
  (set 2026-05-23, 3–6 months) as now due.
- **Cross-cutting IGP geometry alignment** ❌→✅ — PT + IT buckets landed;
  table refreshed with current per-country strategies; residual is naming
  consistency, not coverage.
- **Page-weight blob** ⏳→✅ — two-tier split shipped (3.3 MB startup blob +
  per-slug lazy panel JSON at `wiki/data/d/`).

Unchanged / confirmed still open: FR SIQO 2 missing wines (Cabernet de Saumur,
Côtes de Blaye — absent from extraction and build), ES sub-municipio precision
(SIGPAC/parroquia ×4), Wikidata QIDs 1,230/2,886, MT/CY grape VIVC+tooltip
enrichment (no `raw/vivc/by-slug/` files for ġellewża/girgentina/giannoudi/…),
HU dűlő Phase-2 parsers, DE Großlagen + Mecklenburger/S-H Landwein geometry,
CZ Ryzlink buketový verification, VIVC open questions (Sárfehér, Moschato
Samou) + the gitignored `slug_overrides.json` pin backup note.

Rully + Maranges CAVB cahiers landed via Type 1C OCR fallback — 35 new slugs
(24 Rully premier-crus + 9 Maranges climats), section X 8050/9349 chars, 02d
ran fine on both, 02e produced 7 EN/ES/NL translations.

Stale audit confirmed three "code follow-ups" already shipped:
- AOC Wikipedia override consumption live in
  `scripts/02b_fetch_aoc_lexicon.py:64-66,322-373,388-390` (cache carries
  `override_source=curator`).
- ES grape lexicon already iterates `raw/es/pliegos-extracted/` via
  `collect_grape_slugs` in `scripts/02b_fetch_grape_lexicon.py:76-95`.
- DOCUMENTO ÚNICO anchor regex matches both Toro + Ribera del Guadiana (RDG's
  "0 grapes principal" was role-routing, not anchor).

Earlier same day:
- Wikipedia AOC override merge — fr 44→101, es 0→29.
- ES national-pliego URL research merged 12 entries into
  `raw/es/national-pliegos/manual_overrides.json` + stage 02f override-priority
  read wired in `scripts/es/02f_extract_national_pliegos.py` + parser tightened
  in `scripts/_lib/es/national_pliego.py` → 138 new variety-DOP additions, zero
  regressions.
- 6 stale research prompts under `scripts/_lib/` deleted after their batches
  closed.
- ES consejo regulador URL merge — 56 new entries to `appellation_urls.json`,
  `by_slug` now 205.
