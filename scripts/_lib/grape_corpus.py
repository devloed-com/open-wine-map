"""Cross-country grape-slug inventory over the FR / ES / PT / IT corpora.

Walks `raw/inao/cahier-extracted/`, `raw/es/pliegos-extracted/`,
`raw/pt/cadernos-extracted/`, `raw/it/disciplinari-extracted/` and
`raw/it/masaf-disciplinari-extracted/` (the stage-02f MASAF sidecars —
their grapes never reach the doc-unico extractions, which stay stubs)
once and exposes three derived views that the downstream stages share:

- `collect_grape_slugs()` — full per-slug record: `{name, by_lang}`
  where `by_lang` is a `{country_code: count}` map. Single source of
  truth.
- `per_slug_display_name()` — legacy `{slug: display_name}` view (the
  shape 02b/grapes and 02g/VIVC consumed before this module existed).
- `per_slug_dominant_lang()` — `{slug: dominant_country_code}` where the
  dominant country is whichever corpus mentions the slug most often.
  Ties break alphabetical (`es` < `fr` < `pt`).

The dominant-cahier-language index drives the Wikipedia-source
preference chain in the new `02b_translate_grapes.py` and the locale
fallback in stage 04.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

from unidecode import unidecode

from _lib.grape_labels import _COLOUR_CODE_RE, clean_name, fold_capitals, is_capitals

ROOT = Path(__file__).resolve().parent.parent.parent
_SOURCES: tuple[tuple[str, Path], ...] = (
    ("fr", ROOT / "raw" / "inao" / "cahier-extracted"),
    ("es", ROOT / "raw" / "es" / "pliegos-extracted"),
    ("pt", ROOT / "raw" / "pt" / "cadernos-extracted"),
    ("it", ROOT / "raw" / "it" / "disciplinari-extracted"),
    ("it", ROOT / "raw" / "it" / "masaf-disciplinari-extracted"),
    ("at", ROOT / "raw" / "at" / "dokumente-extracted"),
    ("de", ROOT / "raw" / "de" / "dokumente-extracted"),
    ("si", ROOT / "raw" / "si" / "dokumenti-extracted"),
    # National-spec sidecars (stage 02f) carry the grape rosters for the
    # grandfathered SI/HR wines whose EU-OJ document was never published —
    # the dokumenti-extracted stubs have none. Mirrors the IT MASAF entry.
    ("si", ROOT / "raw" / "si" / "specifikacije-extracted"),
    ("hr", ROOT / "raw" / "hr" / "dokumenti-extracted"),
    ("hr", ROOT / "raw" / "hr" / "specifikacije-extracted"),
    ("ro", ROOT / "raw" / "ro" / "dokumente-extracted"),
    ("bg", ROOT / "raw" / "bg" / "dokumenti-extracted"),
    ("gr", ROOT / "raw" / "gr" / "dokumenti-extracted"),
    ("sk", ROOT / "raw" / "sk" / "dokumenty-extracted"),
    ("cz", ROOT / "raw" / "cz" / "dokumenty-extracted"),
    ("ch", ROOT / "raw" / "ch" / "dokumente-extracted"),
    # Malta — source language is English (EU single documents are EN).
    ("en", ROOT / "raw" / "mt" / "dokumente-extracted"),
    ("en", ROOT / "raw" / "gb" / "specs-extracted"),
    ("hu", ROOT / "raw" / "hu" / "dokumentumok-extracted"),
    ("nl", ROOT / "raw" / "nl" / "dokumenten-extracted"),
    # Belgium — per-record source_lang (nl Flemish / fr Walloon); nl covers
    # the majority incl. the cross-border Maasvallei.
    ("nl", ROOT / "raw" / "be" / "dokumenten-extracted"),
    ("fr", ROOT / "raw" / "lu" / "cahier-extracted"),
    ("el", ROOT / "raw" / "cy" / "dokumenti-extracted"),
    # National-spec sidecars whose rosters stage 04 merges into the map
    # (the SI/HR precedent above). The cz/sk/gr/ro register-fiches-extracted
    # dirs stay out: stage 04 reads only their terroir text.
    ("el", ROOT / "raw" / "cy" / "national-specs-extracted"),
    ("bg", ROOT / "raw" / "bg" / "national-specs-extracted"),
    # "gr" matches the primary gr row above so the per-slug dominant-lang
    # vote doesn't split (the whole column mixes country codes and locales
    # — el/de/sl/cs would be the locale-correct values; unknown codes fall
    # through the 02b-translate source chain harmlessly).
    ("gr", ROOT / "raw" / "gr" / "national-specs-extracted"),
    ("sk", ROOT / "raw" / "sk" / "national-specs-extracted"),
    ("ro", ROOT / "raw" / "ro" / "national-specs-extracted"),
)


# The corpus-wide label of a slug: what the filter chips, the search
# suggestions, the prose lines and a pill whose record has no spelling of
# its own show (stage 04 `grapes_info[slug].name`). A record's own pill
# keeps its own document's spelling (`grape_names`, grape_labels.py).
_SYNONYM_TAIL_RE = re.compile(r"\s+[-—–]\s+.*$")
_GERMAN_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def label_surface(name: str) -> str:
    """One record's spelling of a grape as a label candidate: the extraction
    debris (`clean_name`, which also closes a hyphen pdftotext broke across a
    line — "cabernet- sauvignon"), the "- synonym" tail ("Durella B. -
    Durello") and the OIV colour code ("Barbera N.", "Fetească regală B")
    dropped."""
    s = _SYNONYM_TAIL_RE.sub("", clean_name(name or ""))
    return _COLOUR_CODE_RE.sub("", s).strip()


def spelling_key(s: str) -> str:
    """Case, accents and punctuation folded — the key two surfaces share when
    they spell the same word: Kékfrankos / kekfrankos / KÉKFRANKOS,
    cabernet-sauvignon / Cabernet Sauvignon, Памид / pamid (a Cyrillic slug is
    its unidecode form; a Greek slug follows the register's transcription,
    η → i, so Αθήρι and Athiri stay two spellings)."""
    return re.sub(r"[\W_]+", "", unidecode(unicodedata.normalize("NFKC", s)).casefold())


_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "ʼ": "'", "`": "'", "´": "'"})
_NON_LATIN_RE = re.compile(r"[\u0370-\u03ff\u1f00-\u1fff\u0400-\u04ff]")


def _capitals_only(surfaces) -> int:
    return 0 if any(not is_capitals(s) for s in surfaces) else 1


def _mixed_case(s: str) -> bool:
    return any(ch.isupper() for ch in s) and not is_capitals(s)


def _form_key(s: str) -> str:
    """Casefold with the typography folded — the key of one spelling with
    its accents and punctuation (Nero d'Avola and Nero d’Avola are one)."""
    s = unicodedata.normalize("NFKC", s).translate(_APOSTROPHES).casefold()
    return re.sub(r"\s+", " ", s).strip()


def _has_marks(s: str) -> bool:
    return any(unicodedata.combining(ch) for ch in unicodedata.normalize("NFKD", s))


def pick_label(slug: str, votes: Counter, slug_votes: int = 0) -> str:
    """The label for `slug` from the spellings its records use.

    `votes` counts each cleaned surface (`label_surface`) — keyed
    `(surface, lang)`, or a bare surface — and `slug_votes` the records whose
    name is the slug itself: the lexicon's key written back by an extractor,
    a spelling of nothing. The surfaces are grouped by `spelling_key`, and
    the group that spells the slug — the lexicon's own canonical spelling, as
    some regulator writes it (Blauer Wildbacher over a more frequent
    Wildbacher, Bouvier over Findling) — wins; a DE slug's German
    transliteration of an umlaut (raeuschling) is tried too. Without such a
    group the slug-as-name records settle for the slug, else the most
    frequent group wins, a group seen only in capitals yielding to one with
    a mixed-case spelling. Inside the group the most frequent form decides
    accents and punctuation (Cabernet Sauvignon over the FR cahiers'
    Cabernet-Sauvignon, Sémillon over Semillon) — except a form without
    diacritics beside the same language's form with them, which is the
    extraction's loss, not a spelling (the Tejo and Douro cadernos read
    "Castelao"; Aleatico beside the French Aléatico is two spellings and
    the count decides) — and its mixed-case surface is taken; a Latin label
    left in capitals is lower-cased for the client's Title Case, a Greek one
    keeps its capitals (lower case would drop the tonos); a slug its records
    also write as itself never takes a Greek or Cyrillic label. Deterministic:
    every tie breaks on the text."""
    if not votes:
        return slug
    surfaces: dict[str, int] = {}
    langs: dict[str, set] = {}
    for key, n in votes.items():
        surf, lang = (key if isinstance(key, tuple) else (key, ""))
        surfaces[surf] = surfaces.get(surf, 0) + n
        langs.setdefault(surf, set()).add(lang)
    groups: dict[str, dict[str, int]] = {}
    for surf, n in surfaces.items():
        groups.setdefault(spelling_key(surf), {})[surf] = n
    own_key = spelling_key(slug)
    group = groups.get(own_key)
    if group is None:
        for g in groups.values():
            if any(spelling_key(s.casefold().translate(_GERMAN_UMLAUTS)) == own_key for s in g):
                group = g
                break
    if group is None and slug_votes:
        return slug
    if group is None:
        group = min(groups.values(), key=lambda g: (_capitals_only(g), -sum(g.values()), min(g)))
    forms: dict[str, dict[str, int]] = {}
    for surf, n in group.items():
        forms.setdefault(_form_key(surf), {})[surf] = n

    def form_langs(form: dict) -> set:
        return set().union(*(langs[s] for s in form))

    def degraded(form: dict) -> int:
        # Only against a form of the same script: a Latin transcription
        # beside the Greek spelling is not the Greek with its tonos lost.
        mine_form = min(form)
        if _has_marks(mine_form):
            return 0
        mine = form_langs(form)
        latin = not _NON_LATIN_RE.search(mine_form)
        return 1 if any(
            _has_marks(min(other)) and form_langs(other) & mine
            and latin == (not _NON_LATIN_RE.search(min(other)))
            for other in forms.values() if other is not form
        ) else 0

    def form_rank(form: dict) -> tuple:
        any_form = min(form)
        non_ascii = sum(1 for ch in any_form if ord(ch) > 127)
        return (_capitals_only(form), degraded(form), -sum(form.values()), -non_ascii, any_form)

    form = min(forms.values(), key=form_rank)
    label = min(form, key=lambda s: (0 if _mixed_case(s) else 1, -form[s], s))
    if slug_votes and _NON_LATIN_RE.search(label):
        return slug
    return fold_capitals(label, slug, {})


def collect_grape_slugs() -> dict[str, dict]:
    """Return `{slug: {"name": label, "by_lang": {lang: count}}}`.

    `name` is the slug's corpus-wide label, chosen by `pick_label` from every
    spelling the records give it. Until 2026-10-23 it was the first surface
    met in filesystem order, raw: Cabernet Sauvignon's chip read
    "Cabernet- Sauvignon" (a pdftotext line break in one Hérault IGP) and
    189 Italian and Greek varieties carried their colour code ("Barbera N.").
    """
    out: dict[str, dict] = {}
    votes: dict[str, Counter] = {}
    slug_votes: Counter = Counter()
    for lang, src in _SOURCES:
        if not src.exists():
            continue
        for jp in sorted(src.glob("*.json")):
            if jp.name.startswith("_"):
                continue
            rec = json.loads(jp.read_text(encoding="utf-8"))
            for d in (rec.get("grapes") or {}).get("details") or []:
                s = d.get("slug")
                if not s:
                    continue
                entry = out.setdefault(s, {"name": s, "by_lang": Counter()})
                entry["by_lang"][lang] += 1
                name = d.get("name") or ""
                if name == s:
                    slug_votes[s] += 1
                    continue
                surf = label_surface(name)
                if surf:
                    votes.setdefault(s, Counter())[(surf, lang)] += 1
    for s, entry in out.items():
        entry["name"] = pick_label(s, votes.get(s) or Counter(), slug_votes[s])
        entry["by_lang"] = dict(entry["by_lang"])
    return out


def per_slug_display_name(corpus: dict[str, dict] | None = None) -> dict[str, str]:
    """Legacy `{slug: display_name}` view."""
    if corpus is None:
        corpus = collect_grape_slugs()
    return {slug: entry["name"] for slug, entry in corpus.items()}


def per_slug_dominant_lang(corpus: dict[str, dict] | None = None) -> dict[str, str]:
    """`{slug: dominant_country_code}`. Ties break alphabetical."""
    if corpus is None:
        corpus = collect_grape_slugs()
    out: dict[str, str] = {}
    for slug, entry in corpus.items():
        by_lang = entry["by_lang"]
        if not by_lang:
            continue
        out[slug] = sorted(by_lang.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return out
