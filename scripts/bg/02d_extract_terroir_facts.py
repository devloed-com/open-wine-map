"""Extract noteworthy terroir facts from each BG wine's "Описание на
връзката" (ЕДИНЕН ДОКУМЕНТ link section) using a bounded LLM layer with
dual-source grounding.

BG analog of `scripts/ro/02d_extract_terroir_facts.py`. Same per-bullet
provenance, fuzzy-grounding, and cache-invalidation rules; the
differences are:

  - source = BG record's `link_to_terroir` (ЕДИНЕН ДОКУМЕНТ link section
    from EUR-Lex; Bulgaria has no national-spec parser branch in v1).
  - Wikipedia hint = `raw/wikipedia/aocs/bg/<slug>.json` (fetched by
    `scripts/02b_fetch_aoc_lexicon.py --lang bg --source raw/bg/dokumenti-extracted`).
  - LLM prompt is in Bulgarian and asks for Bulgarian bullets.
  - Output cache = `raw/terroir-facts/<slug>.json` (single shared dir;
    `country: "bg"` distinguishes from FR/ES/PT/IT/AT/SI/HR/RO records).

In v1 only ~3 of 54 wines have a non-stub ЕДИНЕН ДОКУМЕНТ (~51 are
Art.107 grandfathered stubs awaiting curator input).

Providers: anthropic / mistral / ollama / manual (mirrors RO 02d).
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

from _lib import batch, cache, llm_json, providers, roundtrip  # noqa: E402

EXTRACTED = ROOT / "raw" / "bg" / "dokumenti-extracted"
WIKI_AOCS = ROOT / "raw" / "wikipedia" / "aocs" / "bg"
CACHE_DIR = ROOT / "raw" / "terroir-facts"
MANIFEST = CACHE_DIR / "manifest-bg.json"

MIN_LIEN_CHARS = 400
FUZZY_THRESHOLD = 0.6
WIKI_HINT_CHAR_CAP = 1500


# Same 4-bucket structure as FR/ES/PT/IT/AT/SI/HR/RO 02d, with Bulgarian
# topic vocabulary matched to the ЕДИНЕН ДОКУМЕНТ "Описание на връзката"
# content pattern.
SUBSECTIONS = [
    {
        "key": "facteurs_naturels",  # FR key kept for stage-04 render parity
        "label": "Природни фактори (геология, почви, климат, релеф)",
        "topics": (
            "геология, почвен състав, климат, релеф, води, "
            "изложение, местоположения и населени места"
        ),
        "max_bullets": 5,
    },
    {
        "key": "facteurs_humains",
        "label": "Исторически и човешки фактори (история, практики)",
        "topics": (
            "история на наименованието за произход, лозарски и винарски "
            "практики, традиционни сортове грозде"
        ),
        "max_bullets": 2,
    },
    {
        "key": "produit",
        "label": "Характеристики на продукта (сензорен профил)",
        "topics": "цветове, аромати, структура, отлежаване, сензорен профил на вината",
        "max_bullets": 2,
    },
    {
        "key": "interactions",
        "label": "Причинно-следствени връзки (връзка терруар / вино)",
        "topics": (
            "ясна връзка между терруара и характера на вината, "
            "израз на почвата или климата във виното"
        ),
        "max_bullets": 1,
    },
]


# Bulgarian Wikipedia section headings that map to each ЕДИНЕН ДОКУМЕНТ
# sub-section. Bulgarian wine-region articles use a wide range of
# headings; the list is permissive.
WIKI_TO_SUBSECTION: dict[str, list[str]] = {
    "facteurs_naturels": [
        "География", "Местоположение", "Геология", "Почви", "Почва", "Климат",
        "Релеф", "Лозя", "Лозарство", "Природа", "Природни условия", "Терен",
    ],
    "facteurs_humains": [
        "История", "Етимология", "Наименование", "Сортове", "Сортове грозде",
        "Лозарство", "Винарство", "Винопроизводство", "Традиция",
        "Винарска култура",
    ],
    "produit": [
        "Вина", "Вино", "Типове вина", "Характеристики", "Сензорен профил",
    ],
    "interactions": [],
}
WIKI_TO_SUBSECTION["interactions"] = WIKI_TO_SUBSECTION["facteurs_naturels"]


EXTRACT_SYSTEM = """Извлечи забележителни характеристики на едно българско вино със защитено наименование за произход от ДВА източника: единния документ / продуктовата спецификация (регулаторен авторитет) и извлечението от българската Wikipedia (общодостъпен справочник, сомелиерски речник).

Целеви читател: ценители на вино или сомелиери с опит, заинтересовани от конкретните особености на произхода. Заслужава да се отбележи: геоложки формации с техническото им наименование, специфични типове почви (чернозем, канелена горска почва, смолница, песъчливо-чакълеста, льос, мергел, варовик, пясъчник), местен климат и ветрове (умереноконтинентален, преходноконтинентален, средиземноморско влияние, понтийско влияние, фьон, бора, бургазлия), традиционни сортове грозде, характерни лозарски практики, точен сензорен профил, датирани исторически моменти.

═══ ИЗТОЧНИК 1: извлечение от Wikipedia (релевантни секции) ═══
{wiki_hint}

═══ ИЗТОЧНИК 2: текст на единния документ (в потребителското съобщение по-долу) ═══

Подсекция за обработка: {label}
Приоритетни категории: {topics}

Строги правила:
- Всеки елемент ТРЯБВА да е подкрепен от ПОНЕ ЕДИН цитат: `cahier_quote` (буквален от единния документ) ИЛИ `wiki_quote` (буквален от извлечението от Wikipedia по-горе). И двата са силно препоръчителни, когато и двата източника описват една и съща информация.
- Приоритизирай единния документ като основен източник: използвай `cahier_quote` винаги когато фактът се появява там.
- Добави `wiki_quote`, когато Wikipedia предоставя стандартния технически речник за факт, който единният документ описва с други думи.
- Ако забележителен факт е споменат само в Wikipedia, можеш да го запазиш само с `wiki_quote` — при показване ще бъде приписан на Wikipedia.
- Цитатите са БУКВАЛНИ (копирани) от съответния източник. НИКОГА не приписвай на даден източник текст, който не се появява там.
- Без оценъчни преценки ("изключителен", "престижен" …).
- Без външни заключения. Без числа, които не се появяват в нито един от двата източника.
- Максимум {max_bullets} елемента, всеки ≤ 140 символа.
- Ако нито единният документ, нито Wikipedia съдържат конкретен факт, заслужаващ внимание за тази подсекция, върни празен списък.

Отговори САМО в JSON, без текст преди или след:
{{"facts": [{{"bullet": "...", "cahier_quote": "...", "wiki_quote": "..."}}, ...]}}
За липсващ цитат използвай празен низ ""."""


# ─────────────────────────────────────────────────────────────── helpers ──


def normalize(s: str) -> str:
    return " ".join((s or "").split()).lower()


def cahier_sha(text: str) -> str:
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
        return wiki_record.get("lead_extract", "")[:char_cap]
    sections = _index_wiki_sections(full, WIKI_TO_SUBSECTION.get(sub_key, []))
    pieces = [sections["__intro__"]] if sections.get("__intro__") else []
    for h in WIKI_TO_SUBSECTION.get(sub_key, []):
        if h in sections:
            pieces.append(f"# {h}\n{sections[h]}")
    blob = "\n\n".join(pieces).strip()
    return blob[:char_cap] if blob else (wiki_record.get("lead_extract", "")[:char_cap])


def _ground_facts(
    raw_facts: list[dict], lien_text: str, wiki_hint: str,
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
        cc = fuzzy_coverage(cq, lien_text) if cq else 0.0
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


def _resolve_lien_and_source(rec: dict) -> tuple[str, dict]:
    lien = rec.get("link_to_terroir") or ""
    src = rec.get("source") or {}
    eu_url = src.get("final_url") or src.get("source_url") or ""
    return lien, {"pdf_url": eu_url, "kind": "eu-oj"}


def collect_targets() -> list[dict]:
    """Return BG records with a long-enough link_to_terroir."""
    out = []
    for jp in sorted(EXTRACTED.glob("*.json")):
        if jp.name.startswith("_"):
            continue
        rec = json.loads(jp.read_text(encoding="utf-8"))
        if rec.get("is_sub_denomination"):
            continue
        lien, prov = _resolve_lien_and_source(rec)
        if len(lien) < MIN_LIEN_CHARS:
            continue
        rec["link_to_terroir"] = lien
        rec["_terroir_source"] = prov
        out.append(rec)
    return out


def _build_user_message(label: str, lien_text: str) -> str:
    return (
        f"Подсекция за обработка: {label}\n\n"
        f"Текст на единния документ (Описание на връзката):\n\n{lien_text}"
    )


def _process_subsection(
    provider, model_id: str, record: dict, sub: dict, wiki_record: dict,
) -> tuple[list[dict], int, str]:
    lien = record.get("link_to_terroir") or ""
    wiki_hint = _wiki_hint_for_subsection(wiki_record, sub["key"])
    system = EXTRACT_SYSTEM.format(
        wiki_hint=wiki_hint or "(извлечение от Wikipedia недостъпно)",
        label=sub["label"],
        topics=sub["topics"],
        max_bullets=sub["max_bullets"],
    )
    user = _build_user_message(sub["label"], lien)
    try:
        raw = provider.chat(system=system, user=user, max_tokens=1500, num_ctx=8192)
    except Exception as e:  # noqa: BLE001
        return [], 0, str(e)
    payload, perr = llm_json.parse_facts(raw)
    if payload is None:
        return [], 0, perr or "no JSON in response"
    raw_facts = payload.get("facts") or []
    kept, dropped = _ground_facts(raw_facts, lien, wiki_hint)
    return kept, dropped, ""


def _process_record(provider, model_id: str, record: dict) -> dict:
    slug = record["slug"]
    wiki_path = WIKI_AOCS / f"{slug}.json"
    wiki_record = json.loads(wiki_path.read_text(encoding="utf-8")) if wiki_path.exists() else {}
    lien = record.get("link_to_terroir") or ""
    wiki_revision = wiki_record.get("revision") if wiki_record else None
    wiki_url = wiki_record.get("page_url") if wiki_record else None
    prov = record.get("_terroir_source") or {}

    all_facts: list[dict] = []
    n_dropped_total = 0
    sub_errors: list[tuple[str, str]] = []
    for sub in SUBSECTIONS:
        kept, dropped, err = _process_subsection(
            provider, model_id, record, sub, wiki_record,
        )
        n_dropped_total += dropped
        if err:
            sub_errors.append((sub["key"], err))
            continue
        for f in kept:
            f["subsection"] = sub["key"]
            all_facts.append(f)

    payload = {
        "country": "bg",
        "source_lang": "bg",
        "slug": slug,
        "name": record.get("name") or slug,
        "facts": all_facts,
        "n_dropped": n_dropped_total,
        "model": model_id,
        "model_kind": provider.kind,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cahier_source_sha": cahier_sha(lien),
        "cahier_source_pdf_url": prov.get("pdf_url") or "",
        "cahier_source_kind": prov.get("kind") or "",
        "wiki_source_revision": wiki_revision,
        "wiki_source_url": wiki_url,
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
    if existing.get("country") != "bg":
        return False
    cur_sha = cahier_sha(record.get("link_to_terroir") or "")
    if existing.get("cahier_source_sha") != cur_sha:
        return False
    wiki_path = WIKI_AOCS / f"{slug}.json"
    cur_rev = None
    if wiki_path.exists():
        try:
            wj = json.loads(wiki_path.read_text(encoding="utf-8"))
            cur_rev = wj.get("revision")
        except (ValueError, OSError):
            pass
    if existing.get("wiki_source_revision") != cur_rev:
        return False
    return True


def _job_payload(record: dict) -> dict:
    slug = record["slug"]
    lien = record.get("link_to_terroir") or ""
    wiki_path = WIKI_AOCS / f"{slug}.json"
    wiki_record = json.loads(wiki_path.read_text(encoding="utf-8")) if wiki_path.exists() else {}
    return {
        "slug": slug,
        "name": record.get("name") or slug,
        "lien": lien,
        "lien_sha": cahier_sha(lien),
        "wiki_record": wiki_record,
    }


def emit_todo(out_path: Path, *, skip_cached: bool, limit: int = 0) -> int:
    items: list[dict] = []
    n_records_emitted = 0
    for rec in collect_targets():
        if skip_cached and _is_cache_valid(rec):
            continue
        if limit and n_records_emitted >= limit:
            break
        n_records_emitted += 1
        job = _job_payload(rec)
        for sub in SUBSECTIONS:
            wiki_hint = _wiki_hint_for_subsection(job["wiki_record"], sub["key"])
            items.append({
                "slug": job["slug"],
                "subsection": sub["key"],
                "subsection_label": sub["label"],
                "topics": sub["topics"],
                "max_bullets": sub["max_bullets"],
                "system_prompt": EXTRACT_SYSTEM.format(
                    wiki_hint=wiki_hint or "(извлечение от Wikipedia недостъпно)",
                    label=sub["label"],
                    topics=sub["topics"],
                    max_bullets=sub["max_bullets"],
                ),
                "cahier_text": job["lien"],
                "wiki_hint": wiki_hint,
                "cahier_source_sha": job["lien_sha"],
                "wiki_source_revision": (job["wiki_record"] or {}).get("revision"),
                "facts": [],
            })
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_lang": "bg",
        "n_items": len(items),
        "items": items,
    }
    cache.write_json(out_path, payload)
    print(
        f"[02d/bg] wrote {out_path} ({len(items)} items across "
        f"{len({i['slug'] for i in items})} wines)",
        file=sys.stderr,
    )
    return 0


def _write_imported_cache(
    *, slug: str, name: str, facts: list[dict], lien: str, wiki_record: dict,
    translator_id: str, translator_kind: str, prov: dict,
) -> None:
    payload = {
        "country": "bg",
        "source_lang": "bg",
        "slug": slug,
        "name": name,
        "facts": facts,
        "model": translator_id,
        "model_kind": translator_kind,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cahier_source_sha": cahier_sha(lien),
        "cahier_source_pdf_url": prov.get("pdf_url") or "",
        "cahier_source_kind": prov.get("kind") or "",
        "wiki_source_revision": wiki_record.get("revision") if wiki_record else None,
        "wiki_source_url": wiki_record.get("page_url") if wiki_record else None,
    }
    cache.write_json(CACHE_DIR / f"{slug}.json", payload)


def _classify_imported_facts(slug_items: list[dict], lien: str) -> list[dict]:
    out: list[dict] = []
    for it in slug_items:
        wiki_hint = it.get("wiki_hint") or ""
        sub_key = it.get("subsection") or "facteurs_naturels"
        kept, _ = _ground_facts(it.get("facts") or [], lien, wiki_hint)
        for f in kept:
            f["subsection"] = sub_key
            out.append(f)
    return out


def _import_one_slug(
    slug: str, slug_items: list[dict], record_index: dict,
    *, translator_id: str, translator_kind: str,
) -> str:
    rec = record_index.get(slug)
    if rec is None:
        print(f"  skip {slug}: unknown slug (no extracted record)", file=sys.stderr)
        return "unknown_slug"
    lien = rec.get("link_to_terroir") or ""
    cur_sha = cahier_sha(lien)
    first = slug_items[0]
    if first.get("cahier_source_sha") and first["cahier_source_sha"] != cur_sha:
        print(
            f"  skip {slug}: document SHA mismatch — re-run --emit-todo to refresh",
            file=sys.stderr,
        )
        return "sha_mismatch"
    wiki_path = WIKI_AOCS / f"{slug}.json"
    wiki_record = json.loads(wiki_path.read_text(encoding="utf-8")) if wiki_path.exists() else {}
    facts = _classify_imported_facts(slug_items, lien)
    _write_imported_cache(
        slug=slug,
        name=rec.get("name") or slug,
        facts=facts,
        lien=lien,
        wiki_record=wiki_record,
        translator_id=translator_id,
        translator_kind=translator_kind,
        prov=rec.get("_terroir_source") or {},
    )
    return "wrote"


def import_todo(in_path: Path, *, translator_id: str, translator_kind: str) -> int:
    if not in_path.exists():
        print(f"error: {in_path} does not exist.", file=sys.stderr)
        return 1
    try:
        payload = json.loads(in_path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"error: could not parse {in_path}: {e}", file=sys.stderr)
        return 1

    by_slug: dict[str, list[dict]] = {}
    for it in payload.get("items") or []:
        by_slug.setdefault(it["slug"], []).append(it)

    record_index = {r["slug"]: r for r in collect_targets()}
    counts = {"wrote": 0, "sha_mismatch": 0, "unknown_slug": 0}
    for slug, slug_items in by_slug.items():
        outcome = _import_one_slug(
            slug, slug_items, record_index,
            translator_id=translator_id, translator_kind=translator_kind,
        )
        counts[outcome] += 1
    print(
        f"[02d/bg] wrote {counts['wrote']} cache files; "
        f"skipped sha_mismatch={counts['sha_mismatch']}, "
        f"unknown_slug={counts['unknown_slug']}",
        file=sys.stderr,
    )
    return 0


def _build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--provider", default="ollama", choices=("anthropic", "mistral", "ollama", "manual"),
    )
    ap.add_argument("--model", default=None)
    ap.add_argument("--ollama-url", default=providers.DEFAULT_OLLAMA_URL)
    ap.add_argument("--mistral-url", default=providers.DEFAULT_MISTRAL_URL)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--batch", action="store_true")
    roundtrip.add_arguments(ap)
    return ap


def _dispatch_emit_or_import(args) -> int | None:
    rc = roundtrip.validate_emit_import(args)
    if rc is not None:
        return rc
    if args.emit_todo:
        return emit_todo(Path(args.emit_todo), skip_cached=not args.all, limit=args.limit)
    if args.import_path:
        return import_todo(
            Path(args.import_path),
            translator_id=args.translator_id,
            translator_kind=args.translator_kind,
        )
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
        print("[02d/bg] batch: nothing to do.", file=sys.stderr)
        return 0
    print(f"[02d/bg] batch: {len(targets)} wines (provider={args.provider}, "
          f"model={model_id})", file=sys.stderr)

    def run_loop(prov):
        global CACHE_DIR
        if getattr(prov, "kind", "") == "collecting":
            keep = CACHE_DIR
            CACHE_DIR = Path(tempfile.mkdtemp(prefix="batch-02d-bg-"))
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
        sidecar=ROOT / "raw" / ".batch" / "02d-bg.json",
        run_loop=run_loop,
    )
    return 0


def main() -> int:
    args = _build_argparser().parse_args()

    if not EXTRACTED.exists():
        print(
            f"error: {EXTRACTED} missing — run scripts/bg/02_extract_pliegos.py first",
            file=sys.stderr,
        )
        return 1
    if not WIKI_AOCS.exists():
        print(
            f"warning: {WIKI_AOCS} missing — bullets will be document-only. "
            "Run scripts/02b_fetch_aoc_lexicon.py --lang bg "
            "--source raw/bg/dokumenti-extracted to enable Wikipedia salience.",
            file=sys.stderr,
        )

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
        print("[02d/bg] nothing to do — all caches valid.", file=sys.stderr)
        return 0

    provider, model_id = providers.make_provider(
        args.provider, model=args.model, ollama_url=args.ollama_url,
        mistral_url=args.mistral_url,
    )
    if provider is None:
        print(
            f"[02d/bg] manual provider: {len(targets)} wines need extraction. "
            f"Use --emit-todo PATH to dump them, fill in facts offline, then "
            f"--import PATH --translator-id <id> to write cache files.",
            file=sys.stderr,
        )
        return 1

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    print(
        f"[02d/bg] {len(targets)} BG wines to extract "
        f"(provider={args.provider}, model={model_id}, workers={args.workers})",
        file=sys.stderr,
    )

    workers = max(1, args.workers)
    n_done = 0
    n_facts = 0
    t0 = time.time()
    if workers <= 1:
        for rec in tqdm(targets, desc="terroir-bg", leave=False):
            res = _process_record(provider, model_id, rec)
            n_done += 1
            n_facts += len(res.get("facts", []))
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {
                ex.submit(_process_record, provider, model_id, r): r for r in targets
            }
            for fut in tqdm(as_completed(futures), total=len(targets), desc="terroir-bg", leave=False):
                try:
                    res = fut.result()
                    n_done += 1
                    n_facts += len(res.get("facts", []))
                except Exception as e:  # noqa: BLE001
                    print(f"  worker exception: {e}", file=sys.stderr)

    elapsed = time.time() - t0
    MANIFEST.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": args.provider,
        "model": model_id,
        "n_wines_processed": n_done,
        "n_facts_total": n_facts,
        "elapsed_seconds": int(elapsed),
    }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(
        f"[02d/bg] done: {n_done} wines, {n_facts} facts, "
        f"{elapsed/60:.1f} min ({elapsed/max(1,n_done):.1f} s/wine)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
