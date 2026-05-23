# Research results — Austrian wine appellation organisation URLs

Gap type: `at-weinkomitee-url` (Austrian analogue of `it-consorzio-url`).
Source prompt: `tmp/at-weinkomitee-url-research-prompt.md`.
Dispatched 2026-05-22 — 3 parallel `general-purpose` agents (chunks A/B/C) +
1 follow-up agent for `wagram`. All 32 AT wine GIs resolved.

URL probe 2026-05-22 (browser UA, follow redirects): see notes below.

## Agent results (verbatim)

### Chunk A — Niederösterreich + Wien (agent a75ab2a0d97143e9a)

    niederosterreich      | FOUND | Wein Niederösterreich               | https://weinniederoesterreich.at/         | Official Lower Austria wine board (WNM Wein Niederösterreich Marketing GmbH, Krems); regional roof-marketing org for the Niederösterreich PDO and all its DACs
    weinviertel           | FOUND | Regionales Weinkomitee Weinviertel  | https://www.weinvierteldac.at/            | Official site of the 21-member Regional Wine Committee for Weinviertel DAC; describes DAC rules + member growers
    kamptal               | FOUND | Weinstraße Kamptal                  | https://www.weinkultur-kamptal.at/        | Kamptal regional wine-road / marketing association, Langenlois; public-facing wine body for Kamptal DAC (Regionales Weinkomitee Kamptal has no separate site)
    kremstal              | FOUND | Regionales Weinkomitee Kremstal     | https://kremstalwein.at/                  | Official site of the Regional Wine Committee Kremstal (est. March 2002); Kremstal DAC marketing, quality, wine tourism
    traisental            | FOUND | Verein Traisentaler Wein            | https://www.traisentalwein.at/            | Association of Traisental DAC winegrowers (Verein Traisentaler Wein, Reichersdorf); Regionales Weinkomitee Traisental has no separate site
    wachau                | FOUND | Vinea Wachau                        | https://www.vinea-wachau.at/              | Vinea Wachau Nobilis Districtus, the Wachau region's wine association (200+ estates); 11-member Regionales Weinkomitee Wachau has no separate site
    carnuntum             | FOUND | Rubin Carnuntum Weingüter           | https://www.carnuntum.com/                | Official Carnuntum wine-region site (Rubin Carnuntum Weingüter, ~190 producers); Regionales Weinkomitee Carnuntum has no separate site
    thermenregion         | FOUND | Regionales Weinkomitee Thermenregion| https://www.thermenregiondac.at/          | Official site of the Regional Wine Committee Thermenregion; presents Thermenregion DAC
    wien                  | FOUND | Wiener Wein                         | https://www.wienerwein.at/                | Official Vienna wine board run by Landwirtschaftskammer Wien; covers the whole Vienna wine region
    wiener-gemischter-satz| FOUND | Wiener Wein                         | https://www.wienerwein.at/                | Wiener Gemischter Satz DAC is administered by the same Vienna wine board (Landwirtschaftskammer Wien / Regionales Weinkomitee Wien); no separate WGS-DAC org site

(WienWein at wienwein.at rejected — private 6-estate group, not the administering body.)

### Chunk B — Burgenland + Kärnten + Tirol (agent a70de8af37f7cfc9a)

    burgenland            | FOUND | Wein Burgenland          | https://www.weinburgenland.at/    | Burgenland-wide wine marketing board; board includes the Regionales Weinkomitee Burgenland
    neusiedlersee         | FOUND | Verein Neusiedlersee DAC | https://neusiedlersee-dac.wine/   | Official Neusiedlersee DAC site; Impressum names "Verein NEUSIEDLERSEE DAC", Neusiedl am See
    leithaberg            | FOUND | DAC Leithaberg           | https://www.leithaberg.at/        | Official Leithaberg DAC site; DAC rules, soils, member-grower directory
    rosalia               | FOUND | Verein Rosalia           | https://www.rosaliadac.at/        | Official Rosalia DAC site; Impressum "Verein Rosalia", Pöttelsdorf
    mittelburgenland      | FOUND | Verband Blaufränkisch    | https://www.blaufraenkischland.at/| Verband Blaufränkisch (Deutschkreutz); administering association for Mittelburgenland DAC
    eisenberg             | FOUND | Verein EisenbergDAC      | https://www.eisenberg-dac.at/     | Official Eisenberg DAC site; Impressum "Verein EisenbergDAC", Eisenberg/Pinka
    sudburgenland         | FOUND | Weinidylle Südburgenland | https://www.weinidylle.at/        | Verband Weinidylle Südburgenland, Moschendorf; regional wine body for the Südburgenland wine region
    ruster-ausbruch       | FOUND | Verein Ruster Ausbruch DAC| https://www.rusterausbruch.at/   | Official site; "Ruster Ausbruch DAC", Rust; succeeded the Cercle Ruster Ausbruch under the 2021 DAC regulation
    karnten               | FOUND | Weinbauverband Kärnten   | https://weinauskaernten.at/       | Official Carinthian wine growers' association ("Weinbauverband Kärnten")
    tirol                 | FOUND | Tiroler Weinbauverband   | https://www.tirolwein.at/         | Official Tyrolean wine growers' association; 82 members across all eight Tirol districts
    neusiedlersee-hugelland| NONE | —                        | —                                 | Superseded 1985 PDO name; area now marketed as Leithaberg DAC. No org site for the old name. Closest body: Wein Burgenland (weinburgenland.at)

### Chunk C — Steiermark + western regional PDOs + Landwein IGPs (agent ae1f7787d40b32fc5)

    steiermark            | FOUND | Wein Steiermark            | https://steiermark.wine/    | Official wine board for the whole Steiermark wine region; runs the Steiermark DAC origin system
    sudsteiermark         | FOUND | Wein Steiermark            | https://steiermark.wine/    | Südsteiermark DAC — single Regionales Weinkomitee Steiermark; public board Wein Steiermark
    weststeiermark        | FOUND | Wein Steiermark            | https://steiermark.wine/    | Weststeiermark DAC — one Steiermark wine committee covers all three DACs
    vulkanland-steiermark | FOUND | Wein Steiermark            | https://steiermark.wine/    | Vulkanland Steiermark DAC — administered by Regionales Weinkomitee Steiermark (winzer-vulkanland.at is a tourism assoc., rejected)
    steirerland           | FOUND | Wein Steiermark            | https://steiermark.wine/    | Steirerland Landwein IGP coextensive with the Steiermark Bundesland; Wein Steiermark is the administering body
    salzburg              | FOUND | Österreich Wein Marketing  | (ÖWM)                       | Tiny generic regional PDO, no regional wine committee; ÖWM is the only public org
    vorarlberg            | FOUND | Österreich Wein Marketing  | (ÖWM)                       | Tiny generic regional PDO; a Verein der Weinbautreibenden Vorarlbergs exists but has no clear current official site; ÖWM is the authoritative public org
    oberosterreich        | FOUND | Österreich Wein Marketing  | (ÖWM)                       | Tiny generic regional PDO, no regional wine committee; ÖWM is the only public org
    bergland              | FOUND | Österreich Wein Marketing  | (ÖWM)                       | Multi-state Landwein IGP (Kärnten, OÖ, Salzburg, Tirol, Vorarlberg); no regional committee; ÖWM is the only public org
    weinland              | FOUND | Österreich Wein Marketing  | (ÖWM)                       | Multi-state Landwein IGP (NÖ, Burgenland, Wien); no single dedicated org; ÖWM is the only public org

### Follow-up — wagram (agent ab7f97afb66ea1b07)

    wagram | FOUND | Wein Niederösterreich | https://weinniederoesterreich.at/ | No Wagram-specific org site exists — Regionales Weinkomitee Wagram has no standalone website; old wagram.at + wagramwein.at both 301-redirect into the donau.com tourism portal. Wein Niederösterreich is the regional roof body covering Wagram.

## URL probe notes (2026-05-22)

- **HTTP 200**: weinvierteldac.at, weinkultur-kamptal.at, kremstalwein.at,
  vinea-wachau.at, carnuntum.com, thermenregiondac.at, wienerwein.at,
  weinburgenland.at, neusiedlersee-dac.wine, leithaberg.at, rosaliadac.at,
  blaufraenkischland.at, eisenberg-dac.at, weinidylle.at, rusterausbruch.at,
  weinauskaernten.at, tirolwein.at, steiermark.wine — all clean.
- **weinniederoesterreich.at → HTTP 202**: SiteGround anti-bot CAPTCHA
  challenge served to automated clients only; the site loads normally in a
  browser. Live, not broken. (Affects niederosterreich + wagram.)
- **traisentalwein.at**: DNS resolves (81.19.154.98); **HTTPS handshake
  fails** (curl 000 on https://), but **plain HTTP returns 200**. The site
  is live but serves no working TLS — an `https://` link would break,
  `http://` works. Decision needed (see review table).
- **oesterreichwein.at / austrianwine.com → HTTP 307**: locale-negotiation
  redirect; both are the established national wine board and load in a
  browser. Live, not broken.
