# Research task — find an EUR-Lex ENOTNI DOKUMENT (EU single document) for 16 Slovenian wine GIs

## Context

I maintain open-wine-map, a wine-appellation reference built **only** from
public, licence-clear regulator data. Slovenia is country #6 of the corpus.
The EU register (**eAmbrosia**) carries 17 Slovenian wine geographical
indications (14 DOP + 3 IGP). For 16 of them, eAmbrosia's `publications`
array is empty — the only reference is an internal `Ares(2013)…`
summary-sheet id that is not publicly fetchable. These wines are Art. 107
of Reg. (EU) 1308/2013 *grandfathered* names registered automatically when
EU wine GI protection was harmonised.

A wine GI's product specification is published in the EU Official Journal,
Series C, as the "**ENOTNI DOKUMENT**" (Slovenian for "Single Document"). My
pipeline knows how to parse that HTML — it just needs a fetchable URL. The
one Slovenian wine that already works — **Cviček** (PDO-SI-A1561) — has
exactly this kind of publication: `OJ C/2026/256, 16.1.2026`, reachable at
<http://data.europa.eu/eli/C/2026/256/oj/slv>. The HTML there contains a
`<p class="ti-grseq-1">ENOTNI DOKUMENT</p>` anchor followed by numbered
sections (1. Ime ali imena, 2. Vrsta geografske označbe, …, 8. Sorta ali
sorte vinske trte, 9. Jedrnat opis razmejenega geografskega območja,
10. Povezava z geografskim območjem, 11. Dodatne veljavne zahteve).

These ENOTNI-DOKUMENT publications come up most often as:

- **standard-amendment notices** under Reg. (EU) 2024/1143
  ("OBVESTILO O ODOBRITVI STANDARDNE SPREMEMBE") — Cviček's case.
- **Union-amendment publications** under the older Reg. (EU) No 1308/2013
  Art. 105 ("PUBLIKACIJA SPOROČILA O ODOBRITVI STANDARDNE SPREMEMBE" or
  "ZAHTEVEK ZA SPREMEMBO PROIZVODNE SPECIFIKACIJE").
- **OJ-C Series notifications** of various kinds (request for amendment,
  notice of approval, etc.) that embed a consolidated ENOTNI DOKUMENT.

Any of those is acceptable — the parser only needs the consolidated single
document to be on the page.

## What I need from you

For each Slovenian GI below, search the sources listed and return one of:

1. **FOUND** — a real EUR-Lex page that contains a consolidated **ENOTNI
   DOKUMENT** (Slovenian — *Single Document* in EN, *Documento unico* in
   IT, *Document unique* in FR, etc. is also fine; the parser handles any
   language variant of the same template) for *this exact GI*. Give:
   - the OJ-C citation (e.g. `OJ C/2026/256, 16.1.2026`),
   - the ELI URL preferred, ideally `http://data.europa.eu/eli/C/<year>/<n>/oj/slv`
     (or any language variant — my pipeline rewrites the URL to Slovenian),
   - a short `verification_quote` showing the page does name this GI and
     does carry the ENOTNI DOKUMENT block (a one-line excerpt is fine).
2. **NONE** — no public EUR-Lex page exists with a consolidated ENOTNI
   DOKUMENT for this GI. Say so, and note the closest related publication
   you did find (e.g. only a recognition decree, only a label-language
   notification, only a third-country acknowledgement).
3. **UNREACHABLE** — a candidate page exists but you were blocked by a
   JavaScript / CAPTCHA / WAF challenge (EUR-Lex sometimes serves an AWS
   WAF challenge). Give the blocked URL and the challenge type — do not
   guess.

Search in priority order:

1. **EUR-Lex search** — <https://eur-lex.europa.eu/> "Quick search" tab.
   Try the GI name in Slovenian (e.g. `"Goriška Brda"`) restricted to
   Series C; also try the file-number identifier (e.g. `PDO-SI-A0270`).
2. **EUR-Lex advanced search** — <https://eur-lex.europa.eu/advanced-search-form.html?advSearchKey=eGN-quickSearch&qid=> —
   filter by `Author: European Commission` + `Form: Notice` (or
   `Information`) + free-text the GI name + Slovenia (member state SI).
3. **eAmbrosia GI register UI** — `https://ec.europa.eu/agriculture/eambrosia/geographical-indications-register/details/<giIdentifier>`
   (the giIdentifier values are listed in the table below). The HTML
   detail page sometimes shows a "Publications" panel with links the
   public JSON API returns as null.
4. **Google site-restricted search** — `site:eur-lex.europa.eu "<wine name>" "ENOTNI DOKUMENT"` (or `"DOCUMENTO UNICO"`, `"SINGLE DOCUMENT"`).
5. **data.europa.eu ELI catalogue** — `http://data.europa.eu/eli/C/` browser; many SI wine amendments since 2019 land there.

**Identity check:** the page must explicitly name this GI (the *protected
name* string in the table below — match accents) **and** carry a numbered
single-document block listing grape varieties + production rules + a
geographic-area description for the right Slovenian region. A page about a
homonym place, a council decision recognising the name but without the
consolidated document, or an opposition / objection notice does not count.

A confident **NONE is a useful answer.** Do not invent a plausible-looking
OJ citation or URL — only return FOUND when you have opened the page and
confirmed its identity. If the GI is so old that only its initial OJ-L
recognition decree exists (no single-document publication), say so —
that's a NONE.

## The 16 items

| # | slug | name | file_number | giIdentifier | kind | region |
|---|------|------|-------------|--------------|------|--------|
| 1 | bela-krajina         | Bela krajina         | PDO-SI-A0878 | EUGI00000006665 | DOP | Posavje |
| 2 | belokranjec          | Belokranjec          | PDO-SI-A1576 | EUGI00000007401 | DOP | Posavje |
| 3 | bizeljcan            | Bizeljčan            | PDO-SI-A1520 | EUGI00000005099 | DOP | Posavje |
| 4 | bizeljsko-sremic     | Bizeljsko Sremič     | PDO-SI-A0772 | EUGI00000005481 | DOP | Posavje |
| 5 | dolenjska            | Dolenjska            | PDO-SI-A0871 | EUGI00000006662 | DOP | Posavje |
| 6 | goriska-brda         | Goriška Brda         | PDO-SI-A0270 | EUGI00000005684 | DOP | Primorska |
| 7 | kras                 | Kras                 | PDO-SI-A0616 | EUGI00000006521 | DOP | Primorska |
| 8 | metliska-crnina      | Metliška črnina      | PDO-SI-A1579 | EUGI00000007442 | DOP | Posavje |
| 9 | podravje             | Podravje             | PGI-SI-A0995 | EUGI00000006705 | IGP | Podravje (region IGP) |
| 10 | posavje             | Posavje              | PGI-SI-A1061 | EUGI00000006847 | IGP | Posavje (region IGP) |
| 11 | prekmurje           | Prekmurje            | PDO-SI-A0769 | EUGI00000004923 | DOP | Podravje |
| 12 | primorska           | Primorska            | PGI-SI-A1094 | EUGI00000006901 | IGP | Primorska (region IGP) |
| 13 | slovenska-istra     | Slovenska Istra      | PDO-SI-A0609 | EUGI00000006274 | DOP | Primorska |
| 14 | stajerska-slovenija | Štajerska Slovenija  | PDO-SI-A0639 | EUGI00000001921 | DOP | Podravje |
| 15 | teran               | Teran                | PDO-SI-A1581 | EUGI00000007443 | DOP | Primorska |
| 16 | vipavska-dolina     | Vipavska dolina      | PDO-SI-A0448 | EUGI00000005861 | DOP | Primorska |

Notes that may speed the search:

- File numbers in the `PDO-SI-A15xx` range (Belokranjec A1576, Bizeljčan
  A1520, Metliška črnina A1579, Teran A1581) are recent registrations or
  recently re-numbered amendments — these are the most likely to have a
  modern OJ-C ENOTNI-DOKUMENT publication.
- Teran is the subject of EU Delegated Reg. (EU) 2017/1353 (Slovenia ↔
  Croatia labelling dispute). That regulation is NOT the document we want
  — it concerns the Croatian *Hrvatska Istra* label exemption. The Teran
  ENOTNI DOKUMENT, if it exists, is a separate Slovenian-side publication.
- Goriška Brda is a well-known appellation (Friuli-Slovenia border) and a
  plausible candidate for at least an older OJ-C "summary publication".

## Output format

A JSON object ready to merge into
`raw/si/oj-pages/manual_overrides.json`, keyed by slug. The pipeline's
stage 01 reads `url` and `note` per entry; please include
`verification_quote` for the staging review.

```json
{
  "<slug>": {
    "url": "http://data.europa.eu/eli/C/<year>/<n>/oj/slv",
    "note": "<OJ-C citation, publication date, what the notice is (e.g. 'OBVESTILO O ODOBRITVI STANDARDNE SPREMEMBE under Reg 2024/1143')>",
    "verification_quote": "<one-line excerpt from the page showing the GI name + the ENOTNI DOKUMENT header is present>",
    "status": "FOUND"
  },
  "<slug-with-none>": {
    "url": null,
    "note": "<what you found instead, e.g. 'only OJ L1992/123 recognition decree (no consolidated single document published)'>",
    "status": "NONE"
  },
  "<slug-with-block>": {
    "url": "<blocked-URL>",
    "note": "<challenge type, e.g. 'AWS WAF JavaScript challenge'>",
    "status": "UNREACHABLE"
  }
}
```

Group FOUND entries first, then NONE, then UNREACHABLE. An honest NONE or
UNREACHABLE beats a guessed URL — the curator will retry the search by hand
for any NONE.
