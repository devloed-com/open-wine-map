# Visitor feedback triage — 2026-11-08

Queue: `scripts/feedback_report.py --range 30d`, rows since the 2026-11-03
triage (`--range 2026-11-02,2026-11-08`): 10 flags on 5 cards, 6 retracted,
no note, no name offered for credit, no e-mail-link click. The live site ran
the 2026-11-07 build; the three flagged cards' panel payloads were
byte-identical live and local, so the local build is the surface checked.

| flagged | aspect | locale · view | verdict |
|---|---|---|---|
| Bullas, 2026-11-03 00:00 | name, facts, grapes | en · zone z8.4 | grapes wrong (roles); name and facts correct; styles wrong too (validator) |
| Eisenberg, 2026-11-05 12:00, retracted | boundary | en · zone z7.6 | no defect found |
| Monteregio di Massa Marittima, 2026-11-05 12:00, retracted | boundary | en · zone z8.9 | no defect found |
| Kremstal, 2026-11-07 18:00, all four aspects, all retracted | sources, facts, grapes, name | en · zone z8.2 | card matches its single document; the roster question is Wachau's |
| Wachau, 2026-11-07 18:00 | grapes | en · zone z8.2 | card matches its single document; the national specification lists 17 varieties — queued |

The card validator (`audit_cards_llm.py --only wachau --only bullas --only
kremstal --locale en`, Opus, $0.37) graded Wachau and Kremstal "trust" and
Bullas "do-not-trust" with three verified misleading findings.

## Bullas — grapes, styles (es DOP, MAPA national-format pliego)

**Roles.** The card showed all 15 varieties as principal. The pliego's
variety section lists the reds and whites and then says: "De estas variedades
se considera como principal la Monastrell en tintas y la Macabeo entre las
blancas." The ES roster reader read the lists under the default role and
never read the sentence.

Failure mode: *a principal designation the role reader does not read*, three
shapes, six records:

- the sentence after the roster — Bullas; Lebrija ("De ellas son
  consideradas principales Palomino y Palomino Fino"); Málaga ("de las que se
  consideran preferentes «Pero Ximén» y las «Moscateles»"); Valle del
  Miño-Ourense ("… variedades consideradas como principales: - Blancas: … -
  Tintas: …", the list form);
- the singular header "- Variedad principal: Tempranillo." — the role regex
  wrote `principales?`, which never matches "principal", so Valtiendas'
  Tempranillo kept the accessory role of the "Variedades autorizadas" line
  before it;
- "Variedades secundarias:" — not a role word, so Castilla y León's 40
  secondary varieties were principal.

Fix (`scripts/es/02_extract_pliegos.py`): `principal(?:es)?` and
`secundarias?` in the role vocabulary; `_apply_principal_designation` after
the walk — the varieties the sentence names stay principal (longest name
consumed first, a plural family word "Moscateles" naming every Moscatel), the
rest become accessory; nothing moves when the roster carries an explicit
accessory list, or the sentence names none or all. Three reader defects the
tests exposed on the way: a « name wrapped over a line break ("«Pero ⏎ Ximén»"
had been a pill "Ximén"), a roster token that runs into the next sentence
("… y Verdejo. Variedades secundarias:" lost Verdejo), and an " o "
alternative that binds another cultivar ("Picapoll Blanco o Extra" — EXTRA is
a VIVC synonym of Clairette). Lebrija's Sauvignon Blanc, lost before the
sentence split, is back.

**Styles.** The card listed red, rosé, white and the sugar levels; the pliego
says "Los tipos de los vinos amparados … son los siguientes: blancos, rosados,
tintos, de licor y espumosos". The style reader matched the colours of that
list and needed the word "vino" before a type.

Failure mode: *a wine type the pliego states once, without "vino"*, 13 ES
records in four shapes: the type-list sentence (Bullas, Murcia), a dash- or
Wingdings-bulleted "- Vino de licor" line (El Hierro, Ycoden-Daute-Isora,
Castelló, Valdejalón), the EU category cited by number or listed ("a la
categoría 3 "Vino de licor"" — Castilla y León; "de la categoría 5:
espumosos de calidad" — Tharsys; "Categorías de productos vitícolas: vino,
vino de licor, …" — Málaga), and a type as a capitals heading of the link
section ("VINO DE LICOR", Calatayud, Campo de Borja). All four are read now
(`_type_statement_styles`); every new pill was checked against the category
list or type header of its own text.

## The EUR-Lex slicer — 85 of the 90 ES single documents

Four of the thirteen style cases (Calatayud, Campo de Borja, Valencia, Islas
Canarias) had a deeper cause. The single document nests one numbered header
per wine type inside its description ("1. Vino blanco … 5. Vino espumoso
aromático de calidad blanco … 7. Vino blanco, rosado y tinto etiquetado con
la mención «Petit Valencia»", Valencia) and lists the categories of section 3
the same way; the ES slicer read headers last-wins, so the nested headers
shadowed the real sections. Sweep: 85 of the 90 EUR-Lex ES records had no
categories section; Valencia's sparkling type sat under a "5" that "5.
Prácticas vitivinícolas" overwrote; Calatayud's titles began with "Práctica
de cultivo"; Montsant's `description` role was its link text, which is where
its eleven "section-4 varieties" of 2026-10-24 had come from.

Fix: `_template_headers` — a top-level header is a section when its title is
one of the template's (never one opening on "vino") and its number is higher
than the last section's; a sub-number belongs to the open section; every
other header stays in the body, where the style reader reads the numbered
type lines as the titles they were ("4. Rías Baixas Tinto", "3. Vinos
generosos (categoría 1)"). The HU / BG / MT readers have had the monotonic
rule since their first build.

Full ES run against a snapshot of the records (`diff_es_records.py`): 91
records changed, no section shorter than before, 77 records gained their
name section, 46 style lists grew (29 parents; the subzonas follow their
parents), 8 rosters changed roles or membership — Bullas (2 principal, 13
accessory), Castilla y León (9 + 40), Lebrija (2 + 8), Málaga (4 + 3), Valle
del Miño-Ourense (12 + 2), Valtiendas (1 + 4), Tarragona (+ Garnacha and
Trepat as section-4 varietal types, disclosed on the card), Montsant (the
eleven link-prose varieties gone; the INCAVI pliego sidecar, recomputed,
gives twelve as accessories). `tests/test_es_roles_and_types.py` (14 tests);
the ES, phase-C and section-varieties suites pass.

## Wachau — grapes (at DOP), Kremstal — everything, retracted

The validator found the Wachau card consistent with its single document (OJ C
68/2023): § 7 "Wichtigste Keltertraubensorten" names Grüner Veltliner and
Riesling, which the card shows. The regulator's fuller statement is the BML
Produktspezifikation the corrigendum C/2025/90060 of 1 August 2025 links as
the specification in force: its § f calls the two the "Hauptsorten" and allows
a Wachau Gebietswein from 17 varieties (adding Weißer and Grauer Burgunder,
Chardonnay, Neuburger, Muskateller, Sauvignon blanc, Traminer, Frühroter and
Roter Veltliner, Müller-Thurgau, Muskat Ottonel, Gemischter Satz, Blauer
Burgunder, St. Laurent, Zweigelt), an Ortswein from nine, a Riedenwein from
the two. Failure mode: *Austria's EU single documents list the main varieties
only*; 17 of 30 AT cards carry two grapes or fewer. Every Produktspezifikation
is linked from one BML page, same lettered template — an AT national-spec
layer, queued in CURATOR_TODO with the recipe. Not a card error: the card
states what its cited document states.

Kremstal, flagged on all four aspects and retracted within the hour by the
same visitor, grades "trust" (one cosmetic misfiled bullet). Wachau's facts:
the medieval-terraces statement appears twice (natural factors and the only
human-factors bullet); the dedupe pass keeps both — queued for a scoped
re-gate.

## Eisenberg, Monteregio di Massa Marittima — boundary, retracted

A retracted flag is not proof of no defect. Eisenberg draws the Bezirke
Oberwart, Güssing and Jennersdorf its single document names (72 Gemeinden,
about 1,460 km² against the Bezirke's 1,470); Monteregio is the Tuscany
geoportal's production zone (about 800 km²). `audit_geometry_vs_text.py`
buckets them ABOVE-COMMUNE and NO-TEXT; nothing to fix.

## Verification after the rebuild

- Bullas re-graded by the card validator (en, Opus): 0 findings, from
  "do-not-trust" with 3 verified misleading. The card reads Monastrell and
  Macabeo principal, 13 accessories, and carries Fortified / Liqueur wine and
  Sparkling beside the colours and sugar levels.
- Málaga: one pill "Pero Ximén (Pedro Ximenez)" where the card had shown a
  bogus "Ximén" next to "Pedro Ximénez"; the three Moscatels principal, Lairén,
  Doradilla and Rome accessory, the pliego's liqueur, overripe and raisin wines
  added.
- Montsant: 5 principal (the single document's § 7 plus the Xarello the
  context pin reads), 12 accessories from the INCAVI pliego sidecar — the ten
  link-prose varieties are back, as accessories, where the regulator lists
  them.
- Valencia: Sparkling, Quality sparkling and Semi-sparkling, from the
  categories section the slicer now keeps; Rías Baixas keeps Red and gains its
  Espumoso; Calatayud goes from "red" alone to its full category list.
- Stage 04: `[grapes]` FLAGGED 0 / INHERIT 0, no STALE override, 2,956
  records. Release gate (`validate_release.py --quick`): the same table as the
  2026-11-07 run — empty-grapes, gi-terms, styles, vivc-pins, grape-brackets,
  dup-keys, terroir-facts, parcellaire-gaps, pytest, about-date and
  shell-snapshot pass; the four report-only strict checks fail with the
  counts they had before (grape-surfaces' family words, 49 ambiguous
  synonyms, 119 untranslated pairs, 122 Bétard-delta flags). Nothing new.

## Changes

- `scripts/es/02_extract_pliegos.py`: role vocabulary, principal-designation
  pass, guillemet wrap, sentence-end token split, " o " alternatives, the
  type-statement style rules, the template-title slicer.
- `tests/test_es_roles_and_types.py` (new).
- ES stage 02 re-run (91 records), Montsant and Tarragona national-pliego
  sidecars recomputed, ES wiki pages and stage 04 rebuilt.
- CURATOR_TODO rows (the 2026-11-08 triage section; the Austria roster row);
  CLAUDE.md Spain paragraph.
- No contributor added (no name offered).
