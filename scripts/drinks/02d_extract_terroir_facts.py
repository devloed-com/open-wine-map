#!/usr/bin/env python3
"""Stage 02d of the drinks pipeline: terroir facts of the spirit drinks,
aromatised wines and ciders (raw/drinks/extracted/).

The sibling of the per-country 02d scripts, with three differences:

- **One script, every language.** The drinks records are written in fourteen
  languages (each record's `source_lang`), so the instructions are English
  and name the language the bullets must be written in — the document's own.
  The grounding quotes are verbatim in that language, the connective test of
  the interactions sub-section and the second-reading vocabulary are the
  record's language's.
- **The technical file is the source.** A drink's file describes the product
  and its method at length and its link briefly, so the grounding text is
  the area, the description, the method and the link together
  (`_cahier_context`; description and method capped). Wikipedia is read only
  when an article is cached for the slug in the record's language
  (raw/wikipedia/aocs/<lang>/), which no drinks record has yet.
- **`country: "drinks"` in the cache.** A facts cache names the stage that
  owns its source text (`_lib/terroir_sources`: the gate, the audits and the
  provenance pass load that stage's module); the record's own country rides
  `record_country`.

Same four sub-sections, caps, grounding filter (≥ 0.6), dedupe, earned
interactions, feedback block, snapshot-on-write and batch flow as every
other 02d.

    .venv/bin/python scripts/drinks/02d_extract_terroir_facts.py --batch --provider anthropic [--only SLUG]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import batch, cache, llm_json, providers, roundtrip  # noqa: E402
from _lib.prompt_cache import cached_system, split_user_lead  # noqa: E402
from _lib.terroir_cache import write_source_cache  # noqa: E402
from _lib.terroir_coverage import fuzzy_coverage  # noqa: E402
from _lib.terroir_dedupe import dedupe_facts  # noqa: E402
from _lib.terroir_feedback import with_feedback  # noqa: E402
from _lib.terroir_interactions import earn_interactions  # noqa: E402
from _lib.terroir_normalize import normalize_facts  # noqa: E402
from _lib.terroir_prompts import (
    ask_line,
    should_retry,
    sub_section_cap,
    with_style_rules,
)

EXTRACTED = ROOT / "raw" / "drinks" / "extracted"
WIKI_AOCS_ROOT = ROOT / "raw" / "wikipedia" / "aocs"
CACHE_DIR = ROOT / "raw" / "terroir-facts"
MANIFEST = CACHE_DIR / "manifest-drinks.json"

SOURCE_LANG = "en"  # the default; each record carries its own `source_lang`
DESCRIPTION_CAP = 8000
METHOD_CAP = 12000

LANGUAGE_NAME = {
    "bg": "Bulgarian", "cs": "Czech", "de": "German", "el": "Greek", "en": "English",
    "es": "Spanish", "fr": "French", "hr": "Croatian", "hu": "Hungarian", "it": "Italian",
    "nl": "Dutch", "pt": "Portuguese", "ro": "Romanian", "sk": "Slovak", "sl": "Slovenian",
}
CLASS_NOUN = {"spirit": "spirit drink", "aromatised-wine": "aromatised wine", "cider": "cider or perry"}
MIN_WIKI_CHARS = 400
FUZZY_THRESHOLD = 0.6
WIKI_HINT_CHAR_CAP = 2800


SUBSECTIONS = [
    {"key": "facteurs_naturels", "max_bullets": 5},
    {"key": "facteurs_humains", "max_bullets": 2},
    {"key": "produit", "max_bullets": 2},
    {"key": "interactions", "max_bullets": 1},
]


SUBSECTION_LABELS = {
    "facteurs_naturels": "Natural factors and raw materials (the area, its climate and water, what is distilled or pressed and where it grows)",
    "facteurs_humains": "Historical and human factors (history of the drink in the area, know-how, method)",
    "produit": "Product characteristics (strength, appearance, aroma and taste, categories)",
    "interactions": "Causal interactions (the link between the area and the drink)",
}


SUBSECTION_TOPICS = {
    "facteurs_naturels": "the raw material and where it grows (fruit, grain, grapes and their varieties, herbs, juniper, sugar cane), the climate, relief and soils of the area where the text ties them to the raw material, the water used, the conditions of ageing (cellar climate, altitude, sea air)",
    "facteurs_humains": "dated history of the drink in the area (first written mentions, decrees, guilds, founding distilleries, fairs and awards), the method and the know-how the text describes (pot or column stills, number of distillations, maceration, cask types and minimum ageing, reduction, bottling in the area)",
    "produit": "the drink's alcoholic strength, colour and clarity, aroma and taste, sugar content, the categories, age statements or variants the text defines, what sets it apart from other drinks of its category",
    "interactions": "an explicit causal link the text states between the area (its climate, water, raw material or know-how) and the character or the reputation of the drink",
}


# No heading table: a drink's article, where one is cached, is read by its
# opening (the hint is the intro, capped).
WIKI_TO_SUBSECTION: dict[str, list[str]] = {k["key"]: [] for k in SUBSECTIONS}


EXTRACT_SYSTEM = """You extract noteworthy facts about {name}, a {class_noun} with a protected geographical indication, from its technical file or product specification (primary source — the geographical area, the description, the method and the link with the area) and, where present, a Wikipedia extract (secondary source).

The document is written in {language}. Write every bullet in {language}; quotes stay verbatim in the language of their source.

Target reader: an informed drinks enthusiast or sommelier. Noteworthy: the raw material and where it comes from, named places, dated historical anchors, the stills, casks and ageing the method requires, figures the text gives (strengths, years, quantities), the precise sensory profile, what the text says ties the drink to its area.

═══ SOURCE 1: Technical file / product specification (given at the very start of this prompt, before these instructions) ═══

═══ SOURCE 2: Wikipedia extract (relevant sections, may be empty) ═══
{wiki_hint}

Sub-section handled: {label}
Preferred categories: {topics}

Strict rules:
- Each bullet MUST be backed by AT LEAST ONE quote: `cahier_quote` (verbatim from the technical file) OR `wiki_quote` (verbatim from the Wikipedia extract). Prefer `cahier_quote` — the file is the regulator source.
- If only Wikipedia mentions a noteworthy fact, keep only `wiki_quote` — it will be attributed to Wikipedia at render time.
- Quotes are VERBATIM (copy-paste) from their source. NEVER attribute to a source text that does not appear in it.
- No value judgements ("exceptional", "prestigious"…).
- No figures absent from both sources.
- At most {max_bullets} bullets; each bullet is one full sentence of roughly 120–220 characters — never a telegraphic fragment.
- If neither the file nor Wikipedia contains a concrete noteworthy fact for this sub-section, return an empty list.

Reply ONLY in JSON, no preamble:
{{"facts": [{{"bullet": "…", "cahier_quote": "…", "wiki_quote": "…"}}, ...]}}
Use an empty string "" for the missing quote."""
EXTRACT_SYSTEM = with_style_rules(EXTRACT_SYSTEM)


USER_LEAD = "Sub-section: {label}\n\nRegulator context:\n\n{ctx}"


# ─────────────────────────────────────────────────────────────── helpers ──


def wiki_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _find_heading(full: str, heading: str) -> int:
    idx = full.find(f"\n\n{heading}\n\n")
    if idx == -1:
        idx = full.find(f"\n{heading}\n")
    return idx


def _index_wiki_sections(full: str, headings: list[str]) -> dict[str, str]:
    positions = sorted(
        (idx, h) for h in headings if (idx := _find_heading(full, h)) != -1
    )
    section_text: dict[str, str] = {}
    intro_end = positions[0][0] if positions else len(full)
    section_text["__intro__"] = full[:intro_end].strip()
    for i, (start, h) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(full)
        section_text[h] = full[start:end].strip()
    return section_text


def _wiki_hint_for_subsection(
    wiki_record: dict, sub_key: str, char_cap: int = WIKI_HINT_CHAR_CAP,
) -> str:
    if not wiki_record or wiki_record.get("missing") or wiki_record.get("error"):
        return ""
    full = wiki_record.get("full_text") or ""
    if not full:
        return (wiki_record.get("lead_extract") or wiki_record.get("extract", ""))[:char_cap]
    headings = WIKI_TO_SUBSECTION.get(sub_key, [])
    sections = _index_wiki_sections(full, headings)
    pieces = [sections["__intro__"]] if sections.get("__intro__") else []
    for h in headings:
        if h in sections:
            pieces.append(f"# {h}\n{sections[h]}")
    blob = "\n\n".join(pieces).strip()
    return (blob[:char_cap]
            if blob
            else (wiki_record.get("lead_extract") or wiki_record.get("extract", ""))[:char_cap])


def _ground_facts(
    raw_facts: list[dict], cahier_ctx: str, wiki_hint: str,
) -> tuple[list[dict], int]:
    kept: list[dict] = []
    dropped = 0
    for f in raw_facts:
        bullet = (f.get("bullet") or "").strip()
        cq = (f.get("cahier_quote") or "").strip()
        wq = (f.get("wiki_quote") or "").strip()
        if not bullet:
            dropped += 1
            continue
        cc = fuzzy_coverage(cq, cahier_ctx) if cq else 0.0
        wc = fuzzy_coverage(wq, wiki_hint) if wq else 0.0
        c_ok = cc >= FUZZY_THRESHOLD
        w_ok = wc >= FUZZY_THRESHOLD
        if not (c_ok or w_ok):
            dropped += 1
            continue
        if c_ok and w_ok:
            provenance = "both"
        elif c_ok:
            provenance = "cahier"
        else:
            provenance = "wiki"
        kept.append({
            **f,
            "cahier_coverage": round(cc, 3),
            "wiki_coverage": round(wc, 3),
            "provenance": provenance,
        })
    return kept, dropped


# ─────────────────────────────────────────────── source-text + targets ──


def _lang(record: dict) -> str:
    lang = record.get("source_lang") or SOURCE_LANG
    return lang if lang in LANGUAGE_NAME else SOURCE_LANG


def _cahier_context(record: dict) -> str:
    """The grounding text of a drink: its category, area, description, method
    and link, as stage 02 read them. Bullets grounded in this block carry
    `provenance=cahier`."""
    roles = record.get("section_roles") or {}
    pieces: list[str] = [
        f"Name: {record.get('registered_name') or record.get('name') or ''}",
        f"Category: {record.get('register_category') or record.get('drink_category') or ''}",
    ]
    geo = (record.get("geo_area_brief") or "").strip()
    if geo:
        pieces.append(f"Geographical area:\n{geo}")
    description = (roles.get("description") or "").strip()
    if description:
        pieces.append(f"Description:\n{description[:DESCRIPTION_CAP]}")
    method = (roles.get("method") or "").strip()
    if method:
        pieces.append(f"Method:\n{method[:METHOD_CAP]}")
    link = (record.get("link_to_terroir") or "").strip()
    if link:
        pieces.append(f"Link with the geographical area:\n{link}")
    return "\n\n".join(pieces)


def _wiki_record_for(slug: str, lang: str = SOURCE_LANG) -> dict:
    path = WIKI_AOCS_ROOT / lang / f"{slug}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def _has_usable_wiki(rec: dict) -> bool:
    if not rec or rec.get("missing") or rec.get("error"):
        return False
    full = rec.get("full_text") or ""
    if len(full) >= MIN_WIKI_CHARS:
        return True
    extract = rec.get("lead_extract") or rec.get("extract", "")
    return len(extract) >= MIN_WIKI_CHARS


def collect_targets() -> list[dict]:
    out: list[dict] = []
    for jp in sorted(EXTRACTED.glob("*.json")):
        if jp.name.startswith("_"):
            continue
        rec = json.loads(jp.read_text(encoding="utf-8"))
        if rec.get("is_sub_denomination") or rec.get("stub"):
            continue
        rec["source_lang"] = _lang(rec)
        # the technical file is the primary source: no Wikipedia article is
        # needed, and one is read only when cached in the record's language
        wiki = _wiki_record_for(rec["slug"], rec["source_lang"])
        if not _has_usable_wiki(wiki):
            wiki = {}
        rec["_wiki_record"] = wiki
        rec["_cahier_ctx"] = _cahier_context(rec)
        out.append(rec)
    return out


# ─────────────────────────────────────────────────────────────── core loop ──


def _process_subsection(provider, model_id: str, record: dict, sub: dict):
    label = SUBSECTION_LABELS[sub["key"]]
    topic = SUBSECTION_TOPICS[sub["key"]]
    wiki = record.get("_wiki_record") or {}
    cahier_ctx = record.get("_cahier_ctx") or ""
    wiki_hint = _wiki_hint_for_subsection(wiki, sub["key"])
    lang = _lang(record)
    system = EXTRACT_SYSTEM.format(
        name=record.get("name") or record["slug"],
        class_noun=CLASS_NOUN.get(record.get("product_class") or "", "drink"),
        language=LANGUAGE_NAME[lang],
        wiki_hint=wiki_hint or "(no Wikipedia extract available)",
        label=label, topics=topic, max_bullets=sub_section_cap(sub, cahier_ctx),
    )
    system = with_feedback(system, record["slug"])
    # The regulator text is the cached leading block: the four sub-section calls share it.
    _, doc = split_user_lead(USER_LEAD, label=label, ctx=cahier_ctx)
    user = ask_line("en", label)
    system = cached_system(doc, system, phased=True)
    try:
        raw = provider.chat(system=system, user=user, max_tokens=1500, num_ctx=8192,
                            cache_phase=sub["key"])
    except Exception as e:  # noqa: BLE001
        return [], 0, str(e)
    payload, perr = llm_json.parse_facts(raw)
    if payload is None:
        return [], 0, perr or "no JSON in response"
    raw_facts = payload.get("facts") or []
    if not raw_facts and should_retry(sub["key"], lang, f"{cahier_ctx}\n{wiki_hint}"):
        # an empty descriptive sub-section on a text that carries its vocabulary: one second
        # reading (terroir_prompts); the first answer stands when the retry yields nothing
        retried = record.setdefault("_retried", [])
        if sub["key"] not in retried:
            retried.append(sub["key"])
        try:
            raw = provider.chat(system=system, user=ask_line("en", label, retry=True),
                                max_tokens=1500, num_ctx=8192, cache_phase=sub["key"], follow_up=True)
        except Exception:  # noqa: BLE001
            raw = ""
        second, _ = llm_json.parse_facts(raw)
        raw_facts = (second or {}).get("facts") or []
    kept, dropped = _ground_facts(raw_facts, cahier_ctx, wiki_hint)
    return kept, dropped, ""


def _source_url(record: dict) -> str:
    src = record.get("source") or {}
    return (src.get("attachment_url") or src.get("final_url") or src.get("source_url")
            or (src.get("national_spec") or {}).get("url") or "")


def _process_record(provider, model_id: str, record: dict) -> dict:
    slug = record["slug"]
    wiki = record.get("_wiki_record") or {}
    cahier_ctx = record.get("_cahier_ctx") or ""

    all_facts: list[dict] = []
    n_dropped_total = 0
    sub_errors: list[tuple[str, str]] = []
    for sub in SUBSECTIONS:
        kept, dropped, err = _process_subsection(provider, model_id, record, sub)
        n_dropped_total += dropped
        if err:
            sub_errors.append((sub["key"], err))
            continue
        for f in kept:
            f["subsection"] = sub["key"]
            all_facts.append(f)

    deduped = dedupe_facts(all_facts)
    all_facts = deduped.kept
    earned = earn_interactions(all_facts, _lang(record))
    all_facts = earned.kept
    normalize_facts(all_facts)

    payload = {
        # the stage that owns the source text (`_lib/terroir_sources`); the
        # record's own country beside it
        "country": "drinks",
        "record_country": record.get("country") or "",
        "source_lang": _lang(record),
        "slug": slug,
        "name": record.get("name") or slug,
        "facts": all_facts,
        "n_dropped": n_dropped_total,
        "n_deduped": len(deduped.drops),
        "n_unearned_interactions": len(earned.dropped),
        "model": model_id,
        "model_kind": provider.kind,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cahier_source_sha": wiki_sha(cahier_ctx),
        "cahier_source_pdf_url": _source_url(record),
        "cahier_source_kind": (record.get("source") or {}).get("kind", ""),
        "wiki_source_revision": wiki.get("revision"),
        "wiki_source_url": wiki.get("page_url"),
        "subsection_errors": sub_errors,
        **({"retried_subsections": list(record["_retried"])} if record.get("_retried") else {}),
    }
    write_source_cache(CACHE_DIR / f"{slug}.json", payload)
    return payload


def _is_cache_valid(record: dict) -> bool:
    slug = record["slug"]
    p = CACHE_DIR / f"{slug}.json"
    if not p.exists():
        return False
    try:
        existing = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return False
    if existing.get("country") != "drinks":
        return False
    if existing.get("cahier_source_sha") != wiki_sha(record.get("_cahier_ctx") or ""):
        return False
    wiki = record.get("_wiki_record") or {}
    if existing.get("wiki_source_revision") != wiki.get("revision"):
        return False
    return True


# ─────────────────────────────────────────────────────── round-trip flow ──


def emit_todo(out_path: Path, *, skip_cached: bool, limit: int = 0) -> int:
    items: list[dict] = []
    n_records_emitted = 0
    for rec in collect_targets():
        if skip_cached and _is_cache_valid(rec):
            continue
        if limit and n_records_emitted >= limit:
            break
        n_records_emitted += 1
        for sub in SUBSECTIONS:
            wiki_hint = _wiki_hint_for_subsection(rec.get("_wiki_record") or {}, sub["key"])
            label = SUBSECTION_LABELS[sub["key"]]
            items.append({
                "slug": rec["slug"],
                "lang": _lang(rec),
                "subsection": sub["key"],
                "subsection_label": label,
                "max_bullets": sub_section_cap(sub, rec.get("_cahier_ctx") or ""),
                "system_prompt": with_feedback(EXTRACT_SYSTEM.format(
                    name=rec.get("name") or rec["slug"],
                    class_noun=CLASS_NOUN.get(rec.get("product_class") or "", "drink"),
                    language=LANGUAGE_NAME[_lang(rec)],
                    wiki_hint=wiki_hint or "(no Wikipedia extract)",
                    label=label, topics=SUBSECTION_TOPICS[sub["key"]],
                    max_bullets=sub_section_cap(sub, rec.get("_cahier_ctx") or ""),
                ), rec["slug"]),
                "cahier_ctx": rec.get("_cahier_ctx") or "",
                "wiki_hint": wiki_hint,
                "cahier_source_sha": wiki_sha(rec.get("_cahier_ctx") or ""),
                "wiki_source_revision": (rec.get("_wiki_record") or {}).get("revision"),
                "facts": [],
            })
    cache.write_json(out_path, {
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_items": len(items),
        "items": items,
    })
    print(f"[02d/drinks] wrote {out_path} ({len(items)} items across "
          f"{len({i['slug'] for i in items})} drinks)", file=sys.stderr)
    return 0


def import_todo(in_path: Path, *, translator_id: str, translator_kind: str) -> int:
    if not in_path.exists():
        print(f"error: {in_path} does not exist.", file=sys.stderr)
        return 1
    payload = json.loads(in_path.read_text(encoding="utf-8"))
    by_slug: dict[str, list[dict]] = {}
    for it in payload.get("items") or []:
        by_slug.setdefault(it["slug"], []).append(it)
    record_index = {r["slug"]: r for r in collect_targets()}
    counts = {"wrote": 0, "sha_mismatch": 0, "unknown_slug": 0}
    for slug, slug_items in by_slug.items():
        rec = record_index.get(slug)
        if rec is None:
            counts["unknown_slug"] += 1
            continue
        cahier_ctx = rec.get("_cahier_ctx") or ""
        first = slug_items[0]
        if first.get("cahier_source_sha") and first["cahier_source_sha"] != wiki_sha(cahier_ctx):
            counts["sha_mismatch"] += 1
            continue
        facts: list[dict] = []
        for it in slug_items:
            kept, _ = _ground_facts(it.get("facts") or [], cahier_ctx, it.get("wiki_hint") or "")
            for f in kept:
                f["subsection"] = it.get("subsection") or "facteurs_naturels"
                facts.append(f)
        wiki = rec.get("_wiki_record") or {}
        write_source_cache(CACHE_DIR / f"{slug}.json", {
            "country": "drinks", "record_country": rec.get("country") or "",
            "source_lang": _lang(rec), "slug": slug,
            "name": rec.get("name") or slug, "facts": facts,
            "model": translator_id, "model_kind": translator_kind,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "cahier_source_sha": wiki_sha(cahier_ctx),
            "cahier_source_pdf_url": _source_url(rec),
            "cahier_source_kind": (rec.get("source") or {}).get("kind", ""),
            "wiki_source_revision": wiki.get("revision"),
            "wiki_source_url": wiki.get("page_url"),
        })
        counts["wrote"] += 1
    print(f"[02d/drinks] wrote {counts['wrote']} cache files; "
          f"skipped sha_mismatch={counts['sha_mismatch']}, "
          f"unknown_slug={counts['unknown_slug']}", file=sys.stderr)
    return 0


# ─────────────────────────────────────────────────────────────────  main ──


def _build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--provider", default="ollama",
                    choices=("anthropic", "mistral", "ollama", "manual"))
    ap.add_argument("--model", default=None)
    ap.add_argument("--ollama-url", default=providers.DEFAULT_OLLAMA_URL)
    ap.add_argument("--mistral-url", default=providers.DEFAULT_MISTRAL_URL)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--batch", action="store_true",
                    help="submit all drinks to the provider Batch API")
    roundtrip.add_arguments(ap)
    return ap


def _dispatch_emit_or_import(args) -> int | None:
    rc = roundtrip.validate_emit_import(args)
    if rc is not None:
        return rc
    if args.emit_todo:
        return emit_todo(Path(args.emit_todo), skip_cached=not args.all, limit=args.limit)
    if args.import_path:
        return import_todo(Path(args.import_path),
                           translator_id=args.translator_id,
                           translator_kind=args.translator_kind)
    return None


def _run_batch(args) -> int:
    if not batch.supports(args.provider):
        print("error: --batch requires --provider anthropic|mistral", file=sys.stderr)
        return 1
    model_id = args.model or batch.default_model(args.provider, stage="02d")
    targets = collect_targets()
    if args.only:
        needles = [s.lower() for s in args.only]
        targets = [r for r in targets if any(n in r["slug"].lower() for n in needles)]
    if args.limit:
        targets = targets[: args.limit]
    targets = [r for r in targets if args.refresh or not _is_cache_valid(r)]
    if not targets:
        print("[02d/drinks] batch: nothing to do.", file=sys.stderr)
        return 0
    print(f"[02d/drinks] batch: {len(targets)} drinks (provider={args.provider}, "
          f"model={model_id})", file=sys.stderr)

    def run_loop(prov):
        global CACHE_DIR
        if getattr(prov, "kind", "") == "collecting":
            keep = CACHE_DIR
            CACHE_DIR = Path(tempfile.mkdtemp(prefix="batch-02d-drinks-"))
            try:
                for rec in targets:
                    _process_record(prov, model_id, rec)
            finally:
                shutil.rmtree(CACHE_DIR, ignore_errors=True)
                CACHE_DIR = keep
        else:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            for rec in targets:
                _process_record(prov, model_id, rec)

    batch.run_two_pass(
        provider=args.provider, model=model_id,
        sidecar=ROOT / "raw" / ".batch" / "02d-drinks.json",
        run_loop=run_loop, thinking=batch.default_thinking(args.provider, stage="02d"),
        follow_ups=True,
    )
    return 0


def main() -> int:
    args = _build_argparser().parse_args()
    if not EXTRACTED.exists():
        print(f"error: {EXTRACTED} missing — run scripts/drinks/02_extract_technical_files.py first",
              file=sys.stderr)
        return 1

    sub_rc = _dispatch_emit_or_import(args)
    if sub_rc is not None:
        return sub_rc

    if args.batch:
        return _run_batch(args)

    targets = collect_targets()
    if args.only:
        needles = [s.lower() for s in args.only]
        targets = [r for r in targets if any(n in r["slug"].lower() for n in needles)]
    if args.limit:
        targets = targets[: args.limit]
    if not args.refresh:
        targets = [r for r in targets if not _is_cache_valid(r)]
    if not targets:
        print("[02d/drinks] nothing to do — all caches valid.", file=sys.stderr)
        return 0

    provider, model_id = providers.make_provider(
        args.provider, model=args.model, stage="02d", ollama_url=args.ollama_url,
        mistral_url=args.mistral_url,
    )
    if provider is None:
        print(f"[02d/drinks] manual provider: {len(targets)} drinks need extraction.",
              file=sys.stderr)
        return 1

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[02d/drinks] {len(targets)} drinks to extract "
          f"(provider={args.provider}, model={model_id}, workers={args.workers})",
          file=sys.stderr)

    workers = max(1, args.workers)
    n_done = n_facts = 0
    t0 = time.time()
    if workers <= 1:
        for rec in tqdm(targets, desc="terroir-drinks", leave=False):
            res = _process_record(provider, model_id, rec)
            n_done += 1
            n_facts += len(res.get("facts", []))
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(_process_record, provider, model_id, r): r for r in targets}
            for fut in tqdm(as_completed(futures), total=len(targets), desc="terroir-drinks", leave=False):
                try:
                    res = fut.result()
                    n_done += 1
                    n_facts += len(res.get("facts", []))
                except Exception as e:  # noqa: BLE001
                    print(f"  worker exception: {e}", file=sys.stderr)

    elapsed = time.time() - t0
    MANIFEST.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": args.provider, "model": model_id,
        "n_wines_processed": n_done, "n_facts_total": n_facts,
        "elapsed_seconds": int(elapsed),
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(f"[02d/drinks] done: {n_done} drinks, {n_facts} facts, {elapsed/60:.1f} min",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
