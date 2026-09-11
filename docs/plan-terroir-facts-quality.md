# Terroir-fact quality fixes — implementation handoff (2026-09-11)

Self-contained plan for a fresh session. Everything below was established by
reading a stratified sample of 1,000 English terroir-fact bullets (plus an
earlier 100) against their source quotes, and by a set of corpus-wide checks.
Evidence, sampler output and per-bullet tags are preserved under
`tmp/terroir-facts-review/` (gitignored, see "Evidence" at the end).

Nothing in this plan changes the public-source rules in `CLAUDE.md`: every fix
is either a pipeline-code change, a prompt change, or a curator re-source
through the existing `manual_overrides.json` mechanism.

## TL;DR

| finding | scale | root cause | work item |
|---|---|---|---|
| Source-language common nouns and non-Latin script left in EN bullets | 16 % of all bullets; 37–51 % for GR/BG/HU/CZ/HR/LU; 12 % IT | the per-country 02e "Preserve … verbatim" prompt lists contain common nouns (soils, climates, harvest categories, scheme abbreviations) | **W1** |
| Alsace grand-cru pages carry Zotzenberg's geology, slope, Sylvaner rule and 1992 date | 51 records, ~250 of 430 bullets wrong | 02d slicer keys spans by section number over the one shared 339 KB cahier → last chapter wins | **W2a** |
| Pierrevert carries Saint-Pourçain's lien; L'Étoile and Grands-Echezeaux carry Bourgogne Passe-tout-grains' lien | 3 records, 15 bullets, all wrong | stage 01 fetched the wrong BO Agri PDF (L'Étoile and Grands-Echezeaux share one manifest filename) | **W2b** |
| Same fact repeated inside one record | 10 % of bullets (435 identical-quote repeats in 340 records, plus paraphrases) | the four sub-section calls re-extract the same sentence; no dedupe | **W3** |
| "wiki" provenance on facts that are grounded in the cahier | 626 of 982 wiki-labelled facts | quotes containing "[…]" fail the longest-contiguous-match coverage test | **W4** |
| Arrows, INAO colour codes (Pinot Noir N), unexpanded VT/SGN, missing terminal period, meta text ("confirmed by Wikipedia") | 4.3 % + 8 % punctuation | no style rules in the 02d prompt; codes are cahier vocabulary | **W5** |
| Bullets with no information ("uniqueness stems from soil, climate and varieties") | 3.4 % overall, 18 % GR | boilerplate sentence shared by many GR/CY specs | **W6** |
| Hedge dropped: "repose essentiellement sur pinot noir" → "exclusively Pinot Noir" | 14 FR bullets corpus-wide | no "keep hedges" rule | **W5** |
| Fact filed under the wrong sub-section | 1.7 % | sub-section is the slice the call came from, not a per-fact judgement | **W7** |
| Audit covers only fr/es/gb and none of the above checks | — | — | **W8** |

What is **not** broken: numeric hallucination. Of 1,275 numbers that appear in
a bullet but not in its grounding quote, at most 5 are unsupported by the
source text once number formats are normalised (`13°5`, `22, 5`, `un
centinaio`, `anno mille`). Extraction fidelity is high; the defects are
mechanical and prompt-level.

Baseline rates (n = 1,000, Wilson 95 % CI) to beat after the fixes:

| category | rate |
|---|---|
| content error / over-claim / mistranslation | 3.4 % (2.4–4.7) — 1.6 % once W2 is fixed |
| untranslated common noun or non-Latin script | 16.1 % (14.0–18.5) |
| near-duplicate within record | 10.1 % (8.4–12.1) |
| provenance mislabelled as wiki | 5.4 % (4.2–7.0) |
| style (arrow / colour code / abbreviation / meta) | 4.3 % (3.2–5.7) |
| no information | 3.4 % (2.4–4.7) |
| misfiled sub-section | 1.7 % (1.1–2.7) |
| no terminal punctuation | 8.1 % (6.6–10.0) |
| fully clean | 58.1 % |

## Recommended order

1. **W2a** (slicer) and **W3/W4 post-pass scripts** — code only, no LLM cost,
   fix the only outright-wrong content.
2. **W2b** curator re-source (three PDFs) — needs a human on the BO Agri UI.
3. **W5** normaliser (deterministic) + **W8** audit — gives the acceptance
   checks before any re-run.
4. **W1** prompt split + **W5/W6** prompt rules — then the targeted LLM
   re-runs (see "Re-run plan").
5. **W7** last; lowest impact.

Follow the memory rule "only fetch what's missing": never re-run 02d/02e
unfiltered across the corpus; every re-run below is scoped to the records a
detector script names.

---

## W1 — Split the 02e "preserve verbatim" lists

**Files.** `scripts/02e_translate_terroir_facts.py` (`build_system_prompt`, the
FR/ES base — line ~68) and all 20 country scripts
`scripts/<cc>/02e_translate_terroir_facts.py` (at, be, bg, ch, cy, cz, de, es,
gb, gr, hr, hu, it, lu, mt, nl, pt, ro, si, sk). Each has one long
`- Preserve <Language> proper nouns verbatim: …` line (bg:42, gr:42–43, hu:42,
hr:42, it:51, es:47, …). The target-locale glossary lives in
`scripts/_lib/translation_glossary.py` (`_EN_GLOSSARY`, `_NL_GLOSSARY`).

**Change.** Split every list into two buckets and rewrite the rule text:

- *Keep verbatim* (proper nouns and registered terms): appellation, region,
  commune and vineyard-site **names**; grape **names** (transliterated when the
  source script is not Latin); **named** formations and named winds (Marnes à
  exogyra virgula, Flysch di Cormons, llicorella, albariza, tuffeau,
  Muschelkalk, Rotliegend, Mistral, Bora, Meltemi); registered traditional
  terms and Prädikat tiers (Aszú, Szamorodni, Vinsanto, Nychteri, tokajský
  výber, Trockenbeerenauslese, Vendanges Tardives, Sélection de Grains Nobles).
- *Translate* (common nouns — this is what currently leaks): generic soil and
  rock words (IT argille / calcare / marne / arenaria / scisti / calcareniti /
  argilliti; HU lösz / mészkő / homokkő / agyagpala / barna erdőtalaj /
  csernozjom / vulkáni talaj; BG льос / чернозем / канелена горска почва /
  смолница; HR-SI vapnenac / crvenica / fliš / apnenec / ilovica / laporovec /
  lapor; PT xisto; DE Lehm / Quarzit / Gneis / Granit / Urgestein /
  Vulkangestein / Steillage / Lagenwein; NL leem / klei / zandleem / mergel;
  LU-FR gypse / marnes keupériennes / calcaire conchylien); climate phrases
  (умереноконтинентален климат, μεσογειακό κλίμα, ηπειρωτικό κλίμα,
  kontinentalna klima, kontinentální podnebí, pannonisches Klima); generic
  harvest and wine-law categories (kasna berba, desertno vino, predikatno vino,
  pozna trgatev, ledeno vino, suhi jagodni izbor, pozdní sběr, slámové víno,
  αφρώδεις οίνοι, λιαστοί οίνοι, pezsgő, gyöngyözőbor, vendemmia, fruttaia);
  site words (lege, dűlő, viniční trať, podgorie, borvidék, vinorodni okoliš,
  ribera, páramo, gromače, emparrado); scheme abbreviations (ΠΓΕ / ΠΟΠ / ЗНП /
  ЗГУ / OEM / OFJ / CHOP / CHZO / ZOI → PGI / PDO).
- Allow a **one-time gloss** of a genuinely technical local term the way
  Drenthe's bullet already does: "boulder clay (keileem)", "dry-stone walls
  (prizidi)". Never the reverse ("Continental (ηπειρωτικό κλίμα)").
- Add a **hard script rule** for GR/BG/CY: "The output must be entirely in
  Latin script. Transliterate Greek and Cyrillic proper nouns using the
  EU-official Latin form (Ξινόμαυρο → Xinomavro, Στара планина → Stara
  Planina, Гъмза → Gamza)." The eAmbrosia `transcriptions[0]` field and the
  grape lexicon's Latin slugs are the reference spellings.
- Extend `_EN_GLOSSARY` with the calques the sample caught: "minerality NOT
  mineralité"; "wine-grape varieties NOT must varieties" (CZ moštové odrůdy);
  "style / version NOT typology" (IT tipologia); "actual alcohol NOT developed
  alcohol" (IT gradi svolti); "carbonate / calcareous soils NOT carbonated
  soils" (FR carbonatés); "vineyard sites NOT lege / dűlők"; "para-barros is a
  Portuguese soil class, never invent proto-barros"; Beaujolais "grillage /
  pigeage / remontage" = submerged-cap / punch-down / pump-over.
- Optional but recommended: move the two-bucket rule into a shared helper
  (`scripts/_lib/terroir_prompts.py`, `preserve_rules(source_lang)`) so 21
  scripts stop drifting. Move-only; keep each country's proper-noun roster.

**Cache invalidation.** 02e caches key on `source_facts_sha`; a prompt change
does *not* trigger re-translation. Country 02e scripts have `--refresh` but no
`--only` (the 02d scripts have `--only`; FR 02d has `--slug`). Add `--only SLUG`
(repeatable) to every 02e script (mirror the 02d flag), then re-translate only
the slugs a detector names. Detector: scan `raw/translations/terroir-facts/
<lang>/*.json` for non-Latin script (`[Ѐ-ӿͰ-Ͽ]`) and for the leak regex below;
check **all four target locales**, not only EN. Run with `--batch --provider
anthropic --refresh --only …` (the batch path loads `.env`).

```python
LEAK = re.compile(r"(?i)\b(lösz|mészkő|homokkő|argille|argilliti|arenari[ae]|calcar[ei]|marn[ae]|scisti|"
                  r"podgori\w*|mineralité|kasna berba|desertn\w+ vin\w*|predikatn\w+|pozna trgatev|"
                  r"ledeno vino|okoliš|vapnen\w+|crvenic\w+|fliš|apnen\w+|xisto\w*|leem|zandleem|mergel|"
                  r"viničn\w+|dűlő\w*|lege\b|Steillage\w*|Lagenwein\w*|Urgestein|typology|must varieties)\b")
```

**Acceptance.** Non-Latin characters in Latin-target caches = 0 outside quoted
local words that carry a gloss; leak-regex hits < 20 corpus-wide; a fresh
50-bullet GR/BG/HU/CZ/HR sample reads as English.

## W2 — Wrong chapter / wrong cahier

### W2a Shared-cahier slicer (Alsace grand cru, 51 records)

`scripts/02d_extract_terroir_facts.py`: `_spans_by_top` (line ~183) builds
`out[m.group(1)] = (start, end)` over every `1°- / 2°- / 3°-` anchor in the
lien, so with 51 cru chapters in one 339 KB `lien_au_terroir` the **last**
chapter (Zotzenberg, alphabetically last) wins for every cru. Only the
`produit` slice (generic to all crus) is currently correct.

Fix in `slice_section_x`: when the lien contains more than one `1°` anchor,
first locate the record's own chapter — the heading `« Alsace grand cru
<Cru> »` (compare accent-folded; the record's `name` is the cru name) — and
restrict the lien to the window from that heading to the next `« Alsace grand
cru` heading before slicing. If no own chapter is found, log loudly and skip the
record rather than fall back. Add a unit test on a synthetic three-chapter lien.

Then re-run for the 51 slugs only: `02d … --slug alsace-grand-cru-… --refresh`
(FR 02d uses `--slug`), which changes `source_facts_sha` and re-queues 02e for
those records automatically. Expect the new facts to describe each cru's own
geology (Gloeckelberg is granitic sand, Rangen volcanic, Kitterlé sandstone,
etc. — the chapter texts say so).

The longer-term home for this is stage 02 (CLAUDE.md notes sub-sections of a
shared cahier are not parsed in v1); the 02d fix is sufficient for the terroir
layer.

### W2b Wrong PDF bound to the record (3 parents) — curator + guard

| id | slug | lien actually belongs to | evidence |
|---:|---|---|---|
| 290 | `pierrevert` | Saint-Pourçain | lien mentions Saint-Pourçain 6×, Pierrevert 0×; manifest PDF `e2a5794e…` |
| 187 | `l-etoile` | Bourgogne Passe-tout-grains (Mâcon / Jura regional text) | lien byte-identical to `bourgogne-passe-tout-grains`; manifest PDF `49acff22…`, shared with Grands-Echezeaux |
| 184 | `grands-echezeaux` | same as above | same PDF `49acff22…` |

Route: a curator finds the right cahier on the BO Agri search UI and pins it in
`raw/inao/cahiers/manual_overrides.json` (mechanism in CLAUDE.md, "Manual
override mechanism"), then stage 01 → `02 --only` → `02d --slug` → 02e → 04.
The corresponding entry is in `CURATOR_TODO.md` (France).

Guard (stage 02 or `audit_terroir_facts.py`): for every FR parent with a lien
≥ 800 chars, tokenise the appellation name (drop stop words such as côtes, de,
saint, grand, cru, village, coteaux) and require at least one token to occur in
the lien; otherwise emit a warning and, in `--strict`, fail. The check that
found these three is in `tmp/terroir-facts-review/` (see Evidence).

## W3 — Dedupe within a record

Two layers:

- **Post-pass now** (no LLM cost): `scripts/dedupe_terroir_facts.py` rewriting
  `raw/terroir-facts/*.json` in place. Drop a fact when (a) its normalised
  `cahier_quote` or `wiki_quote` (≥ 30 chars) equals an earlier fact's, or
  (b) `rapidfuzz.fuzz.token_set_ratio(bullet_a, bullet_b) ≥ 85`. Keep the
  earlier fact unless the later one has provenance `both` or a longer quote.
  Rewriting changes `source_facts_sha`, so 02e re-translates the ~340 touched
  records automatically (`--batch`).
- **In 02d** for future runs: the same routine after the four sub-section calls
  (FR: the loop around line ~436 that does `facts.append(classified)`; every
  country 02d has the same `f["subsection"] = sub["key"]` pattern, e.g.
  `scripts/it/02d_extract_terroir_facts.py:362`). Put it in
  `scripts/_lib/terroir_dedupe.py` and call it from all 21 scripts. Add one
  prompt line: "Do not restate a fact already covered by another sub-section."

Sample cases to test against: `skalicky-rubin` facts 3/10,
`moselle-luxembourgeoise` facts 1/2/3/6/7/8/10 (42 km, 129–142 m and the two
cantons appear three times each), `vulkanland-steiermark` 5/7, `sobes` 3/7,
`hrvatsko-podunavlje` 3/6, `colline-lucchesi` 2/7, `halkidiki` 3/7.

## W4 — Coverage check with ellipses

`fuzzy_coverage` (FR 02d line ~171; the same function is duplicated in the
country 02d scripts and in `scripts/audit_terroir_facts.py`) uses one
longest-contiguous match. The model legitimately joins two spans with "[…]",
"[...]" or "…", which caps coverage well below 0.6 and flips provenance to
`wiki` (626 cases) or drops the fact.

Fix: split the quote on `\[…\]|\[\.\.\.\]|…|\.\.\.`, compute coverage per span,
and take the minimum (spans shorter than ~15 chars ignored). Move the function
to `scripts/_lib/terroir_coverage.py` and import it everywhere. Then a post-pass
(`audit_terroir_facts.py --rewrite-provenance`, or a small script) recomputes
`cahier_coverage` / `wiki_coverage` / `provenance` on the existing caches
without an LLM call. Expect roughly 600 facts to move from `wiki` to `cahier`
or `both`; the panel attribution ("via Wikipedia · CC BY-SA 4.0") changes
accordingly at the next stage-04 build.

## W5 — Style rules and a deterministic normaliser

**Prompt (02d `EXTRACT_SYSTEM`, FR line ~132, and the country equivalents):**

- Full sentences ending with a period; no "→"; no label prefixes ("Colour:",
  "Climate:", "Soils:").
- Grape names without INAO colour codes (N / B / G / Rs / Rg).
- Expand VT / SGN / TBA on first use.
- Never refer to "the document", "the cahier", "the disciplinare" or
  "Wikipedia" inside the bullet (two bullets leaked "confirmed by Wikipedia" /
  "according to the document").
- Keep the source's hedges: essentiellement, principalement, parfois, souvent,
  généralement, "repose sur". Do not strengthen to "exclusively", "100 %",
  "only", "always".
- Skip statements that would be true of any appellation.

**02e:** add "drop INAO colour-code suffixes" and "end every bullet with a
period" to the base rules.

**Normaliser (`scripts/_lib/terroir_normalize.py`, applied at stage-04 render
and available as a cache post-pass):** append a terminal period when missing;
strip ` (N|B|G|Rs|Rg)` after a token that resolves in the grape lexicon; expand
`VT` / `SGN` in FR/EN/ES/NL. Leave arrows and meta text to a targeted re-run:
the ~150 arrow bullets and the "exclusively / 100 %" bullets are re-extracted
with `--slug … --refresh` once the prompt rules are in.

## W6 — Boilerplate filter (conservative)

Detect a `cahier_quote` (normalised, ≥ 60 chars) shared by ≥ 3 records of the
same country **and** matching a tautology pattern (`uniqueness … attributed
to`, `directly linked to the character`, `no uniform description`, `defined by
their typicity`, `favourable soil and climatic conditions`). Drop such facts
unless they are the record's only fact. Do **not** filter on shared quotes
alone — several cahiers are legitimately shared (Anjou family, the Calabrian
IGT text, the RO caiete, the Alsace `produit` slice). Add the pattern list to
the 02d prompt as things to skip.

## W7 — Sub-section per fact (low priority)

Either ask the model to return `"subsection"` per fact and use it when it
disagrees with the slice, or add a keyword reclassifier in the post-pass
(yield / density / pruning / vinification / AOC dates → facteurs_humains; soil
/ climate / relief → facteurs_naturels; colour / aroma / palate → produit).
Sample cases: `haspengouwse-wijn` 4/10 (yield cap under naturels), `la-tache`
1/9, `moselle-luxembourgeoise` 6/10, `tarquinia` 5/5 (climate under humains),
`castelli-romani` 3/5, `vin-santo-del-chianti` 8/8.

## W8 — Audit extension

`scripts/audit_terroir_facts.py` only knows fr / es / gb
(`EXTRACTED_BY_COUNTRY`, line ~45). Extend it to every country by reusing each
country 02d's lien resolver (`_resolve_lien_and_source`, which already handles
the national-spec sidecars), and add checks, each with a count and `--strict`
failure:

- non-Latin script in Latin-target translation caches;
- INAO colour codes, arrows, label prefixes, missing terminal period;
- intra-record identical quotes and bullet similarity ≥ 85;
- cross-record identical quotes (report only, with the whitelist of shared
  cahiers);
- FR parent whose lien never names the appellation (W2b guard);
- shared-cahier records whose quotes are not found in their own chapter (W2a);
- provenance `wiki` with a non-empty `cahier_quote` after W4.

## Re-run plan and cost

1. Land W2a, W3 post-pass, W4 post-pass, W5 normaliser, W8 checks. Run the
   audit to get the "before" counts.
2. Curator supplies the three PDFs (W2b); run stage 01 → 02 `--only` for them.
3. Land W1 + W5/W6 prompt rules (+ `--only` on the 02e scripts).
4. LLM re-runs, all `--batch --provider anthropic`, all scoped:
   - 02d `--refresh`: the 51 Alsace slugs, the 3 re-sourced slugs, the ~150
     arrow records, the 14 "exclusively" records, the GR/AT boilerplate
     records — roughly 250 records.
   - 02e `--refresh --only …`: every record whose `source_facts_sha` changed
     (automatic) plus the W1 detector list in all four target locales — on the
     order of 2,000 record-locale pairs. Anthropic batch pricing makes this
     cheap; do not use Ollama with `--workers > 1` (memory rule).
5. `scripts/04_build_maps.py`, then the audit in `--strict`.
6. Re-sample 200 bullets (seed 2027) with the sampler below, tag with the same
   rubric, and compare against the baseline table. Target: untranslated < 2 %,
   duplicates < 2 %, content errors < 1.5 %, style < 1 %, provenance mislabel
   ≈ 0.

## Evidence (`tmp/terroir-facts-review/`, gitignored)

- `sample1000-review.md` — every flagged bullet of the 1,000 sample with EN,
  source bullet, quotes and tags. Rubric: ERR (content error / over-claim), MT
  (mistranslation), UNT (untranslated common noun), LOW, SUB, STY, DUP, META;
  automatic tags NONLATIN, ARROW, CODE, NOPUNCT, PROVMIS, DUPQ, ALSACE.
- `sample1000_tagged.json` — the same sample as data (`issues` per bullet).
- `tags.txt` — the raw manual tags by sample index.
- `sample.json` — the earlier 100-bullet sample.
- `numcheck.log`, `numcheck_notfound.json` — the corpus-wide beyond-quote
  number check.

Sampler (reproduces `sample1000.json`; seed 2026, ≥ 10 per country, rest
proportional):

```python
import json, glob, os, random, collections
rows = []
for p in sorted(glob.glob("raw/terroir-facts/*.json")):
    slug = os.path.basename(p)[:-5]
    if slug.startswith("manifest"): continue
    src = json.load(open(p)); c = src.get("country", "fr")
    enp = f"raw/translations/terroir-facts/en/{slug}.json"
    en = json.load(open(enp))["facts"] if os.path.exists(enp) else (src["facts"] if c in ("mt", "gb") else None)
    if en is None: continue
    for i, f in enumerate(src["facts"]):
        if i < len(en):
            rows.append(dict(slug=slug, country=c, i=i, en=en[i]["bullet"], src=f["bullet"],
                             cq=f.get("cahier_quote", ""), wq=f.get("wiki_quote", ""),
                             prov=f.get("provenance"), sub=f.get("subsection")))
random.seed(2026)
byc = collections.defaultdict(list)
for r in rows: byc[r["country"]].append(r)
sample = [r for c, l in byc.items() for r in random.sample(l, min(10, len(l)))]
rest = [r for r in rows if r not in sample]
sample += random.sample(rest, 1000 - len(sample)); random.shuffle(sample)
```

Corpus-wide detectors used in the review (rewrite as audit checks in W8):
non-Latin `re.compile(r"[Ѐ-ӿͰ-Ͽ]")` over EN bullets → 791 hits (GR 503 / 1,170,
BG 264 / 544); INAO code `[a-zé]\s(N|B|G|Rs|Rg)(?=[\s,;:.)]|$)` → 160 FR bullets;
arrows → 152; identical `cahier_quote` within a record → 435; `provenance ==
"wiki" and cahier_quote` → 626; lien-never-names-appellation → 4 FR parents
(the 3 above plus `saone-et-loire`, which is fine).
