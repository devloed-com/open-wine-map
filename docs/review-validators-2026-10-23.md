# Validators — first runs (2026-10-23)

The five validator skills of [plan-validators.md](plan-validators.md) were built
and run for the first time on 2026-10-23. This note records what each run
covered, what it found and what the findings taught about the validators
themselves; the queued actions are in CURATOR_TODO.md under "validators,
first runs". Raw reports: `tmp/validation/` (gitignored), copies of this
session's under the scratchpad.

## `/validate-sources` — `audit_source_freshness.py`

Corpus-level probes (10 requests, cached a day) over 1,673 parent records in
21 countries, then a 60-record HEAD sample of the national and regional tiers.

| tier | result |
|---|---|
| eAmbrosia (1,195 GI rows) | 1,067 CURRENT · **62 NEWER-UPSTREAM** (26 with a new OJ C single document, the rest a modification date after our fetch — usually a register attachment) · 64 IN-OPPOSITION · 2 GONE with `removedFlag` (Salemi, Ambt Delden — both already in `cancelled_gis.json`) · **1 NEW registered PDO not indexed: Nivegy-völgy (PDO-HU-02816)** |
| data.gouv.fr (INAO) | **parcellaire release 2026-10-19 newer than the 2026-09-28 built**; SIQO CSV and the two aires CSVs current (the latter by saved-after-publication, the listing's ETag is not comparable) |
| GOV.UK | 6 / 6 registered current; The Crouch Valley `applied-for` (pending, reported as such) |
| GISCO LAU / NUTS, swisstopo | 2024 / 2024 / 2026-01 current; Bétard SNAPSHOT by design; 10 layers UNVERIFIABLE (no release listing fetched — CAOP, ONS, IGN, cadastre, IET, SIGPAC, MAPA zone, IT geoportals, SITG, IVV) |
| counts | every eAmbrosia-spined country reconciles 1:1 after the known exemptions (RO duplicate administrative registrations, the BE-owned Maasvallei); FR 440 live / 441 parents (12 live file numbers with no SIQO row — the register's own stale FR entries, Blaye, Côtes de Blaye, …) |
| per-record sample (60 records, 47 URLs) | 37 CURRENT · **2 GONE** (Priorat's INCAVI pliego, Znojemská's Sbírka file) · 1 RELINKED (Dehesa del Carrizal, JCCM) · 7 UNREACHABLE (`www.mapa.gob.es` SSL error from this machine — host breaker tripped; one BO Agri reset) |

What the run taught: the register's GI rows must carry the file number and
name to be readable; the counts need the FR binding (`resolved.json`) and the
duplicate-registration rule; the aires CSVs have no comparable ETag, so the
local file's save date against the resource date decides; GOV.UK's slugs are
not ours (compare the register URL's path); a pending application is CURRENT
with a reason, not NEW.

Not run: `--inao` over France (466 pages ≈ 10 min; the 22 newer arrêtés of
2026-09-20 remain the latest list), `--deep` corpus-wide, `--reference`.

## `/validate-cards` — `audit_cards_llm.py`

Synchronous run, 3 records, Opus 5.5, 75 s, ≈ $0.42:

| record | verdict | findings |
|---|---|---|
| Rioja Alta (es, sub-denomination) | **do-not-trust** | 4 verified misleading: the Alavesa *product characteristics* bullet on the Rioja Alta card (sibling-leak — the known 2026-09-20 defect), a separate "Malvasía (Malvasia Dubrovacka)" pill where the 2026 single document lists Malvasía riojana under Alarije (wrong-grape-identity: the VIVC pin), an accessory tier the regulator does not assign (wrong-role), the sweet / semi-sweet category missing (missing-style); plus the El Ternero enclave (Burgos) absent from the area line, and the untranslated Spanish summary fragment |
| Pauillac (fr) | trust | 4 defective / cosmetic: two natural- and human-factor omissions (the oceanic climate; the 18 crus classés), the French date on the English card |
| Znojmo (cz) | trust | none |

Every quote re-grounded (0 unverified). Two prompt rules were added from this
run: style pills are taxonomy nodes shown at several depths (not duplicates);
"every variety shown as principal where the regulator splits no roles" owes
no note.

The 40-record stratified batch run (`--sample 40 --seed 7 --batch`, estimate
≈ $4) is reported in the section below.

## `/validate-cards` — 40-record stratified sample

Batch run `--sample 40 --seed 7 --batch`: 40 records from 20 countries
(stub cards with augmented content included, sub-denominations in
proportion), Opus 5.5 adaptive thinking, one Batch API job of 40 requests,
1 h 36 min wall-clock, **$2.12** (604 k input / 87 k output tokens; the
estimate said $2.84). 0 records failed; 155 findings — 66 misleading, 81
defective, 8 cosmetic; 3 quotes failed re-grounding and are not counted.
Reports: `tmp/validation/cards-sample40.{json,md}`, curator rows
`cards-sample40-rows.md`, feedback evidence `cards-sample40-feedback/`.

As reported by the judge: **25 of 40 cards carry a verified misleading
finding (62.5 %, Wilson 95 % 47–76 %)**. By section: grapes 37, styles 19,
terroir facts 5, area 4, summary 1. Verdicts: 12 do-not-trust, 13 caution,
15 trust (the 6 FR records: 5 trust, 1 caution; the 3 CH: trust).

Every misleading finding was then looked up on the rendered card, the
sidecars or the lexicon. What that reading changes:

**The fact layer is confirmed clean.** 5 misleading facts in 40 cards
(≈ 300 bullets): three stale Wikipedia-sourced bullets (Alicante L'Alcoià ×2,
the obsolete two-subzone division; Monterrei, the six-municipality list that
predates the 2025 Cualedro / Laza parishes), one narrowed attribution
(Tokajské: Peter the Great "credited" the wine where the source says the
wine was credited), one sibling confusion (Maltese Islands: a DOK sentence
on the IĠT card). The 1.3 % of the gate programme holds on this sample.
Emitted as feedback evidence → `scripts/build_terroir_feedback.py
--evidence tmp/validation/cards-sample40-feedback --review-id
cards-2026-10-23T083709`.

**Ten of the 66 are not card defects:**

- *Moravské (4).* The judge was given the 2011 EU register fiche and not the
  Vyhláška 88/2017 decree the card follows (`raw/cz/national-specs/varieties.json`
  is not in `SIDECAR_DIRS`): Domina, the six accessory names, the six roles
  and the seven "extra" varieties (Cabernet Cortis, Medea, …) are
  fiche-vs-decree differences. Packet gap — add the decree sidecar.
- *Roles on Primorska, Východoslovenská, Balatonmelléki, Bela krajina (5).*
  The EU register fiche splits MAIN / OTHER where the national spec lists
  varieties role-less and the card shows all principal (the SI / SK / HU
  convention). A policy question, not an extraction error; the CZ Znojmo
  rule of 2026-10-22 (fiche roster when narrower) is the precedent.
- *Tokajské summary (1).* The card renders facts and no summary (facts XOR
  summary), but `card_fields` handed the judge the record's `summary` field
  regardless — the same artefact produced the 15 *defective*
  `label-fragment` / `untranslated-term` summary findings. Validator
  defect, fixed the same day: `card_packet.card_fields` exposes the summary
  only when the card renders it (`tests/test_card_packet.py`).

**56 real misleading defects in 23 of 40 cards (57.5 %, Wilson 42–72 %)**,
in six failure modes — the roster and style layers, not the facts:

| failure mode | findings | records | what the sweep says |
|---|---:|---:|---|
| grape identity (lexicon / VIVC) | 5 | 5 | `perle-von-zala`, `zala-gyoengye`, `zala-gyongye` → `csabagyongye` in `GRAPE_ALIAS` is wrong — Perle von Zala *is* Zalagyöngye, a different cultivar — and the `csabagyongye` by-slug VIVC record is #13374 ZALA GYOENGYE while `zalagyongye` has none. **15 cards** carry csabagyongye (HU 8, DE 3, GB 4); 5 HU cards show "Csabagyöngye (Zala Gyoengye)" beside "Zalagyöngye". Also: Malvasia di Candia aromatica split into "Malvasia (Malvasia Dubrovacka)" + bare "Candia" (the Dubrovačka pin of the Rioja Alta smoke run again); Moschato Samou → Muscat Ottonel (Larnaka); Blanca de Monterrei and Doña Blanca both → Siria (verify on VIVC: one synonym, or two cultivars). |
| roster parser | 3 | 2 | Irsai Olivér split into "Irsai" + "Olivér (Plavaie)" by the HU termékleírás parser (the sidecar carries two names); Μονεμβασίας lifted from the Malvasia Χάνδακας-Candia history narrative; its two capped varieties (≤ 15 % together) shown as unrestricted principals. |
| missing varieties | 20 | 9 | lexicon gaps — Drenthe's seven (Baco noir, Birstaler Muscat, Excelsior, Melody, Muscat Blue, Palatina, Polo Muscat: all in `raw/nl/extraction-unknowns.json`), Kéknyelű (HU; not even in the unknowns queue), Cabernet franc (HU national unknowns), Castilla's Coloraillo / Garnacha peluda / Verdoncho, Larnaka's Soultanina; a colour-word ban — Východoslovenská's Rosa (`_BANNED_SURFACES`); a slug collision — Méditerranée's Muscat à petits grains Rg folds into the B entry; parser reach — Colli Altotiberini's Cabernet Sauvignon / Merlot (varietal types), Dealurile Olteniei's Merlot / Pinot Noir / Burgund Mare (named only in the yield table), Dunavska ravnina's Latin-script Viognier in a Cyrillic list. |
| styles | 19 | 12 | omissions of listed categories — rosé (Alentejo Borba, Bela krajina, Jardins de Wallonie, Východoslovenská, Laona-Akama, Larnaka: the two CY cards are white-only where the spec regulates red and rosé), sparkling / licoroso (Alentejo Borba; La Palma's espumoso, aguja, licor), sweet (Bela krajina, Zakynthos) — and four extras from the grape-colour style floor: White + Red on the sparkling-only Vlaamse mousserende kwaliteitswijn, Rosé on Drenthe (`_GRAPE_COLOUR_TO_STYLE` maps a rose-berried grape to a rosé style), Sweet on Valle Belice, Late Harvest on Dunavska ravnina. |
| "N commune(s)" header | 3 | 3 | `_meta_tail` prints `communes_matched` for every geometry source outside the FR parcel / CSV family; on zone- and NUTS-drawn records the field is the commune-list parser's count (1), not the aire: La Palma (14 municipios), Colli Altotiberini (8 comuni), Monterrei (parishes of 8 ayuntamientos) all read "1 commune(s)". **388 parent cards** corpus-wide: IT geoportal-zone 232, ES mapa-zone 86, GR gisco-nuts-region 38, GR gisco-commune-list 14, ES geometry-research-municipios 5, IT gisco-comune-union 4, … |
| area disclosure | 1 | 1 | Monterrei's parish line lists the 49 parishes and not the whole municipio Vilardevós the redraw includes — read as a missing municipality. |
| terroir facts | 5 | 5 | above. |

The 81 *defective* findings (not counted above) are led by `source-not-cited`
(11: the MASAF disciplinare or national spec the roster came from is not in
the card's Sources list — Colli Altotiberini, Valle Belice, …), `other`
terroir-fact omissions (11), the summary artefact (15) and sub-denomination
relation notes (6); they are listed per record in `cards-sample40.md`.

What the run says about the validator itself: the judge is precise where it
has the document (0 unverified quotes on 155 findings, every spot-checked
claim held) and systematically wrong where the packet is incomplete or a
house convention is undocumented — three of the four such cases found here
are now fixed or named (summary exposure; the CZ decree sidecar; the fiche
roles stated as a convention in the prompt). The 10 % false-positive rate
of this run is the number to beat on the next sample.

## `/validate-geometry` — `audit_geometry_vs_text.py`

Full runs on RO · BG · HU · CH (217 records), a 260-record sample over FR · AT
· RO · BG · HU · CH.

| run | OK | SUSPECT | NO-UNITS | NO-TEXT | ABOVE-COMMUNE |
|---|---:|---:|---:|---:|---:|
| RO · BG · HU · CH | 71 | **9** | 53 | 82 | 2 |
| FR · AT · … sample (260) | 83 | 1 | 160 | 12 | 4 |

The nine: **Дунавска равнина** (BG PGI drawn as the union of its 21 member
PDOs — 40 obshtini — while its text names 100: the `region-pdo-union`
fallback under-draws a PGI whose text is a commune list; the fix is the
`gisco-commune-list` step that already exists in the BG chain); **Etyek-Buda**
(Bétard covers Budapest, Biatorbágy, Aba, Csabdi whole; the text names them
in part or not at all); five RO IGPs drawn from commune lists whose named and
drawn sets differ by 5–30 units (a mix of the județ-scoped homonym rule
against the audit's 25 km rule, villages named below the commune tier, and
prose tokens in the parsed list); two RO PDOs where Bétard's padding draws
whole communes the text does not name (Crişana, Lechinţa). FR: 75 OK, no
SUSPECT; the 153 NO-UNITS are DGCs (no delimitation text of their own).

What the run taught (three rounds, each removing a class of false positive):
LAU names carry tier prefixes ("Oraş Babadag", "Municipiul Tulcea") — folded;
a same-named commune in another county is the layer's, not the text's — a
unit farther than 25 km from the polygon is set aside; Hungarian county names
are above the commune tier; a French sub-denomination's aire lookup falls back
to its parent's row — a DGC has no named set of its own and is tested for
containment only; the tiled geometries are simplified, so containment needs a
0.25 km² floor and compares polygons of one kind only (a whole-commune DGC or
a cadastral lieu-dit against a parent's parcels is outside by construction);
and the record's parsed `geo_communes` is the deterministic side, `--llm` the
independent one. Not run: `--llm` (ES / DE / IT / PT / GR have no deterministic
reader yet).

## `/validate-release` — `validate_release.py --quick`

11 quick gates in 6.3 min:

| gate | status |
|---|---|
| empty-grapes, gi-terms, styles, vivc-pins, dup-keys, terroir-facts, parcellaire-gaps, about-date | pass |
| grape-surfaces | **fail** — 8 fuzzy bindings (Malvasia Nera → malvasia-nera-di-brindisi ×4, Refosco nostrano → refosco-di-faedis ×4, …) |
| ambiguous-synonyms | **fail** — 47 risky surfaces (Nerello → frappato, Serprino → glera-lunga, Cagnina → canaiolo-nero, …) |
| untranslated | **fail** — 300 (slug, locale) pairs, 145 slugs |
| betard-delta | **fail** — 121 FLAGGED, 0 REVIEWED (the overrides table is empty) |

All four red gates are pre-existing states of the build, not regressions of
this work; they are the curator queues the audits already report. The umbrella
makes them visible in one table — the point of the gate.

`diff_records.py snapshot` of the current build: 2,955 records, 2.6 MB; a
self-diff is empty.

## Tests

35 new tests (`test_card_packet`, `test_cards_llm`, `test_freshness`,
`test_geometry_vs_text`, `test_diff_records`, `test_validator_skills`); the
full suite passes (1,498). Ruff is clean on every new file; the three remaining
repo-wide findings are in files of the uncommitted 2026-10-22 work
(`04_build_maps.py` import order, `tests/test_masaf_roles.py`).


## Addendum — phase B (2026-10-23, Fable 5.1 after Opus 5.5 halted)

Items 3–8 of the work list are closed in CURATOR_TODO (each row carries what
changed); the retry's record is `tmp/validation/phaseB-attempt2-2026-10-23.md`.
What a reader of the cards sees:

- the 12 NL provincie PGIs carry their seven listed varieties and no longer a
  Rosé their single document never names; nine NL / BE records gain the Rosé
  theirs lists, and the three Flemish PDOs have a description again (the BE
  slicer is monotonic);
- Kéknyelű on eight HU cards; the wrapped halves ("Irsai" / "Olivér (Plavaie)",
  "Cabernet" / "franc") read as one name on fifteen;
- Malvasia Χάνδακας-Candia and Malvasia Σητείας list their seven varieties
  with the capped two as accessories — the GR national-spec reader now takes the real header over a prose line that merely carries a keyword, reads a grape sentence as an enumeration, and counts a colour word only beside a wine word; 31 GR rosters changed, every one read (Βηλάνα, Μπεκάρι, Βλάχικο, Βραδυανό, Κορινθιακό gained; Μαυρούδι its own pill on 11 cards instead of "(Agiorgitiko)"; the generic Malvasia and a colour word gone);
- Larnaka and Laona-Akama carry the colours their alcohol minima state; the
  three CY cards with Σουλτανίνα list it and Moschato Samou is the Samos
  muscat, not Ottonel;
- 53 FR cards carry the red or pink petits-grains muscat as its own pill;
  nine ES cards Garnacha peluda as its own; Castilla Coloraillo; Colli
  Altotiberini, Colli Romagna Centrale and Ischia their Article 1 varietal
  types; three RO cards their yield-table varieties; Дунавска равнина
  Viognier; the five modern SK specs Rosa;
- Monterrei's Blanca de Monterrei pill carries no bracket and the parish line
  names Vilardevós whole.

Left on purpose: the GB / MT style readers' "rosé for any red grape" (phase
C), the ≤ 15 % optional group of Handakas-Candia and Arkadia's link-only
semi-sparkling (phase C's GR category row), and the terroir caches of the GR
records whose link text the strict header pass completed (phase D's re-run
scope, listed in CURATOR_TODO). No LLM run; ≈ 30 live VIVC requests.


## Addendum — phase C (2026-10-23, Opus 5.5)

Items 9 and 10 of the work list, and the GB / MT "rosé for any red grape"
phase B left, are closed in CURATOR_TODO (each row carries what changed); the
step-by-step record is `tmp/validation/phaseC-2026-10-23.md`. Five full
builds, each one's record diff equal, record for record, to the union of the
style previews it followed; `audit_styles.py --strict` passed after each. A
style preview (stage-04 load + augment + style chokepoint, no geometry) ran
before every build and caught the one regression a reader change would have
shipped: Prosecco, whose newly read Rosé switched off the floor's White. What
a reader of the cards sees:

- the floor reads the categories a record declares
  (`scripts/_lib/wine_categories.py`): Vlaamse mousserende kwaliteitswijn
  shows Quality Sparkling alone, Crémant d'Alsace, Franciacorta and the two
  Walloon sparklings no colour their texts do not name (Crémant d'Alsace and
  Franciacorta: White and Rosé, the Walloons no Red); Dealu Mare and Cotnari,
  which declare still wine, keep Red;
- a sweet or dessert wine is Sweet, an ice wine Icewine, a straw wine Vin de
  paille, a wine of dried grapes Raisin wine — never Late Harvest: Dunavska
  ravnina, Muškat momjanski, Nemea, Argolida, Dafnes, the two Patras PDOs; 15
  HR specs gain Raisin wine or Noble Rot, two HU cards lose a Late Harvest
  only their jégbor had given;
- PT has a style reader (it had none): 66 cards gain Rosé, sparkling,
  licoroso or the traditional method their caderno lists; SI reads the
  register's single document beside its national text (Rosé on 12 of 17 cards,
  none had one); SK its "Farba:" line; ES a national pliego's lettered type
  list (La Palma's espumoso, aguja, licor); RO the description's sub-sections;
- Greek and Hungarian sweetness levels listed as wine types are Semi-sweet /
  Sweet (67 GR cards, Zakynthos among them; 16 HU); the four GR / CY readers
  share one token-based colour matcher, which also reads a list of colours
  sharing one wine word (Larnaka's Red) and stopped reading Santorini's aged
  Vinsanto hue as a red wine; a (semi-)sparkling type in any inflection beside
  a wine word gives Arkadia, Ήπειρος, Makedonia and Tyrnavos their
  Semi-sparkling;
- the Italian readers read the type titles a description is sliced into
  (Franciacorta, Prosecco, Abruzzo, Riviera del Garda Rosé; Roma and Vicenza
  Red and Rosé; Maremma Toscana's Passito and Vendemmia tardiva …) and the
  head word of the colour field — "colore: giallo paglierino" is a white wine
  even when the type is named Pigato, Pecorino or Vitovska: 22 cards gain
  White (Riviera Ligure di Ponente, Offida, Carso, Cagliari, Colli Piacentini,
  Vittoria …), Prosecco keeps the White its newly read Rosé would have
  switched off, and the Vin Santo DOCs lose a Red the floor took from the
  Sangiovese of their Occhio di Pernice; IT cards whose colour came from the
  grapes alone: 51 → 2;
- Crémant d'Alsace reads its "Types de produit" section (White, Rosé);
- the UK and Maltese readers state their colours from the text (the DEFRA
  analytical limits; the register's single document for Malta and Gozo, which
  also gives them Sweet, Late Harvest and Raisin wine, cited on the card).

Valle Belice was not a card defect: its Sweet is Art. 6 "sapore: da secco a
dolce"; the MASAF sidecar now keeps Art. 6, so the judge's packet carries it.
Side effects, both read: the HU 02 re-run applied phase B's Kéknyelű binding
to six HU EU-document records (phase B had re-run HU 02f only); the GR 02
re-run exposed the substring colour match fixed above. The release gate
(`validate_release.py --quick`) passes 9 of 13 checks, its four failures —
grape-surfaces, ambiguous-synonyms (46), untranslated (300 pairs),
betard-delta (121) — with the same counts as before phase C; the suite passes
(1,574).

Left on purpose, each with a CURATOR_TODO row: 112 cards whose colour still
comes from their grapes alone (DE 27, RO 20, FR 18, CH 15, AT 14 …;
Cerasuolo d'Abruzzo, rosé-only, shows Red — a "colore: rosa" reading would
also hit the Occhio di Pernice); the IT documento-unico slicer that takes
per-type headers for sections (25 of 129 records; fixing it moves sections,
rosters and terroir text); the FR "seconde fermentation en bouteille" as
Traditional Method (60 records, each to read — Bugey Cerdon is ancestrale);
Madeira's floor colours on a fortified-only DOC; the Maltese Islands IĠT stub
not wired to its fiche; the "Vin de liqueur" label in EN / NL; semi-dry; the
128 IT non-stub MASAF sidecars; the HU termékleírás colour fallback. No LLM
run (the paired before / after reading is phase H's); about a dozen
eAmbrosia attachment requests (the MT and SI fiches).

## Addendum — phase D (2026-10-23, Opus 5.5)

Item 11 of the work list, plus the 21 Greek records whose link text phase B's
strict header pass re-read, all closed in CURATOR_TODO. Run
`phaseD-2026-10-23`, one rollback unit; the per-record before / after is
`tmp/validation/phaseD-facts-diff.md`, every record read.

The evidence merge needed three fixes first (tests added, CLAUDE.md updated):

- `build_terroir_feedback.py` filed a card finding under the card's slug. The
  two Alicante findings were read on the L'Alcoià card, which inherits
  Alicante's facts, so they would have gone to a sidecar no extraction reads.
  It now files a finding under the record that owns the facts and recovers the
  source-language bullet and its index. The recurrence check therefore sees
  non-English records: it found Monterrei's and Tokajské's claims at score
  100 before the re-run.
- The "unless the source states it explicitly" exemption would have let a
  stale Wikipedia statement through, because the article does state it. A
  source-vintage or sibling claim now reads "assert it only if the current
  regulator text itself states it", and the gate carries the matching note.
- The LLM audit skipped an English-source record as untranslated (Maltese
  Islands). It now grades the record's source bullets.

Scope: 25 records — Alicante, Monterrei, Tokajské, Maltese Islands and the 21
Greek records. 02d ran as a batch. The gate batch stalled at 0 / 25 after 86
minutes, so the gate, 02e and the back-check ran synchronously under the same
run id. The boilerplate post-pass then dropped 5 Greek tautology bullets.

**Result.** None of the five claims is in the new bullets, and do-not-claim
recurrence went from 5 to 0 in the scope. `audit_terroir_facts.py --strict`
stayed at 0 failures, and every translation cache is aligned. The paired LLM
audit (Opus 5.5) went from 5 misleading bullets of 161 to 0 of 171 (95 % CI
0–2.2 %), and from 7 defective to 3. Four records improved; none got worse.
The Greek records gained most: their link text is no longer cut at a
sub-heading, so Lesvos, Χάνδακας-Candia and Serres went from 2 bullets to 7,
and Thessaloniki from 4 to 6.

**What the gate and the audit cannot see:**

- *Stale Wikipedia facts.* A stale statement graded against the same
  Wikipedia hint passes. For the three source-vintage claims, the evidence is
  their absence from the new bullets (best fuzzy match ≤ 54), not the audit.
- *Coverage.* Sonnet 5.5 keeps to the per-sub-section caps, which the older
  caches overshoot: 948 of the corpus's 1,644 hold more than a cap allows.
  The re-run therefore cost some faithful facts:
  - Tokajské went from 13 bullets to 9 and lost the Rákóczi «VINUM REGUM – REX
    VINORUM» and tuff-cellar bullets that its own capture hint asks for;
  - Monterrei lost its variety list;
  - Alicante lost its sparkling and Moscatel bullets;
  - Maltese Islands lost its Cassar de Malte bullet.

  Decided 2026-10-24 — see the follow-up below.

**Found along the way, each in its own CURATOR_TODO row:**

- The GR / CY national-spec link section has no end anchor, so it runs into
  the later sections; 47 Greek texts carry more than 1,000 characters of tail.
  Fix it before the next Greek terroir pass.
- Kavala's "21ου αιώνα" reads as a source typo.
- Three clarity defects remain.
- Ticino, English and Welsh wine are due for 02d after phases B and C, and
  Collioure is gate-pending. All four are outside the scope.

Cost ≈ $10: $3.00 in the batch ledger (02d $0.96, the LLM audits $2.04) and
an estimated $6–7 for the synchronous gate, 02e and back-check, which the
ledger does not record.

Phase E's build (22:27) carries these facts, except the boilerplate drop: 5
Greek cards show the tautology until the next build. To undo the run:
`rollback_terroir_facts.py --run phaseD-2026-10-23`, then stage 04.

### Phase D follow-up (2026-10-24) — the caps are set by the code

Boris took the proposal: the allowance for a long text moves from a sentence
the model had to weigh ("you may return up to two extra bullets", set
against each call's hard "Maximum N") into the number itself.
`terroir_prompts.sub_section_cap` gives a regulator text over 4,000
characters — measured once per record on the cached leading document block,
never the Wikipedia hint — the caps 7 / 4 / 3 / 1; interactions is never
widened, the allowance sentence is gone, and every one of the 21 02d scripts
sets its cap through the helper (linted). Freshness keys are untouched, so
the change re-stales nothing and applies when a record is next re-run. The
corpus numbers behind the decision: 1,275 of the 1,622 measurable liens are
over the threshold (the rule is close to a base-cap raise), 873 of the 948
overshooting caches are long texts, and the +2 / +2 / +1 keeps 1,851 of
their 2,374 above-cap bullets when they are re-run.

Tokajské, run `cap-2026-10-24`, twice under one id. The raised caps alone
gave 13 facts (6 / 4 / 3): the tuff cellars came back, Rákóczi did not —
the four human-factor slots went to Béla IV, the cellars, the 1650 first
výberové víno and the aszú technology, so the capture hint still had no
standing. The hint block was then reworded as a priority inside its
sub-section (the cap stands; a hinted fact the text states goes ahead of an
unhinted one) and the record re-run: 14 facts (7 / 4 / 3), Rákóczi's
«Vinum regum – rex vinorum» and the tuff cellars both in, and the Tsar
Peter bullet back as the source's two coordinated sentences — the gate
rewrote the extractor's causal join into the source's coordination, with no
agent for the attribution, which was the review's finding. Gate 11
supported / 3 rewritten / 0 dropped; paired Opus audit 9 → 14 bullets,
0 misleading and 0 defective on both sides; strict audit 0 failures; the
back-check fixed one ES soil term and one NL article. ≈ $1, synchronous.

The other three phase D losses were not the cap. Monterrei's variety list
had come from Wikipedia's «uva preferente» line — the 681-character
regulator text names no variety and the pills carry the roster — so the
narrower bullet is a correction. Maltese Islands' product slot was free;
the lost bullet named a producer brand from Wikipedia and the regulator's
IĠT yield rule replaced it. Alicante is a different mechanism: a product
sub-section returned empty from a 2,215-character text that states two
product facts verbatim, and an empty product section is common corpus-wide
(346 of 1,155 Sonnet 5 caches, 19 of 27 Sonnet 5.5). Re-run alone, the
product call again returned one bullet and the dedupe removed two more that
restated the natural factors; with the Spanish product topics widened to
name the wine types made and a variety's colour range, and a capture hint
naming the two statements, the third extraction returned both as its two
product bullets (7 → 9 facts, 0 misleading on both sides, gate 8 / 1 / 0).
The topics change applies to every Spanish record on its next re-run; the
other product prompts still read "colours, aromas, structure, ageing".

### Greek end anchor (2026-10-24) — the link ends at the trailing sections

The GR / CY national-spec parser gave the link section no end: the
template's trailing sections ("8. ΑΛΛΕΣ ΠΡΟΫΠΟΘΕΣΕΙΣ", "9. ΕΦΑΡΜΟΣΤΕΕΣ
ΑΠΑΙΤΗΣΕΙΣ", the control authorities, the application form, the ministry
letterhead) carried no role, so `link_to_terroir` ran to the end of the
document in 123 of the 151 sidecars, 41 of them by more than 1,000
characters, and the form's "Δεσμός: http://…" re-opened the link by the
bare keyword. `POST_LINK_ROLE` (`_lib/gr/specifikacija.py`,
`tests/test_gr_spec_link_end.py`): once the link has opened, a
capitalised header of those sections — tested before the role keywords,
under the strict header rules in both passes — opens a post-link role no
reader consumes, and nothing re-opens a role after it; the salvage
window's end anchors are folded (its "προϋποθέσεις" anchor had kept its
dialytika and never matched). The GR and CY 02f sweeps, each with a
per-record diff of sections, roster, styles, area units and link text:
113 of 139 GR and 10 of 12 CY links changed, every one a pure prefix cut
(Ήπειρος 19,267 → 5,171, Arkadia 15,993 → 5,725, Kos 15,563 → 6,075,
Χάνδακας-Candia 70,081 → 59,680); no roster or style moved; 27 GR area
texts lost the legal block a re-opened area header had swallowed (only
`decree_year` shifted, all still before the 2011 tier threshold, so no
polygon moves); the stage-04 prose scan loses no style slug.

**Re-run `gr-anchor-2026-10-24`**, every stage a batch: 128 records —
115 GR, 10 CY, 1 CH, 2 GB: the cut links, Τύρναβος and Μακεδονία (new
stage-02 texts from the parallel session), and the three stale caches of
the phase D list (Ticino, English and Welsh wine). 02d under the
code-set caps: 900 → 1,023 bullets; the gate (Opus, 74 minutes at
0 / 128 and then whole) kept 934, rewrote 65, dropped 24, moved 22,
refused no rewrite → 999 facts, 63 records up, 26 down, 39 unchanged.
By sub-section: natural factors 565 → 596, human factors 269 → 363 (the
raised cap), product 24 → 14, interactions 42 → 26. Of the 30 records
that lost their interaction, 19 lost the "uniqueness is due to soil,
climate and winds" tautology, 4 had it re-filed under the natural
factors, and 5 lost a real causal statement (Έβρος, Χαλικούνα,
Ιωάννινα, Κάρυστος, Χάνδακας-Candia) — the cap is 1 and 103 of the 128
now carry none. The Welsh and English wine caches lost the Roman / 1970s
planting and 22 → 48 vineyard bullets the specification does not carry.

**Found reading the losses — the empty sub-section, in Greek.** Three
records came back with no natural-factors bullet and seven with no
product bullet although the old bullets' quotes are still in the cut
text, and the call returned `{"facts": []}` with nothing filtered
(`n_dropped` 0, `n_deduped` 0): Αιγαίο Πέλαγος (3 → 0 on 14,401
characters), Καρδίτσα, and for the product Αρκαδία, Χίος, Κρήτη,
Μακεδονία, Μαυροδάφνη Κεφαλληνίας, Μεσσηνία, Ραψάνη. Μαυροδάφνη's lost
statements — "λίγες σταγόνες … μεταχρωματίζουν ένα ποτήρι λευκού οίνου",
the 19th-century geographer's "βαθυτάτου χρώματος ερυθρού" — are colour
and aroma, inside the Greek product topics as written, so the Spanish
product-topic widening is not the lever here; the open row in
CURATOR_TODO starts with a one-record reproducibility test. Πελοπόννησος
(5 → 0 natural) is a different case: its `wrong-source` caution says the
natural-factor sections describe Αχαΐα, Πλαγιές Αιγιαλείας and Αρκαδία,
and the extractor obeyed it.

**Back-check** (Opus, 510 caches, 66 minutes at 0 / 510 and then whole):
3,982 translated bullets, 451 fixed (11.3 %), none rejected. The fixes,
by hand-classified kind: 72 exonyms (Thessaly → Thessalië, Parnassus →
el Parnaso, Στερεά Ελλάδα → Grecia Central), 65 transliterations (Χάνδαξ
had come out as "Handax" where the EU form is Chandax), 43 false friends
and wrong senses (ρετσίνι the resin read as the wine, the heliothermal
index as heat summation), 26 Dutch article agreements, 22 hedges
weakened or strengthened, 19 units and dates (στρεμματικές αποδόσεις is
per stremma, not per hectare), 18 place names back-formed from a Greek
genitive (Kranias, Thapsana), and 174 single-sentence sense errors.
Every translation cache is aligned with its source (510 pairs, 0
misaligned, 0 pending).

**Strict audit**: 9 failures, all one check — nine translated bullets
still carried Greek script: a local term glossed in brackets after its
transliteration (άμετρος, λιαστός οίνος, ξερολιθιές, τίνες, μορλούκια),
the ΘΑΣΙΩΝ amphora stamp, and Theognis' verse quoted in Greek on the
Lilantio Pedio card. The deterministic normalise post-pass is the tool for
exactly that, and its dry run exposed two defects in it: the all-caps
stamp came out as "ThASION" (the capital theta kept a lower-case h), and
a gloss that transliterates to the very word before it was kept ("tines
(tines)", "xerolithies (xerolithies)"). Both fixed in
`_lib/terroir_normalize.py` (an all-caps token stays upper case; a
redundant gloss loses its bracket; `tests/test_terroir_normalize.py`),
then the post-pass applied to the six records under the same run id — 9
translated bullets, 0 source bullets, so no hash moved — and the audit
re-run: **0 strict failures**. Its 8 feedback recurrences are all outside
the scope and pre-existing (Mambourg, Bohotin, Irpinia, Montefalco
Sagrantino, Muscat de Rivesaltes, Retsina Peanias, Riesi, Saale-Unstrut).

Cost: $16.03 for the chain (02d $3.83, gate $3.81, 02e $2.20, back-check
$6.19) plus about $2.4 for the two LLM audits — the "after" batch $0.82,
the "before" state run synchronously at the full rate after its batch had
sat three hours at 0/30 (cancelled with nothing succeeded, so unbilled;
every other Opus batch of the day landed whole at 66–76 minutes).

**Paired LLM audit** (`audit_terroir_facts_llm.py`, Opus, the same 30
records — 24 GR, 4 CY, 1 CH, 1 GB — graded in EN on the backup and on the
live caches):

| state | bullets | misleading | share (Wilson 95 %) | defective |
|---|---:|---:|---|---:|
| before (`--from-backup gr-anchor-2026-10-24`) | 202 | 3 | 1.49 % (0.51–4.27) | 5 |
| after (live) | 223 | 0 | 0 % (0–1.69) | 4 |

3 records improved, 0 worse, 27 unchanged. The three "before" misleading
bullets were the extraction classes the gate is for: Ikaria had the
phylloxera sentence inverted (the source says the vines were quickly
*replaced with* grafted stock, the bullet read as a lasting loss), Laona
Akama carried an invented qualifier ("shallow" topsoil where the source
says only "φτωχό επιφανειακό χώμα"), Spata dropped a "mean" ("a maximum of
35 °C" for "μέση μέγιστη … 35 °C"). None survives. The four "after"
defective bullets are translation nits, not false claims: Ikaria drops the
relativiser "για τα δεδομένα του νησιού" on the vineyard area; Plagies
Pentelikou leaves the common noun "βότρυν" transliterated as "botryn", which
reads as part of a variety name; Retsina Pallinis softens a stated causal
result ("με αποτέλεσμα") to "goes hand in hand with"; Serres transliterates
the local vessel name as the declined form "kouritous" with no gloss. The
peer session's stage-04 builds 2 and 3 carry these caches; its check of the
rendered payloads for the 128 records found 13,716 terroir-fact strings and
none in Greek or Cyrillic script.

**Reproducibility test and batch forensics (afternoon).** The
empty-sub-section finding was tested on one record: `mavrodafni-kefallinias`
re-extracted synchronously under run `gr-repro-2026-10-24` with the very
prompt the batch had sent (the provider passes the [document block,
instructions] system list unchanged; temperature 0.2 on both paths). It did
not reproduce — both product bullets came back, including the "λίγες
σταγόνες … μεταχρωματίζουν ένα ποτήρι λευκού οίνου" one — and the record
was then gated (5 supported, 1 rewrite), translated and back-checked (2
fixes, 0 rejected). The run's raw batch replies, re-read through
`client.messages.batches.results` and the pipeline's own `parse_facts`,
give the shape of the class: of the 115 Greek product calls 107 returned
`{"facts": []}` — 64 of them in nine output tokens, 43 with an explanation,
three of which say the user message carries only the sub-section title
(the document is the cached system block; the user turn is the one-line
ask) and most of the rest that the text holds "no organoleptic profile
(colour, aroma, structure, ageing)", the model reading the product topics
as a tasting note. The natural phase had 7 empties (2 real losses), the
human phase none, interactions 75 (the earned sub-section). Seven of the
twelve Greek records whose text states product facts lost them — sampling
variance on a narrowly read sub-section, not a parse failure and not the
end anchor. Boris gave the go the same afternoon and the fix went into the
20 non-FR scripts through `scripts/_lib/terroir_prompts.py`: the product
topics widened in 15 languages (`product_topics` — the wine types the text
says are made, a variety's colour range, sweetness, ageing, the traditional
methods, and the sentence that a colour / sweetness / type statement is a
product fact without a tasting note), a request line that points at the
document block (`ask_line`; every script's SOURCE-2 header had said "in the
user message below" since the caching refactor moved the document into the
system prompt), and a second reading (`should_retry`: when the natural
factors or the product return an empty list on a text carrying at least
three stems of that sub-section's vocabulary, the call is repeated with a
request line that says the first answer was empty — an empty list only if
there is truly none; interactions and the human factors are never retried)
recorded on the cache as `retried_subsections`. In batch mode the second
readings are a follow-up round (`batch.run_two_pass(..., follow_ups=True)`:
a probe replay collects them, one more batch, the main answers kept in
`.results.json` so an interruption resumes without resubmitting;
`tests/test_batch_follow_ups.py`). The probe on `chios`, synchronous under
run `gr-retry-2026-10-24`: the product call answered empty again and the
second reading returned two product facts. The other seven ran as a synchronous chain under the same id (02d, gate,
translation, back-check, strict audit: 0 failures; none of the eight in the
untranslated-residue detector), 63 → 77 facts. The lost sub-section came
back on five of the eight — arkadia (2 product bullets), makedonia (1),
rapsani (2) and aegeo-pelagos (2 product, and its natural factors 0 → 5)
on the first reading, chios on the second — and stayed empty on three after
two readings although the old bullets' quotes are still in the text:
messinia and kriti (product — "πλούσιο σε χρωστικές και αρώματα"; the sweet,
λιαστοί and λικέρ wines of Crete), karditsa (natural factors, a generic
sentence the gate would drop). The second reading therefore recovered one
of the four records it fired on; with eight records the widened topics and
the pointer cannot be told apart from sampling. The next lever for the
three needs no code: a `capture_if_present` hint in their feedback sidecar
and a scoped re-run. That re-run followed the same evening (`gr-hints-2026-10-24`,
synchronous; one hint per record describing the pre-anchor product / natural
statements as the source states them; 02d, gate, translation, back-check,
strict audit with 0 failures; 21 → 27 facts, 26 after the boilerplate
post-pass). kriti regained its product facts on the first reading (two; the
gate filed the sugar-accumulation one under interactions and cut a 10–15 %
clause another bullet carries). karditsa went from 2 to 5: the natural call
returned three bullets and the gate re-filed all three as human factors (the
"ideal soil and climatic conditions" clause belongs to the sentence on the
wines' fame), its tautology interaction went to the boilerplate filter, and
its natural factors stay empty because the 2,913-character text states none.
messinia's product call answered for the first time, but its product
statements are the effect clauses of its natural factors: the dedupe folded
them and the gate filed the two causal ones (nutrients → aromatic substances,
light and airing → pigments and aromas) under interactions, which leaves the
record at two interactions against the cap of one — the gate's `subsection`
verdict does not apply the cap. Gate: 23 supported, 4 rewritten, 0 dropped,
7 moved; back-check 8 of 108 bullets fixed, 0 rejected; the untranslated
detector lists none of the three. The hint works where the text states the
fact as a sentence of that sub-section and cannot conjure one the text writes
as a clause of another sub-section or does not write at all.

The same afternoon closed the Collioure item of the phase-D row: the record
had been built from INAO's PNOCDC draft of March 2011 (section X an empty
skeleton, 315 characters), the register's attachment is the cahier that
draft became (décret n° 2011-1826 du 7 décembre 2011, no amendment since),
so `register_overrides.json` pins it with `prefer_cahier`; stage 01 / 02
re-sourced the record (lien 14,412 characters, 16 varieties) and a
synchronous one-record chain under `collioure-2026-10-24` gave it 15
supported facts, translated and back-checked (2 fixes), where it had one.

## Phase E (2026-10-23) — grape roles from the EU register fiche

The count behind the decision: 154 cards in eight countries showed every
variety as principal while their register fiche tagged a MAIN / OTHER split
(HU 22, RO 38, GR 39, BG 29, SI 15, SK 7, MT 2, CZ 2 under its own rule; HR's
fiches carry no split). Boris chose option B — membership from the national
roster, roles from the fiche, a variety absent from the fiche shown as
accessory with a count, a national source that splits roles itself left
alone, an 80 % coverage gate. Built as `scripts/_lib/augment/fiche_roles.py`,
run after the last national-spec augmenter in stage 04; the card cites the
fiche on a new Sources line. Dry run on the deployed startup rosters: 134
records applied, 1,616 pills to accessory, 61 unlisted varieties; skipped 18
for coverage (the Hungarian and Romanian fiches of another vintage), 6 with
a national split, 163 fiches without a split, 1 record without a roster
(Maltese Islands). Two side findings went to CURATOR_TODO: Stredoslovenská's
card carries one variety against a 40-variety fiche, and the Portuguese
technical files were never extracted, so the PT "roles not published"
conclusion rests on dre.pt alone.

Build of 2026-10-23 (after the other session's phase D run had exited):
the `[load] register-fiche roles` line matched the dry run — 134 records,
1,616 varieties to accessory, 61 unlisted; the record diff showed 134
role changes and no membership change (the 30 other changed records are the
phase D terroir facts). The four cards the 40-record run had flagged for
roles were re-judged synchronously ($0.59): 13 misleading findings before,
5 after, 4 records improved, 0 worse; Primorska and Východoslovenská `trust`.
What remains is not the overlay's: Balatonmelléki's Piros / Kék Bakator
identity (a lexicon pin), and on Bela krajina the pravilnik split the
decision keeps, a Sparkling pill from the fiche's category list and one
narrowed white-wine fact — all rowed in CURATOR_TODO.


## Addendum — phase F (2026-10-24, Opus 5.5)

Items 13–16 of the work list: the sources the first `/validate-sources` run
found behind their publisher. Every re-extraction ran as snapshot → run →
per-record diff, and every diff was read; the CURATOR_TODO rows under
"`/validate-sources`" carry the detail.

**13 — INAO parcellaire 2026-10-19.** Adopted (11,751 → 11,764 rows). AOC
Montpeyroux finally has parcels of its own (id_denom 2951, 5.9 km²), so the
record left its four-commune union for `parcellaire`. Ladoix was re-digitised:
four premier-cru climats grew, and three gained duplicate null-insee rows
that do not move the union. Montlouis-sur-Loire lost a sliver. Both
carry-forward entries stay: Saint-Sardos still has no row, and the DGC
Languedoc Montpeyroux's own rows are still absent. `audit_parcellaire_gaps.py
--strict` passes; build 1's record diff showed exactly those six records.

**14 — Nivegy-völgy (PDO-HU-02816).** HU index 42 → 43; single document
C/2026/2812 extracted (6 varieties, 7 települések, a 5.7 KB link), region
Balaton. It is drawn from its seven települések (GISCO LAU: one polygon,
58.4 km²; `audit_geometry_vs_text.py` OK, 7 named, 7 drawn). The text
declares still wine only and describes its two wine types as yellow without
the word fehér, so the card's White comes from the grape floor. Hu.wikipedia
has no wine article (pinned `missing`), so its 15 terroir facts ground on the
single document alone: the gate kept 12 and rewrote 3, and the four
translations' back-check fixed three NL bullets. VERIFICATION.md has the
entry.

**15 — 62 GIs modified since our fetch.** Not 62 one-offs but one failure
mode: every stage 01 fetched "the first OJ C listed", and eAmbrosia lists
publications untyped and unordered, so 45 records whose own list already
named a newer single document kept the older one. The stage 01 / 01b scripts
of the 16 EUR-Lex countries now take the newest non-corrigendum OJ C by the
date the register prints (`scripts/_lib/oj_publications.py`). 58 documents
were re-fetched and re-extracted — ES 22, IT 12, RO 9, NL 6, HU 5, CY 2, DE 1,
GR 1. Seven of them are the first single document of a former stub (Landwein
Main, Boca, Fara, Lessona, Marsala, Larnaka, Lefkosia). The ten records
flagged as amendments in progress were held until their newest heading was
read: all ten turned out to be approved standard amendments (no OJ L follows
those, which is why the register's flag cannot decide). Ambt Delden's newest
OJ C is its cancellation request, so its 2018 single document is pinned.

The new documents are mostly on the 2024/1143 template, and reading them
surfaced reader defects, each fixed with its sweep:
- GR / CY / BG / RO: the template's last section ended no link, so the EUR-Lex footer ran into it;
- GR: a stray full stop cost Τύρναβος a community;
- HU: the §3 decoy, a nested "Siller bor" header and the "Bor – Fehér" colour lines;
- ES: "Palomino Fino" read as a manzanilla;
- RO: the last-wins slicer (Cotnari);
- IT: the golden / amber colour heads (Marsala) and a duplicated section title (Terre Tollesi);
- DE: the product lines ("Wein, weiß", Rheinhessen and Landwein Main) and a negated Perlwein;
- RO: a commune line "Oraş Cernavodă - comuna Cernavodă" that would have dropped two towns from Colinele Dobrogei's polygon;
- ES: a season word, "verano", that had put Sciacarello on Valencia and its four subzonas since August.

Build 2's record diff against build 1 (242 changed, 1 added) was read record
by record against the documents. Every style and roster change follows the
new texts: Asti's rosé and Brachetto, Arlanza's ice wine, Condado de Huelva's
generosos, Cigales' "any authorised method", the Romanian rosés and sparkling
wines, Terre Tollesi's four types. The Romanian role moves (Cotești,
Ștefănești, Lechința, then Drăgășani) follow phase E's rule: a yield table
that names varieties §7 omits is a national split, which outranks the fiche.
All 128 fact changes are the peer session's Greek anchor run. The diff
surfaced three more gaps, each fixed with its sweep:
- RO: the yield table printed inside section 5 under "(b) Producții maxime" (11 documents). Drăgășani's 2026 document names Sauvignon, Merlot, Pinot noir, Burgund mare and Tămâioasă românească only there, and they had left the card.
- ES: a Castilian "ñ" municipio name that GISCO spells with "ny". Valencia Valentino's Picanya is the only case, and the subzona had drawn 28 of its 29 municipios.
- CY: the bare "Malvasia Grossa" of the new Cypriot documents, which VIVC files under four primes (Síria, Malvasia Dubrovačka, Vermentino and a black passport of its own name). It now has its own slug, pinned `false`.

Builds 3 and 4 changed exactly the records each fix targeted: Drăgășani and
Valentino, then Larnaka and Lefkosia.

**16 — dead URLs.** INCAVI moved its pliegos and every Catalan single
document still cites the old path. Nine DOs are relinked: Priorat on its June
2026 pliego, Penedès off MAPA's 2022 copy onto INCAVI's current one. The
Czech decrees cite e-Sbírka. JCCM's moved host is relocated in code. MAPA's
"SSL error" is client-side (Python's certifi lacks MAPA's intermediate; curl
connects), and es/02f now falls back to curl.

**Left, with reasons (CURATOR_TODO).**
- A decision on Agudelo / Sumoll in the Catalan records. A researched 2026-05-19 alias says Godello; VIVC flags Agudelo as Chenin blanc's official name in Spain, and INCAVI's pliego says Chenin.
- Varieties a newer single document names outside §7, which the readers do not read: Piemonte's Sauvignon (§4) and Eger's Turán and Cabernet dorsa (§5.1).
- Malvasia Bianca Lunga under two slugs (42 + 57 records).
- The ES slicer, which lets nested headings overwrite sections 1–5 in 70 of 149 records (pre-existing; the card fields survive).
- Marsala's card, which loses Dry and Sweet now that its governing text is the single document. A sweetness-only MASAF union was measured (9 records: one wrong colour, four unsupported) and not applied before the non-stub sidecars are re-read.
- Asti's "pas dosè".
- Condado's newer pliego, behind a host that resets from this machine.
- Five filed but unpublished amendments. Bükk's moved its date and adds one Bétard-delta flag.
- Douro's minor-amendment caderno.
- Bürgstadter Berg's decision layout.
- Montsant's sidecar, which colours Garnacha peluda white. No card shows it.
- The 45 terroir caches whose source text changed: 86 bullets in 19 of them no longer find their quote. Four of these records left their MAPA pliego and no longer ground most of their bullets.

**Builds and gate.** Four stage-04 builds, the last with 2,956 records (+1, Nivegy-völgy), and each build's record diff was read: build 1 showed item 13's six records; build 2 showed the documents of items 14–16 and the peer session's 128 fact changes; builds 3 and 4 showed exactly their fixes' records. On build 4, `validate_release.py --quick` passes 11 checks and fails 4, all four already failing in phase E. Phase F's share of them:
- grape-surfaces: 8 flags, all correct bindings caught by the audit's word-count rule (Pineau d’Aunis in the six NL provinces, Terre Abruzzesi's "Refosco nostrano", Badacsony's "budai");
- ambiguous-synonyms: none — the count is 46 as in phase E, once Malvasia Grossa was pinned;
- untranslated: 4 bullets, Nivegy-völgy's "dűlő" glossed beside its translation, as Bükk, Füred, Mura and Tokaj already are;
- Bétard-delta: one flag, Bükk, whose amendment date the HU index refresh brought in (121 → 122).

The ten records from the peer's run that untranslated lists are all a Spanish "mar Egeo", the correct exonym — a detector false positive, not a translation defect.

**Cost.** About $0.6 of synchronous Anthropic calls for the Nivegy-völgy chain (02d, gate, 02e, back-check; estimated from token counts, since synchronous calls are not in the batch ledger) and one live VIVC search. This phase ran no batch job. The peer session's Greek anchor run ($16.03, batch) is in its own section above.

## Addendum — phase G (2026-10-24, Opus 5.5)

Items 17–19 of the work list: the polygons `/validate-geometry` found
disagreeing with their text. Each re-extraction ran as backup → run →
per-file diff (only the commune-list fields moved), and the one stage-04
build's record diff changed exactly five records; the CURATOR_TODO rows under
"`/validate-geometry`" carry the detail.

**17 — the two BG PGIs are drawn from their obshtini.** Дунавска равнина was
the union of its 21 member PDOs and covered 40 of the obshtini its ЕДИНЕН
ДОКУМЕНТ names; Тракийска низина, a stub the first run could not read, was
the union of 32 southern PDOs. Both texts list obshtini under „Област X:"
headers and then cut villages out of them, a template the BG reader now
reads: each name is held to its oblast (two obshtini are called Бяла and
the text names both), "Д. Митрополия" and "Вълчидол" resolve to Долна
Митрополия and Вълчи дол, and "Септември" is an obshtina, not a month. 21
obshtini in each PGI are held only in part; they are drawn whole and the
card lists them. Дунавска равнина: 118 obshtini, 17,316 → 46,151 km².
Тракийска низина: 93, 55,220 → 43,393 km². Its old union had drawn all of
north-east Bulgaria through Bétard's Черноморски район PDO, ground the
northern text claims, so the two PGIs used to overlap; they no longer do.
`--country bg --strict` passes (118 / 118, 93 / 93), and the independent LLM
read agrees: 118 of 118 for Дунавска равнина. For Тракийска низина it
differs only by the three Smolyan obshtini held "само землищата на" a few
villages. "Добрич" first drew the city obshtina alone, an island inside
Добрич-селска. The ИАЛВ's Черноморски район spec settles it: under one
"Община Добрич" it lists the city and the villages of Добричка. Both units
are drawn now, which makes Дунавска равнина 119 units and 47,445 km².

**18 — RO: mostly the audit, once the parser.** The five RO IGPs' SUSPECT
came largely from the audit itself. Its 25 km homonym rule bound villages
("Comuna Plugari, satele Plugari, Oneşti") to same-named communes of the
next county (Municipiul Oneşti, Bacău). Stage 04 already holds a name to
its header's județ, and the audit now does the same. The LLM read (7
records) names nothing the parser misses. What the parser draws beyond the
LLM's list falls into three explained classes. One of them showed a real
defect: a village listed under its commune bound any same-named commune of
the county. That is right for the communes split off in 2004 (Paleu from
Cetariu, Saligny from Mircea Vodă, ~20 more) and wrong for coincidences.
The resolver now binds such a name only to a commune that touches its head.
Six coincidental communes left three IGPs: Pănceşti, Tansa, Cristeşti and
Fântânele (Dealurile Moldovei), Cotmeana (Munteniei), Măldăreşti
(Olteniei). The prose tokens are gone. Dropping quoted sub-denomination
names also let two shadowed communes back into their lists: "Comuna
Biharia" (Crişana) and "Comuna Iana".

**19 — Bétard padding, queued.** A sweep of the Bétard-drawn HU / RO / BG
PDOs gives the class: Etyek-Buda, Mátra (all of Budapest for
"Budapest-Rákosliget"), Duna, Balaton, Balaton-felvidék, Crişana and six
RO PDOs one unit each. Its fix is the commune-list redraw already used for
the post-Bétard PDOs, which needs a partial-unit disclosure first.

**The audit, changed.** BG names are scoped by oblast and RO names by
județ, with the village rule mirrored. A national-spec stub is read from
its sidecar, as stage 04 draws it (HU / RO NO-TEXT 28 → 0). That surfaced
one new finding: Monor's termékleírás names four települések and the HU
reader kept one. The reader ended a list at its first "település…", and
Monor names one group per hill. Fixed: every group is read and headings are
dropped. That changed 8 HU lists, all for the better: Monor 1 → 4 and Tolna
0 → 59 (its text opens on "Települések:"), and Duna gains five headed
names. All eight are Bétard-drawn, so no polygon moved. On the `--llm` side, the model reports each unit's county and
keeps villages apart. Its answer budget grows with the text and triples for
Cyrillic, because the first two BG answers came back truncated. A truncated
answer is no longer cached as "names nothing".

**Cost.** Synchronous Opus 5.5 for the LLM reads: 7 RO texts, then the 2 BG
texts twice (the first pair truncated). About $4–6 estimated from the answer
sizes; synchronous calls are not in the batch ledger. No batch job ran.

## Addendum — phase H (2026-10-24 → 25, Opus 5.5)

Item 20 of the work list: the closing build and the measurements behind it.
The CURATOR_TODO subsection "Phase H — close" carries one row per item.

**The build.** A full stage-04 build is byte-identical to the build of 21:40
(23,677 files), and its record diff is empty, so the phase G tree builds
deterministically. Over phases A–G the record diff is 950 records changed and
one added (Nivegy-völgy).

**The gates.** `validate_release.py --quick` fails on the four gates that
failed on the first run, all of them queues rather than regressions: the
grape-surfaces queue of family words the lexicon folds onto one member
("Canaiolo", "Malvasia Nera", "Refosco nostrano"), 46 ambiguous synonyms
(47 on the first run), 320 untranslated pairs and 122 Bétard-delta records.
The other eight gates pass, and pytest passes 1,674 tests. The untranslated
count had first read 413. The rise was not in the translations: every
stage-03 generator dropped its whole country from the shared
`wiki/_index.json` before merging, so an earlier
`03_generate_wiki.py --only collioure` had left one French entry of 1,541.
Stage 04 does not read that index, but the untranslated detector takes its appellation-name exemption from it ("Alsace" inside "Crémant
d'Alsace"), and `terroir_roster` takes the sub-denomination roster of the
dedupe pass and the 02d / 02e prompts from it. All 21 generators now merge
through `extract_index.wiki_index_kept`: a `--only` run replaces only its
selection, and the FR run leaves `index.md` / `log.md` alone. A wiring lint
in `tests/test_extract_index.py` covers it. With the FR index rebuilt the
count is 320 (300 on the first run). Of the rise, 47 flags are real, on the
caches the phase D–G re-runs re-translated (Egeo, Piemonte, Toscana kept in
the source form; dűlő, Podgoria, Argille left untranslated) and queued for a
scoped 02e refresh. The Bétard-delta count reached 122 before phase F's
index refresh, not in this phase.

**Sources.** `audit_source_freshness.py` on the 241 records the phases
touched, then `--deep` on the Last-Modified verdicts, found no new upstream
content. The 16 eAmbrosia modification dates carry no new publication. The
11 Last-Modified verdicts (Laona Akama, the SZPI PDF of the nine CZ records,
Priorat's pliego) are sha-identical: server re-stamps. The 2 GONE are already
in `cancelled_gis.json`, and the 70 UNREACHABLE come from six hosts that
reset or fail SSL from this machine. The two SI NEWER-UPSTREAM verdicts
(Belokranjec, Metliška črnina) are the validator's own: it compares against
an SI register index older than the documents the build holds.

**Geometry.** `--country bg --strict` passes with 0 SUSPECT.

**The cards, before and after.** The 23 cards that carried real defects on
2026-10-23 were re-graded by the same judge (Opus 5.5, batch) and paired
with the first run: cards with a misleading finding 23 → 7, misleading
findings 61 → 14; 21 cards better, 2 the same, none worse. Every misleading
finding of the first run on these cards is gone, except two: Castilla's
missing Verdoncho, and Bela krajina's roles, which are a house decision.
Each of the 14 was read against the build and its documents. Twelve are real
and two are judgement calls. They are mostly rosters the phases changed,
seen afresh:

- **Grape identity.** Kék and Piros Bakator share one slug (Balatonmelléki).
  Castilla's Verdoncho, Albillo Dorado and Tinto de la Pámpana Blanca bind,
  through VIVC synonyms, the slugs of the Pardillo, Albillo Real and Tinto
  Velasco the same pliego lists beside them. In Larnaka a synonym after the
  dash ("Malvasia di Candia — Malvasia Aromatica") makes a pill of its own.
  La Palma's comma-less "Listán Prieto Moscatel negro" has a slug of its own.
- **A stale extraction.** Larnaka and Lefkosia lack Malvasia Lunga. The
  current reader returns it, but both records were extracted the morning
  before the Malvasia bianca split.
- **A reader gap, not isolated.** Seven RO cards miss a rosé their single
  document names in a list sharing one noun ("vinuri albe, roze").
- **Facts.** La Palma states the 1505 planting without the source's "se cree
  que" (a hedge the gate passed in September), and gives a Wikipedia alcohol
  range for vino de tea where the pliego gives one range per colour.
  Dunavska ravnina's facts leave out that the sparkling wine is Gergana alone.
- **Judgement calls.** Dealurile Olteniei's Merlot is accessory by the RO
  yield-table rule and MAIN in the register fiche. Bela krajina keeps its
  pravilnik split.

The identity findings point to a wider class, swept on the build: 118 parent
cards show two slugs VIVC files under one number (194 pairs). The largest
group is 46 Tuscan and Umbrian cards where the register's "Prugnolo gentile"
binds the Corsican `nielluccio` and sits beside Sangiovese. Then come Greco
and Greco bianco (15), Ansonica and Inzolia (11), and the PT IVV rosters.
Some pairs are deliberate and some are the regulator's own two names, so
this is a curator queue, not a defect count. The list is in
`tmp/validation/vivc-shared-pills-2026-10-25.txt`.

**Not done in this phase, and why.** None of the new findings was fixed
here. Each needs a re-extraction with its own diff and another build, and
the phase's job was to measure the tree the earlier phases left. They are
queued with their recipes.

**Cost.** The card batch: $1.52 (440 k input / 56 k output tokens; the
estimate said $1.82). Over the programme since 2026-10-23 the batch ledger
holds $25.49: the 40-card first run $2.12, the Greek anchor chain $16.03,
the curator-decision re-run and the LLM audits making up the rest. The
synchronous calls, which the ledger does not record, are estimated at
$13–16 (phase D gate / 02e / back-check $6–7 and ≈ $1, phase E $0.59,
phase F $0.6, phase G $4–6, the first three-card run $0.42). Total ≈ $39–42.

## Addendum — phase H, fixes applied (2026-10-25, Opus 5.5 then Fable 5.1)

Boris asked for the 14 findings of the phase H re-grade to be fixed, and
settled the one decision among them: the register fiche's roles win over the
Romanian yield-table rule, with a warning on the card. Opus 5.5 applied the
fixes and halted when the harness's safety check failed seven times in a row
(a transient outage, nothing lost); Fable 5.1 took over from the one failing
test and finished the chain. Nothing is committed.

**Fixed, each re-extracted with a per-record diff read.**

- **Merlot on Dealurile Olteniei (the decision).** `augment/fiche_roles.py`
  applies the fiche's MAIN / OTHER split to the RO yield-table records too;
  a yield-table variety the fiche tags MAIN is listed under the principal
  pills with an amber line in all four locales. Four cards: Coteşti, Dealurile
  Olteniei, Drăgăşani, Ştefăneşti.
- **Romanian rosé, not isolated.** `document_unic.colour_styles` reads a
  colour list sharing one noun, the cedilla spellings and the yield table:
  12 cards gained the rosé their text states, 3 caiet cards lost a rosé a
  pink berry had given them. The record diff of the closing build then
  showed Coteşti had lost its Red: its description is a per-variety list and
  the floor had switched off. The reader now reads the link section too
  (sub-sections included); the RO sweep changed Coteşti and Dealurile
  Crişanei and nothing else.
- **Grape identity.** Piros Bakator on its own passport (#905); Castilla's
  Verdoncho, Albillo Dorado and Tinto de la Pámpana Blanca apart from the
  varieties they had merged into, Crujidera into Moravia dulce, the region
  Castilla-La Mancha and a sourced note on «Campo de Calatrava»; Larnaka and
  Lefkosia with Malvasia Lunga back and the synonym pill gone, Μοσχάτο Κύπρου
  its own slug; La Palma's comma-less "Listán Prieto Moscatel negro" split.
- **The 118-card shared-VIVC class**, pair by pair: folds (Nielluccio and
  Prugnolo gentile into Sangiovese on 46 Tuscan and Umbrian and the Corsican
  cards, Inzolia into Ansonica, Rolle into Vermentino, seven Spanish pairs
  per MAPA), own slugs with no bracket, corrected passports (Cariñena gris),
  PT keeps as a country rule, two layout-debris pills folded. 31 VIVC pins
  verified or written on the live passports; the decisions in
  `scripts/_lib/vivc_shared_pills.json`. Closing build: 48 pairs on 29 cards,
  37 `keep`, 11 `review` (queued).
- **Facts.** La Palma's two wrong facts and Dunavska ravnina's missing
  Gergana fact through feedback sidecars and run `phaseH-fix-2026-10-25`
  ($0.34); the re-grade then found a third La Palma fact — "tea barrels … 20
  days to several years", a Wikipedia figure the pliego caps at six months —
  fixed the same way under `phaseH-fix3-2026-10-25` (14 facts, gate 14 / 14
  with 4 rewrites, back-check 2 fixes, audit clean; the 1505 bullet keeps its
  "se cree que"). Castilla's narrowed limestone claim through the first run,
  then a synchronous second pass (`phaseH-fix2-2026-10-25`, cents) — its product
  sub-section stays empty by structure: the lien writes every product
  statement as a consequence of a natural factor, so the product bullets
  restate the natural-factor quotes and the dedupe removes them (twice). The
  three product statements survive inside the natural-factor bullets. The ES
  `--only` is a substring: `--only castilla` also re-extracted Castilla y
  León, rolled back from the same run.
- **Two false alarms corrected in the tools, not the data.** The 47
  "untranslated" flags were exonyms already in the target form, place names
  inside longer names, quoted titles and glossed terms: the detector exempts
  those classes (320 → 120 pairs, every dropped row read). The two Slovenian
  NEWER-UPSTREAM verdicts: the freshness probe now recognises the document
  the build holds (all 17 SI rows current).
- **An incident, repaired.** A full 02g run wrote a miss over 17 resolved
  VIVC slugs (Blaufränkisch queried as "blauer limberger", Catarratto, the
  Greek and Cypriot natives by their Greek spelling); all 17 restored and
  pinned, and a miss no longer replaces a resolution. The pin test then
  caught the one lexicon gap left: `malvasia-aromatica` had no colour entry.

**Left, and why.** Dunavska ravnina's natural factors: the OJ document's §8
describes none (0 hits for "Данни за географския район"), the register fiche's
link does — a source change for BG 02d, queued. Bela krajina keeps its
pravilnik split by decision. The 11 shared-VIVC `review` pairs, the four
standing gates (the family-word surfaces, 48 ambiguous synonyms — four made
visible by today's folds —, 120 untranslated pairs, 122 Bétard-delta records)
are the queue rows.

**Measurements.** Two full stage-04 builds; the cumulative record diff against
the pre-fix build is 220 records (130 principal rosters, 81 accessory, 15
styles, 4 source lists, 3 fact sets, 1 region), every row read against a
documented decision. `audit_terroir_facts --strict` 0 failures on the re-run
records; `audit_vivc_coverage --strict`, `audit_grape_identity --strict`,
`audit_dup_keys` clean.

**The cards, before and after.** The seven cards that still carried a
misleading finding after phase H were re-graded by the same judge (Opus 5.5,
batch, $0.57; Lefkosia graded for the first time): misleading findings 14 →
3, cards with one 7 → 2; six cards better, Bela krajina counted "worse" by
one new finding. Castilla, Dunavska ravnina, Larnaka, Lefkosia, Balatonmelléki
and Dealurile Olteniei read `trust` with no misleading finding. The three
left: La Palma's tea-barrel figure (fixed above, after the re-grade); Bela
krajina's roles (the pravilnik split, kept by decision) and its Sparkling pill,
which the judge calls an extra but is the register fiche's own category list
("4. Peneče vino", cited on the card) — a judgement call, kept. Report:
`tmp/validation/cards-phaseH-fix-8.{json,md}`, paired against
`cards-phaseH-23.json`. One style blemish the re-grade surfaced without
flagging it: three EN bullets corpus-wide open on "According to the
specification" (La Palma, Arabako Txakolina, Manzanilla de Sanlúcar) — the
style rule says never to mention the document; queued for the normaliser.

**Release gate** (`validate_release.py --quick`, three builds today): every
check passes except the four standing queues phase H already listed —
grape-surfaces (the family words the lexicon folds onto one member:
Canaiolo, Malvasia Nera, Refosco nostrano), ambiguous synonyms 46 → 48
(four surfaces today's folds made visible: Subirat → Alarije, Malvasia rosa
→ Malvasia di Schierano, Moscatel-Galego → Moscatel Galego Branco, Mostosa →
Trbljan; Nerello → Frappato left the list), untranslated 320 → 120, Bétard
delta 122 (unchanged). pytest 1,691 pass.

**Cost.** Batch ledger today: $0.34 (the first fix run) + $0.57 (the 8-card
re-grade) = $0.91; the synchronous Castilla and La Palma passes (02d, gate,
02e, back-check) are not in the ledger, ≈ $0.40. Programme total since
2026-10-23 ≈ $41–43.

## Addendum — document self-references (2026-10-25, Opus 5.5)

The phase H re-grade had noted three EN bullets opening on "According to the
specification". **Not isolated.** The sweep found 143 bullets in 30 records
naming their own document or Wikipedia at the opening, the end or in
brackets (32 source, 111 translated), against the 4 + 11 first counted: the
four "Según el pliego, …" / "Secondo il disciplinare, …" leads (Vin Santo
del Chianti Classico's EN and NL carried the lead too, as "According to the
production specification" and "Volgens het productiereglement"); the MASAF
template's "Il disciplinare afferma / indica / stabilisce che …" in 21 IT
records, rendered by 02e as "The production regulations state that …",
"Le cahier des charges indique que …", "Het productiereglement stelt dat
…"; "According to / Selon / Volgens Wikipedia" leads; trailing "… selon
Wikipédia", "…, come attesta il disciplinare". The cause is the
do-not-claim escape "unless the source states it explicitly", answered by
naming the source; the gate grades the claim, which is supported, and
nothing looked for the reference. The Greek "Σύμφωνα με …" bullets
(Theopompus, a chrysobull, the Tripoli station) are the source's own
attributions and are untouched, as is the disciplinare as an object of
history ("fu approvato nel 1967").

**Fixed, run `docref-2026-10-25`.** A deterministic cut in
`terroir_normalize` (02d write time, the post-pass, stage-04 render): the
reference goes, the claim stays, re-capitalised. A Dutch or German fronted
reference is not cut — the finite verb would come first — and went back to
02e: 24 Dutch caches re-translated (Sonnet 5.5) and back-checked (Opus 5.5:
29 fixes on other bullets of the fresh translations — exonyms, het/de
agreement, "cretaceo" ≠ "krijtachtig" —, none on the cut bullets). Two
source bullets naming Wikipedia the cut cannot reach were re-gated one
record each under the gate's new rewrite case: oolde's Dutch "Volgens
Wikipedia bevat de bodem …" (the gate also narrowed #4 to Twente and moved
#10 to human factors) and neszmely's Hungarian mid-sentence "a Wikipedia
szerint", whose fresh Dutch translation had fronted it; both re-translated
and back-checked (neszmely FR: "deux tiers" corrected to "un tiers").
`audit_terroir_facts --strict`: `document_reference` 143 → 0, all checks 0;
`translation_stale` 0. The gate refuses a rewrite that adds a reference;
the feedback escape now ends "(then state it plainly, without naming the
source)". Two neighbours found on the way: the Latinisation turned "l'α-
terpinéol" into "l'a-terpinéol" (its chemical-prefix guard missed an elided
article — fixed), and the untranslated detector counted α-terpineol as
residual script where the audit does not (fixed; 3 La Palma pairs).

**Measurements.** Full stage-04 build; record diff against
`records-after-phaseH-fix3.json`: 54 records, `facts_sha` only — 28
parents and 26 sub-denominations inheriting their bullets (Bardolino's
three sottozone, Cognac's seven crus, Monthélie's sixteen premiers crus).
Rendered EN bullets: every change is the cut, except the re-gated and
re-translated oolde and neszmely (24 rewordings, read). Every rendered
panel: 0 strict references. `validate_release --quick`: only the four
standing queues fail — grape-surfaces, ambiguous synonyms 48, untranslated
119 (120 at phase H close + 3 α-terpineol pairs from `phaseH-fix3`, − those
3 as false positives, − neszmely nl), Bétard delta 122. Model spend ≈ $1
(synchronous runs, estimated from today's batch rows; no batch ledger row).

**Left.** `document_reference_mid`, report-only: 246 bullets in 60 records
where the reference needs rewording — mid-sentence, the document as the
agent of a verb ("Il disciplinare descrive i vini come …"), and the
Wikipedia comparisons ("…, mientras que Wikipedia los describe como …"),
some of which set two figures side by side. The gate's rewrite case is the
tool; a scoped re-gate of the 58 source records is queued in CURATOR_TODO.

### Follow-up (2026-10-25) — the report-only references, re-gated

Boris asked for the 246 `document_reference_mid` bullets to be done. **Not
isolated either:** the sweep before the run added 9 IT records citing the
disciplinare as the setter of a rule ("le tipologie previste dal
disciplinare", "entro i limiti del disciplinare"), the Portuguese "definidos
no caderno de especificações", the Swiss "prévus par le règlement" and a
Slovak "podľa Wikipédie" the detector had missed (its Wikipedia pattern took
no inflection) — 69 records, all added to the report check. The gate's
rewrite case was made specific before the run: a rule stays a rule, stated
without the document; where a bullet sets the source text beside Wikipedia,
the source's statement is kept and Wikipedia's only where it adds a detail
that does not contradict it, neither named, the source's figure where the two
differ.

**Run `docref-mid-2026-10-25`.** Gate on the 69 records (Opus 5.5 batch,
$2.97): 76 references removed — Yecla keeps its 300 mm and loses
Wikipedia's 350, Clos des Lambrays its 260–350 m against 250, Bonarda and
Tarragona fold Wikipedia's compatible detail in unnamed —, 65 further
rewrites, the gate doing its job on the re-read records (dropped hedges
restored: "fundamentalmente", "souvent", "tipicamente"; Rangen's 850 mm read
as the rainfall, not the average; Monthélie's cooler mesoclimate credited to
the combe; Osco's geology narrowed to Molise), 4 sub-section moves, every one
read. Then 238 translation caches re-translated (Sonnet 5.5, $1.41; one
reply that failed the stage's count check redone synchronously) and
back-checked (Opus 5.5, $3.19: 199 fixes in 2,579 bullets — tipologia,
generoso / généreux, sapido, appellation left in French, exonyms, het/de).
Run total $7.57 at the batch rate, above the $5 estimate.

**Vaud, rolled back out of the run.** The gate dropped 5 of its 7 facts —
the Bonvillars, Chablais, Côtes de l'Orbe, La Côte and Vully sub-region
bullets — as "a sub-zone, not this appellation". On the Vaud card they are
right; the defect was on its 8 sub-appellation cards, which showed every
sibling's bullet, because stage 04's sibling filter matched a sibling only
when the bullet *opened* on its name and these open "L'appellation X" / "Le
vignoble de X". The filter now reads a name behind that wrapper and folds
hyphens ("Côtes-de-l'Orbe" against "Côtes de l'Orbe"); the test is shared
with the dedupe post-pass. Corpus sweep: Vaud's 8 cards only. Vaud keeps its
"aux minima prévus par le règlement" — the 2 report rows left — and the Vully
bullet still shows on its children: Vully is cross-cantonal and no Vaud child,
so no sibling.

**Measurements.** `document_reference_mid` 246 → 2, `meta_text` 186 → 18,
`audit_terroir_facts --strict` 0. Record diff against
`records-after-docref.json`: 141 records, fact fields only — the 68 re-gated
records, 65 sub-denominations inheriting their bullets, the 8 Vaud cards
(7 → 3 or 4 facts: the canton-wide bullets and their own). `validate_release
--quick`: only the four standing queues fail; untranslated 119 → 121, both new
pairs one bullet — Wien's EN and FR now say "the Wien wine-growing region" /
"le vignoble de Wien" where the earlier translation had Vienna / Vienne; two
re-translations and the back-check keep "Wien" as the appellation's name, the
detector reads a region-named record as a place. Left as a judgement call.

## Addendum 2026-10-25 — listing under every branch: cantons, regions

**Wien re-translated.** The exonym rule of the 02e prompt now covers the wine
region named after the city ("Weinbaugebiet Wien" → "the Vienna wine-growing
region"), verbatim only as the appellation's name; the EN and FR caches were
re-translated and the detector's two new pairs are gone.

**Vully and Zürichsee: one record, listed under each canton (`co_parents`).**
Vully (FR / VD) had sat under Fribourg only — Vaud never counted it, and
Vaud's Vully bullet showed on every Vaud card; Zürichsee (SZ / ZH) was
Schwyz's sub-denomination and drew Schwyz alone. Both are now nobody's
sub-denomination, listed under the cantonal AOC of each canton that has one,
with an "Also part of" line, inheriting nothing (Boris: option 2, and the
same rule wherever the pattern recurs — the Maasvallei rule one level down).
Zürichsee's area is each canton's own ruling: the seven ZH Bezirke of the
Strickhof Verfügung of 26 June 2020 Ziff. III and the ten SZ communes of the
Allgemeinverfügung of 28 July 2025 Ziff. 2.1 — 76 communes, 0.39 × the
two-canton area it was drawn as.

**The same pattern one level up: 63 records listed under every region they
span (`region_aliases`).** A record whose area spans several regions of its
country's sidebar is listed under each and names them all on its meta line
("Lombardia, Veneto"), one "All appellations in …" link each; it keeps its
primary region for the title, the description and JSON-LD, and its
sub-denominations stay in their own region. Three sources: a table citing a
verbatim quote of each record's area text (24 records — IT 15, found by the
provinces each text names: Garda, Lugana, San Martino della Battaglia,
Valdadige, Terradeiforti, Delle Venezie, Trevenezie, Prosecco, Vigneti delle
Dolomiti, Colli di Luni, Orvieto, Lison, Lison-Pramaggiore, Alto Livenza,
Vallagarina; ES Cava — which had no region and sat in "no region" — Rioja,
Jumilla, Ribera del Queiles; AT Weinland, Bergland; BG the two PGIs; CY
Pitsilia), the umbrella PGIs' member tables (19: the DE Landweine under their
Anbaugebiete, HU Dunántúli and Zemplén, SK Slovenská, MT Maltese Islands) and,
for France, the wine regions whose own AOCs share communes with the record's
INAO aire (20: Atlantique, Méditerranée, Pays d'Oc, Terres du Midi, the Gard
IGPs, Cévennes, Languedoc, the three Rivesaltes AOCs, the Bourgogne regionals
under Beaujolais, Beaujolais under Bourgogne, Comtés Rhodaniens). The query
core's region filter and facets read every region (`filter({region:
'Veneto'})` returns Garda), so the MCP server answers the same once
redeployed. `scripts/sweep_region_aliases.py`, the geometric detector: 85
candidates accepted, 30 rejected with their reason (Bétard overlaps in DE /
HU / SI / BG, a neighbour's filing, Clairette de Bellegarde's one shared
commune), 2 new — Taubertäler, queued until a text names its Bereiche.

Not isolated, and not only listings: the sweep found five records filed in
the wrong region, fixed at the source — Debrői hárslevelű (five Heves
villages of the Eger district) under Tokaj, Monor (a Kunság municipality)
under Felső-Magyarország, and Nizza, Garda Colli Mantovani and Terre
Siciliane under "Italia" for want of a regione. Also found and queued: five
IT interregional polygons drawn from one regional geoportal that miss their
other region's part (Prosecco, Delle Venezie, Vigneti delle Dolomiti,
Valdadige, Colli di Luni), Bayerischer Bodensee-Landwein drawn as the whole
Baden Anbaugebiet by its member table, and Rioja Alavesa carrying Rioja's
region.

**`audit_geometry_overlaps.py --strict` passes again.** The one SUSPICIOUS
sliver, Côtes du Lot / Périgord, is Salviac, in both aires of the INAO CSV;
its whitelist entry had been keyed on the Rocamadour DGC and is re-keyed to
the parent, and the Agenais / Côtes du Lot entry is dropped (Fumel left Côtes
du Lot's polygon with its 2026-10-04 aire change). `validate_release --quick`
had not run the geometry audits, which is why the failure went unseen.

**Record diff** against `records-after-coparents.json`: 6 records — the five
regions above and Zürichsee's geometry. The aliases themselves are a startup
field the diff does not compare.
