"""Health check for the stage-02d terroir-fact caches and their stage-02e
translations. Not a pipeline stage: run it after 02d / 02e (or on a
schedule), and in `--strict` mode as the acceptance gate before a build.

Sources are resolved through each country's own stage-02d module
(`_lib.terroir_sources.resolve_sources`) — lazily, once per country, and
only for the countries present in the selected caches — so every record
is graded against precisely the text 02d graded it against: the lien (or
the CH / MT / GB context block), the national-spec sidecar fallbacks and
the per-sub-section Wikipedia hint with its country-specific cap.

Checks. S = strict (counts towards the `--strict` exit code), R = report
only (a count and the offending rows, never a failure):

  cahier / wiki drift        R  cached `cahier_source_sha` /
                                `wiki_source_revision` no longer match the
                                current sources — 02d should be re-run for
                                the record.
  erosion                    R  per bullet, the coverage of `cahier_quote`
                                / `wiki_quote` is recomputed against the
                                CURRENT sources; a bullet none of whose
                                quotes still reaches FUZZY_THRESHOLD has
                                eroded (the source moved out from under it).
  length cap                 R  bullets over 240 chars (soft cap; the
                                prompts ask for 120–220).
  non_latin                  S  Cyrillic or Greek characters in a
                                translated bullet — every locale under
                                raw/translations/terroir-facts/ is
                                Latin-script.
  colour_code                S  a regulatory grape colour code left in a
                                bullet ("pinot noir N", "riesling B"),
                                source and translated; only fires after a
                                real grape name (`strip_colour_codes`).
  no_terminal_punct          S  the bullet does not end in . ! ? … —
                                source and translated.
  arrow                      R  "→" in a bullet, source and translated.
  label_prefix               R  the bullet opens with "Label: " — a
                                sub-zone name ("Rioja Oriental: …") is a
                                legitimate lead, so report only.
  meta_text                  R  the bullet talks about the document or
                                Wikipedia instead of the terroir
                                ("confirmed by Wikipedia").
  intra_record_duplicates    S  two facts of one record that
                                `duplicate_reason` deems restatements
                                (near-identical bullets, or the same
                                source quote with overlapping bullets).
  cross_record_shared_quotes R  one normalised `cahier_quote` (≥ 60 chars)
                                shared by ≥ 3 records of a country — a
                                shared cahier or boilerplate. The count is
                                the number of such groups; the report lists
                                the 30 largest with their slugs.
  name_guard                 S  an FR record whose current lien (≥ 800
                                chars) never names the appellation — the
                                signature of the wrong BO Agri PDF bound
                                to the record (plan W2b). The name is
                                tokenised (accents and case folded, stop
                                words and tokens under 4 letters dropped)
                                and one token must occur in the lien.
                                `NAME_GUARD_WHITELIST` lists the verified
                                exceptions (Saône-et-Loire: correct lien
                                that never names it).
  no_own_chapter             S  an FR record on a shared cahier (the 51
                                Alsace grands crus share one lien) whose
                                own `« Alsace grand cru <Cru> »` chapter
                                cannot be located (plan W2a).
  quote_outside_own_chapter  S  a shared-cahier fact whose `cahier_quote`
                                does not ground (FUZZY_THRESHOLD) inside the
                                record's own chapter — it was extracted
                                from another cru's chapter (plan W2a).
  feedback_recurrence        R  a do-not-claim entry of the record's review
                                feedback (`raw/terroir-facts-feedback/`,
                                `_lib/terroir_feedback.py`) whose
                                source-language bullet still matches a
                                current bullet: the known misleading claim
                                is still there (before a 02d re-run) or
                                came back (after one). Only extraction /
                                both entries count.
  wiki_with_cahier_quote     R  provenance `wiki` although a `cahier_quote`
                                is present: the quote grounds below the
                                threshold (paraphrase or typography, plan
                                W4).
  multi_sentence             R  a source bullet holding two or more
                                sentences (review 2026-09-12, R9).
  en_equals_src              R  a translated bullet identical to its
                                source bullet — the translation did not
                                happen.
  cross_record_identical_en  R  one EN bullet shared verbatim by ≥ 2
                                records (the Alsace produit slice, the
                                retsina cluster); count = groups.
  foreign_name               R  the record's source text names ANOTHER
                                appellation of the same country ≥ 3 times
                                and its own 0 times — a pasted section
                                (ΥΠΑΑΤ), a mis-bound PDF, an annex (R4).
  wiki_binding               R  the bound Wikipedia article's title shares
                                no token with the record name (Toro for
                                Tirol, a village for an IGT); curator
                                pins are trusted.
  masaf_sidecar_stale        R  an IT record whose MASAF sidecar predates
                                the annex-aware article slicer (R4).
  gate_pending               R  a record never passed through the
                                claim-support gate, or whose facts changed
                                since (`scripts/02d_verify_terroir_facts.py`).
  rewrite_rejected           R  a gate rewrite the guards refused (kept the
                                original bullet) — for a human look.
  translation_stale          R  a translation cache keyed to a source facts
                                sha that is no longer the record's, and not
                                re-keyed `pending:` — 02e will redo it on its
                                next corpus-wide pass; listed so it is not a
                                surprise there.
  rewrite_missing            R  a gate `rewrite` verdict that came back with
                                no rewrite text (kept the original bullet
                                as supported, note kept) — for a human look.

  name_guard_other           R  the name guard for the 20 non-FR countries
                                (the record's source text through
                                `terroir_sources`). Report only: CZ
                                records ground on a region-wide CHZO or a
                                per-wine-type fiche text that never names
                                the wine by design, and inflected names
                                (Greek, Slavic, Hungarian) are matched on
                                a crude stem.

The name guard requires the whole folded name minus stop words — or the
stem of its longest token of ≥ 6 letters — to occur, not any 4-letter
token ("tout" and "grains" occur in any French cahier). `--strict-labels`
promotes `label_prefix` to strict once the pre-style-block corpus has
been re-extracted.

The three FR checks read the extracted record's full `lien_au_terroir`
(raw/inao/cahier-extracted/), not the text 02d grades against: stage 02d
now pre-slices a shared cahier to the record's own chapter, and the
checks must still catch a cache extracted before it did.

The drift / erosion / name-guard / chapter checks need the record's
current sources; a record whose slug is no longer a 02d target is graded
against empty sources (so its bullets report as eroded) and listed under
`no_source_today_aocs`, and a country whose 02d module fails to load is
listed under `source_unresolved_countries` with its records exempt from
those checks (the pure bullet checks still run).

Outputs: one line per record on stderr (unless --quiet; --verbose adds
the bullets), the aggregate summary as JSON on stderr, and with
`--report PATH` the full JSON: `summary`, per-record `aocs` (with
per-bullet coverage and style findings) and `findings` — the offending
(slug[, lang, index]) rows per check.

Exit code: 0, or 1 on an internal error (missing cache directory). With
`--strict`: 1 when any strict check has a count > 0.

Usage:
  .venv/bin/python scripts/audit_terroir_facts.py --quiet --report tmp/terroir-facts-review/audit.json
  .venv/bin/python scripts/audit_terroir_facts.py --country fr --slug chablis --verbose
  .venv/bin/python scripts/audit_terroir_facts.py --strict --quiet
"""

from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import cache  # noqa: E402
from _lib.terroir_cache import LANGS, TERROIR, TRANSLATIONS  # noqa: E402
from _lib.terroir_chapters import is_shared, own_chapter  # noqa: E402
from _lib.terroir_coverage import (  # noqa: E402
    FUZZY_THRESHOLD,
    SourceMatcher,
    fuzzy_coverage,
    normalize,
)
from _lib.terroir_dedupe import duplicate_reason, facts_sha  # noqa: E402
from _lib.terroir_feedback import load_feedback, recurrence_findings  # noqa: E402
from _lib.terroir_normalize import strip_colour_codes  # noqa: E402
from _lib.terroir_sources import COUNTRIES, Sources, resolve_sources  # noqa: E402

FR_EXTRACTED = ROOT / "raw" / "inao" / "cahier-extracted"

BULLET_SOFT_CAP = 240

NAME_GUARD_MIN_LIEN = 800
NAME_GUARD_MIN_TOKEN = 4
NAME_GUARD_LONG_TOKEN = 6
# saone-et-loire: a correct lien that never names it. calvados-domfontais: SIQO
# misspells the name (the cahier and the register say "Domfrontais" — see
# scripts/_lib/fr/register_overrides.json), so the stem test cannot match.
NAME_GUARD_WHITELIST = {"saone-et-loire", "calvados-domfontais"}
FOREIGN_NAME_MIN_HITS = 5
FOREIGN_NAME_MIN_CHARS = 6
MASAF_SIDECARS = ROOT / "raw" / "it" / "masaf-disciplinari-extracted"
MASAF_CURRENT_TEMPLATE = "it-masaf-disciplinare-v3"
WIKI_AOCS = ROOT / "raw" / "wikipedia" / "aocs"
_WIKI_LANG = {"at": "de", "si": "sl", "gr": "el", "cz": "cs", "lu": "fr", "mt": "en", "gb": "en", "cy": "el"}
NAME_STOP_WORDS = frozenset(
    "aoc aop igp vin vins de du des d l la le les et ou saint sainte grand grands cru crus "
    "village villages cotes coteaux premier cote mont pays val vallee".split()
)

SHARED_QUOTE_MIN_CHARS = 60
SHARED_QUOTE_MIN_RECORDS = 3
SHARED_QUOTE_TOP = 30

NON_LATIN_RE = re.compile(r"[Ѐ-ӿͰ-Ͽ]")
ARROW_RE = re.compile("→")
# A one- or two-word label ("Colour:", "Rioja Oriental:"), no parenthesis —
# not an enumerating colon inside a sentence ("Three main soil types
# coexist:", "Zierfandler (Synonym: Spätrot)").
LABEL_PREFIX_RE = re.compile(r"^\s*(?:[^\s:(\d]+\s){0,1}[^\s:(\d]+:\s")
META_RE = re.compile(
    r"(?i)\b(wikipedia|according to the (production |product )?(document|specification|cahier|disciplinare|pliego)|confirmed by"
    r"|the (cahier|disciplinare|specification|pliego) (states|says|notes)"
    # source-language forms: "secondo il disciplinare", "selon le cahier des charges",
    # "según el pliego", "laut (der) Produktspezifikation", "volgens het productdossier"
    r"|secondo (il|quanto (previsto|indicato|riportato) (dal|nel)) disciplinare|il disciplinare (prevede|stabilisce|indica|riporta)"
    r"|selon le cahier des charges|le cahier des charges (précise|indique|prévoit|stipule)"
    r"|según (el|lo (establecido|indicado) en el) pliego|el pliego (establece|indica|recoge)"
    r"|laut (der |dem )?(produktspezifikation|einzige[nm] dokument)|gemäß (der |dem )?(produktspezifikation|einzige[nm] dokument)"
    r"|volgens het (productdossier|enig document)|conform het (productdossier|enig document)"
    r"|segundo o caderno|de acordo com o caderno)\b"
)
TERMINAL_PUNCT = ".!?…"
MULTI_SENTENCE_RE = re.compile(r"[.!?]\s+[A-ZÀ-ÝΑ-ΩА-Я]")

STRICT_CHECKS = frozenset({
    "non_latin", "colour_code", "no_terminal_punct", "intra_record_duplicates",
    "name_guard", "no_own_chapter", "quote_outside_own_chapter",
})
# Every check name, in report order.
CHECKS = (
    "non_latin", "colour_code", "no_terminal_punct", "arrow", "label_prefix", "meta_text",
    "multi_sentence", "intra_record_duplicates", "cross_record_shared_quotes",
    "cross_record_identical_en", "en_equals_src", "name_guard", "name_guard_other", "foreign_name", "wiki_binding",
    "no_own_chapter", "quote_outside_own_chapter", "wiki_with_cahier_quote",
    "feedback_recurrence", "masaf_sidecar_stale", "gate_pending", "rewrite_rejected",
    "rewrite_missing", "translation_stale",
)
_LETTERS_RE = re.compile(r"[^\W\d_]+")


def log(msg: str) -> None:
    print(f"[audit] {msg}", file=sys.stderr)


# ──────────────────────────────────────────────── pure checks (bullet) ──


_CHEM_PREFIX_RE = re.compile(r"\b[αβγδ]-(?=[A-Za-z])")


def has_non_latin(bullet: str) -> bool:
    """Greek / Cyrillic script in a bullet — ignoring a Greek-letter
    chemical prefix ("α-terpineol"), which is correct chemistry."""
    return bool(NON_LATIN_RE.search(_CHEM_PREFIX_RE.sub("", bullet or "")))


def has_colour_code(bullet: str) -> bool:
    """A grape colour code (` N` / ` B` / ` G` / ` Rs` / ` Rg`) after a grape
    name — `strip_colour_codes` leaves any other capital alone."""
    return bool(bullet) and strip_colour_codes(bullet) != bullet


def has_arrow(bullet: str) -> bool:
    return bool(ARROW_RE.search(bullet or ""))


def has_label_prefix(bullet: str) -> bool:
    return bool(LABEL_PREFIX_RE.match(bullet or ""))


def missing_terminal_punct(bullet: str) -> bool:
    b = (bullet or "").rstrip()
    return not b or b[-1] not in TERMINAL_PUNCT


def has_meta_text(bullet: str) -> bool:
    return bool(META_RE.search(bullet or ""))


def has_multiple_sentences(bullet: str) -> bool:
    """Two or more sentences: a terminator followed by a capital. A decimal
    ("13.5 % vol") or an abbreviation before a lowercase word does not fire."""
    return bool(MULTI_SENTENCE_RE.search((bullet or "").strip()[:-1]))


STYLE_CHECKS = (
    ("colour_code", has_colour_code),
    ("arrow", has_arrow),
    ("label_prefix", has_label_prefix),
    ("no_terminal_punct", missing_terminal_punct),
    ("meta_text", has_meta_text),
    ("multi_sentence", has_multiple_sentences),
)


def style_findings(bullet: str) -> list[str]:
    """Names of the style checks that fire on `bullet`, in STYLE_CHECKS order."""
    return [name for name, check in STYLE_CHECKS if check(bullet)]


# ───────────────────────────────────────────────── pure checks (record) ──


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.casefold()


def name_tokens(name: str) -> list[str]:
    """The appellation-name tokens a lien is expected to mention: letter
    runs of the folded name, minus stop words and tokens under
    NAME_GUARD_MIN_TOKEN letters."""
    return [
        t for t in _LETTERS_RE.findall(fold(name))
        if t not in NAME_STOP_WORDS and len(t) >= NAME_GUARD_MIN_TOKEN
    ]


def lien_names_record(lien: str, name: str) -> bool | None:
    """True / False: the folded lien contains the whole folded name minus
    stop words, or — when the name has one — its longest token of at least
    NAME_GUARD_LONG_TOKEN letters. Any 4-letter token was too weak: "tout"
    and "grains" occur in every French cahier, so Bourgogne
    Passe-tout-grains passed on the Beaujolais cahier (review 2026-09-12).
    None: the name has no usable token, so nothing can be required."""
    tokens = name_tokens(name)
    if not tokens:
        return None
    folded = fold(lien)
    whole = " ".join(tokens)
    if whole in folded:
        return True
    longest = max(tokens, key=len)
    if len(longest) >= NAME_GUARD_LONG_TOKEN and name_stem(longest) in folded:
        return True
    if len(longest) < NAME_GUARD_LONG_TOKEN:
        return any(t in folded for t in tokens)
    return False


def name_stem(token: str) -> str:
    """A crude inflection-tolerant stem: the token minus its last two
    letters (never shorter than 5). Greek, Slavic, Hungarian and Romanian
    names decline — «Ρετσίνα Βοιωτίας» is named «Βοιωτία» in its own text,
    «Šobes» appears as «Šobesu» — so the longest-token test matches the
    stem, not the dictionary form."""
    return token[: max(5, len(token) - 2)]


def name_guard_finding(lien: str, name: str, slug: str) -> bool:
    """True when the W2b guard fires: a lien of at least NAME_GUARD_MIN_LIEN
    chars that never names the appellation, for a slug not whitelisted."""
    if slug in NAME_GUARD_WHITELIST or len(lien) < NAME_GUARD_MIN_LIEN:
        return False
    return lien_names_record(lien, name) is False


def foreign_names(lien: str, name: str, others: dict[str, str]) -> list[dict]:
    """Other appellations of the same country whose whole folded name
    (≥ FOREIGN_NAME_MIN_CHARS) occurs ≥ FOREIGN_NAME_MIN_HITS times in the
    record's source text while the record's own name never does — the
    signature of a pasted section, a mis-bound PDF or an annex. `others`
    is {slug: folded name}. A name that is a substring of the record's own
    name (Chianti inside Chianti Classico) is skipped."""
    if len(lien) < NAME_GUARD_MIN_LIEN or lien_names_record(lien, name) is not False:
        return []
    folded = fold(lien)
    own = " ".join(name_tokens(name))
    out: list[dict] = []
    for slug, other in others.items():
        key = name_stem(max(other.split(), key=len)) if other else ""
        # A short stem ("terre", "colli", "pisa") is a generic word, not a name.
        if len(key) < FOREIGN_NAME_MIN_CHARS or key in own or own in other:
            continue
        n = folded.count(key)
        if n >= FOREIGN_NAME_MIN_HITS:
            out.append({"other": slug, "hits": n})
    out.sort(key=lambda r: -r["hits"])
    return out[:5]


def wiki_binding_finding(country: str, source_lang: str, slug: str, name: str) -> dict | None:
    """The bound Wikipedia article's title must share a name token (or a
    5-letter prefix) with the record name; curator pins are trusted."""
    lang = source_lang or _WIKI_LANG.get(country, country)
    w = cache.read_json_or_none(WIKI_AOCS / lang / f"{slug}.json")
    if not w or w.get("missing") or w.get("error") or w.get("override_source") == "curator":
        return None
    title = w.get("title") or w.get("wiki_title") or unquote((w.get("page_url") or "").rsplit("/", 1)[-1]).replace("_", " ")
    if not title:
        return None
    t_tokens = name_tokens(title)
    n_tokens = name_tokens(name)
    for a in n_tokens:
        for b in t_tokens:
            if a == b or a in b or b in a or (len(a) >= 5 and len(b) >= 5 and a[:5] == b[:5]):
                return None
    return {"title": title, "lang": lang}


def masaf_sidecar_stale(slug: str) -> bool:
    d = cache.read_json_or_none(MASAF_SIDECARS / f"{slug}.json")
    return bool(d) and d.get("parser_template") != MASAF_CURRENT_TEMPLATE


def gate_pending(data: dict) -> bool:
    from _lib.terroir_gate import needs_gate  # local import: keep the audit's imports flat
    return needs_gate(data)


def own_chapter_findings(lien: str, name: str, facts: list[dict]) -> list[dict]:
    """W2a rows for a record on a shared cahier: `no_own_chapter` when the
    record's chapter is not found, else `quote_outside_own_chapter` for
    every cahier-grounded fact (provenance `cahier` / `both`) whose
    `cahier_quote` does not ground inside that chapter. A `wiki` fact is
    skipped: its cahier quote never grounded at extraction either (02d keeps
    a fact on either quote), so it says nothing about which chapter the
    record was graded against. Empty for a lien that is not shared."""
    if not is_shared(lien):
        return []
    window = own_chapter(lien, name)
    if window is None:
        return [{"check": "no_own_chapter"}]
    matcher = SourceMatcher(lien[window[0]:window[1]])
    out: list[dict] = []
    for i, f in enumerate(facts):
        quote = (f.get("cahier_quote") or "").strip()
        if not quote or f.get("provenance") == "wiki":
            continue
        cov = matcher.coverage(quote)
        if cov < FUZZY_THRESHOLD:
            out.append({"check": "quote_outside_own_chapter", "index": i, "coverage": round(cov, 3)})
    return out


def intra_record_duplicates(facts: list[dict]) -> list[dict]:
    """Every pair (i < j) of facts that `duplicate_reason` deems restatements."""
    out: list[dict] = []
    for i in range(len(facts)):
        for j in range(i + 1, len(facts)):
            reason = duplicate_reason(facts[i], facts[j])
            if reason:
                out.append({"i": i, "j": j, "reason": reason})
    return out


def wiki_with_cahier_quote(facts: list[dict]) -> list[int]:
    return [
        i for i, f in enumerate(facts)
        if f.get("provenance") == "wiki" and (f.get("cahier_quote") or "").strip()
    ]


def shared_quote_groups(
    facts_by_slug: dict[str, list[dict]],
    min_chars: int = SHARED_QUOTE_MIN_CHARS,
    min_records: int = SHARED_QUOTE_MIN_RECORDS,
) -> list[dict]:
    """Normalised `cahier_quote`s of at least `min_chars` shared by at least
    `min_records` distinct records, largest group first."""
    slugs_by_quote: dict[str, set[str]] = defaultdict(set)
    for slug, facts in facts_by_slug.items():
        for f in facts:
            q = normalize(f.get("cahier_quote") or "")
            if len(q) >= min_chars:
                slugs_by_quote[q].add(slug)
    groups = [
        {"quote": q, "count": len(slugs), "slugs": sorted(slugs)}
        for q, slugs in slugs_by_quote.items() if len(slugs) >= min_records
    ]
    groups.sort(key=lambda g: (-g["count"], g["quote"]))
    return groups


# ──────────────────────────────────────────────────────────── sources ──


class SourceResolver:
    """Resolves each country's stage-02d sources once, on first request."""

    def __init__(self) -> None:
        self._by_country: dict[str, dict[str, Sources] | None] = {}
        self.failed: dict[str, str] = {}

    def get(self, country: str) -> dict[str, Sources] | None:
        if country not in self._by_country:
            self._by_country[country] = self._resolve(country)
        return self._by_country[country]

    def _resolve(self, country: str) -> dict[str, Sources] | None:
        if country not in COUNTRIES:
            self.failed[country] = "no stage-02d module for this country"
            log(f"{country}: {self.failed[country]}")
            return None
        log(f"{country}: resolving stage-02d sources …")
        t0 = time.monotonic()
        try:
            sources = resolve_sources(country)
        except Exception as e:  # noqa: BLE001
            self.failed[country] = repr(e)
            log(f"{country}: FAILED to resolve sources: {e!r}")
            return None
        log(f"{country}: {len(sources)} source records in {time.monotonic() - t0:.1f}s")
        return sources


def country_names() -> dict[str, dict[str, str]]:
    """{country: {slug: folded appellation name minus stop words}} over every
    terroir-facts cache (FR names from the extracted records) — the
    candidate set for the foreign-name guard."""
    out: dict[str, dict[str, str]] = defaultdict(dict)
    for p in TERROIR.glob("*.json"):
        if p.name.startswith("manifest"):
            continue
        d = cache.read_json_or_none(p)
        if not d:
            continue
        country = d.get("country") or "fr"
        name = d.get("name") or (fr_record(p.stem)[0] if country == "fr" else p.stem)
        tokens = name_tokens(name)
        if tokens:
            out[country][p.stem] = " ".join(tokens)
    return out


def fr_record(slug: str) -> tuple[str, str]:
    """(name, full lien) of the FR extracted record — FR caches carry no
    `name`, and the W2a / W2b checks grade the unsliced lien."""
    rec = cache.read_json_or_none(FR_EXTRACTED / f"{slug}.json") or {}
    return rec.get("name") or slug, (rec.get("lien_au_terroir") or "").strip()


# ──────────────────────────────────────────────────────────────── audit ──


def audit_one(
    data: dict, src: Sources | None, source_status: str, name: str, fr_lien: str = "",
    others: dict[str, str] | None = None,
) -> dict:
    """Audit one source cache against its current sources. `source_status`
    is `ok` (src given), `missing` (the slug is no longer a 02d target —
    graded against empty sources) or `unresolved` (the country's 02d module
    failed to load — source-dependent checks skipped). `fr_lien` is the FR
    extracted record's full lien for the name-guard and own-chapter checks."""
    slug = data.get("slug")
    country = data.get("country") or "fr"
    facts = data.get("facts") or []
    cahier_drift = src is not None and src.cahier_sha != data.get("cahier_source_sha")
    wiki_drift = (
        src is not None and src.wiki_revision is not None
        and src.wiki_revision != data.get("wiki_source_revision")
    )
    graded = source_status != "unresolved"

    bullets: list[dict] = []
    for f in facts:
        sub = f.get("subsection") or "facteurs_naturels"
        bullet = f.get("bullet") or ""
        cq = f.get("cahier_quote") or ""
        wq = f.get("wiki_quote") or ""
        cov_c = src.matcher.coverage(cq) if (graded and src and cq) else 0.0
        cov_w = fuzzy_coverage(wq, src.hints.get(sub, "")) if (graded and src and wq) else 0.0
        still_grounded = (not graded) or cov_c >= FUZZY_THRESHOLD or cov_w >= FUZZY_THRESHOLD
        bullets.append({
            "bullet": bullet,
            "subsection": sub,
            "provenance": f.get("provenance", ""),
            "cached_cahier_coverage": f.get("cahier_coverage", 0.0),
            "cached_wiki_coverage": f.get("wiki_coverage", 0.0),
            "current_cahier_coverage": round(cov_c, 3),
            "current_wiki_coverage": round(cov_w, 3),
            "still_grounded": still_grounded,
            "over_length_cap": len(bullet) > BULLET_SOFT_CAP,
            "style": style_findings(bullet),
        })

    name_guard = False
    chapter: list[dict] = []
    foreign: list[dict] = []
    guard_text = fr_lien if country == "fr" else (src.cahier if (graded and src) else "")
    if guard_text:
        name_guard = name_guard_finding(guard_text, name, slug)
        foreign = foreign_names(guard_text, name, others or {}) if name_guard else []
    if country == "fr" and fr_lien:
        chapter = own_chapter_findings(fr_lien, name, facts)
    wiki_binding = wiki_binding_finding(country, data.get("source_lang") or "", slug, name)
    rejected = [
        i for i, f in enumerate(facts) if (f.get("support") or {}).get("verdict") == "rewrite-rejected"
    ]
    missing = [i for i, f in enumerate(facts) if (f.get("support") or {}).get("rewrite_missing")]

    return {
        "slug": slug,
        "country": country,
        "name": name,
        "n_facts": len(facts),
        "source_status": source_status,
        "cahier_drift": cahier_drift,
        "wiki_drift": wiki_drift,
        "translator": data.get("translator") or data.get("model_id") or data.get("model"),
        "translator_kind": data.get("translator_kind") or data.get("model_kind"),
        "bullets": bullets,
        "duplicates": intra_record_duplicates(facts),
        "wiki_with_cahier_quote": wiki_with_cahier_quote(facts),
        "name_guard": name_guard,
        "foreign_name": foreign,
        "wiki_binding": wiki_binding,
        "chapter": chapter,
        "feedback_recurrence": recurrence_findings(load_feedback(slug), facts),
        "masaf_sidecar_stale": country == "it" and masaf_sidecar_stale(slug),
        "gate_pending": gate_pending(data),
        "rewrite_rejected": rejected,
        "rewrite_missing": missing,
    }


def audit_translations(slug: str, source_facts: list[dict] | None = None) -> tuple[dict[str, int], list[dict], list[str]]:
    """(bullets per locale, finding rows, EN bullets) for the slug's
    translation caches. `source_facts` enables `en_equals_src` (a
    translated bullet identical to its source bullet, same index)."""
    n_by_lang: dict[str, int] = {}
    rows: list[dict] = []
    en_bullets: list[str] = []
    src_bullets = [(f.get("bullet") or "").strip() for f in (source_facts or [])]
    src_sha = facts_sha(source_facts) if source_facts else None
    for lang in LANGS:
        t = cache.read_json_or_none(TRANSLATIONS / lang / f"{slug}.json")
        if not t or t.get("mode") == "verbatim":
            continue
        facts = t.get("facts") or []
        n_by_lang[lang] = len(facts)
        key = t.get("source_facts_sha") or ""
        if src_sha and key != src_sha and not key.startswith("pending:"):
            # keyed to a source that has since changed and not marked for 02e:
            # invisible until 02e's next corpus-wide pass (two such caches sat
            # in LU / AT until the 2026-09-14 smoke happened to pick them up)
            rows.append({"check": "translation_stale", "slug": slug, "lang": lang})
        for i, f in enumerate(facts):
            bullet = f.get("bullet") or ""
            checks = [c for c in style_findings(bullet) if c != "multi_sentence"]
            if has_non_latin(bullet):
                checks.insert(0, "non_latin")
            if i < len(src_bullets) and src_bullets[i] and bullet.strip() == src_bullets[i]:
                checks.append("en_equals_src")
            rows.extend({"check": c, "slug": slug, "lang": lang, "index": i} for c in checks)
            if lang == "en":
                en_bullets.append(bullet)
    return n_by_lang, rows, en_bullets


def identical_en_groups(en_by_slug: dict[str, list[str]], min_records: int = 2) -> list[dict]:
    """EN bullets (normalised) shared verbatim by ≥ `min_records` records."""
    slugs_by_bullet: dict[str, set[str]] = defaultdict(set)
    for slug, bullets in en_by_slug.items():
        for b in bullets:
            nb = normalize(b)
            if len(nb) >= 20:
                slugs_by_bullet[nb].add(slug)
    groups = [{"bullet": b, "count": len(sl), "slugs": sorted(sl)}
              for b, sl in slugs_by_bullet.items() if len(sl) >= min_records]
    groups.sort(key=lambda g: (-g["count"], g["bullet"]))
    return groups


def collect_findings(
    audits: list[dict], translation_rows: list[dict], shared_groups: list[dict],
    identical_en: list[dict] | None = None,
) -> dict[str, list[dict]]:
    """The offending rows per check, source-cache rows first."""
    rows: dict[str, list[dict]] = {name: [] for name in CHECKS}
    for a in audits:
        slug = a["slug"]
        for i, b in enumerate(a["bullets"]):
            for check in b["style"]:
                rows[check].append({"slug": slug, "index": i})
        for d in a["duplicates"]:
            rows["intra_record_duplicates"].append({
                "slug": slug, "index": d["j"], "duplicate_of": d["i"], "reason": d["reason"],
            })
        for i in a["wiki_with_cahier_quote"]:
            rows["wiki_with_cahier_quote"].append({"slug": slug, "index": i})
        if a["name_guard"]:
            key = "name_guard" if a["country"] == "fr" else "name_guard_other"
            rows[key].append({"slug": slug, "name": a["name"], "country": a["country"]})
        if a.get("foreign_name"):
            rows["foreign_name"].append({"slug": slug, "name": a["name"], "country": a["country"],
                                         "names": a["foreign_name"]})
        if a.get("wiki_binding"):
            rows["wiki_binding"].append({"slug": slug, "name": a["name"], **a["wiki_binding"]})
        for c in a["chapter"]:
            rows[c["check"]].append({"slug": slug, **{k: v for k, v in c.items() if k != "check"}})
        for r in a.get("feedback_recurrence") or []:
            rows["feedback_recurrence"].append({"slug": slug, **r})
        if a.get("masaf_sidecar_stale"):
            rows["masaf_sidecar_stale"].append({"slug": slug})
        if a.get("gate_pending"):
            rows["gate_pending"].append({"slug": slug})
        for i in a.get("rewrite_rejected") or []:
            rows["rewrite_rejected"].append({"slug": slug, "index": i})
        for i in a.get("rewrite_missing") or []:
            rows["rewrite_missing"].append({"slug": slug, "index": i})
    for r in translation_rows:
        rows[r["check"]].append({k: v for k, v in r.items() if k != "check"})
    rows["cross_record_shared_quotes"] = shared_groups
    rows["cross_record_identical_en"] = identical_en or []
    return rows


def summarize(
    audits: list[dict],
    findings: dict[str, list[dict]],
    *,
    translation_caches: int,
    translated_bullets: int,
    verbatim_skipped: int,
    unresolved: dict[str, str],
) -> dict:
    """Aggregate counters and medians over the per-AOC audits, plus one
    `{count, strict}` entry per check."""
    bullets_per_aoc = [a["n_facts"] for a in audits]
    by_provenance: Counter[str] = Counter()
    by_subsection: Counter[str] = Counter()
    by_translator_kind: Counter[str] = Counter()
    by_country: Counter[str] = Counter()
    over_cap = 0
    eroded_bullets = 0
    eroded_aocs: list[str] = []
    for a in audits:
        by_translator_kind[a["translator_kind"] or ""] += 1
        by_country[a["country"]] += 1
        any_eroded = False
        for b in a["bullets"]:
            by_provenance[b["provenance"]] += 1
            by_subsection[b["subsection"]] += 1
            over_cap += b["over_length_cap"]
            if not b["still_grounded"]:
                eroded_bullets += 1
                any_eroded = True
        if any_eroded:
            eroded_aocs.append(a["slug"])

    checks: dict[str, dict] = {}
    for name in CHECKS:
        rows = findings[name]
        entry = {"strict": name in STRICT_CHECKS, "count": len(rows)}
        if name in dict(STYLE_CHECKS) or name == "non_latin":
            entry["source"] = sum(1 for r in rows if "lang" not in r)
            entry["translated"] = len(rows) - entry["source"]
        if name in ("intra_record_duplicates", "feedback_recurrence", "rewrite_rejected", "rewrite_missing",
                    "en_equals_src"):
            entry["records"] = len({r["slug"] for r in rows})
        checks[name] = entry
    strict_failures = sum(c["count"] for c in checks.values() if c["strict"])

    return {
        "n_aocs": len(audits),
        "bullets_total": sum(bullets_per_aoc),
        "bullets_per_aoc_median": statistics.median(bullets_per_aoc) if bullets_per_aoc else 0,
        "bullets_per_aoc_min": min(bullets_per_aoc) if bullets_per_aoc else 0,
        "bullets_per_aoc_max": max(bullets_per_aoc) if bullets_per_aoc else 0,
        "by_provenance": dict(by_provenance),
        "by_subsection": dict(by_subsection),
        "by_translator_kind": dict(by_translator_kind),
        "by_country": dict(sorted(by_country.items())),
        "over_length_cap": over_cap,
        "eroded_bullets": eroded_bullets,
        "eroded_aocs": eroded_aocs,
        "cahier_drift_aocs": sum(1 for a in audits if a["cahier_drift"]),
        "wiki_drift_aocs": sum(1 for a in audits if a["wiki_drift"]),
        "no_source_today_aocs": [a["slug"] for a in audits if a["source_status"] == "missing"],
        "source_unresolved_countries": unresolved,
        "source_unresolved_aocs": sum(1 for a in audits if a["source_status"] == "unresolved"),
        "verbatim_skipped": verbatim_skipped,
        "translation_caches": translation_caches,
        "translated_bullets_total": translated_bullets,
        "checks": checks,
        "strict_failures": strict_failures,
    }


# ───────────────────────────────────────────────────────────── output ──


def print_per_aoc(audit: dict, verbose: bool) -> None:
    flags: list[str] = []
    if audit["source_status"] != "ok":
        flags.append(f"source-{audit['source_status']}")
    if audit["cahier_drift"]:
        flags.append("cahier-drift")
    if audit["wiki_drift"]:
        flags.append("wiki-drift")
    eroded = sum(1 for b in audit["bullets"] if not b["still_grounded"])
    if eroded:
        flags.append(f"eroded={eroded}")
    over = sum(1 for b in audit["bullets"] if b["over_length_cap"])
    if over:
        flags.append(f"over_cap={over}")
    styled = sum(1 for b in audit["bullets"] if b["style"])
    if styled:
        flags.append(f"style={styled}")
    if audit["duplicates"]:
        flags.append(f"dups={len(audit['duplicates'])}")
    if audit["wiki_with_cahier_quote"]:
        flags.append(f"wiki+cq={len(audit['wiki_with_cahier_quote'])}")
    if audit["name_guard"]:
        flags.append("name-guard")
    if any(c["check"] == "no_own_chapter" for c in audit["chapter"]):
        flags.append("no-own-chapter")
    outside = sum(1 for c in audit["chapter"] if c["check"] == "quote_outside_own_chapter")
    if outside:
        flags.append(f"outside-chapter={outside}")
    if audit.get("feedback_recurrence"):
        flags.append(f"known-bad={len(audit['feedback_recurrence'])}")
    if audit.get("foreign_name"):
        flags.append("foreign-name=" + ",".join(f["other"] for f in audit["foreign_name"][:2]))
    if audit.get("wiki_binding"):
        flags.append(f"wiki-binding={audit['wiki_binding']['title'][:30]!r}")
    if audit.get("gate_pending"):
        flags.append("gate-pending")
    if audit.get("rewrite_rejected"):
        flags.append(f"rewrite-rejected={len(audit['rewrite_rejected'])}")
    if audit.get("rewrite_missing"):
        flags.append(f"rewrite-missing={len(audit['rewrite_missing'])}")
    flag_str = (" [" + ", ".join(flags) + "]") if flags else ""
    print(
        f"  {audit['slug']:40} {audit['country']:2} n={audit['n_facts']:2} "
        f"{audit['translator_kind'] or '-':12}{flag_str}"
    )
    if verbose:
        for b in audit["bullets"]:
            notes: list[str] = []
            if not b["still_grounded"]:
                notes.append(
                    f"eroded (now cahier={b['current_cahier_coverage']} "
                    f"wiki={b['current_wiki_coverage']})"
                )
            if b["over_length_cap"]:
                notes.append("over length cap")
            notes.extend(b["style"])
            note = ("  ⚠ " + "; ".join(notes)) if notes else ""
            print(f"      {b['provenance']:6} [{b['subsection'][:8]:>8}] {b['bullet'][:80]}{note}")


# ─────────────────────────────────────────────────────────────── main ──


def select_caches(
    slugs: set[str] | None, countries: set[str] | None, sample: int,
) -> tuple[list[tuple[Path, dict]], int]:
    """(selected (path, cache) pairs in slug order, verbatim caches skipped)."""
    selected: list[tuple[Path, dict]] = []
    verbatim = 0
    for p in sorted(TERROIR.glob("*.json")):
        if p.name.startswith("manifest"):
            continue
        if slugs and p.stem not in slugs:
            continue
        d = cache.read_json_or_none(p)
        if d is None:
            log(f"err {p.stem}: unreadable cache")
            continue
        if d.get("mode") == "verbatim":
            verbatim += 1
            continue
        if countries and (d.get("country") or "fr") not in countries:
            continue
        selected.append((p, d))
    if sample and len(selected) > sample:
        random.seed(0)
        selected = sorted(random.sample(selected, sample), key=lambda t: t[0])
    return selected, verbatim


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--sample", type=int, default=0,
        help="audit only N AOCs (random sample); 0 = all (default)",
    )
    ap.add_argument(
        "--slug", action="append", default=None,
        help="restrict to specific AOC slug(s); repeatable",
    )
    ap.add_argument(
        "--country", action="append", default=None,
        help="restrict to a country code (the cache's `country`, missing = fr); repeatable",
    )
    ap.add_argument("--verbose", action="store_true", help="print every bullet, not just AOC summary")
    ap.add_argument("--quiet", action="store_true", help="suppress per-AOC lines (totals only)")
    ap.add_argument("--report", metavar="PATH", default=None, help="write full audit JSON to PATH")
    ap.add_argument(
        "--strict", action="store_true",
        help="exit 1 when any strict check (see module docstring) has a count > 0",
    )
    ap.add_argument(
        "--strict-labels", action="store_true",
        help="also treat label_prefix as strict (once the pre-style-block corpus is re-extracted)",
    )
    args = ap.parse_args()
    global STRICT_CHECKS
    if args.strict_labels:
        STRICT_CHECKS = STRICT_CHECKS | {"label_prefix"}

    if not TERROIR.exists():
        print("error: raw/terroir-facts is missing — run 02d first", file=sys.stderr)
        return 1

    t_start = time.monotonic()
    selected, verbatim_skipped = select_caches(
        set(args.slug) if args.slug else None,
        set(args.country) if args.country else None,
        args.sample,
    )
    if not selected:
        log("no terroir-facts caches to audit.")
        return 0
    log(f"{len(selected)} AOC caches ({verbatim_skipped} verbatim skipped)")

    resolver = SourceResolver()
    audits: list[dict] = []
    translation_rows: list[dict] = []
    translation_caches = 0
    translated_bullets = 0
    facts_by_country: dict[str, dict[str, list[dict]]] = defaultdict(dict)
    en_by_slug: dict[str, list[str]] = {}
    names_by_country = country_names()
    for p, d in selected:
        slug = d.get("slug") or p.stem
        d["slug"] = slug
        country = d.get("country") or "fr"
        sources = resolver.get(country)
        if sources is None:
            src, status = None, "unresolved"
        else:
            src = sources.get(slug)
            status = "ok" if src is not None else "missing"
        name, fr_lien = fr_record(slug) if country == "fr" else (d.get("name") or slug, "")
        others = {k: v for k, v in names_by_country.get(country, {}).items() if k != slug}
        try:
            a = audit_one(d, src, status, name, fr_lien, others)
        except Exception as e:  # noqa: BLE001
            log(f"err {slug}: {e!r}")
            continue
        audits.append(a)
        facts_by_country[country][slug] = d.get("facts") or []
        n_by_lang, rows, en_bullets = audit_translations(slug, d.get("facts") or [])
        translation_caches += len(n_by_lang)
        translated_bullets += sum(n_by_lang.values())
        translation_rows.extend(rows)
        if en_bullets:
            en_by_slug[slug] = en_bullets
        if not args.quiet:
            print_per_aoc(a, verbose=args.verbose)

    shared_groups: list[dict] = []
    for country, by_slug in sorted(facts_by_country.items()):
        shared_groups.extend({"country": country, **g} for g in shared_quote_groups(by_slug))
    shared_groups.sort(key=lambda g: (-g["count"], g["country"], g["quote"]))
    identical_en = identical_en_groups(en_by_slug)

    findings = collect_findings(audits, translation_rows, shared_groups, identical_en)
    summary = summarize(
        audits, findings,
        translation_caches=translation_caches,
        translated_bullets=translated_bullets,
        verbatim_skipped=verbatim_skipped,
        unresolved=resolver.failed,
    )
    summary["elapsed_seconds"] = round(time.monotonic() - t_start, 1)
    print("\n[audit] summary:", file=sys.stderr)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str), file=sys.stderr)

    if args.report:
        report_rows = dict(findings)
        report_rows["cross_record_shared_quotes"] = shared_groups[:SHARED_QUOTE_TOP]
        out = Path(args.report)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "summary": summary,
            "findings": report_rows,
            "aocs": audits,
        }, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        log(f"full report → {args.report}")

    if args.strict and summary["strict_failures"] > 0:
        log(f"STRICT: {summary['strict_failures']} strict finding(s) — exit 1")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
