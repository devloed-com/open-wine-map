"""Extract noteworthy terroir facts from each ES wine's "Vínculo con la
zona geográfica" (pliego section 8 / 10) using a bounded LLM layer with
dual-source grounding.

ES analog of `scripts/02d_extract_terroir_facts.py`. Same per-bullet
provenance, fuzzy-grounding, and cache invalidation rules; the
differences are:

  - source = ES record's `link_to_terroir` (already cleaned by stage
    02 — no per-section slicer needed; the EU "documento único"
    template puts the full vínculo text in one block).
  - Wikipedia hint = `raw/wikipedia/aocs/es/<slug>.json` (fetched by
    `scripts/02b_fetch_aoc_lexicon.py --lang es`).
  - LLM prompt is in Spanish and asks for Spanish bullets.
  - Output cache = `raw/terroir-facts/<slug>.json` (single shared dir;
    `country: "es"` distinguishes from FR records).

Subzonas (DGCs) are skipped — they inherit the parent's bullets at
the stage-03 / stage-04 rendering layer.

Providers: anthropic / mistral / ollama / manual (mirrors FR 02d).
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

EXTRACTED = ROOT / "raw" / "es" / "pliegos-extracted"
WIKI_AOCS = ROOT / "raw" / "wikipedia" / "aocs" / "es"
CACHE_DIR = ROOT / "raw" / "terroir-facts"
MANIFEST = CACHE_DIR / "manifest-es.json"

MIN_LIEN_CHARS = 400
FUZZY_THRESHOLD = 0.6
WIKI_HINT_CHAR_CAP = 1500


# Same 4-bucket structure as FR 02d, with Spanish topic vocabulary
# matched to the EU pliego "Vínculo con la zona geográfica" content
# pattern (factores naturales / factores humanos / producto / vínculo
# causal).
SUBSECTIONS = [
    {
        "key": "facteurs_naturels",  # FR key kept for stage-04 render parity
        "label": "Factores naturales (geología, suelos, clima, relieve)",
        "topics": (
            "geología, naturaleza de los suelos, clima, relieve, "
            "hidrografía, exposición, subzonas y municipios"
        ),
        "max_bullets": 5,
    },
    {
        "key": "facteurs_humains",
        "label": "Factores humanos (historia, prácticas)",
        "topics": (
            "historia de la denominación, prácticas vitivinícolas y "
            "de elaboración, variedades tradicionales"
        ),
        "max_bullets": 2,
    },
    {
        "key": "produit",
        "label": "Características del producto (perfil sensorial)",
        "topics": "colores, aromas, estructura, guarda, perfil sensorial de los vinos",
        "max_bullets": 2,
    },
    {
        "key": "interactions",
        "label": "Interacciones causales (vínculo terroir / vino)",
        "topics": (
            "vínculo explícito entre el terroir y el carácter del vino, "
            "expresión del suelo o del clima en el vino"
        ),
        "max_bullets": 1,
    },
]


# Wikipedia ES section names that map to each pliego sub-section as
# salience hint. Spanish wine articles vary in section naming; this
# list is permissive (multiple synonyms per bucket).
WIKI_TO_SUBSECTION: dict[str, list[str]] = {
    "facteurs_naturels": [
        "Geografía", "Geología", "Geología y orografía", "Suelos",
        "Clima", "Climatología", "Zona de producción", "Zona geográfica",
        "Subzonas", "Comarca", "Viñedo", "Localización",
    ],
    "facteurs_humains": [
        "Historia", "Antigüedad", "Edad Media", "Edad Moderna",
        "Etimología", "Variedades autorizadas", "Variedades de uva",
        "Elaboración", "Vinificación", "Cultivo de la vid",
        "Crianza", "Tradición",
    ],
    "produit": [
        "Vinos", "Tipos de vinos", "Características de los vinos",
        "Gastronomía", "Maridaje",
    ],
    "interactions": [],
}
WIKI_TO_SUBSECTION["interactions"] = WIKI_TO_SUBSECTION["facteurs_naturels"]


EXTRACT_SYSTEM = """Extraes hechos notables sobre una denominación de origen vinícola española a partir de DOS fuentes: el pliego de condiciones de la UE (autoridad reglamentaria) y el resumen de Wikipedia ES (referencia popular, vocabulario sumiller).

Lector destinatario: aficionado al vino o sumiller informado, interesado en las particularidades concretas de una denominación. Lo notable: formaciones geológicas con su nombre estándar, tipos de suelo específicos, microclimas y vientos locales, variedades tradicionales, prácticas vitícolas distintivas, perfil sensorial preciso, anclajes históricos datados.

═══ FUENTE 1: Resumen Wikipedia (secciones pertinentes) ═══
{wiki_hint}

═══ FUENTE 2: Texto del pliego (en el mensaje del usuario abajo) ═══

Sub-sección tratada: {label}
Categorías a privilegiar: {topics}

Reglas estrictas:
- Cada viñeta DEBE estar respaldada por AL MENOS UNA cita: `cahier_quote` (verbatim del pliego) O `wiki_quote` (verbatim del resumen Wikipedia anterior). Ambas son fuertemente recomendadas cuando las dos fuentes cubren la misma información.
- Privilegia el pliego como fuente primaria: usa `cahier_quote` siempre que el hecho aparezca allí.
- Añade `wiki_quote` cuando Wikipedia aporte el vocabulario técnico estándar para un hecho que el pliego describe con sus propios términos. La viñeta puede combinar ambos vocabularios.
- Si solo Wikipedia menciona un hecho notable (vocabulario o detalle ausente del pliego), puedes conservarlo solo con `wiki_quote` — se atribuirá a Wikipedia en el rendering final.
- Las citas son VERBATIM (copiadas y pegadas) de su fuente respectiva. NUNCA atribuyas a una fuente un texto que no figura en ella.
- Sin juicios de valor ("excepcional", "extraordinario", "prestigioso"...).
- Sin inferencia externa. Sin cifras ausentes de las dos fuentes.
- Máximo {max_bullets} viñetas, ≤ 140 caracteres cada una.
- Si ni el pliego ni Wikipedia contienen un hecho notable concreto para esta sub-sección, devuelve una lista vacía.

Responde ÚNICAMENTE en JSON, sin texto antes o después:
{{"facts": [{{"bullet": "...", "cahier_quote": "...", "wiki_quote": "..."}}, ...]}}
Usa una cadena vacía "" para la cita ausente."""


# ─────────────────────────────────────────────────────────────── helpers ──


def normalize(s: str) -> str:
    return " ".join((s or "").split()).lower()


def cahier_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fuzzy_coverage(quote: str, source: str) -> float:
    """Longest-contiguous-match coverage of `quote` in `source` (0–1)."""
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
    """Pull the relevant Wikipedia ES section text for a sub-section. Falls
    back to the lead extract when no matching headings are found."""
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
    """Filter LLM facts that fail dual-source grounding. Returns
    (kept_facts, n_dropped). Each kept fact has cahier_coverage,
    wiki_coverage, and provenance fields added."""
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


# ───────────────────────────────────────────────────────────── core loop ──


def collect_targets() -> list[dict]:
    """Return ES parent records (skipping DGCs and stubs and short pliegos)."""
    out = []
    for jp in sorted(EXTRACTED.glob("*.json")):
        if jp.name.startswith("_"):
            continue
        rec = json.loads(jp.read_text(encoding="utf-8"))
        if rec.get("is_sub_denomination") or rec.get("stub"):
            continue
        lien = rec.get("link_to_terroir") or ""
        if len(lien) < MIN_LIEN_CHARS:
            continue
        out.append(rec)
    return out


def _build_user_message(label: str, lien_text: str) -> str:
    return (
        f"Sub-sección a tratar: {label}\n\n"
        f"Texto del pliego (Vínculo con la zona geográfica):\n\n{lien_text}"
    )


def _process_subsection(
    provider, model_id: str, record: dict, sub: dict, wiki_record: dict,
) -> tuple[list[dict], int, str]:
    """Run one LLM extraction for (record, sub-section). Returns
    (kept_facts, n_dropped, error_or_empty)."""
    lien = record.get("link_to_terroir") or ""
    wiki_hint = _wiki_hint_for_subsection(wiki_record, sub["key"])
    system = EXTRACT_SYSTEM.format(
        wiki_hint=wiki_hint or "(sin resumen Wikipedia disponible)",
        label=sub["label"],
        topics=sub["topics"],
        max_bullets=sub["max_bullets"],
    )
    user = _build_user_message(sub["label"], lien)
    try:
        raw = provider.chat(system=system, user=user, max_tokens=1500, num_ctx=8192)
    except Exception as e:  # noqa: BLE001
        return [], 0, str(e)
    # Tolerant JSON extraction
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

    src = record.get("source") or {}
    payload = {
        "country": "es",
        "source_lang": "es",
        "slug": slug,
        "name": record.get("name") or slug,
        "facts": all_facts,
        "n_dropped": n_dropped_total,
        "model": model_id,
        "model_kind": provider.kind,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cahier_source_sha": cahier_sha(lien),
        "cahier_source_pdf_url": src.get("final_url") or src.get("source_url") or "",
        "wiki_source_revision": wiki_revision,
        "wiki_source_url": wiki_url,
        "subsection_errors": sub_errors,
    }
    cache.write_json(CACHE_DIR / f"{slug}.json", payload)
    return payload


def _is_cache_valid(record: dict) -> bool:
    """Cache hit iff cahier_sha + wiki_revision both unchanged."""
    slug = record["slug"]
    p = CACHE_DIR / f"{slug}.json"
    if not p.exists():
        return False
    try:
        existing = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return False
    if existing.get("country") != "es":
        return False  # FR cache for the same slug — should not happen
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


def _run_batch(args) -> int:
    """Extract terroir facts for every ES wine via the provider Batch API."""
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
        print("[02d/es] batch: nothing to do.", file=sys.stderr)
        return 0
    print(f"[02d/es] batch: {len(targets)} wines (provider={args.provider}, "
          f"model={model_id})", file=sys.stderr)

    def run_loop(prov):
        # _process_record writes the cache unconditionally; in the collect
        # pass redirect CACHE_DIR to a throwaway so pass 1 leaves no caches.
        global CACHE_DIR
        if getattr(prov, "kind", "") == "collecting":
            keep = CACHE_DIR
            CACHE_DIR = Path(tempfile.mkdtemp(prefix="batch-02d-es-"))
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
        sidecar=ROOT / "raw" / ".batch" / "02d-es.json",
        run_loop=run_loop,
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--provider", default="ollama", choices=("anthropic", "mistral", "ollama", "manual"),
        help="LLM backend (default ollama, mirroring 02c on this machine)",
    )
    ap.add_argument("--model", default=None,
                    help=f"model id (defaults: anthropic={providers.DEFAULT_ANTHROPIC_MODEL}, "
                         f"mistral={providers.DEFAULT_MISTRAL_MODEL}, "
                         f"ollama={providers.DEFAULT_OLLAMA_MODEL})")
    ap.add_argument("--ollama-url", default=providers.DEFAULT_OLLAMA_URL)
    ap.add_argument("--mistral-url", default=providers.DEFAULT_MISTRAL_URL)
    ap.add_argument("--workers", type=int, default=1,
                    help="concurrent LLM calls (keep 1 for Ollama on M1 32GB)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--refresh", action="store_true",
                    help="re-extract even when cache is valid")
    ap.add_argument("--batch", action="store_true",
                    help="submit all wines to the provider Batch API "
                         "(--provider anthropic|mistral; ~50%% cheaper); "
                         "resumes an in-flight batch on re-run")
    args = ap.parse_args()

    if not EXTRACTED.exists():
        print(f"error: {EXTRACTED} missing — run scripts/es/02_extract_pliegos.py first",
              file=sys.stderr)
        return 1

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
        print("[02d/es] nothing to do — all caches valid.", file=sys.stderr)
        return 0

    provider, model_id = providers.make_provider(
        args.provider, model=args.model, ollama_url=args.ollama_url,
        mistral_url=args.mistral_url,
    )
    if provider is None:
        print(f"[02d/es] manual provider not yet wired for ES; pass --provider ollama",
              file=sys.stderr)
        return 1

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    print(
        f"[02d/es] {len(targets)} ES wines to extract "
        f"(provider={args.provider}, model={model_id}, workers={args.workers})",
        file=sys.stderr,
    )

    workers = max(1, args.workers)
    n_done = 0
    n_facts = 0
    t0 = time.time()
    if workers <= 1:
        for rec in tqdm(targets, desc="terroir-es", leave=False):
            res = _process_record(provider, model_id, rec)
            n_done += 1
            n_facts += len(res.get("facts", []))
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {
                ex.submit(_process_record, provider, model_id, r): r for r in targets
            }
            for fut in tqdm(as_completed(futures), total=len(targets), desc="terroir-es", leave=False):
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
        f"[02d/es] done: {n_done} wines, {n_facts} facts, "
        f"{elapsed/60:.1f} min ({elapsed/n_done:.1f} s/wine)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
