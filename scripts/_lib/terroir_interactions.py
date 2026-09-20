"""The `interactions` sub-section is earned, not filled (review 2026-09-12,
R3).

Every 02d prompt asks for a fourth sub-section — the causal terroir → wine
links — with a cap of one bullet, and the models fill it: the share sat
at 10.8 % of all bullets across two runs, one per record, and 7 of the
25 residual misleading bullets on the acceptance sample were causal
links the source never states. Measured on the r1 corpus, 69 % of those
quotes carry an explicit connective, 8 % carry one only in the bullet
(the manufactured link) and 23 % carry none. STYLE_RULES and the gate
both say the sub-section is admitted only when the source sentence itself
states the link; this module makes that a deterministic test on the
bullet's *grounding quote* (the source's words, never the bullet — a
bullet can add the "thanks to" the source lacks, and that is precisely
the failure mode):

  has_connective(text, lang)     an explicit causal or consecutive
                                 connective of `lang` — "grâce à",
                                 "conferisce", "bedingt durch", "λόγω", …
  earn_interactions(facts, lang) stage 02d, after its four calls: an
                                 `interactions` fact whose quote carries
                                 no connective is dropped (the fourth
                                 call restates the other three when the
                                 source states no link); at most
                                 MAX_INTERACTIONS remain
  demote_unearned(facts, lang)   the gate, after its verdicts: such a
                                 fact is moved to the natural factors
                                 instead (its causal wrapper has been
                                 rewritten away by then)

The fourth call itself stays: the INAO cahier's section X.3
"Interactions causales" and the EU single document's 8.4 are where the
regulator states the links, and dropping the call would lose them.
No bullet is ever promoted into `interactions` from the other
sub-sections — the lists below are deliberately broad (they include
"gives", "permet", "provides"), which is right for a drop / demote test
and wrong for a promotion test.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_INTERACTIONS = 2
_LANG_ALIAS = {"mt": "en", "at": "de", "ch": "fr", "lu": "fr", "gb": "en", "cz": "cs", "si": "sl",
               "gr": "el", "cy": "el"}

CONNECTIVES: dict[str, tuple[str, ...]] = {
    "fr": ("grâce à", "grâce au", "grâce aux", "en raison de", "en raison du", "en raison des",
           "du fait de", "du fait du", "du fait des", "à cause de", "sous l'effet", "sous l'influence",
           "permet", "permettent", "permettant", "confère", "confèrent", "conférant", "favorise",
           "favorisent", "favorisant", "explique", "expliquent", "entraîne", "entraînent", "induit",
           "induisent", "se traduit", "se traduisent", "contribue", "contribuent", "résulte",
           "résultent", "provient", "proviennent", "conduit à", "conduisent à", "génère", "génèrent",
           "engendre", "engendrent", "procure", "procurent", "assure", "assurent", "garantit",
           "garantissent", "à l'origine de", "d'où", "ainsi", "donc", "par conséquent",
           "c'est pourquoi", "de ce fait", "influence", "influencent", "apporte", "apportent",
           "donne", "donnent", "doit", "doivent"),
    "it": ("grazie a", "grazie al", "grazie alla", "grazie ai", "grazie alle", "a causa di",
           "per effetto di", "per effetto del", "in virtù di", "dovuto a", "dovuta a", "dovuti a",
           "dovute a", "conferisce", "conferiscono", "conferendo", "consente", "consentono",
           "permette", "permettono", "favorisce", "favoriscono", "favorendo", "determina",
           "determinano", "determinando", "spiega", "spiegano", "comporta", "comportano",
           "contribuisce", "contribuiscono", "deriva", "derivano", "pertanto", "quindi",
           "di conseguenza", "garantisce", "garantiscono", "assicura", "assicurano", "apporta",
           "apportano", "influisce", "influiscono", "influenza", "influenzano", "esalta",
           "esaltano", "dona", "donano", "consentendo", "responsabile di", "responsabili di",
           "si traduce", "si traducono", "genera", "generano", "induce", "inducono", "ne deriva"),
    "es": ("gracias a", "debido a", "a causa de", "por efecto de", "confiere", "confieren",
           "permite", "permiten", "favorece", "favorecen", "determina", "determinan", "explica",
           "explican", "aporta", "aportan", "contribuye", "contribuyen", "provoca", "provocan",
           "da lugar", "dan lugar", "se traduce", "se traducen", "por lo que", "por tanto",
           "por ello", "en consecuencia", "influye", "influyen", "garantiza", "garantizan",
           "otorga", "otorgan", "propicia", "propician", "proporciona", "proporcionan",
           "condiciona", "condicionan", "origina", "originan", "responsable de", "responsables de",
           "se debe a", "se deben a", "consecuencia de"),
    "pt": ("graças a", "graças à", "graças ao", "devido a", "devido à", "devido ao", "por causa de",
           "confere", "conferem", "permite", "permitem", "favorece", "favorecem", "determina",
           "determinam", "explica", "explicam", "contribui", "contribuem", "proporciona",
           "proporcionam", "resulta", "resultam", "traduz-se", "traduzem-se", "por isso",
           "consequentemente", "influencia", "influenciam", "origina", "originam", "garante",
           "garantem", "conduz", "conduzem", "dá origem", "dão origem", "deve-se", "devem-se",
           "responsável por", "responsáveis por", "condiciona", "condicionam"),
    "de": ("dank", "aufgrund", "auf grund", "wegen", "infolge", "bedingt durch", "bedingt",
           "bedingen", "bewirkt", "bewirken", "verleiht", "verleihen", "ermöglicht", "ermöglichen",
           "begünstigt", "begünstigen", "führt zu", "führen zu", "sorgt für", "sorgen für",
           "trägt bei", "tragen bei", "beitragen", "prägt", "prägen", "erklärt", "resultiert",
           "resultieren", "ergibt sich", "ergeben sich", "daher", "deshalb", "somit", "dadurch",
           "hierdurch", "wodurch", "folglich", "verantwortlich für", "beeinflusst", "beeinflussen",
           "zurückzuführen", "verdankt", "verdanken", "hervorbringt", "hervorbringen",
           "mit sich bringt", "zur folge", "bestimmt", "bestimmen"),
    "nl": ("dankzij", "vanwege", "als gevolg van", "ten gevolge van", "zorgt voor", "zorgen voor",
           "zorgt ervoor", "zorgen ervoor", "verleent", "verlenen", "leidt tot", "leiden tot",
           "resulteert in", "resulteren in", "draagt bij", "dragen bij", "waardoor", "daardoor",
           "hierdoor", "bevordert", "bevorderen", "verklaart", "verklaren", "bepaalt", "bepalen",
           "beïnvloedt", "beïnvloeden", "te danken aan", "toe te schrijven aan", "daarom",
           "mogelijk maakt", "mogelijk maken", "geeft", "geven", "veroorzaakt", "veroorzaken",
           "verantwoordelijk voor"),
    "en": ("thanks to", "due to", "because", "owing to", "as a result", "results in", "result in",
           "resulting in", "gives", "give", "giving", "confers", "confer", "conferring", "allows",
           "allow", "allowing", "enables", "enable", "enabling", "favours", "favors", "favour",
           "favor", "explains", "explain", "leads to", "lead to", "leading to", "contributes",
           "contribute", "contributing", "therefore", "hence", "thus", "consequently",
           "influences", "influence", "responsible for", "attributable to", "imparts", "impart",
           "ensures", "ensure", "promotes", "promote", "determines", "determine", "provides",
           "provide", "creates", "create", "brings", "bring", "helps", "help", "means that"),
    "el": ("χάρη σ", "λόγω", "εξαιτίας", "οφείλεται", "οφείλονται", "προσδίδει", "προσδίδουν",
           "επιτρέπει", "επιτρέπουν", "ευνοεί", "ευνοούν", "συμβάλλει", "συμβάλλουν", "οδηγεί",
           "οδηγούν", "καθορίζει", "καθορίζουν", "εξηγεί", "εξηγούν", "με αποτέλεσμα",
           "ως αποτέλεσμα", "κατά συνέπεια", "συνεπώς", "επομένως", "επηρεάζει", "επηρεάζουν",
           "εξασφαλίζει", "εξασφαλίζουν", "δίνει", "δίνουν", "χαρίζει", "χαρίζουν", "αποδίδει",
           "αποδίδουν", "διαμορφώνει", "διαμορφώνουν", "προσφέρει", "προσφέρουν", "υπεύθυν",
           "δημιουργεί", "δημιουργούν", "επιδρ", "συντελεί", "συντελούν"),
    "bg": ("благодарение на", "поради", "вследствие", "в резултат", "се дължи", "се дължат",
           "придава", "придават", "позволява", "позволяват", "благоприятства", "благоприятстват",
           "допринася", "допринасят", "води до", "водят до", "определя", "определят", "обуславя",
           "обуславят", "затова", "следователно", "влияе", "влияят", "осигурява", "осигуряват",
           "обяснява", "обясняват", "формира", "формират", "създава", "създават", "спомага",
           "спомагат", "отговорн", "предпоставка"),
    "hu": ("köszönhető", "köszönhetően", "miatt", "következtében", "eredményeként",
           "eredményeképpen", "hatására", "biztosít", "biztosítja", "biztosítják", "lehetővé tesz",
           "lehetővé teszi", "lehetővé teszik", "kedvez", "kedveznek", "hozzájárul",
           "hozzájárulnak", "eredményez", "eredményezi", "eredményezik", "meghatároz",
           "meghatározza", "meghatározzák", "magyaráz", "magyarázza", "ezért", "így", "tehát",
           "ennélfogva", "befolyásol", "befolyásolja", "befolyásolják", "kölcsönöz", "kölcsönöznek",
           "okoz", "okozza", "okozzák", "alakít", "alakítja", "alakítják", "teszi lehetővé",
           "felelős", "elősegít", "elősegíti"),
    "cs": ("díky", "kvůli", "v důsledku", "vlivem", "následkem", "dodává", "dodávají", "umožňuje",
           "umožňují", "podporuje", "podporují", "přispívá", "přispívají", "vede k", "vedou k",
           "určuje", "určují", "způsobuje", "způsobují", "vysvětluje", "proto", "tudíž", "tedy",
           "takže", "ovlivňuje", "ovlivňují", "zajišťuje", "zajišťují", "propůjčuje", "propůjčují",
           "má za následek", "mají za následek", "podmiňuje", "podmiňují", "utváří", "vytváří",
           "zodpovědn", "zodpovídá"),
    "sk": ("vďaka", "kvôli", "v dôsledku", "vplyvom", "následkom", "dodáva", "dodávajú", "umožňuje",
           "umožňujú", "podporuje", "podporujú", "prispieva", "prispievajú", "vedie k", "vedú k",
           "určuje", "určujú", "spôsobuje", "spôsobujú", "vysvetľuje", "preto", "teda", "takže",
           "ovplyvňuje", "ovplyvňujú", "zabezpečuje", "zabezpečujú", "prepožičiava", "prepožičiavajú",
           "má za následok", "podmieňuje", "podmieňujú", "vytvára", "vytvárajú", "utvára",
           "zodpovedn"),
    "sl": ("zaradi", "po zaslugi", "zahvaljujoč", "kot posledica", "posledično", "daje", "dajejo",
           "omogoča", "omogočajo", "spodbuja", "spodbujajo", "prispeva", "prispevajo", "vodi do",
           "vodijo do", "določa", "določajo", "povzroča", "povzročajo", "pojasnjuje", "zato",
           "torej", "vpliva", "vplivajo", "zagotavlja", "zagotavljajo", "oblikuje", "oblikujejo",
           "ustvarja", "ustvarjajo", "odgovorn", "pogojuje", "pogojujejo"),
    "hr": ("zahvaljujući", "zbog", "uslijed", "kao posljedica", "posljedično", "daje", "daju",
           "omogućuje", "omogućuju", "omogućava", "omogućavaju", "pogoduje", "pogoduju", "pridonosi",
           "pridonose", "doprinosi", "doprinose", "dovodi do", "dovode do", "određuje", "određuju",
           "uzrokuje", "uzrokuju", "objašnjava", "stoga", "zato", "dakle", "utječe", "utječu",
           "osigurava", "osiguravaju", "oblikuje", "oblikuju", "stvara", "stvaraju", "rezultira",
           "rezultiraju", "odgovorn", "uvjetuje", "uvjetuju"),
    "ro": ("datorită", "din cauza", "ca urmare", "drept urmare", "ca rezultat", "conferă",
           "permite", "permit", "favorizează", "contribuie", "duce la", "duc la", "conduce la",
           "conduc la", "determină", "explică", "generează", "asigură", "de aceea", "prin urmare",
           "astfel", "influențează", "imprimă", "oferă", "rezultă", "se datorează", "se datorează",
           "responsabil", "condiționează", "face posibil", "fac posibil"),
}

_COMPILED: dict[str, re.Pattern[str]] = {}


def _pattern(lang: str) -> re.Pattern[str] | None:
    lang = _LANG_ALIAS.get(lang, lang)
    if lang in _COMPILED:
        return _COMPILED[lang]
    terms = CONNECTIVES.get(lang)
    if not terms:
        return None
    # Word-initial anchoring only: many entries are stems ("επιδρ", "odgovorn").
    alts = "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
    pat = re.compile(rf"(?<![^\W\d_])(?:{alts})", re.IGNORECASE)
    _COMPILED[lang] = pat
    return pat


def has_connective(text: str, lang: str) -> bool:
    """True when `text` (a source quote) carries an explicit causal or
    consecutive connective of `lang`. Unknown language → False."""
    pat = _pattern(lang)
    return bool(pat and text and pat.search(text))


def quote_has_connective(fact: dict, lang: str) -> bool:
    """The grounding quote states a link: the cahier quote when the fact
    is cahier-grounded, the Wikipedia quote when wiki-grounded."""
    prov = fact.get("provenance") or "cahier"
    if prov in ("cahier", "both") and has_connective(fact.get("cahier_quote") or "", lang):
        return True
    return prov in ("wiki", "both") and has_connective(fact.get("wiki_quote") or "", lang)


DEMOTION_TARGET = "facteurs_naturels"


@dataclass
class EarnResult:
    kept: list[dict]
    dropped: list[dict]


def earn_interactions(facts: list[dict], lang: str, *, max_interactions: int = MAX_INTERACTIONS) -> EarnResult:
    """Stage 02d: keep an `interactions` fact only when its quote carries
    a connective, at most `max_interactions` of them (in order); the rest
    are dropped. Other sub-sections pass through untouched."""
    kept: list[dict] = []
    dropped: list[dict] = []
    n = 0
    for f in facts:
        if (f.get("subsection") or DEMOTION_TARGET) != "interactions":
            kept.append(f)
            continue
        if quote_has_connective(f, lang) and n < max_interactions:
            n += 1
            kept.append(f)
        else:
            dropped.append(f)
    return EarnResult(kept, dropped)


def unearned_indices(facts: list[dict], lang: str, *, max_interactions: int = MAX_INTERACTIONS) -> list[int]:
    """Indices of the `interactions` facts the earned rule rejects: quote
    without a connective, or beyond the cap."""
    out: list[int] = []
    n = 0
    for i, f in enumerate(facts):
        if (f.get("subsection") or DEMOTION_TARGET) != "interactions":
            continue
        if quote_has_connective(f, lang) and n < max_interactions:
            n += 1
        else:
            out.append(i)
    return out
