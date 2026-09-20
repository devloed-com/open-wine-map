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
and wrong for a promotion test. A false negative drops a legitimate,
source-stated fact, the costlier error: the first table matched 69 % of
the r1 corpus's interactions quotes; the smoke's dropped bullets ("glavni
čimbenik", "fördert", "και έτσι", "hace que") and samples of the
unmatched FR / NL / RO quotes ("déterminent", "contribuant", "hetgeen
zich vertaalt in", "dă vinuri", "in quanto", "резултат от") drove it to
85 % with noun forms (factor / role / influence), word-initial verb
stems, the plain "because" conjunctions, Romanian cedilla folding and
an English fallback for Dutch records. The residual 15 % is the
manufactured link the rule exists for ("confèrent" in the bullet,
"marquée par" nowhere near it in the quote) plus non-causal
restatements.
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
           "donne", "donnent", "doit", "doivent",
           # noun, gerund and consecutive forms (2026-09-14 smoke: "glavni čimbenik",
           # "fördert", "και έτσι", "hace que" were dropped as unearned)
           "facteur", "facteurs", "rôle", "déterminant", "décisif", "décisive", "responsable",
           "clé pour", "donnant", "apportant", "assurant", "garantissant", "expliquant",
           "entraînant", "induisant", "générant", "de sorte que", "si bien que", "ce qui",
           "sous l'action", "dépend", "dépendent",
           # word-initial stems (the inflections and gerunds the smoke and the FR / NL / RO
           # samples showed missing: "déterminent", "contribuant", "vertaalt zich")
           "détermin", "contribu", "entraîn", "entrain", "engendr", "condui", "confèr", "confér",
           "favoris", "permet", "permett", "expliqu", "indui", "génèr", "génér", "procur", "assur",
           "garanti", "apport", "résult", "provien", "provenan", "tradui", "influenc", "dépend",
           "issu de", "issus de", "issue de", "issues de", "lié à", "liée à", "liés à", "liées à",
           "lié au", "liée au", "liés au", "liées au", "en lien", "responsab", "se reflèt",
           "se traduis", "s'exprim",
           # conjunctions and "result of / in combination with" forms
           "marqué par", "marquée par", "marqués par", "marquées par", "parce que", "puisque",
           "car ", "étant donné", "du fait", "en effet"),
    "it": ("grazie a", "grazie al", "grazie alla", "grazie ai", "grazie alle", "a causa di",
           "per effetto di", "per effetto del", "in virtù di", "dovuto a", "dovuta a", "dovuti a",
           "dovute a", "conferisce", "conferiscono", "conferendo", "consente", "consentono",
           "permette", "permettono", "favorisce", "favoriscono", "favorendo", "determina",
           "determinano", "determinando", "spiega", "spiegano", "comporta", "comportano",
           "contribuisce", "contribuiscono", "deriva", "derivano", "pertanto", "quindi",
           "di conseguenza", "garantisce", "garantiscono", "assicura", "assicurano", "apporta",
           "apportano", "influisce", "influiscono", "influenza", "influenzano", "esalta",
           "esaltano", "dona", "donano", "consentendo", "responsabile di", "responsabili di",
           "si traduce", "si traducono", "genera", "generano", "induce", "inducono", "ne deriva",
           # noun, gerund and consecutive forms (2026-09-14 smoke: "glavni čimbenik",
           # "fördert", "και έτσι", "hace que" were dropped as unearned)
           "fattore", "fattori", "ruolo", "determinante", "determinanti", "decisiv", "donando",
           "permettendo", "garantendo", "assicurando", "esaltando", "influenzando", "contribuendo",
           "generando", "inducendo", "così", "in modo che", "tale da", "tali da", "grazie",
           "dipende", "dipendono", "condiziona", "condizionano", "condizionando",
           # word-initial stems (the inflections and gerunds the smoke and the FR / NL / RO
           # samples showed missing: "déterminent", "contribuant", "vertaalt zich")
           "conferi", "consent", "permett", "favor", "determin", "spieg", "comport", "contribu",
           "deriv", "garant", "assicur", "apport", "influ", "esalt", "gener", "induc", "condizion",
           "dipend", "legat", "si rifle", "si esprim", "responsabil",
           # conjunctions and "result of / in combination with" forms
           "in quanto", "sostenut", "poiché", "perché", "dato che", "visto che", "siccome",
           "infatti"),
    "es": ("gracias a", "debido a", "a causa de", "por efecto de", "confiere", "confieren",
           "permite", "permiten", "favorece", "favorecen", "determina", "determinan", "explica",
           "explican", "aporta", "aportan", "contribuye", "contribuyen", "provoca", "provocan",
           "da lugar", "dan lugar", "se traduce", "se traducen", "por lo que", "por tanto",
           "por ello", "en consecuencia", "influye", "influyen", "garantiza", "garantizan",
           "otorga", "otorgan", "propicia", "propician", "proporciona", "proporcionan",
           "condiciona", "condicionan", "origina", "originan", "responsable de", "responsables de",
           "se debe a", "se deben a", "consecuencia de",
           # noun, gerund and consecutive forms (2026-09-14 smoke: "glavni čimbenik",
           # "fördert", "και έτσι", "hace que" were dropped as unearned)
           "hace que", "hacen que", "haciendo que", "factor", "factores", "papel", "influencia",
           "clave", "decisiv", "determinante", "determinantes", "de ahí", "así",
           "por consiguiente", "generando", "permitiendo", "confiriendo", "aportando",
           "dando lugar", "favoreciendo", "contribuyendo", "depende", "dependen", "gracias",
           # word-initial stems (the inflections and gerunds the smoke and the FR / NL / RO
           # samples showed missing: "déterminent", "contribuant", "vertaalt zich")
           "confier", "permit", "favorec", "determin", "explic", "aport", "contribu", "provoc",
           "influ", "garantiz", "otorg", "propici", "proporcion", "condicion", "origin", "depend",
           "vincul", "ligad", "se refle", "se expres", "se manifiest", "responsab",
           # conjunctions and "result of / in combination with" forms
           "asegur", "result", "relación", "puesto que", "ya que", "porque", "dado que",
           "de hecho"),
    "pt": ("graças a", "graças à", "graças ao", "devido a", "devido à", "devido ao", "por causa de",
           "confere", "conferem", "permite", "permitem", "favorece", "favorecem", "determina",
           "determinam", "explica", "explicam", "contribui", "contribuem", "proporciona",
           "proporcionam", "resulta", "resultam", "traduz-se", "traduzem-se", "por isso",
           "consequentemente", "influencia", "influenciam", "origina", "originam", "garante",
           "garantem", "conduz", "conduzem", "dá origem", "dão origem", "deve-se", "devem-se",
           "responsável por", "responsáveis por", "condiciona", "condicionam",
           # noun, gerund and consecutive forms (2026-09-14 smoke: "glavni čimbenik",
           # "fördert", "και έτσι", "hace que" were dropped as unearned)
           "fator", "fatores", "factor", "factores", "papel", "influência", "determinante",
           "decisiv", "chave", "conferindo", "permitindo", "favorecendo", "contribuindo",
           "proporcionando", "originando", "resultando", "assim", "de modo que", "faz com que",
           "fazem com que", "depende", "dependem", "graças",
           # word-initial stems (the inflections and gerunds the smoke and the FR / NL / RO
           # samples showed missing: "déterminent", "contribuant", "vertaalt zich")
           "confer", "permit", "favorec", "determin", "explic", "contribu", "proporcion", "result",
           "influenc", "origin", "garant", "conduz", "condicion", "depend", "ligad", "associad",
           "reflet", "se express", "se manifest", "responsáv",
           # conjunctions and "result of / in combination with" forms
           "assegur", "relação", "porque", "pois", "já que", "uma vez que", "visto que",
           "de facto", "de fato"),
    "de": ("dank", "aufgrund", "auf grund", "wegen", "infolge", "bedingt durch", "bedingt",
           "bedingen", "bewirkt", "bewirken", "verleiht", "verleihen", "ermöglicht", "ermöglichen",
           "begünstigt", "begünstigen", "führt zu", "führen zu", "sorgt für", "sorgen für",
           "trägt bei", "tragen bei", "beitragen", "prägt", "prägen", "erklärt", "resultiert",
           "resultieren", "ergibt sich", "ergeben sich", "daher", "deshalb", "somit", "dadurch",
           "hierdurch", "wodurch", "folglich", "verantwortlich für", "beeinflusst", "beeinflussen",
           "zurückzuführen", "verdankt", "verdanken", "hervorbringt", "hervorbringen",
           "mit sich bringt", "zur folge", "bestimmt", "bestimmen",
           # noun, gerund and consecutive forms (2026-09-14 smoke: "glavni čimbenik",
           # "fördert", "και έτσι", "hace que" were dropped as unearned)
           "fördert", "fördern", "fördernd", "wirkt sich", "wirken sich", "auswirkung",
           "auswirkungen", "einfluss", "einflüsse", "faktor", "faktoren", "bedeutung für",
           "entscheidend", "maßgeblich", "prägend", "ursache", "verursacht", "verursachen",
           "erlaubt", "erlauben", "unterstützt", "unterstützen", "abhängig", "hängt", "hängen",
           "grundlage für", "voraussetzung",
           # word-initial stems (the inflections and gerunds the smoke and the FR / NL / RO
           # samples showed missing: "déterminent", "contribuant", "vertaalt zich")
           "bewirk", "verleih", "ermöglich", "begünstig", "beeinfluss", "bestimm", "präg",
           "förder", "verursach", "unterstütz", "bedeut", "resultier", "beding", "abhäng", "beruh",
           "zurückzuführ", "verdank", "beitr", "widerspiegel", "spiegelt", "spiegeln",
           "äußert sich", "äußern sich", "zeigt sich", "zeigen sich", "verantwortlich",
           # conjunctions and "result of / in combination with" forms
           "weil", "weshalb", "sodass", "so dass", "damit", "somit", "zumal", "nämlich"),
    "nl": ("dankzij", "vanwege", "als gevolg van", "ten gevolge van", "zorgt voor", "zorgen voor",
           "zorgt ervoor", "zorgen ervoor", "verleent", "verlenen", "leidt tot", "leiden tot",
           "resulteert in", "resulteren in", "draagt bij", "dragen bij", "waardoor", "daardoor",
           "hierdoor", "bevordert", "bevorderen", "verklaart", "verklaren", "bepaalt", "bepalen",
           "beïnvloedt", "beïnvloeden", "te danken aan", "toe te schrijven aan", "daarom",
           "mogelijk maakt", "mogelijk maken", "geeft", "geven", "veroorzaakt", "veroorzaken",
           "verantwoordelijk voor",
           # noun, gerund and consecutive forms (2026-09-14 smoke: "glavni čimbenik",
           # "fördert", "και έτσι", "hace que" were dropped as unearned)
           "factor", "factoren", "rol", "invloed", "bepalend", "doorslaggevend", "cruciaal",
           "essentieel", "zodat", "maakt dat", "maken dat", "hangt af", "hangen af", "afhankelijk",
           "basis voor", "voorwaarde",
           # word-initial stems (the inflections and gerunds the smoke and the FR / NL / RO
           # samples showed missing: "déterminent", "contribuant", "vertaalt zich")
           "ondersteun", "vertaal", "oplever", "lever", "maakt het mogelijk", "maken het mogelijk",
           "uit zich", "uiten zich", "tot uiting", "zo kan", "zo kunnen", "zo ontsta", "bijdra",
           "beïnvloed", "bepal", "leid", "resulteer", "afhankelijk", "hangt", "hangen",
           "te danken", "toe te schrijven", "verklaar", "verleen", "weerspiegel", "gevolg",
           "verantwoordelijk",
           # conjunctions and "result of / in combination with" forms
           "omdat", "doordat", "want ", "aangezien", "immers"),
    "en": ("thanks to", "due to", "because", "owing to", "as a result", "results in", "result in",
           "resulting in", "gives", "give", "giving", "confers", "confer", "conferring", "allows",
           "allow", "allowing", "enables", "enable", "enabling", "favours", "favors", "favour",
           "favor", "explains", "explain", "leads to", "lead to", "leading to", "contributes",
           "contribute", "contributing", "therefore", "hence", "thus", "consequently",
           "influences", "influence", "responsible for", "attributable to", "imparts", "impart",
           "ensures", "ensure", "promotes", "promote", "determines", "determine", "provides",
           "provide", "creates", "create", "brings", "bring", "helps", "help", "means that",
           # noun, gerund and consecutive forms (2026-09-14 smoke: "glavni čimbenik",
           # "fördert", "και έτσι", "hace que" were dropped as unearned)
           "factor", "factors", "role", "key to", "shapes", "shape", "shaping", "drives", "drive",
           "driving", "owes", "owe", "owing", "makes", "make", "making", "so that", "affects",
           "affect", "affecting", "decisive", "determining", "crucial", "essential", "underpins",
           "underpin", "depends", "depend", "dependent", "basis for", "conducive",
           # word-initial stems (the inflections and gerunds the smoke and the FR / NL / RO
           # samples showed missing: "déterminent", "contribuant", "vertaalt zich")
           "confer", "allow", "enabl", "favour", "favor", "explain", "contribut", "influenc",
           "impart", "ensur", "promot", "determin", "provid", "creat", "help", "shap", "driv",
           "affect", "depend", "underpin", "result", "lead", "led to", "yield", "support",
           "linked to", "link between", "reflect", "express", "translat", "manifest", "responsib",
           "attributable", "owing", "thanks", "because", "due to", "conducive",
           # conjunctions and "result of / in combination with" forms
           "as a consequence", "for this reason", "that is why", "indeed"),
    "el": ("χάρη σ", "λόγω", "εξαιτίας", "οφείλεται", "οφείλονται", "προσδίδει", "προσδίδουν",
           "επιτρέπει", "επιτρέπουν", "ευνοεί", "ευνοούν", "συμβάλλει", "συμβάλλουν", "οδηγεί",
           "οδηγούν", "καθορίζει", "καθορίζουν", "εξηγεί", "εξηγούν", "με αποτέλεσμα",
           "ως αποτέλεσμα", "κατά συνέπεια", "συνεπώς", "επομένως", "επηρεάζει", "επηρεάζουν",
           "εξασφαλίζει", "εξασφαλίζουν", "δίνει", "δίνουν", "χαρίζει", "χαρίζουν", "αποδίδει",
           "αποδίδουν", "διαμορφώνει", "διαμορφώνουν", "προσφέρει", "προσφέρουν", "υπεύθυν",
           "δημιουργεί", "δημιουργούν", "επιδρ", "συντελεί", "συντελούν",
           # noun, gerund and consecutive forms (2026-09-14 smoke: "glavni čimbenik",
           # "fördert", "και έτσι", "hace que" were dropped as unearned)
           "έτσι", "παράγοντ", "επίδρασ", "ρόλο", "αιτία", "χάρις", "ώστε", "καθοριστικ",
           "αποφασιστικ", "εξαρτ", "βασίζ", "προϋπόθεση", "με τη σειρά",
           # word-initial stems (the inflections and gerunds the smoke and the FR / NL / RO
           # samples showed missing: "déterminent", "contribuant", "vertaalt zich")
           "προσδίδ", "επιτρέπ", "ευνο", "συμβάλλ", "οδηγ", "καθορίζ", "εξηγ", "επηρε",
           "εξασφαλίζ", "χαρίζ", "αποδίδ", "διαμορφών", "προσφέρ", "δημιουργ", "συντελ", "οφείλ",
           "εξαρτ", "ευθύν", "συνδέ", "αντανακλ", "εκφράζ", "μεταφράζ", "καθιστ",
           # conjunctions and "result of / in combination with" forms
           "συνδυασμ", "ανάλογα", "επειδή", "διότι", "καθώς", "αφού", "γι' αυτό", "γι’ αυτό"),
    "bg": ("благодарение на", "поради", "вследствие", "в резултат", "се дължи", "се дължат",
           "придава", "придават", "позволява", "позволяват", "благоприятства", "благоприятстват",
           "допринася", "допринасят", "води до", "водят до", "определя", "определят", "обуславя",
           "обуславят", "затова", "следователно", "влияе", "влияят", "осигурява", "осигуряват",
           "обяснява", "обясняват", "формира", "формират", "създава", "създават", "спомага",
           "спомагат", "отговорн", "предпоставка",
           # noun, gerund and consecutive forms (2026-09-14 smoke: "glavni čimbenik",
           # "fördert", "και έτσι", "hace que" were dropped as unearned)
           "фактор", "фактори", "роля", "влияние", "определящ", "решаващ", "ключов", "така",
           "по този начин", "предопредел", "зависи", "зависят", "основа за", "условие за",
           # word-initial stems (the inflections and gerunds the smoke and the FR / NL / RO
           # samples showed missing: "déterminent", "contribuant", "vertaalt zich")
           "придав", "позволяв", "благоприят", "допринас", "определ", "обуслав", "влия",
           "осигуряв", "обясняв", "формир", "създав", "спомаг", "завис", "дълж", "свързан",
           "отраз", "изразяв", "предпостав", "благодарение", "поради",
           # conjunctions and "result of / in combination with" forms
           "резултат", "съчетани", "защото", "тъй като", "понеже", "ето защо"),
    "hu": ("köszönhető", "köszönhetően", "miatt", "következtében", "eredményeként",
           "eredményeképpen", "hatására", "biztosít", "biztosítja", "biztosítják", "lehetővé tesz",
           "lehetővé teszi", "lehetővé teszik", "kedvez", "kedveznek", "hozzájárul",
           "hozzájárulnak", "eredményez", "eredményezi", "eredményezik", "meghatároz",
           "meghatározza", "meghatározzák", "magyaráz", "magyarázza", "ezért", "így", "tehát",
           "ennélfogva", "befolyásol", "befolyásolja", "befolyásolják", "kölcsönöz", "kölcsönöznek",
           "okoz", "okozza", "okozzák", "alakít", "alakítja", "alakítják", "teszi lehetővé",
           "felelős", "elősegít", "elősegíti",
           # noun, gerund and consecutive forms (2026-09-14 smoke: "glavni čimbenik",
           # "fördert", "και έτσι", "hace que" were dropped as unearned)
           "tényező", "tényezők", "szerep", "hatás", "döntő", "kulcs", "ezáltal", "függ",
           "függenek", "alapja", "feltétele", "meghatározó",
           # word-initial stems (the inflections and gerunds the smoke and the FR / NL / RO
           # samples showed missing: "déterminent", "contribuant", "vertaalt zich")
           "biztosít", "lehetővé", "kedvez", "hozzájárul", "eredményez", "meghatároz", "magyaráz",
           "befolyásol", "kölcsönöz", "okoz", "alakít", "elősegít", "függ", "köszönhet", "tükröz",
           "megnyilvánul", "összefügg", "kapcsolat", "hatás", "adja", "adják", "ad a",
           # conjunctions and "result of / in combination with" forms
           "garantál", "adódó", "jelenti", "alapj", "megteremt", "mivel", "mert", "hiszen",
           "ugyanis"),
    "cs": ("díky", "kvůli", "v důsledku", "vlivem", "následkem", "dodává", "dodávají", "umožňuje",
           "umožňují", "podporuje", "podporují", "přispívá", "přispívají", "vede k", "vedou k",
           "určuje", "určují", "způsobuje", "způsobují", "vysvětluje", "proto", "tudíž", "tedy",
           "takže", "ovlivňuje", "ovlivňují", "zajišťuje", "zajišťují", "propůjčuje", "propůjčují",
           "má za následek", "mají za následek", "podmiňuje", "podmiňují", "utváří", "vytváří",
           "zodpovědn", "zodpovídá",
           # noun, gerund and consecutive forms (2026-09-14 smoke: "glavni čimbenik",
           # "fördert", "και έτσι", "hace que" were dropped as unearned)
           "faktor", "faktory", "role", "vliv", "určující", "rozhodující", "klíčov", "závisí",
           "závislý", "závislé", "základ pro", "předpoklad", "podmínk",
           # word-initial stems (the inflections and gerunds the smoke and the FR / NL / RO
           # samples showed missing: "déterminent", "contribuant", "vertaalt zich")
           "dodáv", "umožň", "podporuj", "přispív", "vede k", "vedou k", "určuj", "způsobuj",
           "vysvětl", "ovlivň", "zajišť", "propůjč", "podmiň", "utvář", "vytvář", "závis", "odráž",
           "projevuj", "souvis", "spojen", "díky", "dává", "dávají",
           # conjunctions and "result of / in combination with" forms
           "protože", "neboť", "jelikož", "výsledk", "kombinac"),
    "sk": ("vďaka", "kvôli", "v dôsledku", "vplyvom", "následkom", "dodáva", "dodávajú", "umožňuje",
           "umožňujú", "podporuje", "podporujú", "prispieva", "prispievajú", "vedie k", "vedú k",
           "určuje", "určujú", "spôsobuje", "spôsobujú", "vysvetľuje", "preto", "teda", "takže",
           "ovplyvňuje", "ovplyvňujú", "zabezpečuje", "zabezpečujú", "prepožičiava", "prepožičiavajú",
           "má za následok", "podmieňuje", "podmieňujú", "vytvára", "vytvárajú", "utvára",
           "zodpovedn",
           # noun, gerund and consecutive forms (2026-09-14 smoke: "glavni čimbenik",
           # "fördert", "και έτσι", "hace que" were dropped as unearned)
           "faktor", "faktory", "rola", "úloha", "vplyv", "určujúc", "rozhodujúc", "kľúčov",
           "závisí", "závislý", "závislé", "základ pre", "predpoklad", "podmienk",
           # word-initial stems (the inflections and gerunds the smoke and the FR / NL / RO
           # samples showed missing: "déterminent", "contribuant", "vertaalt zich")
           "dodáv", "umožň", "podporuj", "prispiev", "vedie k", "vedú k", "určuj", "spôsobuj",
           "vysvetľ", "ovplyvň", "zabezpeč", "prepožič", "podmieň", "utvár", "vytvár", "závis",
           "odráž", "prejavuj", "súvis", "spojen", "vďaka", "dáva", "dávajú",
           # conjunctions and "result of / in combination with" forms
           "pretože", "lebo", "keďže", "výsledk", "kombináci"),
    "sl": ("zaradi", "po zaslugi", "zahvaljujoč", "kot posledica", "posledično", "daje", "dajejo",
           "omogoča", "omogočajo", "spodbuja", "spodbujajo", "prispeva", "prispevajo", "vodi do",
           "vodijo do", "določa", "določajo", "povzroča", "povzročajo", "pojasnjuje", "zato",
           "torej", "vpliva", "vplivajo", "zagotavlja", "zagotavljajo", "oblikuje", "oblikujejo",
           "ustvarja", "ustvarjajo", "odgovorn", "pogojuje", "pogojujejo",
           # noun, gerund and consecutive forms (2026-09-14 smoke: "glavni čimbenik",
           # "fördert", "και έτσι", "hace que" were dropped as unearned)
           "dejavnik", "dejavniki", "vloga", "vpliv", "odločiln", "ključn", "odvisn", "osnova za",
           "pogoj",
           # word-initial stems (the inflections and gerunds the smoke and the FR / NL / RO
           # samples showed missing: "déterminent", "contribuant", "vertaalt zich")
           "omogoč", "spodbuj", "prispev", "vodi", "določ", "povzroč", "pojasn", "vpliv",
           "zagotav", "oblikuj", "ustvarj", "odvisn", "odraž", "kaže se", "kažejo se", "izraž",
           "povez", "zaradi", "daj",
           # conjunctions and "result of / in combination with" forms
           "ker ", "saj ", "kajti", "rezultat", "kombinacij"),
    "hr": ("zahvaljujući", "zbog", "uslijed", "kao posljedica", "posljedično", "daje", "daju",
           "omogućuje", "omogućuju", "omogućava", "omogućavaju", "pogoduje", "pogoduju", "pridonosi",
           "pridonose", "doprinosi", "doprinose", "dovodi do", "dovode do", "određuje", "određuju",
           "uzrokuje", "uzrokuju", "objašnjava", "stoga", "zato", "dakle", "utječe", "utječu",
           "osigurava", "osiguravaju", "oblikuje", "oblikuju", "stvara", "stvaraju", "rezultira",
           "rezultiraju", "odgovorn", "uvjetuje", "uvjetuju",
           # noun, gerund and consecutive forms (2026-09-14 smoke: "glavni čimbenik",
           # "fördert", "και έτσι", "hace que" were dropped as unearned)
           "čimben", "faktor", "faktori", "utjecaj", "ulog", "uzrok", "razlog", "zaslug",
           "preduvjet", "ključn", "presudn", "odlučuj", "ovisi", "ovise", "temelj",
           # word-initial stems (the inflections and gerunds the smoke and the FR / NL / RO
           # samples showed missing: "déterminent", "contribuant", "vertaalt zich")
           "omoguć", "pogod", "pridonos", "doprinos", "dovod", "određ", "uzrok", "objašnj", "utje",
           "osigur", "oblikuj", "stvar", "rezultir", "uvjet", "ovis", "odraž", "očituj", "povez",
           "zahvaljuj", "zaslug", "daj",
           # conjunctions and "result of / in combination with" forms
           "jer ", "budući", "pošto", "s obzirom", "rezultat", "kombinacij"),
    "ro": ("datorită", "din cauza", "ca urmare", "drept urmare", "ca rezultat", "conferă",
           "permite", "permit", "favorizează", "contribuie", "duce la", "duc la", "conduce la",
           "conduc la", "determină", "explică", "generează", "asigură", "de aceea", "prin urmare",
           "astfel", "influențează", "imprimă", "oferă", "rezultă", "se datorează", "se datorează",
           "responsabil", "condiționează", "face posibil", "fac posibil",
           # noun, gerund and consecutive forms (2026-09-14 smoke: "glavni čimbenik",
           # "fördert", "και έτσι", "hace que" were dropped as unearned)
           "factor", "factori", "rol", "influenț", "determinant", "decisiv", "cheie", "depinde",
           "depind", "face ca", "fac ca", "conferind", "permițând", "favorizând", "contribuind",
           "asigurând", "generând", "baza",
           # word-initial stems (the inflections and gerunds the smoke and the FR / NL / RO
           # samples showed missing: "déterminent", "contribuant", "vertaalt zich")
           "confer", "permit", "favoriz", "contribu", "duce la", "duc la", "conduc", "determin",
           "explic", "gener", "asigur", "influenţ", "influenț", "imprim", "ofer", "rezult",
           "datorit", "depind", "facilit", "înseamnă", "face din", "fac din", "dă", "dau",
           "condiţii în care", "condiții în care", "reflect", "se regăs", "legat de", "legătur",
           "condiţion", "condiț",
           # conjunctions and "result of / in combination with" forms
           "deoarece", "pentru că", "întrucât", "fiindcă", "relaţi", "relați", "combinaţi",
           "combinați", "asigur"),
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


_RO_CEDILLA = str.maketrans({"ţ": "ț", "ş": "ș", "Ţ": "Ț", "Ş": "Ș"})


def has_connective(text: str, lang: str) -> bool:
    """True when `text` (a source quote) carries an explicit causal or
    consecutive connective of `lang`. Unknown language → False. Romanian
    text is folded to comma-below (ț / ș) first — the sources mix both
    spellings; a Dutch record is also tried against the English table
    (Ambt Delden's single document exists only in English)."""
    if not text:
        return False
    pat = _pattern(lang)
    if not pat:
        return False
    if lang == "ro":
        text = text.translate(_RO_CEDILLA)
    if pat.search(text):
        return True
    return lang == "nl" and bool(_pattern("en").search(text))


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
