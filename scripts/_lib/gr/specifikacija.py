"""Parser for the Greek national product specification
(`προδιαγραφή προϊόντος` / `τεχνικός φάκελος` / EU-template `ΕΝΙΑΙΟ
ΕΓΓΡΑΦΟ`) published by ΥΠΑΑΤ on minagric.gr.

138 of 147 GR wines are pre-2009 grandfathered names with no fetchable
EU-OJ ΕΝΙΑΙΟ-ΕΓΓΡΑΦΟ HTML — the canonical public spec is the national
document on the four-w minagric host (stage 01c fetches it). Three on-disk
shapes, all reduced to plain text and parsed by one role-keyword section
splitter:

  - **PDF** (~87 wines) — the structured EU technical-file form with
    ALL-CAPS numbered top-level headers (`6. ΟΙΝΟΠΟΙΗΣΙΜΕΣ ΠΟΙΚΙΛΙΕΣ
    ΑΜΠΕΛΟΥ`). `pdftotext -layout`. Grape section is a colour-letter
    variety list → `parse_grape_list`.
  - **.doc** (~43 wines) — the older `ΠΡΟΔΙΑΓΡΑΦΗ ΤΟΥ ΠΡΟΪΟΝΤΟΣ` form;
    antiword renders it as `|`-bordered tables with named cell headers
    (`Επιτρεπόμενες οινοποιήσιμες ποικιλίες αμπέλου`). The grape body is
    prose ("…από την ερυθρή ποικιλία Αγιωργίτικο…") → capitalized-Greek
    token scan scoped to the grape section.
  - **.docx** (2 wines) — same national form, read via the zip/XML path.

The section splitter reuses the Greek section-role keyword tables and the
`greek_norm` comparator from `eniaio_engrafo` (the same module stage 02's
HTML parser uses), so routing stays identical to the EU-OJ path. Grape /
style parsing reuses the shared `_lib.grape_entity` lexicon matcher.
"""

from __future__ import annotations

import re
import subprocess
import unicodedata
import zipfile
from pathlib import Path

from unidecode import unidecode

from _lib.gr.eniaio_engrafo import (
    COLOUR_BY_KEYWORD,
    SECTION_ROLE_KEYWORDS,
    STYLE_MARKERS,
    greek_norm,
)
from _lib.grape_entity import match_variety

DOCKER_IMAGE = "owm-antiword:latest"

# Header role-detection priority. link_to_terroir is checked BEFORE
# geo_area because a link header ("Δεσμός με τη γεωγραφική περιοχή")
# also contains the geo_area keyword "γεωγραφική περιοχή".
_HEADER_ROLE_ORDER = (
    "name",
    "category",
    "description",
    "viticultural_practices",
    "grape_varieties",
    "link_to_terroir",
    "geo_area",
    "additional_conditions",
)
_ROLE_KW_NORM = {
    role: tuple(greek_norm(kw) for kw in SECTION_ROLE_KEYWORDS[role])
    for role in _HEADER_ROLE_ORDER
}

# Leading list-marker / table-border junk to strip before header testing.
_LEAD_JUNK_RE = re.compile(r"^[\s|>\d.)\-—–•·*]+")
_GREEK_LETTER_BULLET_RE = re.compile(r"^[αβγδεζηθ]\.\s+")
# A capitalised Greek word (≥ 3 chars) — variety names are capitalised.
_CAP_GREEK = r"[Α-ΩΆΈΉΊΌΎΏΪΫ][α-ωάέήίόύώϊϋΐΰ]{2,}"
_LOWER_GREEK = r"[α-ωάέήίόύώϊϋΐΰ]{2,}"
_CAP_GREEK_RE = re.compile(_CAP_GREEK)
# A capitalised Greek word, optionally followed by one more word that is
# either capitalised or lowercase — the lowercase tail catches the
# "Μοσχάτο λευκό" / "Μαλαγουζιά άσπρη" colour-adjective form. Junk bigrams
# are harmless: only lexicon-exact hits are kept downstream.
_CAP_GREEK_SEQ_RE = re.compile(rf"{_CAP_GREEK}(?:\s+(?:{_CAP_GREEK}|{_LOWER_GREEK}))?")
# Latin-script variety names appear verbatim in Greek specs (Chardonnay,
# CARIGNAN, SYRAH, Cabernet Sauvignon, Cinsaut, Gewurztraminer). Match a
# capitalised / all-caps Latin word + an optional second word that may be
# lowercase — the colour-suffix form 'Sauvignon blanc', 'Cabernet franc'.
_LATIN_SEQ_RE = re.compile(r"\b[A-Z][a-zA-Zéèïü]{2,}(?:\s+[a-zA-Zéèïü]{2,})?\b")


def to_text(path: Path) -> str:
    """Reduce a national-spec file (pdf/doc/docx) to plain UTF-8 text."""
    ext = path.suffix.lower().lstrip(".")
    if ext == "pdf":
        return _pdf_to_text(path)
    if ext == "doc":
        return _doc_to_text(path)
    if ext == "docx":
        return _docx_to_text(path)
    raise ValueError(f"unsupported spec format: {path.name}")


def _pdf_to_text(path: Path) -> str:
    try:
        out = subprocess.run(
            ["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"],
            capture_output=True, timeout=120, check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("pdftotext not on PATH (poppler)") from exc
    return out.stdout.decode("utf-8", errors="replace")


def _doc_to_text(path: Path) -> str:
    """Word 97-2003 .doc → text via the shared antiword Docker image
    (`-w 0` no wrap, `-m UTF-8.txt` so Greek survives)."""
    abs_dir = str(path.parent.resolve())
    try:
        out = subprocess.run(
            ["docker", "run", "--rm", "-v", f"{abs_dir}:/data:ro",
             DOCKER_IMAGE, "-w", "0", "-m", "UTF-8.txt", f"/data/{path.name}"],
            capture_output=True, timeout=90, check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "docker not on PATH; build the antiword image: docker build -t "
            f"{DOCKER_IMAGE} -f scripts/si/Dockerfile.doc-converter scripts/si/"
        ) from exc
    text = out.stdout.decode("utf-8", errors="replace")
    if len(text.strip()) >= 200:
        return text
    # antiword rejects a handful of malformed OLE2 .doc files ("Can't read
    # SAT", e.g. Σιάτιστα). Salvage the readable UTF-16LE WordDocument
    # stream directly — loses paragraph structure but recovers the prose
    # (the windowed grape fallback in parse_spec then handles it).
    return _doc_salvage_utf16le(path)


_SALVAGE_KEEP_RE = re.compile(r"[^Ͱ-Ͽἀ-῿A-Za-z0-9 ,.\-%/()\n]+")


def _doc_salvage_utf16le(path: Path) -> str:
    raw = path.read_bytes()
    txt = raw.decode("utf-16-le", errors="ignore")
    clean = _SALVAGE_KEEP_RE.sub(" ", txt)
    return re.sub(r"[ \t]{2,}", " ", clean)


def _docx_to_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab[^>]*/>", "\t", xml)
    return re.sub(r"<[^>]+>", "", xml)


def _strip_header_line(line: str) -> str:
    cand = line.replace("|", " ").strip()
    cand = _LEAD_JUNK_RE.sub("", cand)
    cand = _GREEK_LETTER_BULLET_RE.sub("", cand)
    return cand.strip(" \t:·—–-")


def _header_role(cand: str) -> str | None:
    """Return the section role for a header-candidate line, or None.

    A header is a short line whose normalised form contains a section-role
    keyword. The absolute-length cap rejects sentences that merely mention
    a keyword in passing; the priority order resolves keyword overlaps."""
    if not (5 <= len(cand) <= 85):
        return None
    norm = greek_norm(cand)
    if not norm:
        return None
    # spec-reference appendix ("Δεσμός με τις προδιαγραφές του προϊόντος")
    # is not the terroir link — route it to additional_conditions.
    if "δεσμοσ" in norm and "προδιαγραφ" in norm:
        return "additional_conditions"
    for role in _HEADER_ROLE_ORDER:
        for kw in _ROLE_KW_NORM[role]:
            if kw and kw in norm:
                return role
    return None


def extract_sections(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """Walk lines; slice the document into role-keyed section bodies.
    Returns (sections_by_role, titles_by_role). Consecutive lines under a
    detected header accumulate into that role's body until the next header;
    repeated roles concatenate (handles α./β./γ. subsections)."""
    sections: dict[str, list[str]] = {}
    titles: dict[str, str] = {}
    current: str | None = None
    for raw in text.splitlines():
        cand = _strip_header_line(raw)
        role = _header_role(cand) if cand else None
        if role is not None:
            current = role
            titles.setdefault(role, cand)
            sections.setdefault(role, [])
            continue
        if current is not None:
            body = raw.replace("|", " ").strip()
            if body:
                sections[current].append(body)
    return {k: "\n".join(v).strip() for k, v in sections.items()}, titles


# ── grape parsing ────────────────────────────────────────────────────────

_BULLET_SPLIT_RE = re.compile(r"\s*[—•·]\s*|\n|\s*\d+\.\s+")
_NAME_SYN_SPLIT_RE = re.compile(r"\s+[-–]\s+")
_DROP_PHRASES = (
    "οινοποιησιμες ποικιλιες", "ποικιλιες αμπελου", "ποικιλια αμπελου",
    "ποικιλιες σταφυλιου", "ποικιλια σταφυλιου",
)


def _item_candidates(item: str) -> list[str]:
    parts = _NAME_SYN_SPLIT_RE.split(item, maxsplit=1)
    head = parts[0]
    syn_blob = parts[1] if len(parts) > 1 else ""
    out: list[str] = []
    for c in [head, *syn_blob.split(",")]:
        c = re.sub(r"\s*\(.*?\)\s*", " ", c).strip()
        if c and c not in out:
            out.append(c)
    return out


def parse_grape_list(section_text: str, slug: str, exclude: frozenset = frozenset()) -> dict:
    """Bullet/line-form grape section (PDF colour-letter list, e.g.
    'Αηδάνι άσπρο Β / Αθήρι Β / Ασύρτικο Β')."""
    out = {"principal": [], "accessory": [], "observation": [], "details": []}
    if not section_text:
        return out
    seen: set[str] = set()
    for raw in _BULLET_SPLIT_RE.split(section_text):
        item = raw.strip(" \t;,.-")
        if not item:
            continue
        low = greek_norm(item)
        if any(d in low for d in _DROP_PHRASES) and len(item) < 75:
            continue
        for cand in _item_candidates(item):
            if greek_norm(cand) in exclude:
                continue
            m = match_variety(cand, source_pliego=slug)
            if m is None:
                continue
            if m.slug in seen:
                break
            seen.add(m.slug)
            out["principal"].append(m.slug)
            out["details"].append({
                "slug": m.slug,
                "name": _NAME_SYN_SPLIT_RE.split(item, maxsplit=1)[0].strip(),
                "role": "principal",
                "colour": m.colour,
            })
            break
    return out


def _prose_match_ok(cand: str, res, is_latin: bool) -> bool:
    """Accept a prose-scanned grape match. Exact hits always pass. For a
    Greek-script candidate a fuzzy hit passes only when its romanised first
    letter equals the matched slug's — every Greek false positive is a
    cross-first-char fuzzy hit on a place name / common word (`Νάουσα`→
    xinomavro), while real Greek varieties that resolve by fuzzy (`Μοσχάτο`
    →muscat) are first-char-consistent. A **Latin-script** candidate must
    be exact: Latin internationals are always exact in the lexicon, and a
    bare prefix fuzz (`Cabernet`→cabernet-franc) is a false positive."""
    if res.method == "exact":
        return True
    if is_latin:
        return False
    rom = unidecode(cand).strip().lower()
    return bool(rom) and rom[0] == res.slug[:1].lower()


def _prose_candidates(section_text: str):
    """Yield (full-match, leading-unigram) candidate pairs from both the
    capitalised-Greek and the Latin-script token streams. Greek native
    varieties and verbatim Latin internationals (Chardonnay, CARIGNAN,
    SYRAH, Cabernet Sauvignon) both appear in the prose grape sections."""
    for m in _CAP_GREEK_SEQ_RE.finditer(section_text):
        yield m.group(0), _CAP_GREEK_RE.match(m.group(0)).group(0), False
    for m in _LATIN_SEQ_RE.finditer(section_text):
        # No head-unigram split for Latin: the regex already captures the
        # whole variety name, and splitting 'Cabernet Sauvignon' → bare
        # 'Cabernet' (a deliberate alias → cabernet-franc) would add a
        # phantom second variety.
        yield m.group(0), m.group(0), True


def scan_grapes_prose(section_text: str, slug: str, exclude: frozenset = frozenset()) -> dict:
    """Prose grape section (.doc form): scan capitalised-Greek and
    Latin-script tokens / bigrams against the lexicon. Scoped to the grape
    section so the unknowns queue isn't flooded with place names from the
    whole document. `exclude` holds normalised forms that must not match
    (the appellation's own name — `Ρόδος` else fuzzy-hits the PT grape
    'rodo')."""
    out = {"principal": [], "accessory": [], "observation": [], "details": []}
    if not section_text:
        return out
    seen: set[str] = set()
    for full, head, is_latin in _prose_candidates(section_text):
        for cand in (full, head):
            if greek_norm(cand) in exclude:
                continue
            res = match_variety(cand, source_pliego=slug)
            if res is None or res.slug in seen or not _prose_match_ok(cand, res, is_latin):
                continue
            seen.add(res.slug)
            out["principal"].append(res.slug)
            out["details"].append({
                "slug": res.slug, "name": cand,
                "role": "principal", "colour": res.colour,
            })
            break
    return out


def parse_styles(sections: dict[str, str]) -> list[str]:
    blob = " ".join(
        sections.get(r, "")
        for r in ("description", "category", "additional_conditions", "grape_varieties")
    )
    norm = greek_norm(blob)
    found: set[str] = set()
    for kw, colour in COLOUR_BY_KEYWORD.items():
        if greek_norm(kw) in norm:
            found.add(colour)
    for pattern, slug in STYLE_MARKERS:
        if pattern.search(blob):
            found.add(slug)
    return sorted(found)


def _derive_summary(text: str, max_chars: int = 600) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(". ", 1)[0]
    return cut + ("." if not cut.endswith(".") else "")


# Length-preserving fold (1 char → 1 char) so an anchor found in the
# folded text maps back to the same index in the original. Used for the
# windowed grape fallback when the section splitter finds no header line
# (salvaged corrupt .doc — the grape header survives but inline, not as
# its own line).
def _fold_keep_len(s: str) -> str:
    out = []
    for ch in s:
        base = "".join(
            c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c)
        )
        out.append((base[:1] or ch).lower().replace("ς", "σ"))
    return "".join(out)


_GRAPE_ANCHORS = (
    "οινοποιησιμεσ ποικιλιεσ",
    "ποικιλιεσ αμπελου",
    "κυρια οινοποιησιμη",
    "ποικιλιακη συνθεση",
)


def _grape_windows(text: str) -> list[str]:
    """Every ~700-char window following a grape-section anchor anywhere in
    the text (each capped at the next 'δεσμός' section keyword). A spec can
    contain an anchor phrase both in prose ('ποικιλιακή σύνθεση …') and at
    the real variety header — the caller scans every window and keeps the
    richest, so the prose decoy is discarded."""
    folded = _fold_keep_len(text)
    positions: set[int] = set()
    for anchor in _GRAPE_ANCHORS:
        start = folded.find(anchor)
        while start != -1:
            positions.add(start)
            start = folded.find(anchor, start + 1)
    windows = []
    for pos in sorted(positions):
        window = text[pos:pos + 700]
        cut = _fold_keep_len(window).find("δεσμοσ")
        windows.append(window[:cut] if cut > 40 else window)
    return windows


_TERROIR_START_ANCHORS = (
    "δεσμοσ με την γεωγραφικη",
    "δεσμοσ με τη γεωγραφικη",
    "περιγραφη του δεσμου",
)
_TERROIR_END_ANCHORS = (
    "αλλεσ προϋποθεσεισ",
    "αλλεσ ουσιωδεισ",
    "δικαιολογητικα",
    "παραπομπη στη δημοσιευση",
    "συσκευασια",
)


def _terroir_window(text: str) -> str:
    """The 'ΔΕΣΜΟΣ ΜΕ ΤΗ ΓΕΩΓΡΑΦΙΚΗ ΠΕΡΙΟΧΗ' narrative carved out of the
    full text by anchor (for salvaged corrupt docs with no header lines).
    Runs from the link header to the next top-level section (or a 4 000-char
    cap)."""
    folded = _fold_keep_len(text)
    start = min((folded.find(a) for a in _TERROIR_START_ANCHORS if a in folded), default=-1)
    if start < 0:
        return ""
    ends = [folded.find(a, start + 40) for a in _TERROIR_END_ANCHORS]
    ends = [e for e in ends if e != -1]
    # bound by the nearest end-anchor AND a hard 4 000-char cap (the
    # salvaged text is unstructured — an end-anchor may be far downstream)
    end = min([*ends, start + 4000])
    return re.sub(r"\s+", " ", text[start:end]).strip()


def parse_spec(path: Path, slug: str, name: str = "") -> dict:
    """Parse one national-spec file into a sidecar dict. `name` is the
    appellation's own name — excluded from grape matching so the name
    (repeated through the prose, e.g. 'Π.Ο.Π. Ρόδος') doesn't fuzzy-hit a
    same-spelled grape. Full-name equality only, so Muscat appellations
    whose name merely *contains* the grape ('Μοσχάτος Πατρών') are safe."""
    text = to_text(path)
    exclude = frozenset({greek_norm(name)}) if name.strip() else frozenset()
    sections, titles = extract_sections(text)
    grape_body = sections.get("grape_varieties", "")
    grapes = parse_grape_list(grape_body, slug, exclude)
    if not grapes["principal"]:
        grapes = scan_grapes_prose(grape_body, slug, exclude)
    if not grapes["principal"]:
        # Section splitter found no grape header line (corrupt-doc salvage);
        # fall back to a keyword-windowed scan over the full text, keeping
        # the richest window (discards prose-decoy anchors).
        best = grapes
        for window in _grape_windows(text):
            cand = scan_grapes_prose(window, slug, exclude)
            if len(cand["principal"]) > len(best["principal"]):
                best = cand
        grapes = best
    geo = sections.get("geo_area", "")
    link = sections.get("link_to_terroir", "")
    if len(link) < 400:
        # No clean link section (corrupt-doc salvage): window the
        # 'ΔΕΣΜΟΣ ΜΕ ΤΗΝ ΓΕΩΓΡΑΦΙΚΗ ΠΕΡΙΟΧΗ' narrative out of the full text.
        link = _terroir_window(text) or link
    summary = _derive_summary(sections.get("description") or geo or "")
    return {
        "summary": summary,
        "grapes": grapes,
        "styles": parse_styles(sections),
        "geo_area_brief": geo,
        "link_to_terroir": link,
        "section_roles": sections,
        "section_titles": titles,
        "n_sections": len(sections),
        "n_grapes": len(grapes["details"]),
        "parser_template": f"gr-national-{path.suffix.lower().lstrip('.')}",
    }
