"""Per-target-locale vocabulary preferences for stage 02c/02e translation.

Steers translation models away from awkward literals and toward the
sommelier register that target-locale wine writing actually uses.
Glossaries are target-locale keyed; entries only exist where the corpus
showed recurring problems. Append the returned block to a translation
SYSTEM_PROMPT under a blank-line separator; an empty return makes the
append a no-op for locales without curated guidance.

Curated for NL and EN. The first pass came from a sweep of the FR + ES →
target corpus (~6850 terroir-fact bullets and ~340 ollama-translated
summaries per target); the 2026-09-11 corpus-wide review (plan W1) added
the EN calques that the IT / CZ / SI / HU / PT / FR sources produce. Since
that pass the glossary is appended by `terroir_prompts.translation_system_
prompt` for every 02e script (all 21 source corpora), not only the FR one,
so entries must hold whatever the source language. ES and FR targets were
probed and showed no recurring issues worth a rule today — Mistral handles
FR↔ES cleanly, and the few suspicious-looking FR phrases ("phase visuelle",
"vins francs") turn out to be legitimate French wine vocabulary.
"""

from __future__ import annotations

_NL_GLOSSARY = """\
Dutch (NL) sommelier-register vocabulary — applies whatever the source \
language. Prefer the LEFT term over the RIGHT:
- "stille wijn(en)" NOT "rustige wijn(en)" — for FR "tranquille" / ES "tranquilo"; "rustige" reads as "calm/peaceful".
- "mousserende wijn(en)" NOT "schuimwijn" — for FR "mousseux" / ES "espumoso".
- "aroma's" NOT "aromen" — plural of aroma in modern NL wine writing.
- "vinificatie" NOT "wijnbereiding" or "wijnmaking" — for FR "vinification" / ES "vinificación".
- "onvruchtbare bodem(s)" or "schrale bodem(s)" NOT "steriele bodem(s)" — for FR "sol pauvre" / ES "suelo pobre / estéril"; NL "steriel" implies clinically sterile.
- "uiterlijk / neus / mond" (or "kleur / geur / smaak") NOT "visuele fase / geurige fase / smaakfase" — tasting-note phases; the "fase X" form is a literal of the Spanish pliego template.
- "zuiver(e)" NOT "frank(e)" — for ES "franco / vinos francos" or FR "vins francs" (sensory sense: clean, fault-free aromas/wines).
- "lemig(e)" or "leemachtig(e)" NOT "frank(e)" when describing soil texture — for ES "textura franca", "franco arenoso" (sandy loam), "franco arcilloso" (clay loam). Distinct from the sensory "vinos francos" sense above: this is the soil-science classification term meaning loamy (roughly equal sand/silt/clay).
- "tegelrood" or "baksteenrood" NOT "tegeltoon" — for FR "tuile" / ES "teja" (aged-wine tile colour).
- "vlezig" (one E) NOT "vleesig" — fleshy mouthfeel.
- "smeuïg" NOT "smeerend" — smooth, unctuous palate.
- "geconfijte vruchten" NOT "kandijvruchten" or "confiteraadjes" — for FR "fruits confits" / ES "frutas confitadas".
- "de Marnevallei" / "het Marnedal", "de Audevallei", "de Rhônevallei" NOT a blend such as "Marnedallei" — for FR "la vallée de la Marne / de l'Aude / du Rhône", IT "la valle del …", ES "el valle del …": a river valley is "X-vallei" or "het X-dal"; "-dallei" is not a Dutch word (it appeared in the 2026-09-14 Champagne translation).
- "polyfenolen" NOT "polyphenolen" — Dutch spells with f.
- "tanninerijk" or "rijk aan tannines" NOT "tannisch" — tannic; "tannisch" is a French borrowing not idiomatic in NL wine writing.
- "bottelen" or "flesrijping" NOT "flessenwijze" — for FR "mise en bouteille / élevage en bouteille" / ES "embotellado / crianza en botella".
- Render Spanish-pliego header transliterations like "Vinnen", "Vitwijnen", "Wijndruivenproduct" simply as "Wijnen"."""


_EN_GLOSSARY = """\
English (EN) sommelier-register vocabulary — applies whatever the source \
language. Prefer the LEFT term over the RIGHT:
- "appearance / nose / palate" NOT "visual phase / olfactory phase / gustatory phase" — for FR "phase visuelle/olfactive/gustative" or ES "fase visual/olfativa/gustativa"; these are the standard English tasting-note phase names.
- "clean" or "fault-free" (of aromas or wines) NOT "frank" — for ES "vinos francos / aromas francos" (or FR "vins francs"); "frank" carries no oenological meaning in English.
- "brick(-red)" or "tile(-red)" NOT "brick tone" or "tile tone" — for FR "tuile" / ES "teja" (the colour of aged wine).
- Render Spanish-pliego header fragments like "Wine product", "Wine product VINO", "Wine product VINO Whites and rosés" as plain "Wines" or just drop them — they are pliego template scaffolding, not titles to preserve.
- "minerality" NOT "mineralité" — for FR "minéralité"; the English word exists.
- "wine-grape varieties" or "grape varieties" NOT "must varieties" — for CZ "moštové odrůdy" / SK "muštové odrody" (the legal class of Vitis vinifera varieties authorised for winemaking).
- "style", "version" or "wine type" NOT "typology" — for IT "tipologia" (the wine types a DOC defines: Riserva, Superiore, Spumante, …).
- "actual alcohol" or "actual alcoholic strength" NOT "developed alcohol" — for IT "gradi svolti" / "alcol svolto" (the alcohol actually present, as opposed to potential).
- "carbonate soils" or "calcareous soils" NOT "carbonated soils" — for FR "sols carbonatés"; "carbonated" means fizzy.
- "vineyard sites" or "named vineyards" NOT "lege" / "dűlők" / "tratě" — for SI "lege", HU "dűlő(k)", CZ "viniční tratě" (the site word is a common noun; a site's own name stays verbatim).
- "para-barros" is a Portuguese soil-classification class (the lighter relatives of the "barros" clay soils) — keep it verbatim; never invent "proto-barros".
- "submerged cap" NOT "grillage" — for FR "grillage" (the grid that holds the cap under the surface in Beaujolais / Burgundy vats); "punch-down" for "pigeage"; "pump-over" for "remontage".
- "climat" (kept, italic-free) NOT "climate" — for the Burgundian FR "climat" meaning a named, delimited vineyard site (Les Clos, La Grande Rue); "climate" only for "climat" in its weather sense.
- "tirage" or "bottling for the second fermentation" NOT "disgorgement" — for FR "tirage" (sparkling: the bottling with liqueur de tirage; "dégorgement" is disgorgement; "à compter du tirage" = "from the date of tirage").
- "fortified wine(s)" or "generoso wine(s)" NOT "generous wine(s)" — for ES "vino generoso / vinos generosos" (the regulatory category of fortified, oxidatively aged wines: fino, amontillado, oloroso).
- "loam" NOT "clay" — for DE "Lehm" (clay is "Ton"); "loess" for "Löss"; "primary rock" or "crystalline basement" NOT "primeval rock" for "Urgestein".
- "slight sparkle" or "light spritz" NOT "spiciness" — for DE "Spritzigkeit / spritzig".
- "depth of colour" / "deep-coloured" NOT "layer" — for ES "capa" as in "capa alta / media" (colour intensity).
- "Riesling" for BG "Немски ризлинг / Рейнски ризлинг" and "Welschriesling" for "Италиански ризлинг" — never swap the two.
- "Rhodopes" (EN) for BG "Родопи" / "Rodopi"; keep "Stara Planina" as such (a one-time gloss "(Balkan Mountains)" is fine); "Bavaria" for DE "Bayern".
- A grape name is never translated by sound-alike: HU "Pintes" is the variety Pintes, not "Pinot"; HR "Plavac" stays Plavac.
- A demonym is rendered as its town, never back-formed into a place: IT "caiatino" is "of Caiazzo" (not "the Caiata area"), "aversano" is "of Aversa"."""


_GLOSSARIES: dict[str, str] = {
    "en": _EN_GLOSSARY,
    "nl": _NL_GLOSSARY,
}


def glossary_for(target_lang: str) -> str:
    """Return the glossary block for `target_lang`; empty string when none defined."""
    return _GLOSSARIES.get(target_lang, "")
