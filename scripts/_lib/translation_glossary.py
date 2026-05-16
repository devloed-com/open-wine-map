"""Per-target-locale vocabulary preferences for stage 02c/02e translation.

Steers translation models away from awkward literals and toward the
sommelier register that target-locale wine writing actually uses.
Glossaries are target-locale keyed; entries only exist where the corpus
showed recurring problems. Append the returned block to a translation
SYSTEM_PROMPT under a blank-line separator; an empty return makes the
append a no-op for locales without curated guidance.

Curated for NL and EN based on a sweep of the existing FR + ES → target
corpus (~6850 terroir-fact bullets and ~340 ollama-translated summaries
per target). ES and FR targets were probed and showed no recurring
issues worth a rule today — Mistral handles FR↔ES cleanly, and the few
suspicious-looking FR phrases ("phase visuelle", "vins francs") turn out
to be legitimate French wine vocabulary.
"""

from __future__ import annotations

_NL_GLOSSARY = """\
Dutch (NL) sommelier-register vocabulary — applies to translations from \
both French and Spanish source. Prefer the LEFT term over the RIGHT:
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
- "polyfenolen" NOT "polyphenolen" — Dutch spells with f.
- "tanninerijk" or "rijk aan tannines" NOT "tannisch" — tannic; "tannisch" is a French borrowing not idiomatic in NL wine writing.
- "bottelen" or "flesrijping" NOT "flessenwijze" — for FR "mise en bouteille / élevage en bouteille" / ES "embotellado / crianza en botella".
- Render Spanish-pliego header transliterations like "Vinnen", "Vitwijnen", "Wijndruivenproduct" simply as "Wijnen"."""


_EN_GLOSSARY = """\
English (EN) sommelier-register vocabulary — applies to translations from \
both French and Spanish source. Prefer the LEFT term over the RIGHT:
- "appearance / nose / palate" NOT "visual phase / olfactory phase / gustatory phase" — for FR "phase visuelle/olfactive/gustative" or ES "fase visual/olfativa/gustativa"; these are the standard English tasting-note phase names.
- "clean" or "fault-free" (of aromas or wines) NOT "frank" — for ES "vinos francos / aromas francos" (or FR "vins francs"); "frank" carries no oenological meaning in English.
- "brick(-red)" or "tile(-red)" NOT "brick tone" or "tile tone" — for FR "tuile" / ES "teja" (the colour of aged wine).
- Render Spanish-pliego header fragments like "Wine product", "Wine product VINO", "Wine product VINO Whites and rosés" as plain "Wines" or just drop them — they are pliego template scaffolding, not titles to preserve."""


_GLOSSARIES: dict[str, str] = {
    "en": _EN_GLOSSARY,
    "nl": _NL_GLOSSARY,
}


def glossary_for(target_lang: str) -> str:
    """Return the glossary block for `target_lang`; empty string when none defined."""
    return _GLOSSARIES.get(target_lang, "")
