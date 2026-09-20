"""Prompt fragments shared by the 21 stage-02d extraction scripts.

Every country's `EXTRACT_SYSTEM` is written in its own source language,
which kept the *style* rules from being maintained in one place: arrows,
regulatory colour codes ("Pinot noir N"), unexpanded VT / SGN, bullets
that mention "the document", hedges strengthened to "exclusively", and
one sentence restated by three sub-section calls all slipped through
(2026-09-11 review). `STYLE_RULES` is one English block — the models read
it fine inside a Greek or Bulgarian prompt — and `with_style_rules`
splices it in front of the prompt's final paragraph (the JSON-only
instruction), so every script carries the same rules.

The block opens with the claim-support rule — the gate's own definition
of an over-claim (a causal wrapper on a co-occurrence, a narrowed
attribution, an invented qualifier, a sibling's statement, a
strengthened hedge) — so the extractor does the gate's job first: the
gate rewrote 27 % of the r1 bullets, 44 % of them light edits.
"""

from __future__ import annotations

STYLE_RULES = """\
Claim-support rule — it comes first and every bullet is checked against it afterwards by a verifier that reads the whole source:
- A bullet asserts only what its quoted sentence itself states — every entity, number, unit, direction, spatial or temporal qualifier, hedge and causal link in the bullet must be in the quote. Concretely: never turn the mere presence of a factor into a cause ("volcanic soils give the wine minerality" is admissible only when the source says the soils give it — otherwise write "the soils are volcanic"); never credit one factor with what the source credits to several, and never narrow an attribution the source makes en bloc ("soils, climate and exposure" stays all three); never add a spatial or temporal qualifier ("on the upper slopes", "since the 1960s") the source does not give; never move a statement about a sub-zone, a single site or a neighbouring appellation onto the appellation as a whole; never strengthen or drop a hedge. When the sentence you would like to write goes beyond what the quote supports, write the narrower sentence the quote does support — or leave the fact out.

Style rules (they apply whatever the language of the bullets):
- One fact per bullet, written as one full sentence that ends with a period. No arrows (→), no label prefixes such as "Colour:", "Climate:", "Soils:".
- A bullet is a complete sentence of roughly 120–220 characters. Never compress it into a telegraphic fragment ("Roero (syn. Tanaro)", "Climate: avg 9.8 °C"); a qualifier, a hedge or a spatial attribution is never dropped to save space — write the longer precise sentence instead.
- Prefer bullets that carry a specific named entity or figure — a named wind, lake, river, mountain, geological formation, an altitude, area or rainfall figure, a dated event, a named practice — over general statements. When the text you are given is long (over ~4,000 characters) and describes more such specifics than the maximum allows, you may return up to two extra bullets.
- The causal-interactions sub-section is earned, not filled: a bullet there is admitted only when the quoted source sentence itself states the link between a terroir factor and a wine trait with an explicit connective (because, thanks to, gives, confers, results in, explains, favours, allows — or its equivalent in the source language). If the text only lists factors and wine traits side by side, return an empty list for that sub-section rather than composing the link yourself, and never restate under it a fact already given under the natural factors or the product.
- Grape names without regulatory colour codes: write "Pinot noir", never "Pinot noir N", "Chardonnay B", "Grenache G", "Gewurztraminer Rs", "Pinot gris G".
- Spell out abbreviations on first use: VT = Vendanges Tardives, SGN = Sélection de Grains Nobles, TBA = Trockenbeerenauslese.
- Never refer to the document or its sources inside a bullet: no "the specification", "the cahier", "the disciplinare", "Wikipedia", "according to the document", "confirmed by".
- Keep the source's hedges ("mainly", "mostly", "essentially", "sometimes", "often", "generally"); never strengthen them to "exclusively", "only", "always" or "100 %".
- Do not restate a fact already given in another bullet or covered by another sub-section.
- Skip statements that would be true of any appellation ("the wine's uniqueness stems from soil, climate and grape varieties", "the terroir gives the wines their typicity", "favourable soil and climatic conditions")."""


def with_style_rules(prompt):
    """Return `prompt` (a str, or a {lang: str} dict) with `STYLE_RULES`
    inserted before its final paragraph — the JSON-only instruction that
    every extraction prompt ends with."""
    if isinstance(prompt, dict):
        return {k: with_style_rules(v) for k, v in prompt.items()}
    head, sep, tail = prompt.rpartition("\n\n")
    if not sep:
        return prompt + "\n\n" + STYLE_RULES
    return f"{head}\n\n{STYLE_RULES}\n\n{tail}"


# ───────────────────────────────────── stage-02e translation rules (W1) ──
#
# The 21 stage-02e translation scripts each carried one long
# "Preserve <Language> proper nouns verbatim: …" line whose roster mixed
# real names (Barolo, Xinomavro, Muschelkalk) with common nouns (argille,
# lösz, ЗНП, dűlő, kasna berba) — so the common nouns leaked untranslated
# into every target locale (16 % of all bullets, 37–51 % for GR/BG/HU/CZ/
# HR/LU in the 2026-09-11 review). `translation_rules` is the one shared
# two-bucket rule block; each script keeps only its *names* roster and
# passes it in as `proper_nouns`. Plain text, no `{` / `}` anywhere, so a
# script that still pushes its prompt through `str.format` cannot break.

from _lib.translation_glossary import glossary_for  # noqa: E402

_LANG_NAME = {
    "en": "English", "fr": "French", "es": "Spanish", "nl": "Dutch", "de": "German",
    "it": "Italian", "pt": "Portuguese", "el": "Greek", "bg": "Bulgarian", "hu": "Hungarian",
    "cs": "Czech", "sk": "Slovak", "sl": "Slovenian", "hr": "Croatian", "ro": "Romanian",
    "mt": "Maltese",
}

_NON_LATIN_SOURCES = ("el", "bg")

_KEEP_VERBATIM = (
    "- Keep verbatim (these are names, not vocabulary): appellation names exactly as "
    "registered, even when they coincide with a region (Toscana IGT, Bourgogne, Alsace grand "
    "cru Rangen, Wien DAC); commune and vineyard-site names; institutions (Junta de "
    "Andalucía, Consorzio); grape variety names, including those built on a place (Melon de "
    "Bourgogne), transliterated to the EU-official Latin form when the source script is not "
    "Latin; NAMED geological formations and named winds "
    "(Marnes à exogyra virgula, Flysch di Cormons, llicorella, albariza, tuffeau, Muschelkalk, "
    "Rotliegend, Mistral, Bora, Meltemi); registered traditional terms and Prädikat tiers "
    "(Aszú, Szamorodni, Vinsanto, Nychteri, tokajský výber, Trockenbeerenauslese, "
    "Vendanges Tardives, Sélection de Grains Nobles)."
)

_GEOGRAPHY = (
    "- Geography takes the established TARGET name whenever one exists — countries, regions "
    "used as places, mountain ranges, rivers, lakes and seas are vocabulary, not labels: "
    "Vosges → Vogezen (Dutch) / Vosgos (Spanish); Rhin, Rhein → Rijn / Rhine / Rin; Donau → "
    "Danube / Donau; Appennino → Apennines / Apennijnen / Apeninos; Méditerranée, Mediterraneo → "
    "Mediterranean / Middellandse Zee / Mediterráneo; Atlantique → Atlantic / Atlantische Oceaan; "
    "Toscana → Tuscany / Toscane when it names the region (verbatim only as the appellation); "
    "Piemonte → Piedmont / Piëmont / Piamonte; Sicilia → Sicily / Sicilië / Sicile; Sardegna → "
    "Sardinia / Sardinië / Sardaigne / Cerdeña; Bourgogne → Burgundy / Bourgondië / Borgoña as "
    "the region; Alsace → Elzas / Alsacia as the region; Wien → Vienna / Wenen / Vienne / Viena "
    "as the city; Steiermark → Styria / Stiermarken / Styrie / Estiria; Danube Plain → Danubian "
    "Plain / Donauvlakte / Llanura del Danubio / plaine du Danube. When the target language "
    "has no established form, keep the source form."
)

_TRANSLATE_INTO = (
    "- Translate into TARGET everything else — in particular these common nouns, which are "
    "NOT names and must never be left in the source language: generic soil and rock words "
    "(argille, calcare, marne, arenaria, scisti, calcareniti, argilliti; lösz, mészkő, homokkő, "
    "agyagpala, barna erdőtalaj, csernozjom, vulkáni talaj; льос, чернозем, канелена горска "
    "почва, смолница; vapnenac, crvenica, fliš, apnenec, ilovica, laporovec, lapor; xisto; "
    "Lehm, Quarzit, Gneis, Granit, Urgestein, Vulkangestein, Steillage, Lagenwein; leem, klei, "
    "zandleem, mergel; gypse, marnes keupériennes, calcaire conchylien); climate phrases "
    "(умереноконтинентален климат, μεσογειακό κλίμα, ηπειρωτικό κλίμα, kontinentalna klima, "
    "kontinentální podnebí, pannonisches Klima); generic harvest and wine-law categories "
    "(kasna berba, desertno vino, predikatno vino, pozna trgatev, ledeno vino, suhi jagodni "
    "izbor, pozdní sběr, slámové víno, αφρώδεις οίνοι, λιαστοί οίνοι, pezsgő, gyöngyözőbor, "
    "vendemmia, fruttaia); site words (lege, dűlő, viniční trať, podgorie, borvidék, vinorodni "
    "okoliš, ribera, páramo, gromače, emparrado); scheme abbreviations (ΠΓΕ / ΠΟΠ / ЗНП / ЗГУ / "
    "OEM / OFJ / CHOP / CHZO / ZOI become PDO / PGI in their TARGET form)."
)

_GLOSS_ONCE = (
    "- A one-time gloss of a genuinely technical local term is allowed — the TARGET word first, "
    "the local word once in parentheses, the way \"boulder clay (keileem)\" or \"dry-stone walls "
    "(prizidi)\" does it. Never the reverse (\"Continental (ηπειρωτικό κλίμα)\")."
)

_LATIN_SCRIPT = (
    "- The output must be entirely in Latin script. Transliterate Greek and Cyrillic proper "
    "nouns to the EU-official Latin form (Ξινόμαυρο → Xinomavro, Стара планина → Stara Planina, "
    "Гъмза → Gamza, Σαντορίνη → Santorini); the eAmbrosia transcription and the grape lexicon's "
    "Latin slugs are the reference spellings."
)

_STYLE = (
    "- Drop regulatory colour-code suffixes after grape names (N / B / G / Rs / Rg): write "
    "\"Pinot noir\", never \"Pinot noir N\".\n"
    "- End every bullet with a period.\n"
    "- Keep the source's hedges (mainly / mostly / sometimes / often / generally); never "
    "strengthen them to exclusively / only / always / 100 %."
)


def translation_rules(source_lang: str, target_lang: str, *, proper_nouns: str) -> str:
    """The shared two-bucket terminology block for a 02e system prompt.

    `proper_nouns` is the country's own *names* roster (appellations,
    regions, communes, grapes, named formations / winds, registered
    terms) — may be empty. The returned text contains no `{` / `}`."""
    source = _LANG_NAME.get(source_lang, source_lang)
    target = _LANG_NAME.get(target_lang, target_lang)
    keep = _KEEP_VERBATIM
    roster = (proper_nouns or "").strip().replace("{", "(").replace("}", ")")
    if roster:
        keep += " In this corpus: " + roster.rstrip(".") + "."
    lines = [
        f"Terminology rules ({source} → {target}):",
        keep,
        _GEOGRAPHY.replace("TARGET", target),
        _TRANSLATE_INTO.replace("TARGET", target),
        _GLOSS_ONCE.replace("TARGET", target),
    ]
    if source_lang in _NON_LATIN_SOURCES:
        lines.append(_LATIN_SCRIPT)
    lines.append(_STYLE)
    return "\n".join(lines)


def translation_system_prompt(
    base: str, *, source_lang: str, target_lang: str, proper_nouns: str,
) -> str:
    """`base` (already formatted) + the shared rules + the target-locale
    glossary (`translation_glossary.glossary_for`, when non-empty)."""
    parts = [base, translation_rules(source_lang, target_lang, proper_nouns=proper_nouns)]
    glossary = glossary_for(target_lang)
    if glossary:
        parts.append(glossary)
    return "\n\n".join(parts)
