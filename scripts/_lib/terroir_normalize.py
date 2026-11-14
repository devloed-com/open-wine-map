"""Deterministic clean-up of terroir-fact bullets (stage-04 render + the
`normalize_terroir_facts.py` cache post-pass).

Three mechanical defects the 2026-09-11 review found in 8–12 % of bullets,
none of which needs a model to fix:

- regulatory colour codes copied from the cahier's grape roster
  ("Pinot noir N", "Riesling B", "Gewurztraminer Rs") — stripped when the
  preceding words resolve to a grape in the lexicon, so a stray capital
  after a place name is left alone;
- the INAO mentions "VT" / "SGN" left unexpanded — spelled out;
- no terminal punctuation — a period is appended;
- residual Greek / Cyrillic script in a Latin-target translation: a
  homoglyph inside a Latin word ("Thermoheliоhydric" with a Cyrillic о,
  "Piniatorοs" with a Greek ο) is mapped to its Latin lookalike, and a
  whole non-Latin token left as a gloss ("(ξερολιθιές)", "(смолница)",
  "Мискет врачански") is transliterated with unidecode. Only applied to
  the four target locales, only when the bullet is predominantly Latin
  (a Greek source bullet rendered untranslated is left alone), and never
  to a Greek-letter chemical prefix ("α-terpineol").

- a reference to the document itself — the regulator text the bullet was
  extracted from or the Wikipedia article — at the opening ("Según el
  pliego, …", "Il disciplinare afferma che …", "A Wikipedia szerint …"),
  at the end (", selon le cahier des charges.") or alone in brackets
  ("(según el pliego)"): the reference is cut and the claim kept
  (`strip_document_reference`). A Dutch or German fronted reference
  ("Volgens het productdossier zijn de …", "… stelt dat …") is not cut —
  dropping it would leave the finite verb before the subject — and goes
  back to 02e; `document_reference` reports it, and reports as `mid` the
  forms that need rewording (a mid-sentence "como señala el pliego", the
  document as the agent of a verb, any other mention of Wikipedia). A
  source's own attribution ("according to Strabo", "Σύμφωνα με τον μύθο")
  names no document and is never touched.

Arrows and label prefixes are left to a targeted re-extraction under the
prompt rules in `terroir_prompts`: they need rewording, not a regex.
"""

from __future__ import annotations

import re

from unidecode import unidecode

from _lib import grape_entity, grape_lexicon

COLOUR_CODES = ("N", "B", "G", "Rs", "Rg")
_CODE_RE = re.compile(r"(?:\s+|\s*\()(N|B|G|Rs|Rg)\)?(?=[\s,;:.)\]/]|$)")
# apostrophes split ("l'ugni blanc" → l / ugni / blanc) so the elided article never hides a name
_WORD_RE = re.compile(r"[\w\-]+", re.UNICODE)
_MAX_NAME_WORDS = 4

_EXPANSIONS = [
    (re.compile(r"\bVT\s*/\s*SGN\b"), "Vendanges Tardives / Sélection de Grains Nobles"),
    (re.compile(r"\bVT\b"), "Vendanges Tardives"),
    (re.compile(r"\bSGN\b"), "Sélection de Grains Nobles"),
]
_TERMINAL = ".!?…"
_TARGET_LOCALES = ("en", "fr", "es", "nl")
_NON_LATIN = re.compile(r"[Ѐ-ӿͰ-Ͽ\u1F00-\u1FFF]")  # Cyrillic, Greek, Greek Extended (polytonic)
_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)
_CHEM_PREFIX = re.compile(r"(?:^|['’(«\"])[αβγδ]-\w")  # also after an elided article: "l'α-terpinéol"
_HOMOGLYPH = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j",
    "к": "k", "м": "m", "т": "t", "н": "n", "в": "v", "ѕ": "s", "ԁ": "d", "ԛ": "q",
    "А": "A", "Е": "E", "О": "O", "Р": "P", "С": "C", "У": "Y", "Х": "X", "І": "I", "Ј": "J",
    "К": "K", "М": "M", "Т": "T", "Н": "H", "В": "B", "Ѕ": "S",
    "ο": "o", "ς": "s", "σ": "s", "α": "a", "ε": "e", "ι": "i", "κ": "k", "ν": "n", "ρ": "p",
    "τ": "t", "υ": "u", "χ": "x", "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I",
    "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
})
_HOMOGLYPH_CHARS = {chr(k) for k in _HOMOGLYPH}


_VOCAB = None


def _is_grape(name: str) -> bool:
    """True when `name` is a known variety surface: the grape matcher's exact
    index (VIVC prime names + synonyms + the lexicon) first, then the
    lexicon tables for surfaces the index does not carry."""
    global _VOCAB
    if _VOCAB is None:
        _VOCAB = grape_entity._load_vocabulary()
    if grape_entity._normalise(name) in _VOCAB.exact_index:
        return True
    slug = grape_lexicon._canonical_slug(name)
    return bool(slug) and (slug in grape_lexicon.DEFAULT_COLOUR or slug in grape_lexicon.GRAPE_ALIAS)


def strip_colour_codes(bullet: str) -> str:
    """Remove ` N` / ` B` / ` G` / ` Rs` / ` Rg` (also `(B)`) after a grape name."""
    out = bullet
    pos = 0
    while True:
        m = _CODE_RE.search(out, pos)
        if not m:
            return out
        before = out[: m.start()]
        words = _WORD_RE.findall(before)[-_MAX_NAME_WORDS:]
        hit = any(_is_grape(" ".join(words[i:])) for i in range(len(words)))
        if hit:
            out = before + out[m.end():]
            pos = m.start()
        else:
            pos = m.end()


def expand_mentions(bullet: str) -> str:
    for rx, full in _EXPANSIONS:
        bullet = rx.sub(full, bullet)
    return bullet


# A bullet that ends by citing its own source — ", secondo il disciplinare."
# — despite the prompt's rule; the clause is dropped, the fact stays.
_TRAILING_META_RE = re.compile(
    r"[,;]?\s+(?:secondo (?:il|quanto (?:previsto|indicato|riportato) (?:dal|nel)) disciplinare"
    r"|come (?:indicato|previsto|riportato) (?:dal|nel) disciplinare"
    r"|selon le cahier des charges|comme (?:l'indique|le précise|le prévoit) le cahier des charges"
    r"|según (?:el|lo (?:establecido|indicado) en el) pliego(?: de condiciones)?"
    r"|laut (?:der |dem )?(?:produktspezifikation|einzige[nm] dokument)"
    r"|gemäß (?:der |dem )?(?:produktspezifikation|einzige[nm] dokument)"
    r"|volgens het (?:productdossier|enig document)|conform het (?:productdossier|enig document)"
    r"|segundo o caderno(?: de especificações)?|de acordo com o caderno(?: de especificações)?"
    r"|(?:according to|as (?:stated|set out|indicated) in) the (?:production |product )?(?:specification|document|cahier|disciplinare|pliego)"
    r"|selon le (?:document unique|pliego)|según el documento único|laut (?:dem )?(?:einzigen dokument|produktdossier))"
    r"\s*(?=[.!?…]?\s*$)",
    re.IGNORECASE,
)


def strip_trailing_meta(bullet: str) -> str:
    return _TRAILING_META_RE.sub("", bullet or "")


# ── document self-references (2026-10-25) ────────────────────────────────
# The do-not-claim escape "unless the source states it explicitly" was
# answered by naming the source ("Según el pliego, se cree que …", La Palma)
# and the gate graded the claim, which is supported. Only the regulator
# document and Wikipedia count: "según el estudio de …", "according to
# Strabo", "Σύμφωνα με τον μύθο" are the source's own attributions.
# The document nouns, as the sources and the four translations write them
# (EN "the production regulations", NL "het productiereglement", ES "el
# reglamento de producción" are 02e's renderings of "il disciplinare"). An EU
# regulation cited by number ("el Reglamento (CE) …") is not the document.
_DOC_ES = (r"(?:pliego(?:\s+de\s+condiciones)?(?:\s+de\s+producción)?|reglamento\s+de\s+producción"
           r"|reglamento(?!\s*(?:\(|n[.º°]|\d|de\s+ejecución|delegado|ue\b|ce\b))|documento\s+único)")
_DOC_IT = r"(?:disciplinare(?:\s+di\s+produzione)?|documento\s+unico)"
# "le règlement" is the Swiss cantonal document; a syndicate's "règlement intérieur" is history
_DOC_FR = (r"(?:cahier\s+des\s+charges|document\s+unique"
           r"|règlement(?!\s*(?:intérieur|\(|n[°o.]|\d|ce\b|ue\b|européen|d['’]exécution|délégué)))")
_DOC_PT = r"(?:caderno(?:\s+de\s+especifica[çc][õo]es)?|documento\s+único)"
_DOC_EN = (r"(?:(?:current|corresponding|relevant|official|national)\s+)?"
           r"(?:(?:production|product)\s+(?:specifications?|regulations?|rules|file)|specifications?(?:\s+document)?"
           r"|single\s+document|technical\s+file|cahier(?:\s+des\s+charges)?|disciplinare(?:\s+di\s+produzione)?"
           r"|pliego(?:\s+de\s+condiciones)?|productdossier|produktspezifikation)")
_DOC_NL = (r"(?:product(?:ie)?(?:dossier|specificaties?|specificatieboek|reglement|voorschrift(?:en)?)"
           r"|enig\s+document|lastenboek|reglement(?!\s*\()|specificatie|pliego|disciplinare|cahier\s+des\s+charges)")
_DOC_DE = r"(?:produktspezifikation|spezifikation|einzigen?\s+dokument)"
_DOC_RO = r"(?:caietul(?:ui)?\s+de\s+sarcini|documentul(?:ui)?\s+unic)"
_DOC_HU = r"(?:termékleírás|egységes\s+dokumentum)"
_DOC_ANY = rf"(?:{_DOC_IT}|{_DOC_ES}|{_DOC_FR}|{_DOC_PT}|{_DOC_EN}|{_DOC_NL}|{_DOC_DE})"
_WIKI = r"(?:wikip[eé]di\w*|[ву]икипеди\w*|βικιπαίδει\w*)"  # "podľa Wikipédie", "Wikipedii"
_GLOSS = r"(?:\s*\([^()]{1,40}\))?"  # "het productspecificatieboek (disciplinare)"

# A fronted "according to <document>": cut, with its comma (Hungarian takes
# the postposition and no comma).
_LEAD_CUT = "|".join((
    rf"(?:según|de\s+acuerdo\s+con|conforme\s+a)\s+(?:el|lo\s+(?:establecido|indicado|recogido)\s+en\s+el)\s+{_DOC_ES}",
    rf"conforme\s+al\s+{_DOC_ES}",
    rf"como\s+(?:señala|indica|recoge|establece|precisa|explica|afirma|destaca)\s+el\s+{_DOC_ES}",
    rf"(?:según|de\s+acuerdo\s+con)\s+(?:la\s+)?{_WIKI}",
    rf"(?:secondo|in\s+base\s+a)\s+(?:il|quanto\s+(?:previsto|indicato|riportato|stabilito)\s+(?:dal|nel))\s+{_DOC_IT}",
    rf"(?:stando|in\s+base)\s+al\s+{_DOC_IT}",
    rf"come\s+(?:indica|riporta|precisa|specifica|afferma|sottolinea|ricorda|stabilisce|attesta)\s+il\s+{_DOC_IT}",
    rf"secondo\s+{_WIKI}",
    rf"(?:selon|d['’]après)\s+le\s+{_DOC_FR}",
    rf"conformément\s+au\s+{_DOC_FR}",
    rf"comme\s+(?:l['’]indique|le\s+précise|le\s+souligne|le\s+rappelle|l['’]affirme|le\s+mentionne|le\s+note"
    rf"|l['’]atteste)\s+le\s+{_DOC_FR}",
    rf"(?:selon|d['’]après)\s+{_WIKI}",
    rf"(?:segundo|de\s+acordo\s+com|conforme)\s+o\s+{_DOC_PT}",
    rf"como\s+(?:refere|indica|afirma|salienta)\s+o\s+{_DOC_PT}",
    rf"(?:segundo|de\s+acordo\s+com)\s+(?:a\s+)?{_WIKI}",
    rf"(?:according\s+to|as\s+(?:stated|set\s+out|indicated|noted|described|laid\s+down)\s+in|per)\s+(?:the\s+)?{_DOC_EN}",
    rf"as\s+the\s+{_DOC_EN}\s+(?:states|state|notes|note|indicates|indicate|says|records|points\s+out|explains"
    rf"|specifies|attests|attest|confirms|confirm)",
    rf"according\s+to\s+{_WIKI}",
    rf"(?:conform|potrivit)\s+{_DOC_RO}",
))
_LEAD_HU = rf"(?:az?\s+)?(?:{_DOC_HU}|{_WIKI})\s+szerint"
# Dutch / German: after a fronted adverbial the finite verb precedes the
# subject ("Volgens het productdossier zijn de eerste wijnstokken …"), so the
# lead cannot simply be dropped.
_LEAD_V2 = "|".join((
    rf"(?:volgens|conform)\s+(?:het\s+|de\s+)?{_DOC_NL}",
    rf"zoals\s+(?:het\s+|de\s+)?{_DOC_NL}\s+\w+",
    rf"volgens\s+{_WIKI}",
    rf"(?:laut|gemäß|nach)\s+(?:der\s+|dem\s+|des\s+)?{_DOC_DE}",
    rf"wie\s+(?:die|das|der)\s+{_DOC_DE}\s+\w+",
    rf"laut\s+{_WIKI}",
))
# "<document> states that …": the complement clause is a main clause in the
# Romance languages and English, a verb-final one in Dutch and German.
_REPORT_VERB = (
    r"(?:afferma|indica|specifica|precisa|riporta|evidenzia|sottolinea|ricorda|segnala|rileva|dichiara"
    r"|attesta|osserva|spiega|menziona|conferma|stabilisce|sostiene"            # it
    r"|señala|afirma|recoge|especifica|destaca|subraya|apunta|explica|dice|refiere|establece"
    r"|constata|confirma|recuerda|estipula"                                     # es (+ indica, precisa, sostiene, menciona)
    r"|affirme|indique|précise|souligne|rappelle|mentionne|note|relève|signale|explique|établit"
    r"|constate|confirme|stipule"                                               # fr
    r"|refere|salienta|estabelece|sublinha"                                     # pt
    r"|precizează|arată|menționează|indică|afirmă|subliniază|stabilește"        # ro
    r"|states?|notes?|indicates?|specif(?:y|ies)|says?|records?|reports?|mentions?|points?\s+out"
    r"|affirms?|explains?|stresses|emphasi[sz]es?|observes?|establish(?:es)?|confirms?|recalls?"
    r"|underlines?|highlights?|attests?|stipulates?)"                           # en
)
_SUBJECT_CUT = (
    rf"(?:(?:il|i|el|los|le|les|o|os|the(?:\s+[\w'’-]+)?)\s+)?(?:{_DOC_IT}|{_DOC_ES}|{_DOC_FR}|{_DOC_PT}|{_DOC_EN}|{_WIKI})"
    rf"{_GLOSS}(?:\s+(?:also|anche|también|aussi|também|inoltre|además))?\s+{_REPORT_VERB}\s+(?:che|que|that)"
    rf"|{_DOC_RO}\s+{_REPORT_VERB}\s+că"
)
_SUBJECT_V2 = (
    rf"(?:(?:het|de|die|das|der)\s+)?(?:{_DOC_NL}|{_DOC_DE}|{_WIKI}){_GLOSS}(?:\s+\w+){{1,2}}\s+(?:dat|dass)"
)
_LEAD_CUT_RE = re.compile(rf"^(\W*)(?:{_LEAD_CUT})\s*,\s*", re.IGNORECASE)
_LEAD_HU_RE = re.compile(rf"^(\W*){_LEAD_HU}\s*,?\s+", re.IGNORECASE)
_LEAD_ANY_RE = re.compile(
    rf"^\W*(?:(?:{_LEAD_CUT})\s*,|(?:{_LEAD_V2})(?=\s*,?\s+(?!(?:van|uit|von|aus|des|der|of)\b)\w)|{_LEAD_HU}\b)",
    re.IGNORECASE,
)
_SUBJECT_CUT_RE = re.compile(rf"^(\W*)(?:{_SUBJECT_CUT})\s+", re.IGNORECASE)
_SUBJECT_ANY_RE = re.compile(rf"^\W*(?:{_SUBJECT_CUT}|{_SUBJECT_V2})\b", re.IGNORECASE)
_PAREN_RE = re.compile(rf"\s*\(\s*(?:{_LEAD_CUT}|{_LEAD_V2}|{_LEAD_HU})\s*\)", re.IGNORECASE)
_TRAILING_ANY_RE = re.compile(
    rf"[,;]?\s+(?:{_LEAD_CUT}|{_LEAD_V2}|{_LEAD_HU})\s*[.!?…]?\s*$", re.IGNORECASE
)
# Two sources compared in one bullet: dropping one attribution would merge
# them into one claim, so the clause stays and the bullet is reported.
_CONTRAST_RE = re.compile(
    r"\b(?:mientras\s+que|frente\s+a|tandis\s+que|alors\s+que|mentre|whereas|while|terwijl|während"
    r"|wohingegen|enquanto)\b", re.IGNORECASE,
)
# A mention the cut cannot reach: the attribution inside the sentence, the
# document as the agent of a verb, any other mention of Wikipedia.
_MID_RE = re.compile(
    rf"\b(?:{_LEAD_CUT}|{_LEAD_V2}|{_LEAD_HU}|{_WIKI})\b"
    rf"|\b(?:il|i|el|los|le|les|the|het|de|die|das|der|o|os)\s+{_DOC_ANY}{_GLOSS}"
    rf"(?:\s+(?:also|anche|también|aussi|inoltre))?\s+(?:{_REPORT_VERB}"
    r"|descri\w+|describ\w+|décri\w+|beschrijft|beschreibt|distingu\w+|onderscheidt|unterscheidet"
    r"|caracteri\w+|characteri[sz]\w+|kenmerkt|attribu\w+|atribu\w+|links|lega|liga|relie|koppelt"
    r"|colloca|sitúa|situe|places|plaatst|prevede|prevé|prévoit|impone|impose|esclude|excluye|exclut"
    r"|autorizza|autoriza|autorise|riserva|reserva|réserve|ammette|admite|admet|elenca|enumera|énumère"
    r"|requires|allows|permits|lists|sets\s+out|prescrib\w*|bepaalt|stelt|vermeldt|geeft\s+aan"
    r"|schrijft\s+voor|legt\s+vast|stellt|besagt|legt\s+fest)\b"
    # the document as the setter of a rule ("le tipologie previste dal disciplinare",
    # "entro i limiti del disciplinare"); its history ("fu approvato nel 1967") is a fact
    r"|\b(?:previst\w*|fissat\w*|richiest\w*|consentit\w*|ammess\w*|prescritt\w*|prévu\w*|fixé\w*|exigé\w*"
    r"|establecid\w*|fijad\w*|exigid\w*|definid\w*|estabelecid\w*|fixad\w*"
    r"|defined|required|set|provided|permitted|laid\s+down|allowed)"
    rf"\s+(?:for\s+)?(?:da|dal|nel|in|no|pelo|by|in\s+the|by\s+the|par\s+le|dans\s+le|por\s+el|en\s+el)\s+{_DOC_ANY}\b"
    rf"|\b(?:limiti|limites|limits)\s+(?:del|du|of\s+the)\s+{_DOC_ANY}\b|\bdisciplinare\s+non\s+riporta\b",
    re.IGNORECASE,
)
_SUBJUNCTIVE_RE = re.compile(
    r"\b(?:debbano|debba|siano|possano|vengano|provengano|abbiano|rispettino"
    r"|deban|deba|sean|procedan|puedan|tengan|soient|devam|sejam|provenham)\b",
    re.IGNORECASE,
)
_MODAL = frozenset("can could may might must should shall will would to".split())


def _upper_first(text: str) -> str:
    for i, c in enumerate(text):
        if c.isalpha():
            return text[:i] + c.upper() + text[i + 1:]
    return text


def _subject_cut_safe(bullet: str, m: re.Match) -> bool:
    """The complement of "<document> establishes that" may be a subjunctive
    ("… stabilisce che le uve provengano …") that is no main clause."""
    words = bullet[m.end():].split()[:12]
    if _SUBJUNCTIVE_RE.search(" ".join(words)):
        return False
    # English: "… requires that the grapes be harvested" (a bare "be" after no modal)
    low = [w.casefold().strip(",;") for w in words[:8]]
    return not any(w == "be" and (i == 0 or low[i - 1] not in _MODAL) for i, w in enumerate(low))


# The kinds the audit counts as strict (`document_reference`): the ones the
# cut removes, or a re-translation does.
STRICT_REFERENCE_KINDS = frozenset({"lead", "subject", "trailing", "paren"})


def document_reference(bullet: str) -> str | None:
    """How `bullet` refers to its own document (or to Wikipedia): `lead`,
    `subject`, `trailing`, `paren` — the forms `strip_document_reference`
    cuts, except where the cut is unsafe (Dutch / German word order, a
    subjunctive complement, two sources compared) — `mid` for a mention
    that needs rewording, None for none."""
    b = bullet or ""
    if _LEAD_ANY_RE.search(b):
        return "lead"
    if _SUBJECT_ANY_RE.search(b):
        return "subject"
    if _PAREN_RE.search(b):
        return "paren"
    if _TRAILING_META_RE.search(b) or (_TRAILING_ANY_RE.search(b) and not _CONTRAST_RE.search(b)):
        return "trailing"
    if _MID_RE.search(b):
        return "mid"
    return None


def strip_document_reference(bullet: str) -> str:
    """Cut an opening, closing or bracketed reference to the document and
    keep the claim: "Según el pliego, se cree que …" → "Se cree que …".
    Anything `document_reference` reports and this cannot cut stays as it
    is for 02e / the gate."""
    b = bullet or ""
    m = _LEAD_CUT_RE.match(b) or _LEAD_HU_RE.match(b)
    if m and b[m.end():].strip():
        b = m.group(1) + _upper_first(b[m.end():])
    else:
        m = _SUBJECT_CUT_RE.match(b)
        if m and b[m.end():].strip() and _subject_cut_safe(b, m):
            b = m.group(1) + _upper_first(b[m.end():])
    b = strip_trailing_meta(_PAREN_RE.sub("", b))
    t = _TRAILING_ANY_RE.search(b)
    if t and b[: t.start()].strip() and not _CONTRAST_RE.search(b):
        b = b[: t.start()]
    return b


def ensure_terminal_period(bullet: str) -> str:
    b = bullet.rstrip()
    if not b or b[-1] in _TERMINAL:
        return b
    return b + "."


def _latinize_token(token: str) -> str:
    if _CHEM_PREFIX.search(token):
        return token
    letters = _LETTER.findall(token)
    non_latin = [c for c in letters if _NON_LATIN.match(c)]
    if not non_latin:
        return token
    if len(non_latin) * 2 < len(letters) and all(c in _HOMOGLYPH_CHARS for c in non_latin):
        return token.translate(_HOMOGLYPH)  # a stray lookalike inside a Latin word
    out = "".join(unidecode(c) if _NON_LATIN.match(c) else c for c in token)
    if len(letters) > 1 and all(c.isupper() for c in letters):
        return out.upper()  # an inscription or acronym: "ΘΑΣΙΩΝ" is THASION, not ThASION
    return out


def latinize_residual_script(bullet: str) -> str:
    """Latin-script a mostly-Latin bullet: homoglyphs mapped, whole
    non-Latin tokens transliterated. A bullet whose letters are ≥ 80 %
    non-Latin is left untouched — it is an untranslated source bullet, not
    a residue."""
    letters = _LETTER.findall(bullet)
    if not letters:
        return bullet
    share = sum(1 for c in letters if _NON_LATIN.match(c)) / len(letters)
    if share >= 0.8:
        return bullet
    if share == 0:
        # already Latin: only a bracket that repeats the words before it goes
        return _ANY_GLOSS.sub(_drop_repeated_gloss, bullet)
    out = re.sub(r"\S+", lambda m: _latinize_token(m.group(0)), bullet)
    out = _REDUNDANT_GLOSS.sub(_drop_redundant_gloss, out)
    return _ANY_GLOSS.sub(_drop_repeated_gloss, out)


# A source-script gloss that transliterates to the word it glosses — "tines
# (τίνες)" → "tines (tines)" — says nothing twice; the bracket goes.
_REDUNDANT_GLOSS = re.compile(r"(?<![\w'’-])([^\W\d_][\w'’-]*) \(([^()]+)\)")


def _drop_redundant_gloss(m: re.Match) -> str:
    word, gloss = m.group(1), m.group(2)
    return word if gloss.casefold() == word.casefold() else m.group(0)


# The same for a name of several words: a translator that kept a Greek name
# and glossed it — "Ούζο Πλωμαρίου (Ouzo Plomariou)" — reads "Ouzo Plomariou
# (Ouzo Plomariou)" once the name is transliterated.
_ANY_GLOSS = re.compile(r" \(([^()]+)\)")


def _drop_repeated_gloss(m: re.Match) -> str:
    before, gloss = m.string[: m.start()], m.group(1)
    if len(gloss) < 3 or not before.casefold().endswith(gloss.casefold()):
        return m.group(0)
    start = len(before) - len(gloss)
    return "" if start == 0 or not before[start - 1].isalnum() else m.group(0)


# Dutch: the common noun is "appellatie" (the UI's own word — "Appellatie
# zoeken…", "{p} appellaties"); the French loanword stayed in 260 NL bullets
# ("De appellation is gelegen in de streek Revermont", 2026-09-15). The
# registered term "appellation d'origine contrôlée / protégée" is a name
# and stays.
_NL_APPELLATION_RE = re.compile(r"\b([Aa])ppellation(s?)\b(?!\s+d[’']origine)")

_LOCALE_FIXES = {
    "nl": lambda b: _NL_APPELLATION_RE.sub(r"\1ppellatie\2", b),
}


def locale_fixes(bullet: str, lang: str) -> str:
    fix = _LOCALE_FIXES.get(lang)
    return fix(bullet) if fix else bullet


def normalize_bullet(bullet: str, lang: str = "") -> str:
    """Apply every deterministic fix. `lang` is the locale the bullet is
    rendered in: for the four target locales residual Greek / Cyrillic
    script is also Latinised."""
    if not bullet:
        return bullet
    out = strip_document_reference(expand_mentions(strip_colour_codes(bullet)))
    if lang in _TARGET_LOCALES:
        out = latinize_residual_script(locale_fixes(out, lang))
    return ensure_terminal_period(out)


def normalize_facts(facts: list[dict], lang: str = "") -> int:
    """Normalise `bullet` on every fact in place; returns how many changed."""
    n = 0
    for f in facts:
        b = f.get("bullet") or ""
        nb = normalize_bullet(b, lang)
        if nb != b:
            f["bullet"] = nb
            n += 1
    return n


def normalize_aocs(aocs: dict[str, dict], lang: str = "") -> dict[str, dict]:
    """Stage-04 hook: return a new aocs dict whose `terroir_facts.facts[].bullet`
    are normalised. Records are copied, never mutated — the per-locale dicts
    share record objects with the source `aocs`."""
    out: dict[str, dict] = {}
    for slug, rec in aocs.items():
        tf = rec.get("terroir_facts")
        facts = (tf or {}).get("facts") if isinstance(tf, dict) else None
        if not facts:
            out[slug] = rec
            continue
        new_facts = [{**f, "bullet": normalize_bullet(f.get("bullet") or "", lang)} for f in facts]
        if all(a.get("bullet") == b.get("bullet") for a, b in zip(facts, new_facts)):
            out[slug] = rec
            continue
        out[slug] = {**rec, "terroir_facts": {**tf, "facts": new_facts}}
    return out
