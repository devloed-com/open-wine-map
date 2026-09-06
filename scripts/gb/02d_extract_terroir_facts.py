"""Extract noteworthy terroir facts for each GB wine using the bounded,
dual-source LLM layer.

Unlike Malta — the other English-source corpus, whose amendment
communications carry no link section — every UK product specification
does carry a real terroir narrative, so GB uses the **standard
cahier-primary** model rather than the Wikipedia-primary CH/MT one:

  - The four DEFRA 2011 specifications open each wine part with the link
    text proper (northerly latitude, long growing season, high diurnal
    range, the resulting acidity), 2.4-2.5 KB per record.
  - Sussex has a full `9. Link` section — soils (South Downs chalk, the
    greensands), climate, human factors — 5.5 KB.
  - Darnibole has no link section, so its terroir narrative is its
    `7 b) Definition of the demarcated area`: the ancient slate subsoil,
    the steep south-facing slope, the thermal band. Stage 02 already
    routes it to `link_to_terroir`.

en.wikipedia.org stays the secondary salience hint, exactly as elsewhere.
Records are **not** skipped when Wikipedia is missing — the regulator
text alone is sufficient grounding, which is the whole point of the
cahier-primary model.

`source_lang` is always "en". EN is the canonical rendered surface, so
the bullets need no translation for `/`; stage 02e only translates them
into fr/es/nl.

The 4-subsection structure + JSON schema match AT/MT exactly so stage 04
renders GB facts through the same code path.

Providers: anthropic / mistral / ollama / manual. Batch via
`--batch --provider anthropic`.
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
from difflib import SequenceMatcher
from pathlib import Path

from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import batch, cache, llm_json, providers, roundtrip, terroir_verbatim  # noqa: E402

EXTRACTED = ROOT / "raw" / "gb" / "specs-extracted"
WIKI_AOCS_ROOT = ROOT / "raw" / "wikipedia" / "aocs"
CACHE_DIR = ROOT / "raw" / "terroir-facts"
MANIFEST = CACHE_DIR / "manifest-gb.json"

SOURCE_LANG = "en"
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
    "facteurs_naturels": "Natural factors (geology, soils, climate, relief)",
    "facteurs_humains": "Historical and human factors (history, practices)",
    "produit": "Product characteristics (sensory profile)",
    "interactions": "Causal interactions (terroir / wine link)",
}


SUBSECTION_TOPICS = {
    "facteurs_naturels": "geology and soils (South Downs and Chiltern chalk, the greensands, Kimmeridgian and Portland limestone, greensand, clay, slate), cool maritime climate, northerly latitude (above 49.9°N) and the long growing season it gives, high diurnal range, sunshine hours and growing degree days, aspect and shelter, rainfall",
    "facteurs_humains": "history of viticulture in England and Wales (Roman and monastic roots, the post-1950s revival, the sparkling-wine expansion), wine education and research (Plumpton College), traditional-method sparkling production, hand harvesting, choice of varieties for a cool climate",
    "produit": "wine colours, aromas, structure, natural acidity, autolytic character of the traditional-method sparkling wines, the character of the still wines",
    "interactions": "explicit link between the British terroir and the character of the wine — how the chalk, the cool maritime climate, the long growing season and the high acidity express themselves in the wine",
}


WIKI_TO_SUBSECTION = {
    "facteurs_naturels": [
        "Geography", "Geology", "Climate", "Soil", "Soils", "Terroir",
        "Wine regions", "Regions", "Viticulture", "Vineyards",
    ],
    "facteurs_humains": [
        "History", "Indigenous grapes", "Grapes", "Grape varieties",
        "Varieties", "Production", "Winemaking", "Wineries",
    ],
    "produit": [
        "Wines", "Styles", "Wine styles", "Types of wine", "Production",
    ],
    "interactions": [],
}
WIKI_TO_SUBSECTION["interactions"] = WIKI_TO_SUBSECTION["facteurs_naturels"]


EXTRACT_SYSTEM = """You extract noteworthy facts about a United Kingdom wine appellation from its product specification (primary source — the "Link with the geographical area" text, the demarcated area and the authorised varieties) and, where present, the English Wikipedia article (secondary source).

Target reader: an informed wine lover or sommelier. Noteworthy: named geological formations (the South Downs chalk, the greensands, slate subsoil), specific soil types, the cool maritime climate and northerly latitude, growing-season length and diurnal range, distinctive viticultural and winemaking practices, precise sensory profile, dated historical anchors.

═══ SOURCE 1: Product specification (user message below) ═══

═══ SOURCE 2: Wikipedia extract (relevant sections, may be empty) ═══
{wiki_hint}

Sub-section handled: {label}
Preferred categories: {topics}

Strict rules:
- Each bullet MUST be backed by AT LEAST ONE quote: `cahier_quote` (verbatim from the product specification) OR `wiki_quote` (verbatim from the Wikipedia extract). Prefer `cahier_quote` — the specification is the regulator source.
- If only Wikipedia mentions a noteworthy fact, keep only `wiki_quote` — it will be attributed to Wikipedia at render time.
- Quotes are VERBATIM (copy-paste) from their source. NEVER attribute to a source text that does not appear in it.
- No value judgements ("exceptional", "prestigious"…).
- No figures absent from both sources.
- At most {max_bullets} bullets, each ≤ 140 characters.
- If neither the specification nor Wikipedia contains a concrete noteworthy fact for this sub-section, return an empty list.

Reply ONLY in JSON, no preamble:
{{"facts": [{{"bullet": "…", "cahier_quote": "…", "wiki_quote": "…"}}, ...]}}
Use an empty string "" for the missing quote."""


USER_LEAD = "Sub-section: {label}\n\nRegulator context:\n\n{ctx}"


# ─────────────────────────────────────────────────────────────── helpers ──


def normalize(s: str) -> str:
    return " ".join((s or "").split()).lower()


def wiki_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fuzzy_coverage(quote: str, source: str) -> float:
    q = normalize(quote)
    s = normalize(source)
    if not q:
        return 0.0
    match = SequenceMatcher(None, q, s, autojunk=False).find_longest_match(
        0, len(q), 0, len(s)
    )
    return match.size / len(q)


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


def _cahier_context(record: dict) -> str:
    """The product specification's own terroir narrative, plus the
    demarcated area and variety roster as supporting context. Bullets
    grounded in this block carry `provenance=cahier`."""
    pieces: list[str] = []
    pieces.append(f"Region: {record.get('region') or ''} ({record.get('kind') or ''})")
    geo = record.get("geo_area_brief") or ""
    if geo:
        pieces.append(f"Demarcated area: {geo}")
    grapes = (record.get("grapes") or {}).get("details") or []
    if grapes:
        names = ", ".join(g.get("name") or g.get("slug") for g in grapes[:40])
        pieces.append(f"Authorised varieties: {names}")
    link = record.get("link_to_terroir") or ""
    if link:
        pieces.append(f"Link with the geographical area:\n{link}")
    return "\n".join(pieces)


def _wiki_record_for(slug: str) -> dict:
    path = WIKI_AOCS_ROOT / SOURCE_LANG / f"{slug}.json"
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
        if rec.get("is_sub_denomination"):
            continue
        # Unlike MT/CH, a missing Wikipedia article is not disqualifying:
        # the specification's own link section is the primary source.
        wiki = _wiki_record_for(rec["slug"])
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
    system = EXTRACT_SYSTEM.format(
        wiki_hint=wiki_hint or "(no Wikipedia extract available)",
        label=label, topics=topic, max_bullets=sub["max_bullets"],
    )
    user = USER_LEAD.format(label=label, ctx=cahier_ctx)
    try:
        raw = provider.chat(system=system, user=user, max_tokens=1500, num_ctx=8192)
    except Exception as e:  # noqa: BLE001
        return [], 0, str(e)
    payload, perr = llm_json.parse_facts(raw)
    if payload is None:
        return [], 0, perr or "no JSON in response"
    kept, dropped = _ground_facts(payload.get("facts") or [], cahier_ctx, wiki_hint)
    return kept, dropped, ""


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

    payload = {
        "country": "gb",
        "source_lang": SOURCE_LANG,
        "slug": slug,
        "name": record.get("name") or slug,
        "facts": all_facts,
        "n_dropped": n_dropped_total,
        "model": model_id,
        "model_kind": provider.kind,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cahier_source_sha": wiki_sha(cahier_ctx),
        "cahier_source_pdf_url": (record.get("source") or {}).get("source_url", ""),
        "cahier_source_kind": "gov-uk-product-specification",
        "wiki_source_revision": wiki.get("revision"),
        "wiki_source_url": wiki.get("page_url"),
        "subsection_errors": sub_errors,
    }
    cache.write_json(CACHE_DIR / f"{slug}.json", payload)
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
    if existing.get("country") != "gb":
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
                "lang": SOURCE_LANG,
                "subsection": sub["key"],
                "subsection_label": label,
                "max_bullets": sub["max_bullets"],
                "system_prompt": EXTRACT_SYSTEM.format(
                    wiki_hint=wiki_hint or "(no Wikipedia extract)",
                    label=label, topics=SUBSECTION_TOPICS[sub["key"]],
                    max_bullets=sub["max_bullets"],
                ),
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
    print(f"[02d/gb] wrote {out_path} ({len(items)} items across "
          f"{len({i['slug'] for i in items})} wines)", file=sys.stderr)
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
        cache.write_json(CACHE_DIR / f"{slug}.json", {
            "country": "gb", "source_lang": SOURCE_LANG, "slug": slug,
            "name": rec.get("name") or slug, "facts": facts,
            "model": translator_id, "model_kind": translator_kind,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "cahier_source_sha": wiki_sha(cahier_ctx),
            "cahier_source_pdf_url": (rec.get("source") or {}).get("source_url", ""),
            "cahier_source_kind": "gov-uk-product-specification",
            "wiki_source_revision": wiki.get("revision"),
            "wiki_source_url": wiki.get("page_url"),
        })
        counts["wrote"] += 1
    print(f"[02d/gb] wrote {counts['wrote']} cache files; "
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
                    help="submit all wines to the provider Batch API")
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
    model_id = args.model or batch.default_model(args.provider)
    targets = collect_targets()
    if args.only:
        needles = [s.lower() for s in args.only]
        targets = [r for r in targets if any(n in r["slug"].lower() for n in needles)]
    if args.limit:
        targets = targets[: args.limit]
    targets = [r for r in targets if args.refresh or not _is_cache_valid(r)]
    if not targets:
        print("[02d/gb] batch: nothing to do.", file=sys.stderr)
        return 0
    print(f"[02d/gb] batch: {len(targets)} wines (provider={args.provider}, "
          f"model={model_id})", file=sys.stderr)

    def run_loop(prov):
        global CACHE_DIR
        if getattr(prov, "kind", "") == "collecting":
            keep = CACHE_DIR
            CACHE_DIR = Path(tempfile.mkdtemp(prefix="batch-02d-gb-"))
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
        sidecar=ROOT / "raw" / ".batch" / "02d-gb.json",
        run_loop=run_loop,
    )
    return 0


def main() -> int:
    args = _build_argparser().parse_args()
    if not EXTRACTED.exists():
        print(f"error: {EXTRACTED} missing — run scripts/gb/02_extract_specs.py first",
              file=sys.stderr)
        return 1

    sub_rc = _dispatch_emit_or_import(args)
    if sub_rc is not None:
        return sub_rc

    terroir_verbatim.emit_for_country(
        country="gb", extracted_dir=EXTRACTED, cache_dir=CACHE_DIR,
        default_source_lang=SOURCE_LANG, cahier_source_kind="gov-uk-product-specification",
        only=args.only, log_prefix="[02d/gb]",
    )

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
        print("[02d/gb] nothing to do — all caches valid.", file=sys.stderr)
        return 0

    provider, model_id = providers.make_provider(
        args.provider, model=args.model, ollama_url=args.ollama_url,
        mistral_url=args.mistral_url,
    )
    if provider is None:
        print(f"[02d/gb] manual provider: {len(targets)} wines need extraction.",
              file=sys.stderr)
        return 1

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[02d/gb] {len(targets)} MT wines to extract "
          f"(provider={args.provider}, model={model_id}, workers={args.workers})",
          file=sys.stderr)

    workers = max(1, args.workers)
    n_done = n_facts = 0
    t0 = time.time()
    if workers <= 1:
        for rec in tqdm(targets, desc="terroir-gb", leave=False):
            res = _process_record(provider, model_id, rec)
            n_done += 1
            n_facts += len(res.get("facts", []))
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(_process_record, provider, model_id, r): r for r in targets}
            for fut in tqdm(as_completed(futures), total=len(targets), desc="terroir-gb", leave=False):
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
    print(f"[02d/gb] done: {n_done} wines, {n_facts} facts, {elapsed/60:.1f} min",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
