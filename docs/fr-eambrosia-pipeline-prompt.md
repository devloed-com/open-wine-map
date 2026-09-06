# Task brief — source the French cahiers des charges from the eAmbrosia EU GI register

## Objective

Give the French pipeline a second, self-service source for the *cahier des
charges*: the eAmbrosia EU GI register attachment endpoint. Today FR fetches
exclusively from BO Agri, with a long tail that needs hand-curated URLs, a
Légifrance cookie-injection fetcher, and OCR over professional-org mirrors.
The register serves the **same INAO cahier PDF** with none of that.

This is **plumbing, not a data fix**. FR coverage is already complete
(1,540 records, 0 stubs). The win is retiring fragile fetch paths and
making future FR gaps self-service. Treat regression risk on the 1,540
working records as the primary cost.

## Established facts — verified 2026-08-29, do not re-litigate

Spike run against the live register. Reproduce only if something looks wrong.

| finding | value |
|---|---|
| FR wine GIs in the register (`countryId=fr`, `qualityProductType=Wine`) | **458** |
| carry the full national cahier (`productSpecifications[0].uri`) | **85 %** (n=80 random sample: 68 cahier / 9 single-doc-only / 3 neither) |
| attachment filenames | literally `CDC_Batard-Montrachet.pdf`, `CDC IGP Haute-Marne.pdf` — the INAO cahier, not the thinner EU single document |
| parses with the existing FR extractor | **yes**, unchanged `scripts/02_extract_cahiers.py` |
| AOC round-trip (Bâtard-Montrachet, `PDO-FR-A0571`) | 12 roman sections; `lien` text **byte-identical** to the in-build record (8,424 chars, sha `9bdd4182…`) |
| IGP round-trip (Puy-de-Dôme, `PGI-FR-A1211`) | 8 sections; `lien` **byte-identical** to in-build (5,714 chars, sha `7a3e6a6f…`) |
| the 9 AOCs that today need CAVB/FGVB mirrors + Type-1C OCR | **7 / 9** have a register cahier |

The byte-identical result is the load-bearing fact: for these records the
register is the *same document already in the build*, so a source swap is
content-neutral, not a re-extraction from a different vintage.

Known negatives from the same spike:
- **Musigny** (`PDO-FR-A0582`) — single-doc only; `productSpecifications` is
  a bare `Ares(2013)3755890` reference and `fetch_attachment` returns False.
- **IGP Lorraine** (`PGI-FR-02815`) — neither attachment.
- **Côte de Nuits-Villages** and **Muscat de Frontignan** — no register entry
  under their exact SIQO name. Name matching, not absence: see below.

## What already exists — reuse, do not rebuild

- `scripts/_lib/eambrosia_register.py` — the whole resolver.
  `load_id_map()` (cached at `raw/eambrosia-register/filenumber-id-map.json`,
  3,964 entries), `gi_detail()`, `attachment_refs()` → returns `cahier_uri`
  **and** `single_doc_uri`, `fetch_attachment()` (handles the browser-UA gate
  and HTTP 202-with-PDF-body).
- `scripts/_lib/fiche_technique.py` — parser for the single document, if you
  ever need the 11 % fallback tier.
- `scripts/02_extract_cahiers.py` — `extract_sections` (AOC roman-numeral),
  `extract_igp_sections`, `route_sections`, `candidate_keys()`.
- `scripts/01_scrape_cahiers.py` — `_process_app` walks `pdf_urls` in order
  via `_download_first_pdf`; `_prepend_override_urls` puts curator URLs first.

Endpoint gotchas already encoded in the lib (do not rediscover): the internal
`id` is **not** derivable from `giIdentifier`; the detail path has **no
`/v1/`**; the attachment path **does**; an explicit `Accept: application/pdf`
trips the anti-bot gate.

## The one genuinely new component

**A name → `fileNumber` resolver for FR.** France is INAO-sourced and carries
no `id_eambrosia`, so unlike every other country there is no join key.

- Match SIQO `name` against register `protectedName`, casefolded and
  accent-stripped.
- Exact match alone is **not sufficient** — it missed 2 of 9 spot-checks.
  Route through the existing `candidate_keys()`, which already splits on
  `" ou "`, `" et "`, and commas (`Muscat de Frontignan` is a
  `X ou Y ou Z` case).
- The mapping must be **auditable and pinnable**: emit a resolved map plus an
  unresolved queue, and honour a curator override file for the residue. Do
  not silently fuzzy-match — a wrong bind attaches the wrong cahier to an
  appellation, which is worse than a gap.
- Sub-denominations (1,074 of the 1,540) have no register entry of their own;
  they inherit the parent cahier, as they do today. Resolve at parent level
  only (466 parents vs 458 register GIs).

## Constraints

1. **Additive first.** Append the register URL as a final tier in
   `pdf_urls`, after BO Agri and the curator overrides. Do not reorder or
   remove existing sources in this change. The 466 current canonical
   resolutions must stay canonical.
2. **Shadow before swap.** Land a mode that fetches and extracts from the
   register *without* writing into `raw/inao/cahier-extracted/`, and report
   per-appellation whether the register text matches the in-build text. Ship
   the comparison before shipping the behaviour change.
3. **Public sources only** — satisfied; the register is the EU's own.
   Attribute it as such.
4. **Reproducibility + no-op-on-rerun.** Cache attachments by sha256, record
   full provenance (`register_file_number`, attachment uri, sha256,
   `fetched_at`) in the manifest. A second run with no upstream change must
   be a cache hit.
5. **Polite client.** The 202 + UA gate is deliberate anti-bot. Rate-limit,
   reuse the cached id map (one ~4 MB POST), never parallel-hammer.
6. **No comments unless the *why* is non-obvious**; ruff line length 100;
   logs to stderr with per-appellation progress.

## Verification protocol — mandatory

A pre-change baseline exists at
`/Users/boris/playground/owm-fr-baseline-2026-08-29/` (git HEAD `7e814cd`,
clean tree): full APFS clones of `raw/` and `wiki/`, plus SHA-256 manifests
of 39,334 files across 10 surfaces. See its `BASELINE.md`.

    /Users/boris/playground/owm-fr-baseline-2026-08-29/compare.sh

Exit 0 means every surface is byte-identical. It was verified green at
capture time, so any divergence it reports is caused by your change.

- While the change is additive/shadow-only, `compare.sh` **must stay exit 0**.
- Once the register tier can actually win a resolution, every diff must be
  explained per record — "the extractor ran again" is not an explanation.
  Expect `fr-cahier-extracted` churn to be **zero** for records whose BO Agri
  URL still resolves, since the register is a later tier.
- Stage 04 failures are silent (a country just vanishes from the map).
  `wiki-data`, `wiki-entity-pages` and `wiki-map-data` diffs are the tripwire
  — do not dismiss them as noise.

## Definition of done

- A resolved FR name → `fileNumber` map, an unresolved queue, and a curator
  override file for pinning the residue.
- Register tier wired into stage 01 as the last fallback, with provenance in
  the manifest.
- Shadow report over all 466 parents: how many resolve, how many fetch a
  cahier, and for how many the extracted `lien_au_terroir` is byte-identical
  to the current build.
- `compare.sh` either exit 0, or every diff explained record by record.
- `CLAUDE.md` (FR pipeline section + scripts contract table) and
  `CURATOR_TODO.md` updated. The cross-country Phase-2 retrofit item in
  `CURATOR_TODO.md` is the parent of this work — reconcile it, do not
  duplicate it.

## Out of scope

- Removing BO Agri, `01b_solve_legifrance.py`, or the OCR mirror path. Those
  come out only after the shadow report proves the register covers them —
  a later, separate change.
- Other countries. The cross-country retrofit is tracked separately; this
  brief is FR only.
- The 02d IGP-slicing bug (`Spécificité de la zone géographique` headings not
  recognised, so IGP terroir facts land in one bucket). Real, confirmed
  during the spike, tracked in `CURATOR_TODO.md` — but a different fix.

## Resolve early

- The 15 % without a cahier: fall back to the register **single document**
  (thinner, different template — needs `fiche_technique.py` and an FR keyword
  table, which `scripts/_lib/be/document.py` already has for the Walloon
  wines), or leave them on BO Agri? Cheapest answer is probably: leave them.
- Cahier **vintage**: the two records checked were byte-identical, but that
  is n=2. The shadow report should quantify this across all 466 before anyone
  argues for making the register a *primary* source.
