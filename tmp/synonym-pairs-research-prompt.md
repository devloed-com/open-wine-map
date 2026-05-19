# Research task — 8 disputed grape synonym pairs in Spanish wine pliegos

## Context

I maintain a wine-appellation reference (open-wine-map). Spanish EU-OJ pliegos
(documento único, section 7 "Variedades de uva de vinificación") list varieties
one per line; some lines write two names separated by ` - ` to mark them as
synonyms of one variety, e.g.

  CABERNET SAUVIGNON
  MACABEO - VIURA
  TEMPRANILLO - CENCIBEL

For each pair I need to decide whether they are one variety (fold to one slug)
or two distinct varieties (keep separate). My primary reference is the
**Vitis International Variety Catalogue (VIVC)** — Julius Kühn-Institut,
Geilweilerhof — at https://www.vivc.de/. VIVC variety numbers identify
DNA-confirmed canonical varieties.

For 27 of the 35 pairs I extracted, both sides resolve to the same VIVC
number (DNA-confirmed identity) and I've folded them. **8 pairs remain
disputed** — for these, either VIVC has two entries that look like the same
variety, or VIVC says the two are different varieties but the regulator
asserts identity.

## What I need from you

For each pair below, please answer:

1. **Are these two names truly synonyms for one variety, or are they two
   distinct varieties?** Cite the authoritative source(s) (VIVC pages,
   Robinson/Harding/Vouillamoz _Wine Grapes_ entries, consejo regulador
   websites, regional ampelographic literature, peer-reviewed DNA studies).
2. **If VIVC has duplicate entries**, identify which one is the active
   prime entry and which is obsolete/duplicate (JKI sometimes carries
   legacy records).
3. **Provide a recommended fold direction** if they are synonyms:
   `slug_X → slug_Y`. Use the slug that is the VIVC prime name (lowercase,
   diacritics stripped, spaces → hyphens) when possible.

For each pair, please include the VIVC variety-number URL you consulted
(format: `https://www.vivc.de/index.php?r=passport%2Fview&id=NNNNN`).

## The 8 disputed pairs

### Pair 1 — `listan-negro` vs `almuneco`

- Cited in OJ pliegos: Gran Canaria, Islas Canarias, Lanzarote, Tacoronte-Acentejo
- VIVC #14943 "LISTAN NEGRO" (Spain origin)
- VIVC #6860 "LISTAN PRIETO" (Spain origin) — its ES-official synonym list
  contains BOTH "ALMUNECO" and "LISTAN NEGRO"
- Question: Are #14943 and #6860 the same DNA variety, or two? If two, which
  one is the Canarian Listán Negro that the pliegos refer to? Cf. Listán
  Prieto = Mission / País (the colonial South-American grape) — is the
  Canarian Listán Negro the same as Mission, or distinct?

### Pair 2 — `agudelo` vs `chenin`

- Cited in OJ pliegos: Barbanza-e-Iria, Cataluña, Costers del Segre
- The pliegos write `AGUDELO - CHENIN BLANC`, asserting identity.
- My local data resolved `agudelo` → VIVC #12953 GOUVEIO (Portugal); but
  VIVC #2527 CHENIN BLANC's ES-official synonym list contains "AGUDELO".
- Question: Is Spanish "Agudelo" Chenin Blanc (#2527), or is it Gouveio
  (#12953, = Godello), or has the name been used historically for both?
  Galician sources commonly equate Agudelo with Godello; the pliego's
  Chenin-Blanc claim is unusual.

### Pair 3 — `tinto-velasco` vs `alicante-bouschet`

- Cited in OJ pliego: Sierras de Málaga (line: `TINTO VELASCO - BLASCO`)
- VIVC #17353 "TINTO VELASCO" (Spain) — ES synonym "FRASCO"
- VIVC #304 "ALICANTE HENRI BOUSCHET" (France) — synonym list includes
  "BLASCO" and "GARNACHA TINTORERA"
- Question: Is "Blasco" in the Sierras de Málaga pliego a synonym of
  Alicante Bouschet (per VIVC #304) or of Tinto Velasco (per the pliego's
  ` - ` assertion)? Are Tinto Velasco and Alicante Bouschet the same
  variety, or two?

### Pair 4 — `bastardo-negro` vs `baboso-negro`

- Cited in OJ pliegos: Islas Canarias, Lanzarote, Tacoronte-Acentejo
- VIVC says: Bastardo Negro = TROUSSEAU NOIR (#12668, France);
  Baboso Negro = ALFROCHEIRO (#277, Portugal). Different DNA.
- Question: The Canarian pliegos write `BASTARDO NEGRO - BABOSO NEGRO`
  as synonyms. Is this an ampelographic mis-identification (very common
  with Iberian dark varieties), or has there been a recent DNA study
  reconciling them?

### Pair 5 — `moravia-dulce` vs `crudijera`

- Cited in OJ pliegos: La Mancha, Manchuela
- VIVC #23166 MORAVIA DULCE (Spain) vs #23167 MAVROTHIRIKO (Greece)
- Question: Same variety or different? "Crudijera" is a local Manchuela
  name — does it map to Moravia Dulce, Mavrothiriko, or something else?

### Pair 6 — `merseguera` vs `sumoll-blanco`

- Cited in OJ pliego: Cataluña
- VIVC #7660 MERSEGUERA (Spain) vs #12073 SUMOLL BLANCO (Spain) — both
  Catalan whites, listed as distinct in VIVC.
- Question: Did the Cataluña pliego mean to assert identity, or is this
  a typo / OCR artefact where two consecutive varieties got hyphen-joined?

### Pair 7 — `merenzao` vs `tintilla`

- Cited in OJ pliego: Gran Canaria
- VIVC says: Merenzao = TROUSSEAU NOIR (#12668); Tintilla = GRACIANO
  (#4935). Very different varieties.
- Question: The Gran Canaria pliego writes `MERENZAO - TINTILLA`. Is the
  Canarian Tintilla actually Graciano (per VIVC), Trousseau Noir (per the
  pliego's identity claim), or a third grape "Tintilla de Rota" or
  "Tintilla de Lanzarote"?

### Pair 8 — `merenzao` vs `negro-sauri`

- Cited in OJ pliego: León
- VIVC #12668 TROUSSEAU NOIR (= Merenzao) vs #17252 MARBURGO. Different DNA.
- Question: The León pliego asserts identity. Is Negro Saurí the same as
  Merenzao/Trousseau, or is it the distinct #17252 Marburgo as VIVC
  classifies it?

## Output format

For each pair, please return:

```
### Pair N
Verdict: SAME | DIFFERENT | AMBIGUOUS
Fold direction (if SAME): slug_X → slug_Y
Sources:
- VIVC #NNNNN — <URL>
- <other authoritative source URL>
Brief justification (2-3 sentences).
```

If a pair is AMBIGUOUS, explain what additional evidence would resolve it.
