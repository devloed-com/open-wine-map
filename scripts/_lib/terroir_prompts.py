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
- Prefer bullets that carry a specific named entity or figure — a named wind, lake, river, mountain, geological formation, an altitude, area or rainfall figure, a dated event, a named practice — over general statements. The maximum given for the sub-section already allows for the length of the text; never return more.
- The causal-interactions sub-section is earned, not filled: a bullet there is admitted only when the quoted source sentence itself states the link between a terroir factor and a wine trait with an explicit connective (because, thanks to, gives, confers, results in, explains, favours, allows — or its equivalent in the source language). If the text only lists factors and wine traits side by side, return an empty list for that sub-section rather than composing the link yourself, and never restate under it a fact already given under the natural factors or the product.
- Grape names without regulatory colour codes: write "Pinot noir", never "Pinot noir N", "Chardonnay B", "Grenache G", "Gewurztraminer Rs", "Pinot gris G".
- Spell out abbreviations on first use: VT = Vendanges Tardives, SGN = Sélection de Grains Nobles, TBA = Trockenbeerenauslese.
- Never refer to the document or its sources inside a bullet: no "the specification", "the cahier", "the disciplinare", "Wikipedia", "according to the document", "confirmed by".
- Keep the source's hedges ("mainly", "mostly", "essentially", "sometimes", "often", "generally"); never strengthen them to "exclusively", "only", "always" or "100 %".
- Do not restate a fact already given in another bullet or covered by another sub-section.
- Skip statements that would be true of any appellation ("the wine's uniqueness stems from soil, climate and grape varieties", "the terroir gives the wines their typicity", "favourable soil and climatic conditions")."""


# ───────────────────────────────────────────── the sub-section bullet cap ──
#
# Each sub-section prompt states "Maximum N bullets". Until 2026-10-24 the
# allowance for a long text was a sentence in STYLE_RULES ("you may return
# up to two extra bullets") that the model had to weigh against that hard
# number — Sonnet 5.5 never used it (phase D of the 2026-10-23 validator
# review: 25 re-extractions, none over the base cap, Tokajské's 8.6 k
# characters of history held to 2 human-factor bullets), while the older
# models overshot the caps freely (948 of 1,644 caches). The code knows the
# length, so it sets the number: the regulator text the record is graded
# against (the cached leading document block — the lien, or the CH / GB /
# MT context block), measured once per record, raises the descriptive
# sub-sections; `interactions` is earned, never widened. 1,275 of the
# 1,622 measurable liens are over the threshold, so the rule is close to a
# base-cap raise; the threshold is the one the old sentence named.

LONG_TEXT_CHARS = 4000
LONG_TEXT_BONUS = {"facteurs_naturels": 2, "facteurs_humains": 2, "produit": 1, "interactions": 0}


def sub_section_cap(sub: dict, document_text: str | None) -> int:
    """The `max_bullets` a 02d script passes into one sub-section prompt (and
    writes on its `--emit-todo` item): the sub-section's base cap, raised by
    `LONG_TEXT_BONUS` when the regulator text is over `LONG_TEXT_CHARS`."""
    base = int(sub["max_bullets"])
    if len(document_text or "") > LONG_TEXT_CHARS:
        return base + LONG_TEXT_BONUS.get(sub["key"], 0)
    return base


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

from _lib.terroir_roster import children_names, record_name  # noqa: E402
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

# A translation copies the source noun's gender onto the target noun: FR "le
# vignoble" came out as NL "Het wijngaard" (42 bullets), FR "un arôme" as ES
# "una aroma … marcada", IT "il versante" as FR "les versantes". An Opus
# copy-edit of 400 sampled bullets per locale (2026-10-09) found agreement
# errors in 2.8 % of NL, 1.3 % of FR and 0.8 % of ES bullets, all but one
# written by Sonnet 4.6. English has no grammatical gender, so no rule there.
_AGREEMENT_EXAMPLES = {
    "nl": "\"de wijngaard\" for le vignoble / el viñedo, \"het gebergte\", \"een kwalitatieve wijngaard\", "
          "\"het kristallijne basement\"",
    "fr": "\"au fruit frais\", \"les versants\" for i versanti, \"les Géorgiques latines\"",
    "es": "\"el aroma\" for l'arôme / la fragranza, \"una espaldera\", \"la vertiente\", \"la era mesozoica\"",
}
_AGREEMENT = (
    "- Grammatical agreement follows TARGET, never the source: give every TARGET noun its own gender "
    "and number, and make its article, determiner, adjectives, participles and pronouns agree with it "
    "— not with the gender of the source noun it translates (EXAMPLES)."
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
    if target_lang in _AGREEMENT_EXAMPLES:
        lines.append(_AGREEMENT.replace("TARGET", target).replace("EXAMPLES", _AGREEMENT_EXAMPLES[target_lang]))
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


# ───────────────────────────── appellation context on sub-denomination pages ──
#
# A parent's bullets are inherited by its sub-denominations' pages (FR DGCs,
# ES subzonas, IT sottozone, …). "The clay-limestone soils in the northernmost
# part of the appellation, straddling Rioja Alavesa and Rioja Alta …" is
# Rioja's own sentence, but on the Rioja Alavesa page "the appellation" reads
# as Alavesa (2026-09-15). For a record that has sub-denominations the
# extraction and translation prompts therefore ask for the appellation's
# name wherever the source refers to it only generically. Per record, so it
# lives in the per-record parts of the prompts (the 02e user message, the
# 02d per-record block) — the shared, cached system prompts stay identical.

MAX_LISTED_CHILDREN = 6


def _listed(names: list[str]) -> str:
    head = ", ".join(names[:MAX_LISTED_CHILDREN])
    rest = len(names) - MAX_LISTED_CHILDREN
    return f"{head} and {rest} more" if rest > 0 else head


def appellation_context(slug: str, *, for_translation: bool) -> str:
    """The per-record instruction for a record whose bullets are also
    shown on its sub-denominations' pages; "" for a record without any."""
    kids = children_names(slug)
    if not kids:
        return ""
    name = record_name(slug) or slug
    where = "in the translation" if for_translation else "in the bullet"
    return (
        f"CONTEXT: these bullets describe «{name}» and are also shown on the pages of its "
        f"{len(kids)} sub-denominations ({_listed(kids)}). Where the source refers to the appellation "
        f"as a whole only generically — \"the appellation\", \"the denomination\", \"the DOC / DOCa / DOP\", "
        f"\"the geographical area\", \"the zone\", \"the vineyard\" — name it {where} (\"the {name} appellation\" "
        f"or \"{name}\"), so the sentence stays unambiguous on a sub-denomination page. Keep every "
        f"sub-denomination's own name exactly as it is, and never attach the parent's name to a statement "
        f"that the source makes about one sub-denomination only."
    )


def with_appellation_context(user: str, slug: str) -> str:
    """A 02e user message + the record's context (translation wording)."""
    ctx = appellation_context(slug, for_translation=True)
    return f"{user.rstrip()}\n\n{ctx}" if ctx else user


# ─────────────────────────── the request line, the product topics, the retry ──
#
# Since the prompt-caching refactor the regulator text is the LEADING cached
# block of the system prompt and the user turn carries one line; the 20
# non-FR instruction prompts still said the text was "in the user message
# below", and three of the 115 empty product replies of the
# gr-anchor-2026-10-24 run said so in as many words ("the user turn carries
# only the title"). The request line now points at the document (`ask_line`)
# and so does each script's "SOURCE 2 …" header.
#
# The product sub-section was read as a tasting note: 43 of the 107 empty
# product replies of that run explained "no organoleptic profile" on texts
# that state the wine's colour, sweetness or type (mavrodafni-kefallinias'
# "λίγες σταγόνες … μεταχρωματίζουν ένα ποτήρι λευκού οίνου"). The widened
# topics (`product_topics`, the ES wording of 2026-10-24 generalised — two
# Alicante re-extractions had returned only sentences the natural-factors
# call already gave, never the sparkling or the Moscatel ones) name the wine
# types, a variety's colour range, sweetness, ageing and the traditional
# methods, and say that a colour / sweetness / type statement is a product
# fact without a tasting note.
#
# The residue is sampling variance — the synchronous re-extraction of the
# same prompt returned both bullets — so `should_retry` asks for one second
# reading (a request line that says the first answer was empty) when a
# descriptive sub-section returns [] on a text that carries at least
# RETRY_MIN_HITS distinct stems of that sub-section's vocabulary. The
# interactions sub-section is earned and never retried; the human factors
# had no empty reply in 115.

ASK_LINES: dict[str, tuple[str, str]] = {
    "en": (
        "Sub-section to process: {label}. Work from the source text given at the very start of this "
        "prompt, before the instructions — read it in full.",
        "Sub-section to process: {label}. Second reading — the first answer for this sub-section was an "
        "empty list, yet the source text given at the very start of this prompt (before the "
        "instructions) does carry statements on this sub-section's topics. Read the whole text again "
        "and return every fact it supports for this sub-section; an empty list only if there is truly "
        "none.",
    ),
    "fr": (
        "Sous-section à traiter : {label}. Travaille à partir du texte source donné tout au début de "
        "cette consigne, avant les instructions — lis-le en entier.",
        "Sous-section à traiter : {label}. Seconde lecture — la première réponse pour cette sous-section "
        "était une liste vide, alors que le texte source donné tout au début de cette consigne (avant "
        "les instructions) contient des énoncés sur les thèmes de cette sous-section. Relis le texte en "
        "entier et renvoie chaque fait qu'il étaye pour cette sous-section ; une liste vide seulement "
        "s'il n'y en a vraiment aucun.",
    ),
    "de": (
        "Zu behandelnder Unterabschnitt: {label}. Arbeite mit dem Quelltext, der ganz am Anfang dieses "
        "Prompts vor den Anweisungen steht — lies ihn vollständig.",
        "Zu behandelnder Unterabschnitt: {label}. Zweite Lektüre — die erste Antwort für diesen "
        "Unterabschnitt war eine leere Liste, obwohl der Quelltext ganz am Anfang dieses Prompts (vor "
        "den Anweisungen) Aussagen zu den Themen dieses Unterabschnitts enthält. Lies den gesamten Text "
        "noch einmal und gib jeden Fakt zurück, den er für diesen Unterabschnitt belegt; eine leere "
        "Liste nur, wenn es wirklich keinen gibt.",
    ),
    "nl": (
        "Te behandelen subsectie: {label}. Werk vanuit de brontekst die helemaal aan het begin van deze "
        "prompt staat, vóór de instructies — lees hem volledig.",
        "Te behandelen subsectie: {label}. Tweede lezing — het eerste antwoord voor deze subsectie was "
        "een lege lijst, terwijl de brontekst helemaal aan het begin van deze prompt (vóór de "
        "instructies) wel uitspraken over de onderwerpen van deze subsectie bevat. Lees de hele tekst "
        "opnieuw en geef elk feit terug dat hij voor deze subsectie onderbouwt; een lege lijst alleen "
        "als er werkelijk geen is.",
    ),
    "es": (
        "Sub-sección a tratar: {label}. Trabaja a partir del texto fuente dado al principio mismo de "
        "esta instrucción, antes de las reglas — léelo entero.",
        "Sub-sección a tratar: {label}. Segunda lectura — la primera respuesta para esta sub-sección fue "
        "una lista vacía, aunque el texto fuente dado al principio mismo de esta instrucción (antes de "
        "las reglas) sí contiene enunciados sobre los temas de esta sub-sección. Vuelve a leer el texto "
        "completo y devuelve cada hecho que respalde para esta sub-sección; una lista vacía solo si de "
        "verdad no hay ninguno.",
    ),
    "it": (
        "Sotto-sezione da trattare: {label}. Lavora sul testo fonte riportato all'inizio di questo "
        "prompt, prima delle istruzioni — leggilo per intero.",
        "Sotto-sezione da trattare: {label}. Seconda lettura — la prima risposta per questa sotto-sezione "
        "è stata una lista vuota, eppure il testo fonte riportato all'inizio di questo prompt (prima "
        "delle istruzioni) contiene affermazioni sui temi di questa sotto-sezione. Rileggi tutto il "
        "testo e restituisci ogni fatto che esso supporta per questa sotto-sezione; una lista vuota solo "
        "se davvero non ce n'è nessuno.",
    ),
    "pt": (
        "Sub-secção a tratar: {label}. Trabalha a partir do texto fonte dado no início deste prompt, "
        "antes das instruções — lê-o por inteiro.",
        "Sub-secção a tratar: {label}. Segunda leitura — a primeira resposta para esta sub-secção foi uma "
        "lista vazia, embora o texto fonte dado no início deste prompt (antes das instruções) contenha "
        "afirmações sobre os temas desta sub-secção. Relê o texto completo e devolve cada facto que ele "
        "sustente para esta sub-secção; uma lista vazia só se realmente não houver nenhum.",
    ),
    "el": (
        "Υποενότητα προς επεξεργασία: {label}. Δούλεψε με βάση το κείμενο-πηγή που δίνεται στην αρχή "
        "αυτού του prompt, πριν από τις οδηγίες — διάβασέ το ολόκληρο.",
        "Υποενότητα προς επεξεργασία: {label}. Δεύτερη ανάγνωση — η πρώτη απάντηση για αυτή την "
        "υποενότητα ήταν κενή λίστα, ενώ το κείμενο-πηγή που δίνεται στην αρχή αυτού του prompt (πριν "
        "από τις οδηγίες) περιέχει διατυπώσεις για τα θέματα αυτής της υποενότητας. Ξαναδιάβασε "
        "ολόκληρο το κείμενο και επέστρεψε κάθε στοιχείο που τεκμηριώνει για αυτή την υποενότητα· κενή "
        "λίστα μόνο αν πράγματι δεν υπάρχει κανένα.",
    ),
    "bg": (
        "Подсекция за обработка: {label}. Работи по изходния текст, даден в самото начало на този "
        "промпт, преди указанията — прочети го изцяло.",
        "Подсекция за обработка: {label}. Второ четене — първият отговор за тази подсекция беше празен "
        "списък, а изходният текст, даден в самото начало на този промпт (преди указанията), съдържа "
        "твърдения по темите на тази подсекция. Прочети целия текст отново и върни всеки факт, който "
        "той подкрепя за тази подсекция; празен списък само ако наистина няма нито един.",
    ),
    "cs": (
        "Sledovaná podsekce: {label}. Pracuj se zdrojovým textem uvedeným na samém začátku tohoto "
        "promptu, před pokyny — přečti si ho celý.",
        "Sledovaná podsekce: {label}. Druhé čtení — první odpověď pro tuto podsekci byl prázdný seznam, "
        "přitom zdrojový text uvedený na samém začátku tohoto promptu (před pokyny) obsahuje tvrzení k "
        "tématům této podsekce. Přečti si celý text znovu a vrať každý fakt, který pro tuto podsekci "
        "dokládá; prázdný seznam jen tehdy, když skutečně žádný není.",
    ),
    "sk": (
        "Sledovaná podsekcia: {label}. Pracuj so zdrojovým textom uvedeným na samom začiatku tohto "
        "promptu, pred pokynmi — prečítaj si ho celý.",
        "Sledovaná podsekcia: {label}. Druhé čítanie — prvá odpoveď pre túto podsekciu bol prázdny "
        "zoznam, hoci zdrojový text uvedený na samom začiatku tohto promptu (pred pokynmi) obsahuje "
        "tvrdenia k témam tejto podsekcie. Prečítaj si celý text znova a vráť každý fakt, ktorý pre túto "
        "podsekciu dokladá; prázdny zoznam len vtedy, keď skutočne žiadny nie je.",
    ),
    "hr": (
        "Pododjeljak za obradu: {label}. Radi na izvornom tekstu danom na samom početku ovog prompta, "
        "prije uputa — pročitaj ga u cijelosti.",
        "Pododjeljak za obradu: {label}. Drugo čitanje — prvi odgovor za ovaj pododjeljak bio je prazan "
        "popis, a izvorni tekst dan na samom početku ovog prompta (prije uputa) sadrži tvrdnje o temama "
        "ovog pododjeljka. Ponovno pročitaj cijeli tekst i vrati svaku činjenicu koju on potkrepljuje za "
        "ovaj pododjeljak; prazan popis samo ako je doista nema.",
    ),
    "sl": (
        "Podrazdelek za obravnavo: {label}. Delaj na izvornem besedilu, podanem na samem začetku tega "
        "poziva, pred navodili — preberi ga v celoti.",
        "Podrazdelek za obravnavo: {label}. Drugo branje — prvi odgovor za ta podrazdelek je bil prazen "
        "seznam, čeprav izvorno besedilo, podano na samem začetku tega poziva (pred navodili), vsebuje "
        "trditve o temah tega podrazdelka. Znova preberi celotno besedilo in vrni vsako dejstvo, ki ga "
        "za ta podrazdelek podpira; prazen seznam le, če ga res ni.",
    ),
    "hu": (
        "Feldolgozandó alfejezet: {label}. A prompt legelején, az utasítások előtt megadott "
        "forrásszövegből dolgozz — olvasd végig teljes egészében.",
        "Feldolgozandó alfejezet: {label}. Második olvasás — az ehhez az alfejezethez adott első válasz "
        "üres lista volt, holott a prompt legelején (az utasítások előtt) megadott forrásszöveg "
        "tartalmaz állításokat az alfejezet témáiról. Olvasd újra a teljes szöveget, és add vissza "
        "minden tényt, amelyet erre az alfejezetre alátámaszt; üres listát csak akkor, ha valóban egy "
        "sincs.",
    ),
    "ro": (
        "Subsecțiunea de procesat: {label}. Lucrează pe textul sursă dat chiar la începutul acestui "
        "prompt, înaintea instrucțiunilor — citește-l în întregime.",
        "Subsecțiunea de procesat: {label}. A doua lectură — primul răspuns pentru această subsecțiune a "
        "fost o listă goală, deși textul sursă dat chiar la începutul acestui prompt (înaintea "
        "instrucțiunilor) conține afirmații despre temele acestei subsecțiuni. Recitește întregul text "
        "și returnează fiecare fapt pe care îl susține pentru această subsecțiune; o listă goală doar "
        "dacă într-adevăr nu există niciunul.",
    ),
}


def ask_line(lang: str, label: str, *, retry: bool = False) -> str:
    """The one-line user turn of a 02d sub-section call: the sub-section and a
    pointer at the document block that opens the system prompt; `retry` is the
    second reading `should_retry` asks for."""
    base, again = ASK_LINES[lang]
    return (again if retry else base).format(label=label)


_PRODUCT_TOPICS: dict[str, str] = {
    "en": (
        "colours (and the colour range of a variety), aromas, structure, acidity, sweetness level (dry, "
        "semi-sweet, sweet), alcohol, ageing and keeping, the sensory profile of the wines; the wine "
        "types the text says are made — still, sparkling, semi-sparkling, fortified or liqueur, sweet, "
        "dried-grape or late-harvest, rosé — and what distinguishes each; the traditional production "
        "methods named for the wine; historical descriptions of its taste and its reputation. A "
        "statement of a wine's colour, sweetness or type is a product fact even when the text gives no "
        "tasting note."
    ),
    "fr": (
        "couleurs (et la gamme de teintes d'un cépage), arômes, structure, acidité, niveau de sucrosité "
        "(sec, demi-doux, doux), alcool, élevage et garde, profil sensoriel des vins ; les types de vins "
        "que le texte dit produire — tranquilles, effervescents, pétillants, vins de liqueur ou mutés, "
        "doux, de raisins passerillés ou de vendanges tardives, rosés — et ce qui distingue chacun ; les "
        "méthodes de production traditionnelles nommées pour le vin ; les descriptions historiques de "
        "son goût et sa réputation. Une indication de couleur, de sucrosité ou de type de vin est un "
        "fait sur le produit même sans note de dégustation."
    ),
    "de": (
        "Farben (und die Farbspanne einer Rebsorte), Aromen, Struktur, Säure, Süßegrad (trocken, "
        "halbsüß, süß), Alkohol, Reifung und Lagerfähigkeit, sensorisches Profil der Weine; die "
        "Weintypen, die der Text nennt — Stillwein, Schaumwein, Perlwein, Likörwein, Süßwein, Wein aus "
        "eingetrockneten Trauben oder Spätlese, Roséwein — und was jeden auszeichnet; die für den Wein "
        "genannten traditionellen Herstellungsverfahren; historische Beschreibungen seines Geschmacks "
        "und sein Ruf. Eine Angabe zu Farbe, Süße oder Weintyp ist ein Fakt zum Erzeugnis, auch wenn "
        "der Text keine Verkostungsnotiz enthält."
    ),
    "nl": (
        "kleuren (en het kleurbereik van een druivenras), aroma's, structuur, zuurgraad, "
        "zoetheidsniveau (droog, halfzoet, zoet), alcohol, rijping en bewaarpotentieel, sensorisch "
        "profiel van de wijnen; de wijntypes die de tekst noemt — stille wijn, schuimwijn, parelwijn, "
        "likeurwijn, zoete wijn, wijn van ingedroogde druiven of late oogst, rosé — en wat elk "
        "onderscheidt; de voor de wijn genoemde traditionele productiemethoden; historische "
        "beschrijvingen van zijn smaak en zijn reputatie. Een vermelding van de kleur, de zoetheid of "
        "het type van een wijn is een productfeit, ook zonder proefnotitie."
    ),
    "es": (
        "colores (y la gama de tonalidades de una variedad), aromas, estructura, acidez, nivel de dulzor "
        "(seco, semidulce, dulce), alcohol, crianza y guarda, perfil sensorial de los vinos; los tipos "
        "de vino que el texto dice elaborar — tranquilos, espumosos, de aguja, de licor o generosos, "
        "dulces, de uvas pasificadas o de vendimia tardía, rosados — y lo que distingue a cada uno; los "
        "métodos de elaboración tradicionales nombrados para el vino; las descripciones históricas de su "
        "sabor y su reputación. Una indicación del color, el dulzor o el tipo de un vino es un hecho "
        "sobre el producto aun sin nota de cata."
    ),
    "it": (
        "colori (e la gamma cromatica di un vitigno), profumi, struttura, acidità, grado di dolcezza "
        "(secco, amabile, dolce), alcol, invecchiamento e longevità, profilo sensoriale dei vini; le "
        "tipologie di vino che il testo dice di produrre — fermi, spumanti, frizzanti, liquorosi, dolci, "
        "passiti o da vendemmia tardiva, rosati — e ciò che distingue ciascuna; i metodi di produzione "
        "tradizionali nominati per il vino; le descrizioni storiche del suo gusto e la sua reputazione. "
        "Un'indicazione di colore, dolcezza o tipologia di un vino è un fatto sul prodotto anche senza "
        "nota di degustazione."
    ),
    "pt": (
        "cores (e a gama de tonalidades de uma casta), aromas, estrutura, acidez, nível de doçura (seco, "
        "meio-doce, doce), álcool, estágio e guarda, perfil sensorial dos vinhos; os tipos de vinho que "
        "o texto diz produzir — tranquilos, espumantes, frisantes, licorosos ou generosos, doces, de "
        "uvas passas ou de colheita tardia, rosados — e o que distingue cada um; os métodos de produção "
        "tradicionais nomeados para o vinho; as descrições históricas do seu sabor e a sua reputação. "
        "Uma indicação da cor, da doçura ou do tipo de um vinho é um facto sobre o produto mesmo sem "
        "nota de prova."
    ),
    "el": (
        "χρώματα (και το εύρος αποχρώσεων μιας ποικιλίας), αρώματα, δομή, οξύτητα, βαθμός γλυκύτητας "
        "(ξηρός, ημίγλυκος, γλυκός), αλκοόλ, παλαίωση και αντοχή στον χρόνο, οργανοληπτικό προφίλ των "
        "οίνων· οι τύποι οίνου που το κείμενο λέει ότι παράγονται — ήσυχοι, αφρώδεις, ημιαφρώδεις, "
        "οίνοι λικέρ ή γλυκοί φυσικοί, γλυκοί, λιαστοί ή όψιμης συγκομιδής, ερυθρωποί (ροζέ) — και τι "
        "διακρίνει τον καθένα· οι παραδοσιακές μέθοδοι παραγωγής που κατονομάζονται για τον οίνο· "
        "ιστορικές περιγραφές της γεύσης του και η φήμη του. Μια δήλωση για το χρώμα, τη γλυκύτητα ή "
        "τον τύπο ενός οίνου είναι στοιχείο για το προϊόν ακόμη κι αν το κείμενο δεν δίνει γευστική "
        "περιγραφή."
    ),
    "bg": (
        "цветове (и цветовата гама на един сорт), аромати, структура, киселинност, степен на сладост "
        "(сухо, полусладко, сладко), алкохол, отлежаване и потенциал за съхранение, сензорен профил на "
        "вината; видовете вино, които текстът посочва, че се произвеждат — тихи, пенливи, искрящи, "
        "ликьорни, сладки, от стафидирано грозде или късна реколта, розе — и какво отличава всеки от "
        "тях; традиционните методи на производство, посочени за виното; исторически описания на вкуса "
        "му и репутацията му. Посочването на цвета, сладостта или вида на едно вино е факт за продукта "
        "и без дегустационна бележка."
    ),
    "cs": (
        "barvy (a barevné rozpětí odrůdy), vůně, struktura, kyselina, stupeň sladkosti (suché, "
        "polosladké, sladké), alkohol, zrání a potenciál zrání, senzorický profil vín; druhy vína, které "
        "text uvádí — tichá, šumivá, perlivá, likérová, sladká, z přezrálých či seschlých hroznů nebo "
        "pozdní sběr, růžová — a čím se každý liší; tradiční výrobní postupy uvedené pro víno; "
        "historické popisy jeho chuti a jeho pověst. Údaj o barvě, sladkosti nebo druhu vína je fakt o "
        "výrobku i bez degustační poznámky."
    ),
    "sk": (
        "farby (a farebné rozpätie odrody), vône, štruktúra, kyslosť, stupeň sladkosti (suché, "
        "polosladké, sladké), alkohol, zrenie a potenciál zrenia, senzorický profil vín; druhy vína, "
        "ktoré text uvádza — tiché, šumivé, perlivé, likérové, sladké, z prezretého či scvrknutého hrozna "
        "alebo neskorý zber, ružové — a čím sa každý odlišuje; tradičné výrobné postupy uvedené pre víno; "
        "historické opisy jeho chuti a jeho povesť. Údaj o farbe, sladkosti alebo druhu vína je fakt o "
        "výrobku aj bez degustačnej poznámky."
    ),
    "hr": (
        "boje (i raspon boja jedne sorte), arome, struktura, kiselost, stupanj slatkoće (suho, poluslatko, "
        "slatko), alkohol, dozrijevanje i potencijal starenja, senzorni profil vina; vrste vina koje "
        "tekst navodi — mirna, pjenušava, biser, likerska, slatka, od prosušenog grožđa ili kasne berbe, "
        "rosé — i što svaku razlikuje; tradicionalne metode proizvodnje navedene za vino; povijesni opisi "
        "njegova okusa i njegov ugled. Navod o boji, slatkoći ili vrsti vina činjenica je o proizvodu i "
        "bez degustacijske bilješke."
    ),
    "sl": (
        "barve (in barvni razpon sorte), arome, struktura, kislina, stopnja sladkosti (suho, polsladko, "
        "sladko), alkohol, zorenje in potencial staranja, senzorični profil vin; vrste vina, ki jih "
        "besedilo navaja — mirna, peneča, biser, likerska, sladka, iz sušenega grozdja ali pozne trgatve, "
        "rosé — in kaj vsako razlikuje; tradicionalne metode pridelave, navedene za vino; zgodovinski "
        "opisi njegovega okusa in njegov sloves. Navedba barve, sladkosti ali vrste vina je dejstvo o "
        "proizvodu tudi brez degustacijske opombe."
    ),
    "hu": (
        "színek (és egy fajta színskálája), illatok, szerkezet, savasság, édességi fokozat (száraz, "
        "félédes, édes), alkohol, érlelés és érlelhetőség, a borok érzékszervi profilja; a szövegben "
        "megnevezett bortípusok — csendes, pezsgő, gyöngyöző, likőrbor, édes, töppedt szőlőből készült "
        "vagy késői szüretelésű, rozé — és ami mindegyiket megkülönbözteti; a borra megnevezett "
        "hagyományos készítési eljárások; ízének történeti leírásai és hírneve. Egy bor színének, "
        "édességének vagy típusának megadása termékre vonatkozó tény akkor is, ha a szöveg nem ad "
        "kóstolási jegyzetet."
    ),
    "ro": (
        "culori (și gama de nuanțe a unui soi), arome, structură, aciditate, gradul de dulceață (sec, "
        "demidulce, dulce), alcool, maturare și potențial de învechire, profilul senzorial al vinurilor; "
        "tipurile de vin pe care textul spune că se produc — liniștite, spumante, perlante, licoroase, "
        "dulci, din struguri stafidiți sau cules târziu, roze — și ce le deosebește; metodele "
        "tradiționale de producție numite pentru vin; descrierile istorice ale gustului său și reputația "
        "sa. O mențiune a culorii, a dulceții sau a tipului unui vin este un fapt despre produs chiar și "
        "fără notă de degustare."
    ),
}


def product_topics(lang: str, extra: str = "") -> str:
    """The product sub-section's topic line in `lang`; `extra` (a country's
    own specifics — the UK's autolytic sparkling character, Luxembourg's
    vins vifs / vins ronds) leads it."""
    generic = _PRODUCT_TOPICS[lang]
    return f"{extra.strip().rstrip(';,')}; {generic}" if extra.strip() else generic


RETRY_SUBSECTIONS = ("facteurs_naturels", "produit")
RETRY_MIN_HITS = 3

# Casefolded stems; a text "carries the vocabulary" of a sub-section when at
# least RETRY_MIN_HITS distinct stems occur in it (substring match on the
# casefolded text — Greek final sigma and German ß fold with it).
RETRY_VOCAB: dict[str, dict[str, tuple[str, ...]]] = {
    "en": {
        "produit": ("colour", "color", "aroma", "sweet", "dry ", "sparkling", "acidity", "taste", "palate",
                    "body", "ageing", "aging", "alcohol", "fruit", "rosé", "red wine", "white wine",
                    "fortified", "still wine", "flavour", "flavor", "tannin", "bouquet", "fresh"),
        "facteurs_naturels": ("soil", "clay", "limestone", "chalk", "climate", "altitude", "rainfall",
                              "temperature", "slope", "wind", "river", "sea ", "granite", "schist", "sand",
                              "marl", "volcanic", "geolog", "elevation", "sunshine", "maritime",
                              "continental", "frost", "exposure", "aspect"),
    },
    "fr": {
        "produit": ("couleur", "robe", "arôme", "arome", "doux", "moelleux", "liquoreux", "effervescent",
                    "mousseux", "acidité", "bouche", "goût", "gout", "corps", "garde", "élevage", "alcool",
                    "fruit", "rosé", "rouge", "blanc", "tanin", "tannin", "nez", "frais", "vif"),
        "facteurs_naturels": ("sol", "argil", "calcaire", "craie", "climat", "altitude", "pluvio",
                              "précipitation", "precipitation", "température", "temperature", "pente",
                              "coteau", "vent", "rivière", "fleuve", "mer ", "granit", "schiste", "sable",
                              "marne", "volcan", "géolog", "geolog", "ensoleill", "maritime", "continental",
                              "gel", "exposition", "versant", "relief"),
    },
    "de": {
        "produit": ("farbe", "aroma", "süß", "trocken", "halbtrocken", "lieblich", "schaumwein", "sekt",
                    "perlwein", "säure", "geschmack", "körper", "reifung", "lagerfähig", "alkohol", "frucht",
                    "rosé", "rotwein", "weißwein", "weisswein", "likörwein", "tannin", "gerbstoff", "bukett",
                    "mineral"),
        "facteurs_naturels": ("boden", "lehm", "kalk", "schiefer", "klima", "höhe", "niederschlag", "regen",
                              "temperatur", "hang", "steillage", "wind", "fluss", "rhein", "mosel", "donau",
                              "granit", "sand", "mergel", "löss", "vulkan", "geolog", "sonnen", "frost",
                              "exposition", "lage", "relief"),
    },
    "nl": {
        "produit": ("kleur", "aroma", "zoet", "droog", "halfzoet", "schuimwijn", "mousserend", "parelwijn",
                    "zuur", "smaak", "body", "rijping", "bewaar", "alcohol", "fruit", "rosé", "rode wijn",
                    "witte wijn", "likeurwijn", "tannine", "fris", "mineraal"),
        "facteurs_naturels": ("bodem", "klei", "leem", "kalk", "krijt", "klimaat", "hoogte", "neerslag",
                              "regen", "temperatuur", "helling", "wind", "rivier", "maas", "zee", "graniet",
                              "leisteen", "zand", "mergel", "löss", "loess", "vulkan", "geolog", "zon",
                              "maritiem", "continentaal", "vorst", "expositie", "reliëf", "relief"),
    },
    "es": {
        "produit": ("color", "aroma", "dulce", "seco", "semidulce", "espumoso", "aguja", "acidez", "sabor",
                    "boca", "cuerpo", "crianza", "guarda", "envejec", "alcoh", "frut", "rosado", "tinto",
                    "blanco", "licor", "generoso", "tanino", "fresc", "mineral", "nariz"),
        "facteurs_naturels": ("suelo", "arcill", "caliz", "calcár", "calcar", "clima", "altitud", "altura",
                              "precipitac", "lluvia", "pluviom", "temperatura", "pendiente", "ladera",
                              "viento", "río", "rio ", "mar ", "granit", "pizarra", "esquisto", "arena",
                              "arenis", "marga", "volcán", "volcan", "geolog", "insolac", "marítimo",
                              "maritimo", "continental", "helada", "exposic", "orientac", "relieve", "monta",
                              "sierra", "valle"),
    },
    "it": {
        "produit": ("colore", "profum", "aroma", "dolce", "secco", "amabile", "abboccato", "spumante",
                    "frizzante", "acidit", "sapore", "gusto", "bocca", "corpo", "invecchiam", "affinam",
                    "alcol", "frutt", "rosato", "rosso", "bianco", "liquoroso", "passito", "tannin", "fresc",
                    "mineral", "sapid", "naso"),
        "facteurs_naturels": ("suolo", "terreno", "argill", "calcar", "clima", "altitudine", "altimetr",
                              "quota", "precipitaz", "piogg", "pluviom", "temperatura", "pendenza", "pendio",
                              "collin", "vento", "fiume", "mare", "lago", "granit", "scist", "sabbi", "marn",
                              "vulcan", "geolog", "insolaz", "soleggi", "marittimo", "continentale", "gelat",
                              "esposizion", "giacitura", "rilievo", "mont", "valle"),
    },
    "pt": {
        "produit": ("cor ", "cores", "aroma", "doce", "seco", "meio-doce", "espumante", "frisante", "acidez",
                    "sabor", "boca", "corpo", "estágio", "estagio", "envelhec", "guarda", "álcool", "alcool",
                    "frut", "rosado", "rosé", "tinto", "branco", "licoroso", "generoso", "tanin", "fresc",
                    "mineral", "nariz"),
        "facteurs_naturels": ("solo", "argil", "calcár", "calcar", "clima", "altitude", "precipita", "chuva",
                              "pluvio", "temperatura", "encosta", "declive", "vento", "rio ", "mar ",
                              "granit", "xisto", "arei", "marga", "vulcân", "vulcan", "geolog", "insola",
                              "marítim", "maritim", "atlântic", "atlantic", "continental", "geada", "exposi",
                              "relevo", "serra", "vale", "planalto"),
    },
    "el": {
        "produit": ("χρώμ", "χρωμ", "άρωμ", "αρωμ", "γλυκ", "ξηρ", "ημίγλυκ", "ημιγλυκ", "αφρώδ", "αφρωδ",
                    "ημιαφρ", "οξύτητ", "οξυτητ", "γεύσ", "γευσ", "σώμα", "σωμα", "παλαίωσ", "παλαιωσ",
                    "αλκοολ", "φρούτ", "φρουτ", "ερυθρ", "λευκ", "ροζέ", "ροζε", "λικέρ", "λικερ", "λιαστ",
                    "τανίν", "τανιν", "φρεσκ", "ορυκτ", "επίγευσ", "επιγευσ"),
        "facteurs_naturels": ("έδαφ", "εδαφ", "άργιλ", "αργιλ", "ασβεστ", "κλίμα", "κλιμα", "υψόμετρ",
                              "υψομετρ", "βροχ", "θερμοκρασ", "πλαγι", "κλίσ", "κλισ", "άνεμ", "ανεμ",
                              "μελτέμ", "μελτεμ", "ποταμ", "θάλασσ", "θαλασσ", "λίμν", "λιμν", "γρανίτ",
                              "γρανιτ", "σχιστόλ", "σχιστολ", "αμμ", "μάργ", "μαργ", "ηφαιστ", "γεωλογ",
                              "ηλιοφ", "ηπειρωτ", "παγετ", "έκθεσ", "εκθεσ", "προσανατολ", "ανάγλυφ",
                              "αναγλυφ", "ορειν", "βουν", "κοιλάδ", "κοιλαδ"),
    },
    "bg": {
        "produit": ("цвят", "цвет", "аромат", "сладк", "сухо", "сухи", "полусладк", "пенлив", "искрящ",
                    "киселин", "вкус", "тяло", "отлежав", "стареене", "алкохол", "плод", "розе", "червен",
                    "бял", "бели", "ликьор", "танин", "свеж", "минерал", "букет"),
        "facteurs_naturels": ("почв", "глин", "варовик", "карбонат", "климат", "височина", "надморск",
                              "валеж", "дъжд", "температур", "склон", "наклон", "вятър", "ветров", "река",
                              "море", "морск", "гранит", "шист", "пясъ", "песъчлив", "мергел", "льос",
                              "вулкан", "геолог", "слънч", "континентал", "мраз", "студ", "изложение",
                              "експозиц", "релеф", "планин", "хълм", "долин", "низин", "равнин"),
    },
    "cs": {
        "produit": ("barv", "vůn", "aroma", "sladk", "such", "polosladk", "šumiv", "perliv", "kyselin",
                    "chuť", "tělo", "zrání", "archiv", "alkohol", "ovoc", "růžov", "červen", "bílé", "bílá",
                    "likér", "tanin", "svěž", "mineral"),
        "facteurs_naturels": ("půd", "jíl", "vápen", "opuk", "slín", "klima", "podneb", "nadmořsk", "výšk",
                              "srážk", "dešť", "teplot", "svah", "sklon", "vítr", "větr", "řek", "moře",
                              "žul", "břidl", "písč", "spraš", "čedič", "geolog", "slune", "kontinent", "mráz",
                              "expozic", "orientac", "reliéf", "vrch", "údol", "kopc"),
    },
    "sk": {
        "produit": ("farb", "vôň", "aróm", "arom", "sladk", "such", "polosladk", "šumiv", "perliv", "kyselin",
                    "chuť", "telo", "zreni", "archív", "alkohol", "ovoc", "ružov", "červen", "biel", "likér",
                    "tanín", "svieži", "minerál", "buket"),
        "facteurs_naturels": ("pôd", "hlin", "vápen", "klíma", "klim", "podneb", "nadmorsk", "výšk", "zrážk",
                              "dážď", "teplot", "svah", "sklon", "vietor", "vetr", "riek", "more", "žul",
                              "bridl", "pies", "spraš", "andezit", "vulkan", "sopeč", "geolog", "slne",
                              "kontinent", "mráz", "expozíc", "orientác", "reliéf", "vrch", "údol", "kopc",
                              "pohor"),
    },
    "hr": {
        "produit": ("boj", "arom", "miris", "slatk", "suh", "polusuh", "poluslatk", "pjenu", "biser", "kisel",
                    "okus", "tijel", "dozrijev", "starenj", "alkohol", "voć", "rosé", "ruž", "crn", "crven",
                    "bijel", "liker", "desertn", "tanin", "svjež", "mineral"),
        "facteurs_naturels": ("tlo", "zemljišt", "glin", "vapnen", "lapor", "fliš", "crvenic", "klim",
                              "nadmorsk", "visin", "oborin", "kiš", "padalin", "temperatur", "padin", "nagib",
                              "vjetar", "bura", "jugo", "rijek", "mor", "jezer", "granit", "škriljav", "pijes",
                              "vulkan", "geolog", "sunč", "osunč", "kontinent", "mraz", "ekspozic",
                              "izloženost", "reljef", "brd", "brijeg", "dolin", "planin"),
    },
    "sl": {
        "produit": ("barv", "arom", "vonj", "sladk", "suh", "polsuh", "polsladk", "peneč", "biser", "kisl",
                    "okus", "telo", "zoren", "staran", "alkohol", "sadj", "rosé", "rose", "rdeč", "bel",
                    "liker", "desertn", "tanin", "svež", "mineral"),
        "facteurs_naturels": ("tla", "prst", "glin", "apnen", "lapor", "fliš", "klim", "podneb", "nadmorsk",
                              "višin", "padavin", "dež", "temperatur", "pobočj", "naklon", "lega", "veter",
                              "burja", "rek", "morj", "jezer", "granit", "skrilav", "pešč", "pesk", "vulkan",
                              "geolog", "sonč", "osonč", "kontinent", "zmrzal", "ekspozic", "relief", "grič",
                              "hrib", "dolin", "gor"),
    },
    "hu": {
        "produit": ("szín", "illat", "aroma", "édes", "száraz", "félédes", "félszáraz", "pezsgő",
                    "gyöngyöző", "habzó", "sav", "íz", "test", "érlel", "érett", "alkohol", "gyümölcs",
                    "rozé", "rosé", "vörös", "fehér", "siller", "likőr", "aszú", "tannin", "friss", "ásvány",
                    "minerál"),
        "facteurs_naturels": ("talaj", "agyag", "mész", "lösz", "homok", "márga", "riolit", "andezit",
                              "bazalt", "vulkán", "vulkan", "éghajlat", "klíma", "klima", "magasság",
                              "tengerszint", "csapadék", "eső", "hőmérséklet", "lejtő", "domb", "hegy",
                              "szél", "folyó", "duna", "tisza", "balaton", "tava", "gránit", "pala", "geológ",
                              "napsüt", "napfény", "kontinentális", "fagy", "kitettség", "fekvés", "expozíc",
                              "völgy", "medence", "fennsík", "rendzina", "erdőtalaj", "csernozj", "nyirok"),
    },
    "ro": {
        "produit": ("culo", "arom", "dulce", "sec", "demisec", "demidulce", "spumant", "perlant", "acidit",
                    "gust", "corp", "învech", "invech", "matur", "alcool", "fruct", "roze", "rosé", "roșu",
                    "rosu", "roși", "alb", "licor", "tanin", "prosp", "mineral", "buchet", "catifel"),
        "facteurs_naturels": ("sol ", "solu", "argil", "calcar", "cernoziom", "loess", "nisip", "marn",
                              "vulcan", "clim", "altitudin", "precipita", "ploi", "ploa", "temperatur",
                              "pant", "versant", "deal", "coli", "vânt", "vant", "râu", "dunăr", "dunar",
                              "mare", "lac", "granit", "șist", "sist", "geolog", "însor", "insor", "soar",
                              "continental", "înghe", "inghe", "expozi", "orientar", "relief", "pod", "munț",
                              "munt", "vale", "văi"),
    },
}


def retry_hits(sub_key: str, lang: str, text: str) -> list[str]:
    """The distinct vocabulary stems of `sub_key` (in `lang`) the text carries."""
    stems = RETRY_VOCAB.get(lang, {}).get(sub_key, ())
    if not stems or not text:
        return []
    low = text.casefold()
    return sorted({s for s in stems if s.casefold() in low})


def should_retry(sub_key: str, lang: str, text: str) -> bool:
    """Whether an empty answer for `sub_key` deserves the second reading: a
    descriptive sub-section (never `interactions`, never the human factors)
    on a text that carries at least RETRY_MIN_HITS of its stems."""
    return sub_key in RETRY_SUBSECTIONS and len(retry_hits(sub_key, lang, text)) >= RETRY_MIN_HITS
