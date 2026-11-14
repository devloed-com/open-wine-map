"""The technical file of a spirit-drink GI, as the EU register serves it.

Reg. (EC) 110/2008 Art. 20 had every established spirit GI transmit a
"technical file" (Art. 17(4): name and category, description, geographical
area, method, link, provisions, applicant, supplement / labelling); the
register attaches it to the GI as `singleDocTechFile`. Three layouts reach
us, all of them text-layer PDFs:

- **e-form** — the Commission's own form, printed from eAmbrosia
  ("Transmission of an established geographical indication of spirit
  drinks" in the application language): `I. TECHNICAL FILE`, then `1.` Name
  and type (a name, b category, c country, d language, e type), `2.` Contact
  details, `3.` Description, `4.` Define geographical area (a description,
  b NUTS area), `5.` Method, `6.` Link, `7.` EU / national requirements,
  `8.` Supplement, `9.` Labelling rules, `II. Other information`. The
  numbering is the same in every language, so the sections are read by
  number; the bodies are two-column tables (a label column, a value column).
- **e-form, decimal** — the same form exported with `1.3.` / `1.4.1.`
  numbering (`1. TECHNICAL FILE`, `2. OTHER INFORMATION`).
- **form** — a word-processor document of the member state, following the
  headings of Annex I to Reg. (EU) No 716/2013 in its own language and
  numbering ("Technische Unterlage", "Scheda tecnica", "ΤΕΧΝΙΚΟΣ ΦΑΚΕΛΟΣ",
  "ТЕХНИЧЕСКО ДОСИЕ"). Sections are found by their heading words
  (`ROLE_HEADINGS`, every language pooled: a heading is a short line, so a
  word of another language never collides in practice).

`parse(text)` returns the layout, the roles (`name`, `category`,
`language`, `description`, `geo_area`, `method`, `link`, `labelling`), the
NUTS units of section 4b and the section titles it read. A role it cannot
find is absent — the caller reports it; nothing is guessed.
"""
from __future__ import annotations

import re
from collections import Counter

from unidecode import unidecode

ROLES: tuple[str, ...] = (
    "name", "category", "language", "description", "geo_area", "method", "link", "labelling",
)

# --- page furniture ---------------------------------------------------------

_FURNITURE_RES = (
    re.compile(r"^\s*Ref\. Ares\(\d{4}\)\d+\s*-\s*\d{2}/\d{2}/\d{4}\s*$"),
    re.compile(r"^\s*(?:PGI|PDO)-[A-Z+()]{2,}-\d+\s*$"),
    # "Generado el 27-06-2016 11:45:01" in any language: a word or two, then a timestamp
    re.compile(r"^\s*(?:\S+\s+){0,4}\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2}:\d{2}\b.*$"),
    # the running title with the page counter at the right edge
    re.compile(r"^\s{10,}\S.*\s{2,}\d{1,3}\s*/\s*\d{1,3}\s*$"),
    re.compile(r"^\s*\d{1,3}\s*/\s*\d{1,3}\s*$"),
    re.compile(r"^\s*-?\s*\d{1,3}\s*-?\s*$"),
)


def clean_text(text: str) -> str:
    """Drop the page furniture (the Ares stamp, the file number, the print
    timestamp, the running title, bare page numbers) and fold form feeds."""
    out: list[str] = []
    for line in (text or "").replace("\x0c", "\n").split("\n"):
        if any(rx.match(line) for rx in _FURNITURE_RES):
            continue
        out.append(line.rstrip())
    return "\n".join(out)


# --- the e-form ---------------------------------------------------------------

_EFORM_TOP_RE = re.compile(r"^(?P<indent>\s{0,14})(?P<n>[1-9])\.\s?(?P<title>[^\d\s][^\n]*)$")
_EFORM_ROMAN_RE = re.compile(r"^\s{0,10}(I{1,2})\.\s?\S")
_EFORM_SUB_RE = re.compile(r"^\s{4,24}(?P<k>[a-e])\.\s?(?P<title>\S[^\n]*)$")
_DECIMAL_TOP_RE = re.compile(r"^\s{0,14}1\.(?P<n>[1-9])\.\s+(?P<title>\S[^\n]*)$")
_DECIMAL_SUB_RE = re.compile(r"^\s{0,24}1\.(?P<n>[1-9])\.(?P<k>[1-9])\.\s+(?P<title>\S[^\n]*)$")
_DECIMAL_END_RE = re.compile(r"^\s{0,10}2\.\s{2,}\S")
_NUTS_RE = re.compile(r"^\s*(?P<code>[A-Z]{2}[0-9A-Z]{0,3})\s{2,}(?P<name>\S[^\n]*?)\s*$")
_NUTS_INLINE_RE = re.compile(r"\b([A-Z]{2}[0-9A-Z]{1,3})\b")
_GAP_RE = re.compile(r"^(?P<lead>\s*)(?P<left>\S.*?)(?P<gap>\s{3,})(?P<right>\S.*)$")

_EFORM_ROLE_BY_NUMBER = {3: "description", 4: "geo_area", 5: "method", 6: "link", 9: "labelling"}


def _eform_sections(lines: list[str]) -> dict[int, tuple[str, list[str]]] | None:
    """{n: (title, body lines)} for the `I.` part of an e-form, or None."""
    start = next((i for i, ln in enumerate(lines[:80]) if _EFORM_ROMAN_RE.match(ln)), None)
    if start is None:
        return None
    end = len(lines)
    for i in range(start + 1, len(lines)):
        m = _EFORM_ROMAN_RE.match(lines[i])
        if m and m.group(1) == "II":
            end = i
            break
    heads: list[tuple[int, int, str]] = []
    last = 0
    indent: int | None = None
    for i in range(start + 1, end):
        m = _EFORM_TOP_RE.match(lines[i])
        if not m:
            continue
        n = int(m.group("n"))
        ind = len(m.group("indent"))
        if indent is None:
            if n != 1:
                continue
            indent = ind
        elif abs(ind - indent) > 2 or n <= last:
            continue
        heads.append((n, i, m.group("title").strip()))
        last = n
    if len(heads) < 5:
        return None
    out: dict[int, tuple[str, list[str]]] = {}
    for j, (n, i, title) in enumerate(heads):
        stop = heads[j + 1][1] if j + 1 < len(heads) else end
        out[n] = (title, lines[i + 1: stop])
    return out


def _decimal_sections(lines: list[str]) -> dict[int, tuple[str, list[str]]] | None:
    heads: list[tuple[int, int, str]] = []
    last = 0
    end = len(lines)
    for i, ln in enumerate(lines):
        # "2.    OTHER INFORMATION" closes the technical file; a numbered
        # list item inside a section ("2.  Mezcladas: …") does not
        if last >= 7 and _DECIMAL_END_RE.match(ln):
            end = i
            break
        m = _DECIMAL_TOP_RE.match(ln)
        if not m:
            continue
        n = int(m.group("n"))
        if n <= last:
            continue
        heads.append((n, i, m.group("title").strip()))
        last = n
    if len(heads) < 5:
        return None
    out: dict[int, tuple[str, list[str]]] = {}
    for j, (n, i, title) in enumerate(heads):
        stop = heads[j + 1][1] if j + 1 < len(heads) else end
        out[n] = (title, lines[i + 1: stop])
    return out


def _value_column(body: list[str]) -> int | None:
    """The column the value cells of a two-column section start at: the
    indent most of the value-only lines share (a wrapped value has no label
    beside it). None for a section printed in one column."""
    leads = [len(ln) - len(ln.lstrip()) for ln in body if ln.strip()]
    if len(leads) < 3:
        return None
    base = min(leads)
    deep = Counter(lead for lead in leads if lead >= base + 8)
    if not deep:
        return None
    col, n = deep.most_common(1)[0]
    return col if n >= 2 and n >= len(leads) // 6 else None


def _label_column_lines(body: list[str], col: int) -> list[str]:
    """The lines of a two-column section that start in the label column."""
    return [
        re.sub(r"\s+", " ", ln.strip()) for ln in body
        if ln.strip() and (len(ln) - len(ln.lstrip())) < col - 4
    ]


def learn_labels(texts: list[str]) -> frozenset[str]:
    """The row labels of the e-form in one language, learnt from several
    files of that language.

    pdftotext prints a label cell and its value cell on one line, one space
    apart when the label fills its cell ("Datos de la zona geográfica El
    vínculo con …", "o del origen pertinentes para ligado a …"), so neither
    a gap nor a column tells where the label ends. The form does: its labels
    are the same in every file of a language while the values differ. A
    label fragment is the longest run of opening words of a label-column
    line that most files sharing its first word also share (60 %, two files
    at least) — "Referencia jurídica" stays a label when five of nine files
    go on "Real Decreto"; with fewer than four files of a language nothing is
    learnt, and a label that runs into its value stays in the text (a few
    words too many, never a value word too few)."""
    per_doc: list[list[list[str]]] = []
    for text in texts:
        lines = clean_text(text).split("\n")
        sections = _eform_sections(lines)
        if sections is None or 4 not in sections:
            sections = _decimal_sections(lines)
        if sections is None:
            continue
        doc_lines: list[list[str]] = []
        for n in (3, 5, 6, 9):
            if n not in sections:
                continue
            body = sections[n][1]
            col = _value_column(body)
            if col is None:
                continue
            doc_lines += [ln.split(" ") for ln in _label_column_lines(body, col)]
        if doc_lines:
            per_doc.append(doc_lines)
    if len(per_doc) < 4:
        return frozenset()
    docs_with: dict[tuple[str, ...], set[int]] = {}
    for d, doc_lines in enumerate(per_doc):
        for words in doc_lines:
            for k in range(1, min(len(words), 10) + 1):
                docs_with.setdefault(tuple(words[:k]), set()).add(d)
    labels: set[str] = set()
    for doc_lines in per_doc:
        for words in doc_lines:
            # shared by half the files of the language, and by most of those
            # that open on the same word
            base = len(docs_with[tuple(words[:1])])
            need = max(3, -(-len(per_doc) // 2), -(-base * 6 // 10))
            best = 0
            for k in range(1, min(len(words), 10) + 1):
                if len(docs_with[tuple(words[:k])]) >= need:
                    best = k
                else:
                    break
            fragment = " ".join(words[:best])
            if best and len(fragment) >= 3 and not fragment.isdigit():
                labels.add(fragment)
    return frozenset(labels)


def _strip_label(line: str, labels: frozenset[str]) -> str | None:
    """The value part of a label-column line whose opening words are a known
    label fragment ("" for a label printed alone); None when none opens it."""
    s = re.sub(r"\s+", " ", line.strip())
    best = ""
    for f in labels:
        if len(f) > len(best) and (s == f or s.startswith(f + " ")):
            best = f
    if not best:
        return None
    return s[len(best):].strip()


def _table_values(body: list[str], name: str = "", labels: frozenset[str] = frozenset()) -> str:
    """The prose of a two-column section: the value cells, the label column
    dropped. A line indented to the value column is a value line. A line
    that starts in the label column opens with a label fragment: a learnt
    one (`learn_labels`) is cut off; failing that, a clear gap separates the
    two cells, or the line is a label printed alone. The first row of the
    form's tables repeats the product name ("Title — Product name"):
    dropped."""
    col = _value_column(body)
    if col is None:
        return _paragraphs([ln.strip() for ln in body])
    out: list[str] = []
    for ln in body:
        if not ln.strip():
            out.append("")
            continue
        lead = len(ln) - len(ln.lstrip())
        if lead >= col - 4:
            out.append(ln.strip())
            continue
        new_row = _opens_row(ln)
        value = _strip_label(ln, labels)
        if value is None:
            m = _GAP_RE.match(ln)
            if m and len(m.group("left")) <= 44:
                value = m.group("right").strip()
            elif len(ln.rstrip()) <= col:
                value = ""
            else:
                value = ln.strip()  # text across both columns
        # a new row opens a paragraph — unless the line above stops mid-
        # sentence, which is the wrapped label of the same row (every German
        # label fragment starts on a capital)
        if new_row and out and out[-1] != "" and out[-1].rstrip()[-1:] in ".:;!?":
            out.append("")
        if value:
            out.append(value)
    text = _paragraphs(out)
    if name:
        first, _, rest = text.partition("\n")
        if _norm(first) and (_norm(first) in _norm(name) or _norm(name) in _norm(first)) \
                and len(first) <= len(name) + 40:
            text = rest
    return text.strip()


def _opens_row(label: str) -> bool:
    """A label cell that starts a new table row (a capitalised label), as
    against the wrapped continuation of the label above."""
    s = label.strip()
    return bool(s) and (s[0].isupper() or s[0].isdigit())


def _paragraphs(lines: list[str]) -> str:
    """Join wrapped lines into paragraphs (blank line = break); a line that
    opens a list item or follows a sentence end starts a new line."""
    paras: list[str] = []
    cur: list[str] = []
    for ln in lines:
        s = ln.strip()
        if not s:
            if cur:
                paras.append(" ".join(cur))
                cur = []
            continue
        if cur and re.match(r"^(?:[-–•·*]|\d{1,2}[.)]|[a-z]\))\s", s):
            paras.append(" ".join(cur))
            cur = []
        if cur and cur[-1].endswith("-") and not cur[-1].endswith(" -") and s[:1].islower():
            cur[-1] = cur[-1][:-1] + s
        else:
            cur.append(s)
    if cur:
        paras.append(" ".join(cur))
    return "\n".join(p for p in paras if p)


def _split_sub(body: list[str], decimal_n: int | None = None) -> dict[str, tuple[str, list[str]]]:
    """Sub-items of a section: {a: (title, lines), b: …} (the decimal form's
    1.4.1 / 1.4.2 map to a / b)."""
    marks: list[tuple[str, int, str]] = []
    for i, ln in enumerate(body):
        if decimal_n is not None:
            m = _DECIMAL_SUB_RE.match(ln)
            if m and int(m.group("n")) == decimal_n:
                marks.append(("abcdefghi"[int(m.group("k")) - 1], i, m.group("title").strip()))
        else:
            m = _EFORM_SUB_RE.match(ln)
            if m:
                marks.append((m.group("k"), i, m.group("title").strip()))
    out: dict[str, tuple[str, list[str]]] = {}
    for j, (k, i, title) in enumerate(marks):
        stop = marks[j + 1][1] if j + 1 < len(marks) else len(body)
        out.setdefault(k, (title, body[i + 1: stop]))
    return out


def parse_nuts(lines: list[str]) -> list[dict]:
    """The NUTS rows of section 4b: `ES612   Cádiz`."""
    out: list[dict] = []
    seen: set[str] = set()
    for ln in lines:
        m = _NUTS_RE.match(ln)
        if not m:
            continue
        code = m.group("code")
        if code in seen or not _plausible_nuts(code):
            continue
        seen.add(code)
        out.append({"code": code, "name": m.group("name").strip()})
    return out


_NUTS_COUNTRIES = frozenset((
    "AT BE BG CY CZ DE DK EE EL ES FI FR HR HU IE IT LT LU LV MT NL PL PT RO SE SI SK UK "
    "NO CH IS LI"
).split())


def _plausible_nuts(code: str) -> bool:
    return code[:2] in _NUTS_COUNTRIES and len(code) <= 5


def _first_value(lines: list[str]) -> str:
    return next((ln.strip() for ln in lines if ln.strip()), "")


def _parse_eform(lines: list[str], sections: dict[int, tuple[str, list[str]]], decimal: bool,
                 labels: frozenset[str] = frozenset()) -> dict:
    roles: dict[str, str] = {}
    titles: dict[str, str] = {}
    nuts: list[dict] = []
    if 1 in sections:
        sub = _split_sub(sections[1][1], 1 if decimal else None)
        if "a" in sub:
            roles["name"] = re.sub(r"\s*\([a-z]{2}\)\s*$", "", _first_value(sub["a"][1]))
        if "b" in sub:
            roles["category"] = _first_value(sub["b"][1])
        if "d" in sub:
            roles["language"] = _first_value(sub["d"][1])
    name = roles.get("name", "")
    for n, role in _EFORM_ROLE_BY_NUMBER.items():
        if n not in sections:
            continue
        title, body = sections[n]
        titles[role] = title
        if role == "geo_area":
            sub = _split_sub(body, 4 if decimal else None)
            desc = sub.get("a", ("", body))[1]
            roles[role] = _paragraphs([ln.strip() for ln in desc])
            if "b" in sub:
                nuts = parse_nuts(sub["b"][1])
        else:
            roles[role] = _table_values(body, name, labels)
    return {
        "layout": "eform-decimal" if decimal else "eform",
        "roles": {k: v for k, v in roles.items() if v},
        "geo_nuts": nuts,
        "section_titles": titles,
    }


# --- the word-processor form --------------------------------------------------

# Heading words per role, every language pooled, compared after unidecode +
# lower-casing. `stop` roles end a section without being read.
ROLE_HEADINGS: dict[str, tuple[str, ...]] = {
    "category": (
        "category of the spirit", "kategorie der spirituose", "categoria della bevanda",
        "categoria de la bebida", "categoria da bebida", "categorie de la boisson",
        "katigoria tou alkooloukhou", "kategoriia spirtna", "kategoriia na spirtnata",
        "categoria bauturii", "kategorija jakog", "kategoria liehoviny",
        "kategorija zgane", "categorie van de gedistilleerde",
    ),
    "description": (
        "szeszes ital jellemzoinek", "opis vlastnosti liehoviny",
        "description of the product", "description of product", "product description", "description of principal analytical",
        "description of the aromatised",
        "description du produit", "beschreibung des erzeugnisses",
        "description of the characteristics",
        "description of the spirit", "beschreibung der spirituose", "descrizione della bevanda",
        "descripcion de la bebida", "descricao da bebida", "description de la boisson",
        "perigraphe tou", "opisanie na spirtnata", "descrierea bauturii", "opis jakog",
        "opis liehoviny", "popis liehoviny", "opis zgane", "a szeszes ital leirasa",
        "beschrijving van de gedistilleerde", "descrizione del prodotto",
        "caratteristiche del prodotto", "descripcion del producto",
        "descrizione delle caratteristiche", "descripcion de las caracteristicas",
        "beschreibung des agrarerzeugnisses", "description of the agricultural product",
        "descricao do produto", "description du produit", "beschreibung des erzeugnisses",
        "description of the product", "opis proizvoda", "a termek leirasa",
    ),
    "geo_area": (
        "demarcation of the relevant geographical",
        "geographical area", "geografisches gebiet", "geographisches gebiet",
        "zona geografica", "area geografica", "zone geographique", "aire geographique",
        "skhetike geographike periokhe", "geographike periokhe", "geografski raion",
        "zemljopisno podrucje", "geografsko obmocje", "zemepisna oblast", "foldrajzi terulet",
        "aria geografica", "geografisch gebied", "delimitacion de la zona",
        "zona de produccion", "zona di produzione", "zemepisnej oblasti",
        "geografskega obmocja", "zemljopisnog podrucja", "geografskog podrucja",
        "area geografica da", "regiao demarcada", "foldrajzi teruletet",
        "geografischen gebiet", "geographischen gebiet", "definition of the geographical",
        "delimitacao da area", "zemljopisnog podrucja", "geografskii raion",
    ),
    "method": (
        "beschreibung der produktions",
        "postup vyroby",
        "particular production processes", "specific production processes",
        "herstellungsmethode",
        "method for obtaining", "method of obtaining", "method of production",
        "verfahren zur gewinnung", "verfahren zur herstellung", "herstellungsverfahren",
        "metodo di produzione", "metodo di ottenimento", "metodo di elaborazione",
        "metodo de obtencion", "metodo de elaboracion", "metodo de obtencao",
        "methode d'obtention", "methode d obtention", "methodos paraskeues",
        "methodos paragoges", "metod na poluchavane", "metod za proizvodstvo",
        "metod za poluchavane", "metoda de obtinere", "metoda dobivanja", "postupak proizvodnje",
        "sposob vyroby", "postopek pridobivanja", "eloallitasanak modja",
        "werkwijze voor het verkrijgen", "processo di produzione",
        "metode pridobivanja", "metoda pridobivanja", "sposobu ziskania", "sposob ziskania",
        "metode dobivanja", "nacin proizvodnje", "descripcion del metodo",
        "descrizione del metodo", "beschreibung des verfahrens", "description de la methode",
        "descricao do metodo", "ingredientes",
    ),
    "link": (
        "kozotti kapcsolat", "opis suvislosti", "suvislost medzi",
        "details bearing out the link",
        "link pursuant to",
        "dossier historique", "elements historiques", "geschichtliche elemente", "typicite du produit", "preuve du lien", "nachweis des zusammenhangs",
        "description of the link", "links with geographical origin", "link between the spirit drink",
        "link with the geographical", "zusammenhang mit", "legame con", "vinculo con",
        "relacion con el entorno", "relacion con el medio", "lien avec",
        "ligacao com", "relacao com", "desmos me", "vr'zka s geografskata", "vrzka s geografskata",
        "legatura cu", "povezanost s", "povezava z", "suvislost", "kapcsolat a",
        "verband met", "elementi che dimostrano il legame", "elementos que prueban",
        "ligacao ao", "ligacao a origem", "relacion con el origen", "povezavo z",
        "spojenie so zemepisnym", "suvislost so zemepisnym", "desmos me", "sviaz s",
        "vr'zka s", "vrzka s", "legatura cu mediul", "povezanost sa",
    ),
    "labelling": (
        "specific labelling", "labelling rules", "etikettierungsvorschriften",
        "norme specifiche in materia di etichettatura", "norme di etichettatura",
        "etichettatura", "normas especificas de etiquetado", "etiquetado",
        "regles d'etiquetage", "regles specifiques d'etiquetage", "rotulagem",
        "kanones episemanses", "episemanse", "pravila za etiketirane", "etiketirane",
        "reguli de etichetare", "pravila za oznacivanje", "oznacovanie", "oznacevanje",
        "cimkezes", "etiketteringsvoorschriften",
    ),
    "stop": (
        "odkaz na uverejnenie", "hivatkozas a termekleiras", "reference to publication of the", "reference to the publication of the",
        "main raw material", "applicable requirements", "authorities or bodies verifying", "name and address of the authorities", "names and addresses of the authorities",
        "etiquetage et certification", "kennzeichnung und zertifizierung", "mindestanforderungen an die kontrolle", "description des methodes locales", "beschreibung der lokalen",
        "proof of origin", "inspection body",
        "european union or national", "eu- oder nationale", "eu oder nationale",
        "gemeinschaftliche oder", "disposizioni dell'unione", "disposizioni comunitarie",
        "disposizioni nazionali", "disposiciones de la union", "disposiciones comunitarias",
        "requisitos establecidos", "requisitos de la ue", "dispositions de l'union",
        "dispositions communautaires", "disposicoes", "diataxeis", "razporedbi",
        "dispozitii", "odredbe", "ustanovenia", "dolocbe", "bepalingen",
        "applicant", "antragsteller", "richiedente", "solicitante", "demandeur", "requerente",
        "o aiton", "zaiavitel", "solicitant", "podnositelj", "ziadatel", "vlagatelj",
        "kerelmezo", "aanvrager",
        "supplement to the geographical", "erganzung der geografischen",
        "complemento all'indicazione", "complemento de la indicacion", "complemento a la indicacion",
        "complement a l'indication", "dop'lnenie k'm", "dopulnenie kum", "dopalnenie",
        "sympleroma", "supliment", "dodatak oznaci", "aanvulling",
        "complemento a indicacao", "protecao nacional", "entidade que verifica",
        "zahteve skupnosti", "ime in kontaktni naslov", "dopolnilo h geografski",
        "nombre y direccion", "nazov a adresa", "nome e indirizzo", "name und anschrift",
        "ethnikes diataxeis", "diataxeis tes", "aiton",
        "condizioni da rispettare", "eventuali condizioni", "eventuali requisiti",
        "requisiti previsti", "exigences eventuelles", "requisitos eventuales",
        "condiciones que deben", "anforderungen", "zahteve", "poziadavky", "kovetelmenyek",
        "cerinte", "iziskvaniia", "apaiteseis",
    ),
}

_ENUM_RE = re.compile(
    r"^\s*(?:\(?[A-Za-zΑ-Ωα-ωА-Яа-я]\)|[A-Z]\s*\.\s*-|[IVXΙ]{1,4}\s*\.|\d{1,2}\s*(?:\.\d{1,2})*\s*[.)]?|[-–•])\s*"
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", unidecode(text or "").lower()).strip()


def _letter_spaced(text: str) -> bool:
    """Most of the line's tokens are one or two letters long."""
    tokens = text.split()
    return len(tokens) >= 6 and sum(1 for t in tokens if len(t) <= 2) * 10 >= len(tokens) * 6


def _heading_role(line: str, anywhere: bool = False) -> str | None:
    """The role a line heads, or None: a short line whose first words (an
    enumerator dropped) are a role's heading words. `anywhere` is for a line
    already known to be a heading (a numbered title of a single document):
    the words may then stand at its end — "Kurzbeschreibung der Abgrenzung
    des geografischen Gebiets", "Географско указание … (съответен географски
    район)"."""
    raw = line.strip()
    if not raw or len(raw) > 150:
        return None
    body = _norm(_ENUM_RE.sub("", raw, count=1))
    if not body:
        return None
    if _letter_spaced(body):
        # small capitals come out of pdftotext letter by letter ("D E F I NI
        # T I O N O F T HE GE O GR A P HI C AL A RE A"): compare without spaces
        tight = body.replace(" ", "")
        for role in _ROLE_ORDER:
            for w in ROLE_HEADINGS[role]:
                pos = tight.find(w.replace(" ", ""))
                if pos != -1 and pos <= 30:
                    return role
        return None
    head = body if anywhere else body[:70]
    # The specific roles first: "Vínculo con el área geográfica" is the link,
    # not the area; "Descripción del método de obtención" the method, not the
    # description.
    for role in _ROLE_ORDER:
        for w in ROLE_HEADINGS[role]:
            pos = head.find(w)
            if pos == -1:
                continue
            # the heading words open the line (after at most a short lead such
            # as "angaben zum" / "elementi che dimostrano il")
            if anywhere or pos <= 34:
                return role
    # "Description of Scotch Whisky": the product's own name in the heading
    if re.fullmatch(r"description of [a-z0-9' /-]{3,50}", body.rstrip(" .:;")) and not raw.endswith("."):
        return "description"
    # A one-word heading ("B.- Descripción:", "h) ETIQUETADO.") counts only
    # as a whole short line.
    bare = body.rstrip(" .:;")
    if len(bare) <= 28:
        for role, words in _BARE_HEADINGS.items():
            if bare in words:
                return role
    return None


_ROLE_ORDER: tuple[str, ...] = (
    "link", "method", "labelling", "stop", "category", "geo_area", "description",
)

_BARE_HEADINGS: dict[str, frozenset[str]] = {
    "description": frozenset({
        "descripcion", "descrizione", "beschreibung", "description", "descricao", "opis",
        "perigraphe", "opisanie", "descriere", "leiras", "beschrijving", "popis",
    }),
    "link": frozenset({"link"}),
    "method": frozenset({
        "production method", "metodo de obtencion", "elaboracion", "herstellung", "produzione", "paragoge",
        "proizvodstvo", "elaboracao",
    }),
    "labelling": frozenset({
        "etiquetado", "etichettatura", "etikettierung", "etiquetage", "rotulagem",
        "labelling", "episemanse", "etiketirane", "etichetare", "oznacivanje",
    }),
    "stop": frozenset({
        "cahier des charges", "pflichtenheft", "normativa", "control", "controles", "controlli", "kontrolle", "controle",
        "solicitante", "richiedente", "antragsteller", "demandeur", "requerente",
        "applicant", "aiton", "zaiavitel",
    }),
}


def _is_sentence(line: str) -> bool:
    """A body line rather than a heading: long, or ending like a sentence
    that began before it."""
    s = line.strip()
    if len(s) > 150 or (s[:1].islower() and not re.match(r"^[a-z]\)", s)):
        return True
    # a cross-reference names a section, it does not open one: in brackets
    # ("(βλ. στην ενότητα «Δεσμός με τη γεωγραφική περιοχή»).") or in quotes
    # ("“The links with geographical origin and environment” below.")
    if s[:1] in "“‘\"«„'":
        return True
    return s.startswith("(") and not re.match(r"^\([a-z0-9]{1,3}\)", s)


_CONTENTS_LINE_RE = re.compile(r"\.{4,}\s*\d+\s*$|\s{3,}\d{1,3}(?:\s*-\s*\d{1,3})?\s*$")


def _contents_zone(lines: list[str]) -> set[int]:
    """The line indices of a table of contents: a run of lines ending on a
    page number (four lines apart at most) of which at least three are
    section headings, with the lines between them — an entry wrapped over two
    lines carries its number on the second ("2. DESCRIPTION OF THE SPIRIT
    DRINK INCLUDING PRINCIPAL PHYSICAL, CHEMICAL AND" / "ORGANOLEPTIC
    CHARACTERISTICS   2"), and sub-entries ("2.1. Principal Physical
    Characteristics: 1") sit between the headings. Three headings are
    required, so a table of analytical values (a parameter and a number per
    line) is never taken for one."""
    def numbered(i: int) -> bool:
        return bool(re.search(r"[^\W\d]", lines[i]) and _CONTENTS_LINE_RE.search(lines[i]))

    def entry(i: int) -> bool:
        if not numbered(i):
            return False
        if _heading_role(lines[i]) is not None:
            return True
        # the second line of a wrapped entry: the heading words are above
        return i > 0 and _heading_role(lines[i - 1]) is not None and not numbered(i - 1)

    hits = [i for i in range(len(lines)) if numbered(i)]
    zone: set[int] = set()
    run: list[int] = []
    for i in hits + [10**9]:
        if run and i - run[-1] > 4:
            if sum(1 for k in run if entry(k)) >= 3:
                zone.update(range(run[0] - 1, run[-1] + 1))
            run = []
        run.append(i)
    return zone


_ROW_RE = re.compile(r"^(?P<left>\S(?:.*?\S)?)\s{3,}(?P<right>\S.*)$")
_VALUE_MIN_COL = 24


def _decolumn(lines: list[str]) -> list[str] | None:
    """A file laid out as two-column tables — a label cell at the margin, its
    value cell to the right, label and value wrapping side by side
    ("Demarcation of the relevant geographical      City of Nuremberg" /
    "area                                          Production takes place …")
    — rewritten row by row as the label on a line of its own, then the value
    lines; None for any other file. The value column moves from table to
    table, so each line is cut where it is: a line indented 24 columns or
    more is a value line, a margin line with a gap of three spaces before
    text at such a column is a label and a value. The file is such a table
    when at least four lines are label-and-value and half its lines are one
    or the other (a prose file has a centred title or two at such a column,
    never half its lines)."""
    filled = [ln for ln in lines if ln.strip()]
    if not filled:
        return None

    def cut(ln: str) -> tuple[str, str]:
        indent = len(ln) - len(ln.lstrip())
        if indent >= _VALUE_MIN_COL:
            return "", ln.strip()
        m = _ROW_RE.match(ln)
        if m and m.start("right") >= _VALUE_MIN_COL:
            return m.group("left"), m.group("right")
        return ln.strip(), ""

    cuts = [cut(ln) for ln in filled]
    rows = sum(1 for left, right in cuts if left and right)
    values = sum(1 for left, right in cuts if right and not left)
    # a table's values wrap more than its labels, so value-only lines are the
    # majority; a page printed in two columns of prose (Grappa's decree in the
    # Gazzetta Ufficiale) has text on both sides of nearly every line
    if rows < 4 or values < rows or (rows + values) * 2 < len(filled):
        return None
    out: list[str] = []
    label: list[str] = []
    cells: list[str] = []

    def flush() -> None:
        if label:
            out.append(" ".join(label))
        out.extend(cells)
        if label or cells:
            out.append("")
        label.clear()
        cells.clear()

    label_open = False
    for ln in lines:
        if not ln.strip():
            label_open = False
            continue
        left, right = cut(ln)
        if left and not right and _heading_role(left) is not None:
            # a heading printed across the margin, above the rows it heads
            flush()
            out.extend([left, ""])
            label_open = False
            continue
        if left:
            # a label goes on over the next margin lines ("Link pursuant to
            # Article 2(3) of Regulation (EU)" / "No 251/2014") until a blank
            # line, a value-only line, or a margin line that is itself a
            # section heading: rows may follow each other with no gap
            if not label_open or _heading_role(left) is not None:
                flush()
                label_open = True
            label.append(left)
        else:
            label_open = False
        if right:
            cells.append(right)
    flush()
    return out


def _parse_form(lines: list[str]) -> dict:
    lines = _decolumn(lines) or lines
    marks: list[tuple[str, int, str]] = []
    contents: set[int] = _contents_zone(lines)
    for i, ln in enumerate(lines):
        if i in contents or _is_sentence(ln):
            continue
        role = _heading_role(ln)
        if role is None:
            continue
        # a table of contents lists every heading with a page number or a
        # page range ("6 -8"): no heading, and no body text either
        if _CONTENTS_LINE_RE.search(ln):
            contents.add(i)
            continue
        # a second heading of a role already opened is a sub-heading of the
        # section it sits in ("Angaben zum geografischen Gebiet …" under the
        # link): it neither opens nor closes anything
        if role != "stop" and any(r == role for r, _, _ in marks):
            continue
        marks.append((role, i, ln.strip()))
    roles: dict[str, str] = {}
    titles: dict[str, str] = {}
    for j, (role, i, title) in enumerate(marks):
        if role == "stop" or role in roles:
            continue
        stop = marks[j + 1][1] if j + 1 < len(marks) else len(lines)
        # text on the heading line after a colon belongs to the body
        tail = title.split(":", 1)[1].strip() if ":" in title and len(title.split(":", 1)[1]) > 3 else ""
        body = _paragraphs(([tail] if tail else []) + [
            ln.strip() for k, ln in enumerate(lines[i + 1: stop], i + 1) if k not in contents
        ])
        if len(body) < 12 and role not in ("category",):
            continue
        roles[role] = body
        titles[role] = title
    nuts: list[dict] = []
    return {"layout": "form", "roles": roles, "geo_nuts": nuts, "section_titles": titles}


# --- entry point --------------------------------------------------------------

def parse(text: str, labels: frozenset[str] = frozenset()) -> dict:
    """Slice a technical file. See the module docstring for the result.
    `labels` are the e-form's row labels in the file's language
    (`learn_labels` over the files of that language); without them an e-form
    row whose label runs into its value keeps the label words."""
    lines = clean_text(text).split("\n")
    sections = _eform_sections(lines)
    if sections is not None and 4 in sections:
        return _parse_eform(lines, sections, decimal=False, labels=labels)
    sections = _decimal_sections(lines)
    if sections is not None and 4 in sections:
        return _parse_eform(lines, sections, decimal=True, labels=labels)
    return _parse_form(lines)


# --- language -----------------------------------------------------------------

_STOPWORDS: dict[str, tuple[str, ...]] = {
    "en": ("the", "of", "and", "is", "with", "from", "which", "are"),
    "fr": ("les", "des", "est", "une", "dans", "avec", "par", "sont"),
    "es": ("los", "las", "del", "una", "con", "por", "que", "para"),
    "pt": ("das", "dos", "uma", "com", "não", "são", "pela", "ao"),
    "it": ("della", "delle", "che", "con", "nel", "sono", "gli", "dei"),
    "de": ("der", "die", "und", "das", "mit", "von", "ist", "den"),
    "nl": ("het", "een", "van", "voor", "met", "zijn", "wordt", "niet"),
    "hu": ("és", "az", "hogy", "egy", "nem", "vagy", "kell", "által"),
    "ro": ("și", "din", "care", "este", "sau", "pentru", "prin", "sunt"),
    "hr": ("ili", "koji", "koja", "kao", "nakon", "može", "mora", "biti"),
    "sl": ("ali", "ki", "kot", "lahko", "mora", "pri", "tudi", "so"),
    "sk": ("alebo", "ktorý", "ktoré", "sú", "pri", "môže", "musí", "ako"),
    "cs": ("nebo", "který", "které", "jsou", "při", "může", "musí", "jako"),
    "el": ("και", "του", "της", "των", "από", "για", "στην", "είναι"),
    "bg": ("на", "от", "за", "се", "или", "като", "при", "са"),
}


def detect_language(text: str) -> str:
    """The language a text is written in, by its function words; "" when
    nothing scores (a table, a scan)."""
    words = re.findall(r"[^\W\d_]+", (text or "").lower())
    if len(words) < 40:
        return ""
    counts = Counter(words)
    scores = {
        lang: sum(counts.get(w, 0) for w in stop) for lang, stop in _STOPWORDS.items()
    }
    lang, best = max(scores.items(), key=lambda kv: kv[1])
    return lang if best >= max(8, len(words) // 200) else ""
