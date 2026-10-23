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
