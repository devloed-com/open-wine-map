# Visitor feedback triage — 2026-10-24

Queue: `scripts/feedback_report.py --range 2026-10-13,2026-10-24`. New since
the 2026-10-22 triage (Znojmo, Piemonte/Albarossa): 3 flags, 1 of them
retracted, no note.

| flagged | aspect | locale · view | verdict |
|---|---|---|---|
| Piemonte, 2026-10-23 15:00 | grapes | en · zone z7.2 | real; already fixed in the local build, not deployed |
| Roero, 2026-10-22 21:00 | grapes | en · zone z7.2 | real (label noise); already fixed in the local build, not deployed. A second defect found on the card and fixed today |
| Tirol, 2026-10-23 10:00, retracted | boundary | es · zone z6.9 | no defect |

## Piemonte — the superseded single document

Production shows 18 varieties from the single document of
**C 435/2018**. The newest publication, **C 91/2020**, lists 26 in § 7.
The live card is missing Nebbiolo, Cabernet Sauvignon, Merlot, Viognier,
Croatina, Riesling italico, Riesling renano, Carmenère and Bussanello.

- **Failure mode:** the stage-01 rule that took the first OJ C eAmbrosia lists.
- **Isolated or broader:** broader. Phase F (2026-10-24) replaced it with
  the newest OJ C per record in every EUR-Lex country. 45 records had been
  left on a superseded document.
- **State:** the local build reads C 91/2020: 26 varieties, plus Sauvignon
  as an accessory from § 4. It ships with the next deploy.

## Roero — grapes

The roster matches § 7 (Arneis, Nebbiolo). The live pills read
"Arneis B. (Arneis)" and "Nebbiolo N. (Nebbiolo)": a VIVC bracket that only
repeats the name. The validator found nothing misleading on the card.

- **Failure mode:** the bracket fold did not remove the OIV colour code
  written with a period.
- **Isolated or broader:** broader, 1,288 pills. Fixed on 2026-10-23; the
  local build drops the brackets, production still shows them.

### Found on the same card: boilerplate in the crus list

Roero's "additional geographical units" chip list had one entry:
*Nella legislazione unionale*. That is the value of the 2024/1143 template's
"Quadro di riferimento giuridico" field, not a place name.

- **Isolated or broader:** broader. 8 of the 16 records that have chips
  carried boilerplate, in three forms:
  - **The template field value** taken as a name: Roero, Etna, Trebbiano
    d'Abruzzo, Montecucco Sangiovese (their only entry), Cerasuolo
    d'Abruzzo and Alto Adige (one entry among real ones). Etna's junk entry
    also blocked the stage-04 backfill, so its MASAF contrade never reached
    the card.
  - **A dash-bulleted MASAF annex read as one entry:** "- Isola del Giglio -
    Monte Argentario - …" (Ansonica Costa dell'Argentario, Sovana).
  - **A sentence glued to the last cru:** "Vicenziana. Le suddette menzioni
    geografiche aggiuntive" (Barbaresco), "Zuncai. …" (Barolo).
- **Fix:** in `scripts/_lib/it/menzione.py`:
  - A trigger whose colon is preceded by a template field label is a
    condition title, not a list.
  - A trigger whose sentence ends before the colon introduces nothing.
  - A comma list ends with its sentence ("art. 5" is not a sentence end).
  - A dash-bulleted annex is read across sub-headers, blank lines and page
    numbers, but only when the bullets follow the colon directly.
- **Re-extraction:** the old and new harvester were compared over all 523
  IT documento-unico texts and the 522 MASAF PDFs (the diff found two
  regressions, Etna and the Abruzzo section titles, both fixed before
  re-extracting). Six records were re-extracted with `it/02 --only` and
  seven sidecars with `02f --slug --include-nonstub`. A whole-file diff
  shows only `menzioni` changed.
- **Effect on the cards:**
  - Roero, Trebbiano d'Abruzzo and Montecucco lose the junk chip.
  - Etna gains its 69 contrade.
  - Sovana gains 70 chips, Monteregio di Massa Marittima 26, Riviera del
    Garda Classico 10, Ansonica 9.
  - Barbaresco and Barolo keep 66 and 169 crus with clean names.
- **Tests:** six cases in `tests/test_it_parser.py`.

## Tirol — boundary (retracted)

The single document reads "Die Ursprungsbezeichnung „Tirol" umfasst das
gesamte Bundesland Tirol". The polygon is the union of the Bundesland's
277 Gemeinden (`gisco-bundesland-union`), so there is no defect.

## Validator findings left open

These come from `audit_cards_llm.py --only roero --only piemonte`
(report `tmp/validation/cards-2026-10-24T192035.md`).

- **Piemonte's Sauvignon as accessory** is graded *misleads*. § 4 names
  "Piemonte" Sauvignon as a varietal type (≥ 85 %). The MASAF Article 1
  reader makes the same kind of variety principal, while the § 4 reader
  (decided "accessory" on 2026-10-24) does not. This needs a decision;
  nothing was changed.
- **Piemonte's UGA "Marengo"** (Cortese frizzante / spumante) is not on the
  card.
- **Roero's terroir facts:** one etymology hedge and one "anche" were
  dropped, and one bullet is misfiled. These are defective, not misleading,
  and become a feedback sidecar at the next re-run.
- **The MASAF disciplinare is not in the Sources** of non-stub IT cards.
  This was already queued (validators, 2026-10-23).
