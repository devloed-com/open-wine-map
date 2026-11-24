"""German readings of variety names that mean another cultivar elsewhere.

VIVC files one name under two passports by country: ROTER MUSKATELLER is the
official name *in Germany* on MUSCAT A PETITS GRAINS ROSES #8186 (berry
ROSE) and *in Austria* on MUSCAT A PETITS GRAINS ROUGES #8248 (ROUGE) —
both passports read live on 2026-11-24. The lexicon's alias is the red one
(the FR "Rg" entry, the Romanian Tămâioasă roză), so every German list that
prints «Roter Muskateller» — among its white-wine varieties, beside Roter
Riesling and Roter Traminer (Pfalz § 8) — showed the red Muscat: 15 EU
single documents and 26 BLE specifications (card validator on Franken,
2026-11-24).

A country reading is a reader's pin, never a lexicon fold (the Swiss
«Cornalin», `_lib/ch/reglement.swiss_match`): the German stages wrap the
matcher with `german_match`. Austria's documents list «Muskateller – Roter
Muskateller» as one variety under its first name and bind no red Muscat;
the Swiss cantonal lists that print «Roter Muskateller» keep #8248, the one
small-berried coloured Muscat of the federal list (Sortenverordnung SR
916.151.6, Anhang 8, Stand 1 December 2025: «Muscat rouge à petits grains N
— Muscat rouge»; VIVC lists MUSCAT ROUGE A PETITS GRAINS on #8248).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import replace

# normalised surface → the surface the lexicon binds to the German reading
DE_NAME_PINS: dict[str, str] = {
    "roter muskateller": "muscat-a-petits-grains-roses",
    "muskateller roter": "muscat-a-petits-grains-roses",
    "muskateller rot": "muscat-a-petits-grains-roses",
}


def _key(surface: str) -> str:
    s = unicodedata.normalize("NFKD", surface or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


def german_match(match_fn):
    """`match_fn` with the German readings of `DE_NAME_PINS`; the hit keeps
    the name as printed."""
    if getattr(match_fn, "_german", False):
        return match_fn

    def match(token, *args, **kwargs):
        pinned = DE_NAME_PINS.get(_key(token or ""))
        if not pinned:
            return match_fn(token, *args, **kwargs)
        hit = match_fn(pinned, *args, **kwargs)
        try:
            return replace(hit, name=token.strip()) if hit else hit
        except TypeError:
            return hit

    match._german = True
    return match
