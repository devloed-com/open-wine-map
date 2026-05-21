# Research task — disciplinare URLs for 15 Italian wine GIs

## Context

I maintain a wine-appellation reference (open-wine-map) built only from
public, licence-clear regulator data. The Italian corpus is 531 wine GIs
from the EU eAmbrosia register. Each wine's production rules come from
either (a) the EU-OJ *documento unico* HTML, or (b) the consolidated
*disciplinare di produzione* PDF that MASAF (Ministero dell'agricoltura)
publishes.

**15 of the 531 IT wines have no usable source document** and currently
render as bare stubs (name in the sidebar, no grapes / no terroir text /
region "Italia"). For each I need a public URL to its consolidated
disciplinare di produzione so the pipeline can extract it.

Two failure modes produced this gap:

- **`not-single-document` (9 wines)** — eAmbrosia carries a EUR-Lex URL
  but it resolves to something other than a documento unico, and the
  wine also got no automatic match in MASAF's bundled-archive index.
- **`no-publication` (6 wines)** — eAmbrosia carries no publication URL
  at all; the wine's MASAF PDF used a non-standard template (no
  `Articolo N` headers) so extraction failed.

## What I need from you

For each of the 15 wines below, find **one** public, licence-clear URL
to the wine's current consolidated *disciplinare di produzione* — a PDF
is strongly preferred (the pipeline parses `pdftotext -layout` output;
it cannot yet parse MASAF detail-page HTML).

Search, in rough priority order:

1. **MASAF** — the disciplinari pages under
   `masaf.gov.it` (the "Qualità → Vini DOP e IGP → Disciplinari"
   area; per-wine detail pages often link a PDF).
2. **Gazzetta Ufficiale** (`gazzettaufficiale.it`) — the Decreto
   Ministeriale that approved or consolidated the disciplinare; the DM
   carries the full disciplinare as an annex.
3. **Regional gazette** — for IGTs the approving act is often a
   regional decree (BUR Veneto, BUR Abruzzo, the Regione Siciliana
   gazette, BUR Lombardia).
4. **Consorzio di tutela** site — many consorzi host the disciplinare
   PDF directly.

A URL qualifies only if the document (a) names the GI exactly,
(b) carries the production rules (at minimum an `Articolo 2` grape-
variety list and an `Articolo 9`-style "legame con l'ambiente
geografico"), and (c) is the *current* version, not a superseded one.
Reject pages that are only news, a register entry, or a modification
decree that amends individual articles without restating the full text.

## The 15 wines

### Bucket A — `not-single-document` (9)

| slug | file number | kind | name | region hint |
|---|---|---|---|---|
| colli-aprutini | PGI-IT-A0884 | IGP | Colli Aprutini | Abruzzo (Teramo) |
| colli-del-sangro | PGI-IT-A0744 | IGP | Colli del Sangro | Abruzzo (Chieti) |
| colline-frentane | PGI-IT-A0745 | IGP | Colline Frentane | Abruzzo (Chieti) |
| colline-pescaresi | PGI-IT-A0887 | IGP | Colline Pescaresi | Abruzzo (Pescara) |
| colline-teatine | PGI-IT-A0891 | IGP | Colline Teatine | Abruzzo (Chieti) |
| del-vastese | PGI-IT-A0893 | IGP | del Vastese (also "Histonium") | Abruzzo (Chieti) |
| salemi | PGI-IT-A0807 | IGP | Salemi | Sicilia (Trapani) |
| terre-di-chieti | PGI-IT-A0901 | IGP | Terre di Chieti | Abruzzo (Chieti) |
| valtenesi | PDO-IT-A1188 | DOP | Valtènesi | Lombardia (Garda bresciano) |

### Bucket B — `no-publication` (6)

| slug | file number | kind | name | region hint |
|---|---|---|---|---|
| colli-trevigiani | PGI-IT-A0518 | IGP | Colli Trevigiani | Veneto (Treviso) |
| conselvano | PGI-IT-A0519 | IGP | Conselvano | Veneto (Padova) |
| gambellara | PDO-IT-A0469 | DOP | Gambellara | Veneto (Vicenza) |
| marca-trevigiana | PGI-IT-A0520 | IGP | Marca Trevigiana | Veneto (Treviso) |
| veneto | PGI-IT-A0521 | IGP | Veneto | Veneto (region-wide) |
| veneto-orientale | PGI-IT-A0522 | IGP | Veneto Orientale | Veneto (Venezia/Treviso) |

## Output format

Return a JSON object ready to merge into
`raw/it/masaf-disciplinari/manual_overrides.json`, keyed by slug:

```json
{
  "gambellara": {
    "pdf_url": "https://...",
    "source_org": "masaf|regione|consorzio|gazzetta",
    "verification_note": "What the document is, its date/DM number, and a short quote proving it names the GI and carries the production rules."
  }
}
```

If you genuinely cannot find a public, licence-clear disciplinare for a
wine, return that slug with `"pdf_url": null` and a note explaining what
you found instead (e.g. "only a 1995 recognition decree, no
consolidated text online"). An honest null is more useful than a guess.
