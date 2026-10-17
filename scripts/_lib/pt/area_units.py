"""Freguesia-precision reading of a PT caderno's "Área Delimitada".

`commune_list.parse_commune_list` reads the section at município level:
a município the text restricts to some of its freguesias ("Loulé
(freguesias de Almancil, Boliqueime, …)", "Do concelho de Cascais, as
freguesias de …") comes back whole, a freguesia the text leaves out
("Resende, com exceção da freguesia de Barrô") is ignored, and a
freguesia named on its own ("a freguesia de Ossela, do município de
Oliveira de Azeméis") is lost. This module reads the same text clause by
clause and keeps that structure:

  - ``concelho`` pieces — a município included whole, with the freguesias
    the clause carves out of it (items with role ``exclude``);
  - ``freguesias`` pieces — the freguesias a clause names inside one
    município (its *container*, written before the list — "Do concelho de
    X, as freguesias de …", "X (freguesias de …)", "• X: …" — or after it
    — "as freguesias de …, do concelho de X");
  - ``distrito`` pieces — a whole distrito, minus the municípios and
    freguesias an exception clause names;
  - ``macro`` pieces — the whole Açores / Madeira archipelago.

A freguesia the text includes only in part — "parte das freguesias de",
"(parte)", "(lugares de …)", "as Quintas … na freguesia de", "as
propriedades … nas freguesias de", "os prédios rústicos …", the part an
exception takes away ("Avantos (excluindo as propriedades …)") — is
flagged ``part``: the resolver draws it whole and the card says so. Units
under an altitude limit are flagged the same way. A former freguesia the
text takes out of a União ("da União das freguesias de A e B, apenas a
freguesia de B", "B da União de Freguesias de A e B") is kept as itself;
the union's names after "da União de Freguesias de" follow as
``union_tail`` items, which the resolver drops while they are that
union's components.

Each piece records the sub-região section it was read in. The
appellation's area is the union of every piece — a sub-região lies inside
its appellation, and a sub-região list sometimes names a freguesia the
main list dropped (Terras do Dão's Couto de Esteves) — and an exclusion
removes units from its own clause only.

Boundary prose (a limit traced along roads, rivers and the edges of
units: "segue pelo limite da freguesia de …", "a linha que separa o
concelho de X do concelho de Y") names units as landmarks, not members: a
clause is read up to its first boundary word, and a sub-região whose text
yields no unit at all is reported in ``prose_subregions`` — such an
appellation cannot be drawn from units (Alentejo).

Names are returned as written. Matching them to CAOP — accents, the
pre-2013 names folded into the 2013 Uniões, spelling drift — is the
resolver's job (``geometry.PTPolygonIndex.resolve_area_units``).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


@dataclass
class Item:
    """A freguesia as the text writes it."""

    name: str
    part: bool = False
    # include | exclude | union_tail (the names of the União a former
    # freguesia was taken out of) | locality (a "lugar" the text names
    # inside a freguesia — drawn only when it is itself a freguesia today)
    role: str = "include"
    tail: int = 0  # which union tail a union_tail item belongs to
    # "Coura e Tões da freguesia de Armamar": the tail names the unit that
    # holds the names before it
    holder: bool = False


@dataclass
class Piece:
    kind: str  # concelho | freguesias | distrito | macro
    name: str = ""  # município / distrito / macro token; the container of `freguesias`
    part: bool = False  # included only in part (an altitude limit)
    items: list[Item] = field(default_factory=list)
    excluded_concelhos: list[str] = field(default_factory=list)
    # distrito pieces: (freguesia, município) pairs the exception names
    excluded_freguesias: list[tuple[str, str]] = field(default_factory=list)
    subregion: str = ""
    clause: str = ""


# ---------------------------------------------------------------- text --

_TAIL_RE = re.compile(
    r"\n\s*(?:[a-z][.)]\s*)?Zona\s*\n?\s*NUTS\b|\n\s*b[.)]\s*Mapas\s+da\s+área",
    re.IGNORECASE,
)
_FURNITURE_RES = (
    re.compile(r"^\s*\d{1,3}\.?\s*$"),
    re.compile(r"^\s*P[áa]gina\s+\d+(?:\s*/\s*\d+)?\s*$", re.IGNORECASE),
    re.compile(r"^\s*Caderno\s+de\s+Especifica", re.IGNORECASE),
    re.compile(r"^\s*P(?:DO|GI)\s*-\s*PT\s*[-–]", re.IGNORECASE),
    re.compile(r"^\s*_{5,}\s*$"),
)
# pdftotext renders the Wingdings bullet as U+F0B7.
_BULLET_CHARS = "•"
# "a b r a n g e a União …": a letter-spaced keyword, sometimes run into
# the one-letter article after it.
_LETTER_SPACED = re.compile(r"\b(?:[a-zà-ÿ] ){3,}[a-zà-ÿ]\b")
_SPACED_KEYWORDS = ("abrange", "freguesias", "freguesia", "concelhos", "concelho",
                    "municípios", "município")
_SPACED_HYPHEN = re.compile(r"(?<=\w) -(?=\w)|(?<=\w)- (?=[a-zà-ÿ]\w)")
# Colour scopes of a delimitation ("1. Para vinhos tintos e brancos:",
# "2.Exclusivamente para vinhos brancos:") — the appellation's area is
# their union, so the heading is dropped.
_COLOUR_SCOPE_RE = re.compile(
    r"(?:\b\d+\s*[.)]\s*)?(?:Exclusivamente\s+)?[Pp]ara\s+vinhos?\s+[^:\n]{0,40}:",
)


def _unspace(m: re.Match) -> str:
    word = m.group(0).replace(" ", "")
    for kw in _SPACED_KEYWORDS:
        if word.startswith(kw):
            rest = word[len(kw):]
            return kw + (" " + " ".join(rest) if rest else "")
    return m.group(0)


def normalise_area_text(text: str) -> str:
    """Cut the NUTS / maps tail, drop page furniture and colour headings,
    heal pdftotext artefacts ("a b r a n g e", "Idanha -a -Nova")."""
    if not text:
        return ""
    m = _TAIL_RE.search(text)
    if m:
        text = text[: m.start()]
    text = text.replace("’", "'").replace(" ", " ")
    lines = []
    for line in text.split("\n"):
        if any(r.search(line) for r in _FURNITURE_RES):
            continue
        for ch in _BULLET_CHARS:
            line = line.replace(ch, "\n• ")
        lines.append(line)
    text = "\n".join(lines)
    text = _LETTER_SPACED.sub(_unspace, text)
    text = _SPACED_HYPHEN.sub("-", text)
    text = _COLOUR_SCOPE_RE.sub("\n", text)
    return text


# A line that opens a sub-região section: "a) Sub -região Almeirim: …",
# "Sub-região Borba - …", or a bare "Name:" header ("Baixo Corgo: no
# distrito …", "Chaves:", "a) Estremadura:"). A bulleted "• Armamar: …" is
# a município head, never a sub-região.
_SUBREGIAO_LINE = re.compile(
    r"^\s*(?:[a-h]\)\s*)?Sub\s*-?\s*regi[ãa]o\s+(?:de\s+|do\s+|da\s+)?"
    r"(?P<name>[^:\-–]+?)\s*[:\-–]\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
_HEADER_LINE = re.compile(
    r"^\s*(?:[a-h]\)\s*)?(?P<name>[A-ZÀ-Ý][\wÀ-ÿ'/\- ]{1,38}?)\s*:\s*(?P<rest>.*)$"
)
_HEADER_STOP_WORDS = re.compile(
    r"\b(?:distrito|concelho|munic[íi]pio|freguesia|área|abrange|regi[ãa]o)\b",
    re.IGNORECASE,
)
# A sentence announcing the sub-região delimitations that follow.
_SUBREGIAO_INTRO = re.compile(
    r"sub\s*-?\s*regi[ãa]o\s*(?:«(?P<name>[^»]+)»\s*)?(?:é|são)\s+(?:a|as)\s+seguintes?\s*:",
    re.IGNORECASE,
)
_UNIT_LINE_START = re.compile(
    r"^(?:•|[a-h]\)|\d+[.)]\s|-\s|–\s|A\s+área\b"
    r"|(?:Do|No|Dos|Nos)\s+(?:distrito|concelho|munic[íi]pio)\b"
    r"|Os?\s+(?:distrito|concelho|munic[íi]pio)s?\b)"
)


def _looks_like_section_head(rest: str) -> bool:
    """Outside a declared sub-região list, a bare "Name:" header counts only
    when nothing follows the colon (Trás-os-Montes' "Chaves:") or what
    follows opens a delimitation (Douro's "Baixo Corgo: no distrito de Vila
    Real abrange …")."""
    rest = rest.strip()
    return not rest or bool(re.match(
        r"(?:[Nn]o|[Dd]o|[Oo]s?|[Aa]s?)\s+(?:distrito|concelho|munic|freguesia)", rest))


def _segments(text: str) -> list[tuple[str, str]]:
    """Split the normalised text into (sub-região, text) segments at
    bullets, enumerators, dashes and section headers; wrapped lines are
    joined."""
    out: list[tuple[str, str]] = []
    subregion = ""
    in_subregion_list = False
    buf: list[str] = []

    def flush() -> None:
        if buf:
            seg = re.sub(r"\s+", " ", " ".join(buf)).strip()
            if seg:
                out.append((subregion, seg))
            buf.clear()

    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        m_sub = _SUBREGIAO_LINE.match(line)
        if m_sub:
            flush()
            subregion = re.sub(r"\s*-\s*", "-", m_sub.group("name").strip())
            in_subregion_list = True
            if m_sub.group("rest").strip():
                buf.append(m_sub.group("rest").strip())
            continue
        m_head = None if line.startswith("•") else _HEADER_LINE.match(line)
        if m_head and not _HEADER_STOP_WORDS.search(m_head.group("name")) and (
                in_subregion_list or _looks_like_section_head(m_head.group("rest"))):
            flush()
            subregion = re.sub(r"\s*-\s*", "-", m_head.group("name").strip())
            in_subregion_list = True
            if m_head.group("rest").strip():
                buf.append(m_head.group("rest").strip())
            continue
        intro = _SUBREGIAO_INTRO.search(line)
        if intro:
            # the announcing sentence is no unit: drop it with whatever of
            # it was buffered
            buf.clear()
            subregion = (intro.group("name") or "").strip() or "?"
            in_subregion_list = True
            continue
        if _UNIT_LINE_START.match(line):
            flush()
        buf.append(line)
    flush()
    return out


# ------------------------------------------------------------ clauses --

# Lower-case only: the same words are capitalised in place names (Ribeira
# de Pena, Rio Maior, Linhares, Avelãs da Ribeira).
_BOUNDARY_RE = re.compile(
    r"\b(?:limites?|linha|confinante|separa|separação|segue|seguindo|prossegue|"
    r"continua|continuando|cruzamento|estrada|ribeira|ribeiro|caminho|rio|"
    r"contrafortes|estrema|quota|daqui|deste\s+ponto)\b"
    r"|\b(?:Segue|Continua|Prossegue|Deste\s+ponto|Daqui|De\s+[A-Z]\w+\s+segue)\b"
)
# Membership written in boundary words: "delimitada pela linha limite do
# concelho de Mourão (a área total das três freguesias …)", "os limites da
# sub-região correspondem aos limites dos concelhos de Alvito, Cuba e
# Vidigueira", "a área total das freguesias de Póvoa de São Miguel …".
_BOUNDARY_MEMBER_RES = (
    (re.compile(
        r"(?:é\s+delimitada\s+)?(?:pela\s+)?linha\s+limite\s+do\s+(concelho|munic[íi]pio)\s+de\s+"
        r"(?=[^()]*\((?:a\s+)?área\s+total)", re.IGNORECASE), r"o \1 de "),
    (re.compile(
        r"(?:os\s+)?limites\s+d[ao]\s+sub-?\s*regi[ãa]o\s+correspondem\s+aos\s+"
        r"limites\s+dos\s+(concelhos|munic[íi]pios)\s+de\s+", re.IGNORECASE),
     r"os \1 de "),
    (re.compile(r"\ba\s+área\s+total\s+das\s+freguesias\s+de\s+", re.IGNORECASE),
     "as freguesias de "),
)
# "Os limites da região são os seguintes:" (Carcavelos) — what follows
# restates the area as a boundary walk.
_LIMITS_SECTION_RE = re.compile(
    r"Os\s+limites\s+d[ao]\s+(?:regi[ãa]o|área)\s+s[ãa]o\s+os\s+seguintes\s*:.*$",
    re.IGNORECASE | re.DOTALL,
)
_KEYWORD_PRESENT = re.compile(
    r"\b(?:distritos?|concelhos?|munic[íi]pios?|freguesias?|Uni[ãa]o|"
    r"Arquip[ée]lago|ilhas)\b",
    re.IGNORECASE,
)


def _split_top_level(s: str, seps: str) -> list[str]:
    """Split on the characters in `seps` outside (), [] and — … — groups.
    A '.' ends a sentence only before a space and a capital (or the end) —
    never after an initial ("D. Maria") or inside "n.º"."""
    out, depth, dash, start = [], 0, False, 0
    for i, ch in enumerate(s):
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        elif ch == "—":
            dash = not dash
        elif ch in seps and depth == 0 and not dash:
            if ch == ".":
                prev, nxt = s[max(0, i - 3):i], s[i + 1:i + 3]
                if re.search(r"(?:^|\s)[A-ZÀ-Ýn]$", prev) or (
                        nxt and not re.match(r"\s+[A-ZÀ-Ý•(]|\s*$", nxt)):
                    continue
            out.append(s[start:i])
            start = i + 1
    out.append(s[start:])
    return [p.strip() for p in out if p.strip()]


def _outside_brackets(s: str) -> str:
    """The text of `s` with its (…) and […] groups removed."""
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"\([^()]*\)|\[[^\[\]]*\]", " ", s)
    return s


def _clauses(segment: str) -> list[str]:
    """A segment's clauses: split on top-level ';' and sentence ends; a
    piece with no unit keyword continues the previous clause's list
    (Trás-os-Montes writes "as freguesias de Anelhe; Arcossó; …")."""
    out: list[str] = []
    for sentence in _split_top_level(segment, "."):
        first = True
        for part in _split_top_level(sentence, ";"):
            if not first and out and not _KEYWORD_PRESENT.search(_outside_brackets(part)):
                out[-1] = out[-1] + "; " + part
            else:
                out.append(part)
            first = False
    return out


# ------------------------------------------------------------- tokens --

_NAME_WORD = r"(?!Uni[ãa]o\b|Freguesias?\b)[A-ZÀ-Ý][\wÀ-ÿ'\-/]*"
_CONNECTOR = r"(?:de|da|do|das|dos|d'|à)"
_NAME = (_NAME_WORD + r"(?:\s+D\.\s*" + _NAME_WORD + r"|\s+d'" + _NAME_WORD
         + r"|\s+(?:" + _CONNECTOR + r"\s+)?" + _NAME_WORD + r"|-" + _NAME_WORD + r")*")

_TOKEN_RE = re.compile(
    r"""
      (?P<distrito_all> (?i:
          (?:todas\s+as\s+freguesias\s+de\s+)?todos\s+os\s+(?:munic[íi]pios|concelhos)\s+
              (?:do|dos)\s+distritos?\s+(?:de|da|do)\b
        | (?:abrange\s+)?(?:todo|toda)\s+o\s+distrito\s+(?:de|da|do)\b ) )
    | (?P<distrito> (?<![\wÀ-ÿ])(?:[Oo]s?\s+|[DdNn]os?\s+|[DdNn]as?\s+)?[Dd]istritos?\s+(?:de|da|do)\b )
    | (?P<same_name> (?i: (?:a\s+)?(?:parte\s+da\s+)?freguesias?\s+(?:com\s+o|do)\s+mesmo\s+nome\b ) )
    | (?P<whole_list> (?i:
          todas\s+as\s+freguesias\s+(?:dos|do)\s+(?:munic[íi]pios?|concelhos?)\s+(?:de|da|do|das|dos)\b ) )
    | (?P<container>
          (?<![\wÀ-ÿ])(?:[DdNn]os?|[DdNn]as?)\s+(?:do\s+)?(?i:concelho|munic[íi]pio)\s+(?:de|da|do|das|dos)\b )
    | (?P<conc_list>
          (?<![\wÀ-ÿ])(?:(?:[Oo]s?|[Aa]s?)\s+)?(?i:concelhos?|munic[íi]pios?)\s+(?:de|da|do|das|dos)\b )
    | (?P<only> \bapenas\b )
    | (?P<excl> (?i:
          (?:com|à|a)\s+exce[çc][ãa]o\s+(?:de|da|das|do|dos)\b | \bexcep?to\b
        | \bexcluindo\b | \bexclu[íi]d[ao]s?\b | \bcom\s+exclus[ãa]o\s+d[aeo]s?\b ) )
    | (?P<uniao> (?i: (?:e\s+)?(?:a\s+|à\s+)?Uni[ãa]o\s+(?:de|das)\s+freguesias\s+(?:de|da|do|das|dos)\b ) )
    | (?P<freg_part> (?i:
          \b(?:a\s+|à\s+)?parte\s+(?:da|das|de)\s+freguesias?\b(?:\s+(?:de|da|do|das|dos)\b)? ) )
    | (?P<freg> (?i:
          (?<![\wÀ-ÿ])(?:(?:as|a|nas|na|da|das)\s+)?freguesias?\b(?:\s+(?:de|da|do|das|dos)\b)? ) )
    | (?P<locality> (?i:
          \b(?:nos?\s+|os\s+|o\s+)?lugar(?:es)?\s+(?:de|da|do|das|dos)\b
        | \b(?:as|das|os)\s+quintas?\b | (?-i:\bquintas?\b)
        | \b(?:as\s+)?propriedades\b
        | \b(?:os\s+)?pr[ée]dios\s+r[úu]sticos\b
        | \ba\s+faixa\b )
        | \b(?:as|os)\s+d[aeo]s?\s+(?=[A-ZÀ-Ý]) )
    | (?P<altitude> (?i: \bem\s+áreas\s+de\s+altitude\b[^,;()]* ) )
    | (?P<paren> [(\[] )
    | (?P<dash> — )
    | (?P<sep> [,;] )
    | (?P<colon> : )
    | (?P<conj> \be\b )
    | (?P<name> """ + _NAME + r""" )
    | (?P<word> [\wÀ-ÿ'º°ª\-]+ )
    | (?P<other> \S )
    """,
    re.VERBOSE,
)

_SKIP_WORDS = frozenset({
    "abrange", "abrangendo", "compreende", "inclui", "atualmente", "conforme",
    "descreve", "se", "os", "as", "o", "a", "de", "da", "do", "das", "dos",
    "e", "em", "no", "na", "nos", "nas", "que", "estão", "delimitados",
    "situadas", "situados", "situada", "situado", "também", "mesmo",
    "abrangidas", "ainda", "ou", "parte", "seguintes", "seguinte", "pertence",
    "não", "à", "ao", "pelas", "pelos", "sendo", "para", "vinhos",
})


def _matching_close(s: str, i: int) -> int:
    """Index just past the bracket group opening at s[i]."""
    depth = 0
    for j in range(i, len(s)):
        if s[j] in "([":
            depth += 1
        elif s[j] in ")]":
            depth -= 1
            if depth == 0:
                return j + 1
    return len(s)


def _tokens(s: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    i = 0
    while i < len(s):
        if s[i].isspace():
            i += 1
            continue
        m = _TOKEN_RE.match(s, i)
        if not m:
            i += 1
            continue
        kind = m.lastgroup
        if kind == "paren":
            end = _matching_close(s, i)
            out.append(("paren", s[i + 1:end - 1]))
            i = end
            continue
        if kind == "dash":
            end = s.find("—", i + 1)
            end = len(s) if end < 0 else end
            out.append(("dashgroup", s[i + 1:end]))
            i = end + 1
            continue
        out.append((kind, m.group(0).strip()))
        i = m.end()
    return out


def _clean(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip(" ,;:.")
    return re.sub(r"^(?:e|de|da|do|das|dos)\s+", "", name)


def _split_e(name: str) -> list[str]:
    """Split a list tail "A e B" on its conjunction, never inside a
    parenthesis ("Lamego (Almacave e Sé)")."""
    return [n for n in re.split(r"\s+e\s+(?![^()]*\))", name) if n]


# ------------------------------------------------------------- parser --


class _Walker:
    """Left-to-right walk over a clause's tokens with a small mode machine:
    the current list (municípios / freguesias / localities), the container
    município of freguesia items, and the items still waiting for a
    container written after them."""

    def __init__(self, subregion: str, clause: str, *, bullet_head: bool = False) -> None:
        self.subregion = subregion
        self.clause = clause
        self.bullet_head = bullet_head
        self.pieces: list[Piece] = []
        self.mode: str | None = None
        self.part = False  # the current list is "parte das freguesias de …"
        self.singular = False  # "a freguesia de X" names one freguesia
        self.container: str | None = None
        self.container_used = False
        self.pending: list[Item] = []
        self.last_concelho: Piece | None = None
        self.last_item: Item | None = None
        self.excluding = False
        self.exclusion_owner: Piece | None = None
        self.distrito: Piece | None = None
        self.distrito_mode: str | None = None  # concelhos | freguesias in its exception
        self.altitude = False
        self.locality_from: str | None = None
        self.tail_one = False  # "X da freguesia de U": a one-name tail
        self.tail_id = 0
        self.skip_relative = False  # inside "… que não pertence à …"

    # ---- emitters ----
    def concelho(self, name: str) -> None:
        if len(name) < 2:
            return
        p = Piece("concelho", name=name, subregion=self.subregion, clause=self.clause)
        self.pieces.append(p)
        self.last_concelho = p
        self.last_item = None

    def freguesia(self, name: str, *, part: bool = False, role: str = "include") -> None:
        it = Item(name=name, part=part or self.part, role=role,
                  tail=self.tail_id if role == "union_tail" else 0)
        self.last_item = it
        if self.distrito is not None and self.excluding:
            if self.container:
                self.distrito.excluded_freguesias.append((name, self.container))
            return
        if self.excluding and self.exclusion_owner is not None:
            it.role = "exclude"
            self.exclusion_owner.items.append(it)
            return
        if self.container is not None:
            self.container_piece().items.append(it)
            self.container_used = True
            return
        self.pending.append(it)

    def container_piece(self) -> Piece:
        for p in reversed(self.pieces):
            if p.kind == "freguesias" and p.name == self.container:
                return p
        p = Piece("freguesias", name=self.container or "", subregion=self.subregion,
                  clause=self.clause)
        self.pieces.append(p)
        return p

    def set_container(self, name: str) -> None:
        self.close_container()
        self.container = name
        self.container_used = False
        self.mode = "freguesias"
        self.part = False
        self.singular = False

    def close_container(self) -> None:
        """A container that received no freguesia — "No município da
        Madalena, em áreas de altitude …" — is the whole município."""
        if self.container and not self.container_used and not self.excluding:
            self.concelho(self.container)
        self.container = None
        self.container_used = False

    def bind_pending(self, container: str) -> None:
        if self.pending:
            self.pieces.append(Piece("freguesias", name=container, items=list(self.pending),
                                     subregion=self.subregion, clause=self.clause))
            self.pending.clear()

    # ---- parenthetical after a name ----
    def paren(self, inner: str) -> None:
        low = _fold(inner)
        owner = self.last_concelho if (
            self.mode == "concelhos" and self.last_item is None) else None
        if owner is not None:
            if re.match(r"\s*(?:exclu|exce|com\s+exce|a\s+excep)", low):
                sub = _Walker(self.subregion, self.clause)
                sub.excluding, sub.exclusion_owner, sub.mode = True, owner, "freguesias"
                sub.walk(_tokens(inner))
                return
            if re.search(r"\bfreguesia|\bpropriedad|\bquinta|\bpredio|\blugar", low) \
                    and not re.search(r"area\s+total", low):
                # "Loulé (freguesias de …)": the município is a container
                sub = _Walker(self.subregion, self.clause)
                sub.set_container(owner.name)
                sub.walk(_tokens(inner))
                if sub.pending or any(p.kind == "freguesias" and p.items for p in sub.pieces):
                    self.pieces.remove(owner)
                    self.pieces.extend(sub.pieces)
                    if sub.pending:
                        self.pieces.append(Piece("freguesias", name=owner.name,
                                                 items=list(sub.pending),
                                                 subregion=self.subregion, clause=self.clause))
                    self.last_concelho = None
                return
            if re.fullmatch(r"\s*parte\s*", low):
                owner.part = True
            return
        if self.last_item is not None:
            if re.fullmatch(r"\s*parte\s*", low) or re.search(
                    r"\blugar|\bexcluindo|\bpropriedad|\bquinta", low):
                self.last_item.part = True
                m = re.match(r"\s*lugar(?:es)?\s+(?:de|da|do|das|dos)\s+(.+)$", inner, re.S)
                if m:
                    # Carcavelos' "(lugares de Ribeira da Laje, Cacilhas e
                    # Porto Salvo)": Porto Salvo is a freguesia today
                    owner = self.last_item
                    for n in re.split(r"\s*,\s*|\s+e\s+", re.sub(r"\s+", " ", m.group(1))):
                        if n.strip():
                            self.freguesia(_clean(n), part=True, role="locality")
                    self.last_item = owner
                return
            # "Lamego (Almacave, Sé)", "Óbidos (São Pedro)": part of the name
            self.last_item.name = f"{self.last_item.name} ({re.sub(r'\s+', ' ', inner).strip()})"

    # ---- main loop ----
    def walk(self, toks: list[tuple[str, str]]) -> None:
        i = 0
        while i < len(toks):
            kind, val = toks[i]
            nxt = toks[i + 1] if i + 1 < len(toks) else ("end", "")
            if self.skip_relative and kind != "sep":
                i += 1
                continue
            if kind == "altitude":
                self.altitude = True
            elif kind == "distrito_all":
                self.distrito_list(toks, i + 1)
                return
            elif kind == "distrito":
                if nxt[0] == "name" and self.distrito_is_whole(i, toks):
                    self.distrito_list(toks, i + 1)
                    return
                if nxt[0] == "name":
                    i += 2  # a scoping "Do distrito de X," — not a member
                    continue
            elif kind == "whole_list":
                self.close_container()
                self.mode, self.excluding = "concelhos", False
            elif kind == "conc_list":
                if self.distrito is not None and self.excluding:
                    self.distrito_mode = "concelhos"
                else:
                    self.close_container()
                    self.mode, self.excluding = "concelhos", False
            elif kind == "container" and nxt[0] == "name":
                name = _clean(nxt[1])
                after = toks[i + 2] if i + 2 < len(toks) else ("end", "")
                at_end = after[0] == "end" or (
                    after[0] in ("sep", "colon") and i + 3 >= len(toks)) or after[0] == "paren"
                if self.distrito is not None and self.excluding:
                    self.container = name
                    self.distrito_mode = "freguesias"
                elif self.pending and at_end:
                    self.bind_pending(name)
                else:
                    if self.excluding:
                        self.excluding, self.exclusion_owner = False, None
                    self.set_container(name)
                i += 2
                continue
            elif kind == "excl" and self.last_item is not None and nxt[0] == "locality" \
                    and i > 0 and toks[i - 1][0] in ("name", "paren"):
                self.last_item.part = True
                self.locality_from = self.mode
                self.mode = "locality"
                i += 2
                continue
            elif kind == "excl":
                self.excluding = True
                if self.distrito is None:
                    self.exclusion_owner = self.last_concelho if self.mode == "concelhos" else \
                        self.exclusion_owner
                    self.mode = "freguesias"
                    self.singular = False
            elif kind == "same_name":
                if self.container:
                    self.freguesia(self.container, part="parte" in val.lower())
            elif kind == "uniao":
                if self.union_then_only(toks, i):
                    # "da União das freguesias de A e B, apenas a freguesia
                    # de B": skip the union's names
                    i = self.skip_to_only(toks, i)
                    continue
                if follows_named_item(toks, i):
                    # "Malpartida da União de Freguesias de Malpartida e
                    # Vale de Coelha": the names that follow are the union's
                    self.mode, self.tail_one = "union_tail", False
                    self.tail_id += 1
                else:
                    self.mode, self.singular = "freguesias", False
            elif kind in ("freg", "freg_part") and nxt[0] in ("sep", "conj") \
                    and not re.search(r"\b(?:de|da|do|das|dos)$", val):
                pass  # "as parcelas, freguesias, concelhos e distritos": no list
            elif kind in ("freg", "freg_part"):
                low = val.lower()
                plural = bool(re.search(r"freguesias", low))
                if self.mode == "locality":
                    # "as propriedades …, na freguesia de X": X in part
                    self.mode = "locality_freg"
                    self.singular = not plural
                elif self.distrito is not None and self.excluding:
                    self.distrito_mode = "freguesias"
                elif not plural and low.startswith("da freguesia") and \
                        i > 0 and toks[i - 1][0] in ("name", "paren"):
                    # "Coura e Tões da freguesia de Armamar": Armamar is the
                    # freguesia that now holds them, not a member
                    self.mode, self.tail_one = "union_tail", True
                    self.tail_id += 1
                else:
                    self.mode = "freguesias"
                    self.part = kind == "freg_part"
                    self.singular = not plural
            elif kind == "locality":
                is_lugar = bool(re.search(r"lugar", val, re.I))
                if self.mode in ("freguesias", "locality_freg") and self.last_item is not None \
                        and not prev_is(toks, i, "conj") \
                        and (is_lugar or not prev_is(toks, i, "sep")):
                    # "da freguesia de Paço de Arcos a faixa confinante …",
                    # "a freguesia da Piedade, nos lugares de Engrade …" —
                    # but ", as Quintas da Peça …" opens a new item
                    self.last_item.part = True
                if self.mode not in ("locality", "lugar"):
                    self.locality_from = self.mode
                self.mode = "lugar" if is_lugar else "locality"
            elif kind == "paren":
                if self.mode != "locality":
                    self.paren(val)
            elif kind == "dashgroup":
                sub = _Walker(self.subregion, self.clause)
                sub.mode = "freguesias"
                sub.exclusion_owner = self.last_concelho
                sub.walk(_tokens(val))
                self.pieces.extend(p for p in sub.pieces if p is not self.last_concelho)
                for it in sub.pending:
                    self.pending.append(it)
            elif kind == "sep":
                self.skip_relative = False
                if self.mode == "lugar":
                    self.mode = self.locality_from or "freguesias"
                elif self.mode == "locality_freg" and self.singular:
                    self.mode = self.locality_from or "freguesias"
                    self.singular = False
                elif self.singular:
                    self.singular = False
            elif kind == "colon":
                if self.mode is None and self.last_concelho is not None and \
                        len(self.pieces) == 1 and not self.pending:
                    # "• Armamar: União …": the bullet head is a container
                    owner = self.pieces.pop()
                    self.last_concelho = None
                    self.set_container(owner.name)
            elif kind == "name":
                if self.mode in ("freguesias", "locality_freg") and not self.singular \
                        and compound_ahead(toks, i):
                    val = f"{_clean(val)} e {_clean(toks[i + 2][1])}"
                    self.freguesia(val, part=self.mode == "locality_freg")
                    i += 3
                    continue
                self.name(_clean(val), toks, i)
            elif kind == "word" and val == "que":
                # a relative clause ("a parte da freguesia de Aldeias que não
                # pertence à Região Demarcada do Douro") names no member
                self.skip_relative = True
            elif kind == "word":
                if self.mode in ("freguesias", "locality_freg") and self.container \
                        and val[0].islower() \
                        and val.lower() not in _SKIP_WORDS and len(val) > 2 \
                        and (prev_is(toks, i, "sep") or prev_is(toks, i, "conj")):
                    # Óbidos writes "Pêro Moniz, vermelha e Vilar"
                    self.name(val, toks, i)
            i += 1
        self.close_container()
        if self.altitude:
            for p in self.pieces:
                p.part = True
                for it in p.items:
                    it.part = True
            for it in self.pending:
                it.part = True

    def name(self, name: str, toks: list[tuple[str, str]], i: int) -> None:
        if not name:
            return
        if self.distrito is not None and self.excluding:
            if self.distrito_mode == "concelhos":
                self.distrito.excluded_concelhos.extend(_split_e(name))
            elif self.distrito_mode == "freguesias" and self.container:
                self.distrito.excluded_freguesias.extend(
                    (n, self.container) for n in _split_e(name))
            return
        if self.mode == "concelhos":
            for n in _split_e(name):
                self.concelho(n)
            return
        if self.mode in ("freguesias", "locality_freg"):
            part = self.mode == "locality_freg"
            if self.singular:
                # "a freguesia de Oeiras e São Julião da Barra": one name —
                # join "X e Y" when Y opens no new list
                j = i + 1
                while j + 1 < len(toks) and toks[j][0] == "conj" and toks[j + 1][0] == "name":
                    name = f"{name} e {_clean(toks[j + 1][1])}"
                    toks[j + 1] = ("consumed", "")
                    j += 2
                self.freguesia(name, part=part)
                if self.mode == "locality_freg":
                    self.mode = self.locality_from or "freguesias"
                self.singular = False
                return
            for n in _split_e(name):
                self.freguesia(n, part=part)
            return
        if self.mode == "lugar":
            owner = self.last_item
            for n in _split_e(name):
                self.freguesia(n, part=True, role="locality")
            self.last_item = owner
            return
        if self.mode == "union_tail":
            if self.tail_one:
                self.freguesia(name, role="union_tail")
                self.last_item.holder = True
                self.mode, self.tail_one = "freguesias", False
                return
            for n in _split_e(name):
                self.freguesia(n, role="union_tail")
            return
        if self.bullet_head and self.mode is None and not self.pieces and not self.pending:
            # a bulleted head: "• Moimenta da Beira;", "• Armamar: …"
            self.concelho(name)

    def distrito_is_whole(self, i: int, toks: list[tuple[str, str]]) -> bool:
        """"O distrito de X" / "Distrito de X." opening the clause is the
        whole distrito; "Do/No distrito de X" scopes a list, and so does
        "O distrito de Bragança: os concelhos de …"."""
        tok = toks[i][1]
        if not re.match(r"^(?:Os?\s|Distritos?\b)", tok):
            return False
        after = toks[i + 2] if i + 2 < len(toks) else ("end", "")
        if after[0] == "colon":
            return False
        return all(k in ("word", "other") for k, _ in toks[:i])

    def distrito_list(self, toks: list[tuple[str, str]], j: int) -> None:
        names: list[str] = []
        k = j
        while k < len(toks):
            kind, val = toks[k]
            if kind == "name":
                names.extend(_split_e(_clean(val)))
            elif kind in ("sep", "conj") or (kind == "word" and val.lower() in ("de", "da", "do")):
                pass
            else:
                break
            k += 1
        for n in names:
            self.pieces.append(Piece("distrito", name=n, subregion=self.subregion,
                                     clause=self.clause))
        if names and k < len(toks) and toks[k][0] == "excl":
            self.distrito = self.pieces[-1]
            self.excluding = True
            self.distrito_mode = "concelhos"
            self.walk(toks[k + 1:])

    @staticmethod
    def union_then_only(toks: list[tuple[str, str]], i: int) -> bool:
        for k in range(i + 1, min(len(toks), i + 14)):
            kind = toks[k][0]
            if kind == "only":
                return True
            if kind in ("uniao", "conc_list", "container", "freg_part", "freg"):
                return False
        return False

    @staticmethod
    def skip_to_only(toks: list[tuple[str, str]], i: int) -> int:
        k = i + 1
        while k < len(toks) and toks[k][0] != "only":
            k += 1
        return k + 1


def prev_is(toks: list[tuple[str, str]], i: int, kind: str) -> bool:
    return i > 0 and toks[i - 1][0] == kind


def compound_ahead(toks: list[tuple[str, str]], i: int) -> bool:
    """"A e B" followed by a separator and another name: in a Portuguese
    list only the last item is joined by "e", so "A e B" here is one name
    (Torres Vedras' "São Pedro e Santiago", Valpaços' "Água Revés e
    Crasto")."""
    if i + 4 >= len(toks):
        return False
    return (toks[i + 1][0] == "conj" and toks[i + 2][0] == "name"
            and toks[i + 3][0] == "sep" and toks[i + 4][0] == "name")


def follows_named_item(toks: list[tuple[str, str]], i: int) -> bool:
    """The União token at `i` is written after a freguesia name — "X da
    União de Freguesias de …" or "X, da União …"."""
    k = i - 1
    if k < 0 or toks[k] != ("word", "da"):
        return False
    k -= 1
    if k >= 0 and toks[k][0] == "sep":
        k -= 1
    return k >= 0 and toks[k][0] in ("name", "paren")


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def parse_area_units(area_text: str) -> dict:
    """Return {pieces, subregions, prose_subregions, prose_cut_subregions}
    for one area section.

    `pieces` is a list of `Piece`. `prose_subregions` names the sub-região
    sections that are boundary prose with no unit the parser could read —
    an appellation with any of them cannot be drawn from units.
    `prose_cut_subregions` names every section ("" for the main
    delimitation) in which some clause was boundary prose: such a
    sub-região cannot be drawn from its units alone."""
    text = normalise_area_text(area_text)
    text = _LIMITS_SECTION_RE.sub("", text)
    pieces: list[Piece] = []
    subregions: list[str] = []
    n_by_sub: dict[str, int] = {}
    prose_cut: list[str] = []
    segments = _segments(text)
    for subregion, _ in segments:
        if subregion and subregion not in subregions:
            subregions.append(subregion)
    for subregion, segment in segments:
        n_before = len(pieces)
        for clause in _clauses(segment):
            for rx, repl in _BOUNDARY_MEMBER_RES:
                clause = rx.sub(repl, clause)
            m = _BOUNDARY_RE.search(clause)
            if m:
                # a boundary clause naming other sub-regiões describes their
                # shared edge ("O limite natural que separa a sub-região de
                # Almeirim das do Cartaxo e Santarém é o rio Tejo"), not the
                # section it is printed in
                others = [x for x in subregions if x != subregion
                          and re.search(rf"\b{re.escape(x)}\b", clause)]
                if subregion not in prose_cut and not others:
                    prose_cut.append(subregion)
                clause = clause[: m.start()]
            if not clause.strip():
                continue
            walker = _Walker(subregion, clause, bullet_head=clause.startswith("•"))
            walker.walk(_tokens(clause))
            if walker.pending:
                pieces.append(Piece("freguesias", name="", items=list(walker.pending),
                                    subregion=subregion, clause=clause))
            pieces.extend(walker.pieces)
        n_by_sub[subregion] = n_by_sub.get(subregion, 0) + len(pieces) - n_before
    prose = [s for s in subregions if n_by_sub.get(s, 0) == 0]
    if re.search(r"(?:arquip[ée]lago|regi[ãa]o\s+aut[óo]noma)\s+dos\s+A[çc]ores", text, re.I):
        pieces.append(Piece("macro", name="acores"))
    if re.search(r"(?:arquip[ée]lago|regi[ãa]o\s+aut[óo]noma|regi[ãa]o\s+demarcada)\s+da\s+Madeira"
                 r"|\bRDM\b|ilhas\s+da\s+Madeira\s+e\s+do\s+Porto\s+Santo", text, re.I):
        pieces.append(Piece("macro", name="madeira"))
    return {"pieces": pieces, "subregions": subregions, "prose_subregions": prose,
            "prose_cut_subregions": prose_cut}
