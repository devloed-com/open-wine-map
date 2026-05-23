# SI ENOTNI DOKUMENT research — results (2026-05-23)

Two `general-purpose` research agents (`WebSearch` + `WebFetch`) ran in
parallel against the prompt at
[tmp/si-enotni-dokument-research-prompt.md](si-enotni-dokument-research-prompt.md).
The 16 no-publication SI wine GIs split into chunk A (8) + chunk B (8).

**Outcome: 0 FOUND / 16 NONE / 0 UNREACHABLE.** No public EUR-Lex
ENOTNI DOKUMENT exists for any of the 16 wines.

## Cross-cutting findings

- All 16 carry `publications: null` and `singleDocument: null` in
  eAmbrosia. Their only EU reference is an internal `Ares(2011)…` or
  `Ares(2013)…` summary-sheet id (URI 10327–15984 across the set), which
  is not publicly fetchable (eAmbrosia returns 404).
- These are all Art. 107 of Reg. (EU) 1308/2013 grandfathered names
  (EU protection dates 2006-01-26, 2006-02-17, 2009-08-01, 2009-08-08).
- EUR-Lex quick-search and Google site-restricted search for each GI
  name return either no results or incidental hits to **non-wine**
  products that mention the place name in passing — the closest false
  hits the agents had to rule out:
  - **Bela krajina** → `52009XC0617(05)` is the *Belokranjska pogača*
    food PDO, not the wine.
  - **Kras** → OJ C 048 (2012) is *Kraška panceta* (cured pork), not the
    wine PDO.
  - **Vipavska dolina** → `52010XC1215(04)` is the *Nanoški sir* cheese
    PDO application that locates its production area in Vipavska dolina.
  - **Teran** → the only EUR-Lex hit is Commission Delegated Reg. (EU)
    2017/1353 (the SI/HR labelling regulation — already cited in the
    curated cross-border note); it is NOT a consolidated single document.

## Two findings worth flagging

- **Belokranjec (PDO-SI-A1576) + Metliška črnina (PDO-SI-A1579)** —
  a Slovenian national-level *standardna sprememba* (standard amendment)
  was approved in early 2026 (MKGP public consultation 7 Jan – 9 Feb 2026,
  reported by *dolenjskainfo.com* 2026). The wave of OJ-C amendment
  publications under Reg. (EU) 2024/1143 typically follows national
  approval by some months — these two are the **most likely candidates
  to land a public ENOTNI DOKUMENT on EUR-Lex later in 2026**. Re-check
  in 3–6 months. eAmbrosia's own `amendmentsInProgressFlag: true` on
  PDO-SI-A1579 corroborates this.
- The closest precedent we have is exactly the path Cviček (PDO-SI-A1561)
  followed — its post-2024/1143 standard-amendment notice landed in
  `OJ C/2026/256, 16.1.2026`. Belokranjec and Metliška črnina are the
  most plausible next-in-line.

## Verbatim agent output

### Chunk A (bela-krajina … metliska-crnina)

```json
{
  "bela-krajina": {
    "url": null,
    "note": "Art. 107 of Reg. (EU) 1308/2013 grandfathered name (EU protection date 2006-02-17). eAmbrosia EUGI00000006665 / PDO-SI-A0878 carries singleDocument: null and publications: null. Only reference is summary sheet Ares(2011)1373284 (not publicly fetchable). EUR-Lex quick-search for 'Bela krajina' returns no wine PDO single-document publication; the only related EUR-Lex hit (52009XC0617(05)) concerns the food product 'Belokranjska pogača', not the wine GI. No consolidated ENOTNI DOKUMENT exists in the OJ for this wine.",
    "status": "NONE"
  },
  "belokranjec": {
    "url": null,
    "note": "Art. 107 of Reg. (EU) 1308/2013 grandfathered name (EU protection date 2006-02-17). eAmbrosia EUGI00000007401 / PDO-SI-A1576 has singleDocument: null and publications: null; only summary sheet Ares(2011)1409323. A standard amendment was approved at Slovenian national level in early 2026 (MKGP public consultation 7 Jan – 9 Feb 2026, reported by dolenjskainfo.com 2026), but no corresponding OJ-C 'OBVESTILO O ODOBRITVI STANDARDNE SPREMEMBE' has been published in EUR-Lex yet. EUR-Lex quick-search for 'Belokranjec' returns 134 incidental hits, none being a wine PDO consolidated single-document publication.",
    "status": "NONE"
  },
  "bizeljcan": {
    "url": null,
    "note": "Art. 107 of Reg. (EU) 1308/2013 grandfathered name (EU protection date 2009-08-01). eAmbrosia EUGI00000005099 / PDO-SI-A1520 explicitly states publications: 'Not available' and singleDocument: null; only summary sheet Ares(2013)3131005. EUR-Lex quick-search for 'Bizeljčan' returns 'No results found.' National Slovenian PTP recognition was published in Uradni list RS in March 2009 but no EU OJ-C ENOTNI DOKUMENT publication exists.",
    "status": "NONE"
  },
  "bizeljsko-sremic": {
    "url": null,
    "note": "Art. 107 of Reg. (EU) 1308/2013 grandfathered name (EU protection date 2006-02-17). eAmbrosia EUGI00000005481 / PDO-SI-A0772 carries singleDocument: null and publications: null; only summary sheet Ares(2011)1363194. EUR-Lex quick-search returns no wine PDO single-document publication for this GI; closest related hits (OJ C/2025/6752, C/2025/6753) concern other wines, not Bizeljsko Sremič. No consolidated single document exists in the OJ.",
    "status": "NONE"
  },
  "dolenjska": {
    "url": null,
    "note": "Art. 107 of Reg. (EU) 1308/2013 grandfathered name (EU protection date 2006-02-17). eAmbrosia EUGI00000006662 / PDO-SI-A0871 carries singleDocument: null and publications: null; only summary sheet Ares(2013)3123133. The related Cviček PDO (PDO-SI-A1561, a sub-style produced in Dolenjska) is the only Slovenian wine with an OJ-C publication (OJ C/2026/256), but that document covers Cviček not Dolenjska. No consolidated single document for the Dolenjska regional PDO itself has been published in the OJ.",
    "status": "NONE"
  },
  "goriska-brda": {
    "url": null,
    "note": "Art. 107 of Reg. (EU) 1308/2013 grandfathered name (EU protection date 2006-02-17). eAmbrosia EUGI00000005684 / PDO-SI-A0270 carries singleDocument: null and publications: null; only summary sheet Ares(2013)3122875. EUR-Lex quick-search for 'Goriska Brda' returns 'No results found.' A Slovenian national product specification exists at gov.si (S_Goriska_Brda-1.doc, MKGP) but that is a national document, not an EU OJ-C ENOTNI DOKUMENT. No EU single-document publication exists for this well-known appellation.",
    "status": "NONE"
  },
  "kras": {
    "url": null,
    "note": "Art. 107 of Reg. (EU) 1308/2013 grandfathered name (EU protection date 2006-02-17). eAmbrosia EUGI00000006521 / PDO-SI-A0616 carries singleDocument: null and publications: null; only summary sheet Ares(2011)1354927. EUR-Lex hits for 'Kras' refer to the unrelated food PDO 'Kraška panceta' (OJ C 048, 2012) and other non-wine documents. No consolidated wine single document has been published in the OJ for the Kras wine PDO.",
    "status": "NONE"
  },
  "metliska-crnina": {
    "url": null,
    "note": "Art. 107 of Reg. (EU) 1308/2013 grandfathered name (EU protection date 2009-08-08). eAmbrosia EUGI00000007442 / PDO-SI-A1579 carries singleDocument: null and publications: null; amendmentsInProgress: true; only summary sheet Ares(2011)1409332. A standard amendment was approved at Slovenian national level in early 2026 (MKGP public consultation 7 Jan – 9 Feb 2026 together with Belokranjec), but no corresponding OJ-C 'OBVESTILO O ODOBRITVI STANDARDNE SPREMEMBE' has been published in EUR-Lex yet. EUR-Lex quick-search returns 'No results found' for the GI name.",
    "status": "NONE"
  }
}
```

### Chunk B (podravje … vipavska-dolina)

```json
{
  "podravje": {
    "url": null,
    "note": "eAmbrosia API record (EUGI00000006705, PGI-SI-A0995) shows publications=null and singleDocument=null. Only reference is internal summary sheet Ares(2013)3325958 (URI 15984), not publicly fetchable. Art. 107 Reg. (EU) 1308/2013 grandfathered name (euProtectionDate 2006-01-26). No EUR-Lex amendment publication located via EUR-Lex search, Google site-restricted search, or OJ-C browsing through 2026-05.",
    "status": "NONE"
  },
  "posavje": {
    "url": null,
    "note": "eAmbrosia API record (EUGI00000006847, PGI-SI-A1061) shows publications=null and singleDocument=null. Only reference is internal summary sheet Ares(2011)1384485 (URI 11548), not publicly fetchable. Art. 107 Reg. (EU) 1308/2013 grandfathered name (euProtectionDate 2006-01-26). No EUR-Lex amendment publication located.",
    "status": "NONE"
  },
  "prekmurje": {
    "url": null,
    "note": "eAmbrosia API record (EUGI00000004923, PDO-SI-A0769) shows publications=null and singleDocument=null. Only reference is internal summary sheet Ares(2011)1362403 (URI 10973), not publicly fetchable. Art. 107 Reg. (EU) 1308/2013 grandfathered name (euProtectionDate 2006-02-17). No EUR-Lex amendment publication located.",
    "status": "NONE"
  },
  "primorska": {
    "url": null,
    "note": "eAmbrosia API record (EUGI00000006901, PGI-SI-A1094) shows publications=null and singleDocument=null. Only reference is internal summary sheet Ares(2011)1386923 (URI 11273), not publicly fetchable. Art. 107 Reg. (EU) 1308/2013 grandfathered name (euProtectionDate 2006-01-26). No EUR-Lex amendment publication located.",
    "status": "NONE"
  },
  "slovenska-istra": {
    "url": null,
    "note": "eAmbrosia API record (EUGI00000006274, PDO-SI-A0609) shows publications=null and singleDocument=null. Only reference is internal summary sheet Ares(2013)3122809 (URI 15968), not publicly fetchable. Art. 107 Reg. (EU) 1308/2013 grandfathered name (euProtectionDate 2009-08-08). No EUR-Lex amendment publication located.",
    "status": "NONE"
  },
  "stajerska-slovenija": {
    "url": null,
    "note": "eAmbrosia API record (EUGI00000001921, PDO-SI-A0639) shows publications=null and singleDocument=null. Only reference is internal summary sheet Ares(2011)1355683 (URI 10327), not publicly fetchable. Art. 107 Reg. (EU) 1308/2013 grandfathered name (euProtectionDate 2009-08-08). No EUR-Lex amendment publication located.",
    "status": "NONE"
  },
  "teran": {
    "url": null,
    "note": "eAmbrosia API record (EUGI00000007443, PDO-SI-A1581) shows publications=null and singleDocument=null. Only reference is internal summary sheet Ares(2013)3122934 (URI 15984), not publicly fetchable. Art. 107 Reg. (EU) 1308/2013 grandfathered name (euProtectionDate 2006-02-17). The only related EUR-Lex document is Commission Delegated Regulation (EU) 2017/1353 (CELEX 32017R1353), which permits Croatia to use 'Teran' on Hrvatska Istra labels — this is NOT a Slovenian single-document publication and does not contain an ENOTNI DOKUMENT block for the Slovenian PDO. The PDO-SI-A1581 file number, despite being in the recent A15xx range, has no consolidated EU-OJ single-document publication.",
    "status": "NONE"
  },
  "vipavska-dolina": {
    "url": null,
    "note": "eAmbrosia API record (EUGI00000005861, PDO-SI-A0448) shows publications=null and singleDocument=null. Only reference is internal summary sheet Ares(2011)1340500 (URI 11503), not publicly fetchable. Art. 107 Reg. (EU) 1308/2013 grandfathered name (euProtectionDate 2006-02-17). EUR-Lex quick-search for 'Vipavska dolina' returns 213 hits, all incidental mentions (the closest relevant — CELEX 52010XC1215(04) — is the Nanoški sir cheese PDO application that locates its production area in Vipavska dolina; not a wine single-document publication).",
    "status": "NONE"
  }
}
```
