"""Extract noteworthy terroir facts from each AOC's "Lien au terroir"
(cahier section X) using a bounded LLM layer with dual-source grounding.

Pipeline stage 02d. Sister stage to 02c (translation): both are bounded
narrative layers admitted by CLAUDE.md, both cache per-source-SHA, both
support a manual round-trip flow for forks without API access.

Reads:
  raw/inao/cahier-extracted/*.json    cahier sections (lien_au_terroir)
  raw/wikipedia/aocs/fr/*.json        Wikipedia FR salience hints (02b sister)

Writes:
  raw/terroir-facts/<slug>.json       per-AOC bullets with provenance
  raw/terroir-facts/manifest.json     run summary

Each fact carries TWO quote fields:
  - cahier_quote  (verbatim from cahier; may be empty)
  - wiki_quote    (verbatim from Wikipedia hint; may be empty)
At least one must fuzzy-ground (>= 0.6 longest-contiguous-match coverage)
in its respective source. Per-bullet `provenance` is one of `both` /
`cahier` / `wiki`. The UI renders "via Wikipedia · CC BY-SA 4.0" beside
wiki-only bullets.

Providers:
  anthropic  Anthropic Messages API (recommended for production).
             Requires ANTHROPIC_API_KEY. Default model: claude-haiku-4-5.
  ollama     Local Ollama HTTP API (recommended for offline / forks).
             Default model: mistral-small3.2.
  manual     No network calls. With --emit-todo dumps every untreated
             (AOC, sub-section) work item into one JSON for offline /
             external processing. With --import reads back filled-in
             facts and writes per-AOC cache entries.

Cache invalidation: a per-AOC cache entry is regenerated when EITHER the
cahier `lien_au_terroir` SHA or the Wikipedia revision id has changed
since the cache was written. The two sources version independently — a
Wikipedia edit re-triggers extraction even if the cahier hasn't changed.

DGCs are skipped (they inherit the parent appellation's bullets at the
stage-03 rendering layer; nothing to do here).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import cache, providers, roundtrip  # noqa: E402

EXTRACTED = ROOT / "raw" / "inao" / "cahier-extracted"
WIKI_AOCS = ROOT / "raw" / "wikipedia" / "aocs" / "fr"
CACHE_DIR = ROOT / "raw" / "terroir-facts"
MANIFEST = CACHE_DIR / "manifest.json"

MIN_CAHIER_CHARS = 800
FUZZY_THRESHOLD = 0.6
WIKI_HINT_CHAR_CAP = 1500

# Cahier section X anchors. Validated 100% against the 6-AOC eval sample;
# fall back to a flat slice when the slicer returns < 2 sub-sections.
TOP_RE = re.compile(r"\b([1-9])°\s*[-–]\s*([A-ZÀ-Ý][^\n]{5,80})")
SUB_RE = re.compile(r"\b([a-c])\)\s*[-–]?\s*([A-ZÀ-Ý][^\n]{5,80})")

SUBSECTIONS = [
    {
        "key": "facteurs_naturels",
        "label": "Facteurs naturels (géologie, sols, climat, relief, étendue)",
        "topics": (
            "géologie, nature des sols, climat, relief, hydrographie, "
            "exposition, nombre de communes et de départements, superficie"
        ),
        "max_bullets": 5,
    },
    {
        "key": "facteurs_humains",
        "label": "Facteurs humains (histoire, pratiques)",
        "topics": (
            "histoire de l'appellation, pratiques viticoles et de "
            "vinification, cépages traditionnels"
        ),
        "max_bullets": 2,
    },
    {
        "key": "produit",
        "label": "Caractéristiques du produit (profil sensoriel)",
        "topics": "couleurs, arômes, structure, garde, profil sensoriel des vins",
        "max_bullets": 2,
    },
    {
        "key": "interactions",
        "label": "Interactions causales (lien terroir / vin)",
        "topics": (
            "lien explicite entre terroir et caractère du vin, "
            "expression du sol ou du climat dans le vin"
        ),
        "max_bullets": 1,
    },
]

# Wikipedia FR section names that map to each cahier sub-section as
# salience hint (validated v6).
WIKI_TO_SUBSECTION: dict[str, list[str]] = {
    "facteurs_naturels": [
        "Géologie et orographie", "Géologie", "Climat", "Climatologie",
        "Aire d'appellation", "Vignoble",
    ],
    "facteurs_humains": [
        "Histoire", "Antiquité", "Moyen Âge", "Période moderne",
        "Période contemporaine", "Étymologie", "Encépagement",
        "Méthodes culturales et réglementaires", "Vinification et élevage",
    ],
    "produit": ["Vins", "Types de chablis", "Types de vins", "Gastronomie"],
    "interactions": [],
}
WIKI_TO_SUBSECTION["interactions"] = WIKI_TO_SUBSECTION["facteurs_naturels"]

EXTRACT_SYSTEM = """Tu extrais des faits notables sur une appellation viticole française à partir de DEUX sources : le cahier des charges INAO (autorité réglementaire) et le résumé Wikipedia FR (référence grand public, vocabulaire sommelier).

Lecteur cible : un amateur de vin ou un sommelier averti, qui s'intéresse aux particularités concrètes d'une appellation. Ce qu'il trouve notable : formations géologiques nommées (avec leur nom standard quand il existe), types de sols spécifiques, microclimats et vents locaux, cépages traditionnels, pratiques viticoles distinctives, profil sensoriel précis, ancrages historiques datés.

═══ SOURCE 1 : Résumé Wikipedia (sections pertinentes) ═══
{wiki_hint}

═══ SOURCE 2 : Texte du cahier des charges (donné dans le message utilisateur ci-dessous) ═══

Sous-section traitée : {label}
Catégories à privilégier : {topics}

Règles strictes :
- Chaque puce DOIT être étayée par AU MOINS UNE citation : `cahier_quote` (verbatim du cahier) OU `wiki_quote` (verbatim du résumé Wikipedia ci-dessus). Les deux sont fortement encouragées quand les deux sources couvrent la même information.
- Privilégie le cahier comme source primaire : utilise `cahier_quote` chaque fois que le fait y figure.
- Ajoute `wiki_quote` quand Wikipedia apporte le vocabulaire technique standard (par ex. nom d'ère géologique : « Kimméridgien », « Tithonien », « Cénomanien »...) pour un fait que le cahier décrit avec ses propres termes (par ex. « Marnes à exogyra virgula »). Dans ce cas, la puce peut combiner les deux vocabulaires (« Sols sur Kimméridgien (Marnes à exogyra virgula) »).
- Si seul Wikipedia mentionne un fait notable (vocabulaire ou détail absent du cahier), tu peux le retenir avec uniquement `wiki_quote` — ce sera attribué à Wikipedia dans le rendu final.
- Les citations sont VERBATIM (copiées-collées) de leur source respective. NE JAMAIS attribuer à une source un texte qui n'y figure pas.
- Aucun jugement de valeur (« exceptionnel », « remarquable », « prestigieux »...).
- Aucune inférence externe. Aucun chiffre absent des deux sources.
- Maximum {max_bullets} puces, ≤ 140 caractères chacune.
- Si ni le cahier ni Wikipedia ne contiennent de fait notable concret pour cette sous-section, retourne une liste vide.

Réponds UNIQUEMENT en JSON, sans texte avant ou après :
{{"facts": [{{"bullet": "...", "cahier_quote": "...", "wiki_quote": "..."}}, ...]}}
Utilise une chaîne vide "" pour la citation absente."""


# ─────────────────────────────────────────────────────────────── helpers ──


def normalize(s: str) -> str:
    return " ".join((s or "").split()).lower()


def cahier_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fuzzy_coverage(quote: str, source: str) -> float:
    """Longest-contiguous-match coverage of `quote` in `source` (0.0–1.0)."""
    q = normalize(quote)
    s = normalize(source)
    if not q:
        return 0.0
    match = SequenceMatcher(None, q, s, autojunk=False).find_longest_match(
        0, len(q), 0, len(s)
    )
    return match.size / len(q)


def _spans_by_top(lien: str, tops: list[re.Match]) -> dict[str, tuple[int, int]]:
    """Map top-level numeral ('1'/'2'/'3') → (start, end) span in lien."""
    out: dict[str, tuple[int, int]] = {}
    for i, m in enumerate(tops):
        end = tops[i + 1].start() if i + 1 < len(tops) else len(lien)
        out[m.group(1)] = (m.start(), end)
    return out


def _split_zone_geographique(
    s1: int, e1: int, subs: list[re.Match]
) -> dict[str, tuple[int, int]]:
    """Split section 1° into 1°a (facteurs naturels) / 1°b (facteurs humains)
    on its sub-letter anchors. Falls back to a single naturels span when
    sub-letter anchors aren't present."""
    sub_in_1 = [m for m in subs if s1 <= m.start() < e1]
    if not sub_in_1:
        return {"facteurs_naturels": (s1, e1)}
    out: dict[str, tuple[int, int]] = {}
    for i, m in enumerate(sub_in_1):
        end = sub_in_1[i + 1].start() if i + 1 < len(sub_in_1) else e1
        if m.group(1) == "a":
            out["facteurs_naturels"] = (m.start(), end)
        elif m.group(1) == "b":
            out["facteurs_humains"] = (m.start(), end)
    return out


def slice_section_x(lien: str) -> dict[str, str]:
    """Return {sub_key: text} for the four standard INAO sub-sections.
    Returns an empty dict when the slicer can't find the top-level numbered
    anchors — caller falls back to a flat slice."""
    tops = list(TOP_RE.finditer(lien))
    if not tops:
        return {}
    subs = list(SUB_RE.finditer(lien))
    by_top = _spans_by_top(lien, tops)

    spans: dict[str, tuple[int, int]] = {}
    if "1" in by_top:
        s1, e1 = by_top["1"]
        spans.update(_split_zone_geographique(s1, e1, subs))
    if "2" in by_top:
        spans["produit"] = by_top["2"]
    if "3" in by_top:
        spans["interactions"] = by_top["3"]

    return {k: lien[s:e].strip() for k, (s, e) in spans.items()}


def _find_heading(full: str, heading: str) -> int:
    """Locate a section heading in TextExtracts plaintext (-1 if absent)."""
    idx = full.find(f"\n\n{heading}\n\n")
    if idx == -1:
        idx = full.find(f"\n{heading}\n")
    return idx


def _index_wiki_sections(full: str, headings: list[str]) -> dict[str, str]:
    """Slice a Wikipedia plaintext blob into {heading: body}, plus a synthetic
    `__intro__` covering the text before the first matched heading."""
    positions = sorted(
        (idx, h) for h in headings if (idx := _find_heading(full, h)) != -1
    )
    section_text: dict[str, str] = {}
    intro_end = positions[0][0] if positions else len(full)
    section_text["__intro__"] = full[:intro_end].strip()
    for i, (start, h) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(full)
        body_start = start + len(h) + 2
        section_text[h] = full[body_start:end].strip()
    return section_text


def _build_subsection_hint(
    sub_key: str, wanted: list[str], section_text: dict[str, str]
) -> str:
    chunks: list[str] = []
    if sub_key == "facteurs_naturels" and section_text.get("__intro__"):
        chunks.append(section_text["__intro__"][:400])
    for h in wanted:
        body = section_text.get(h, "").strip()
        if body:
            chunks.append(f"« {h} » : {body}")
    joined = "\n\n".join(chunks)
    if len(joined) > WIKI_HINT_CHAR_CAP:
        joined = joined[:WIKI_HINT_CHAR_CAP].rsplit(" ", 1)[0] + " […]"
    return joined


def load_wiki_hint(slug: str) -> tuple[dict[str, str], dict | None]:
    """Return ({sub_key: hint_text}, wiki_record_or_None).

    Hint text per sub-section: intro (for facteurs_naturels) + the Wikipedia
    sections in WIKI_TO_SUBSECTION, joined and capped at WIKI_HINT_CHAR_CAP.
    """
    cache_file = WIKI_AOCS / f"{slug}.json"
    empty = dict.fromkeys(WIKI_TO_SUBSECTION, "")
    data = cache.read_json_or_none(cache_file)
    if data is None:
        return empty, None
    if data.get("missing") or data.get("error"):
        return empty, data
    section_text = _index_wiki_sections(data.get("full_text", ""), data.get("sections", []))
    out = {
        sub_key: _build_subsection_hint(sub_key, wanted, section_text)
        for sub_key, wanted in WIKI_TO_SUBSECTION.items()
    }
    return out, data


def parse_facts_json(raw: str) -> tuple[dict | None, str | None]:
    """Strip ```json fences, parse, return (parsed_dict, error_or_None)."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.rsplit("```", 1)[0].strip()
    try:
        return json.loads(cleaned), None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def classify_fact(
    raw: dict, cahier_text: str, wiki_text: str
) -> dict | None:
    """Return a fully-populated fact dict, or None if both quotes fail."""
    bullet = (raw.get("bullet") or "").strip()
    cahier_quote = (raw.get("cahier_quote") or "").strip()
    wiki_quote = (raw.get("wiki_quote") or "").strip()
    cahier_cov = fuzzy_coverage(cahier_quote, cahier_text) if cahier_quote else 0.0
    wiki_cov = fuzzy_coverage(wiki_quote, wiki_text) if wiki_quote else 0.0
    cahier_keep = cahier_cov >= FUZZY_THRESHOLD
    wiki_keep = wiki_cov >= FUZZY_THRESHOLD
    if cahier_keep and wiki_keep:
        provenance = "both"
    elif cahier_keep:
        provenance = "cahier"
    elif wiki_keep:
        provenance = "wiki"
    else:
        return None
    return {
        "bullet": bullet,
        "cahier_quote": cahier_quote,
        "wiki_quote": wiki_quote,
        "cahier_coverage": round(cahier_cov, 3),
        "wiki_coverage": round(wiki_cov, 3),
        "provenance": provenance,
    }


# ────────────────────────────────────────────────────────── cache + jobs ──


def cache_path(slug: str) -> Path:
    return CACHE_DIR / f"{slug}.json"


def load_existing(slug: str) -> dict | None:
    return cache.read_json_or_none(cache_path(slug))


def is_stale(existing: dict | None, current_cahier_sha: str, current_wiki_revision) -> bool:
    if existing is None:
        return True
    if existing.get("cahier_source_sha") != current_cahier_sha:
        return True
    if existing.get("wiki_source_revision") != current_wiki_revision:
        return True
    return False


def write_cache(
    *,
    slug: str,
    facts: list[dict],
    cahier_meta: dict,
    wiki_meta: dict,
    translator_id: str,
    translator_kind: str,
) -> None:
    payload = {
        "slug": slug,
        "facts": facts,
        **cahier_meta,
        **wiki_meta,
        "translator": translator_id,
        "translator_kind": translator_kind,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    cache.write_json(cache_path(slug), payload)


def _job_from_record(rec: dict) -> dict | None:
    """Build a per-AOC work entry, or None if the record is a DGC, has no
    slug, or has too little section-X text to be worth processing."""
    if rec.get("is_dgc"):
        return None
    slug = rec.get("slug")
    if not slug:
        return None
    lien = (rec.get("lien_au_terroir") or "").strip()
    if len(lien) < MIN_CAHIER_CHARS:
        return None
    slices = slice_section_x(lien)
    if len(slices) < 2:
        slices = {"facteurs_naturels": lien}
    wiki_hints, wiki_data = load_wiki_hint(slug)
    src = rec.get("source") or {}
    sha = cahier_sha(lien)
    return {
        "slug": slug,
        "name": rec.get("name") or slug,
        "lien": lien,
        "lien_sha": sha,
        "slices": slices,
        "wiki_hints": wiki_hints,
        "wiki_data": wiki_data,
        "cahier_meta": {
            "cahier_source_sha": sha,
            "cahier_source_text_chars": len(lien),
            "cahier_source_pdf_filename": src.get("filename") or "",
            "cahier_source_pdf_url": src.get("boagri_url") or "",
        },
        "wiki_meta": {
            "wiki_source_revision": (wiki_data or {}).get("revision"),
            "wiki_source_url": (wiki_data or {}).get("page_url"),
            "wiki_source_license": (wiki_data or {}).get("license"),
        },
    }


def enumerate_aocs() -> list[dict]:
    """Build the per-AOC work list. One entry per non-DGC AOC with a
    section-X long enough to be worth processing."""
    jobs: list[dict] = []
    for f in sorted(EXTRACTED.glob("*.json")):
        if f.name.startswith("_") or not f.is_file():
            continue
        job = _job_from_record(json.loads(f.read_text()))
        if job is not None:
            jobs.append(job)
    return jobs


# ───────────────────────────────────────────────────── extraction (loop) ──


def build_prompt(spec: dict, wiki_hint: str) -> str:
    return EXTRACT_SYSTEM.format(
        label=spec["label"],
        topics=spec["topics"],
        max_bullets=spec["max_bullets"],
        wiki_hint=wiki_hint or "(pas de section Wikipedia pertinente)",
    )


def extract_one_aoc(provider, job: dict) -> tuple[list[dict], list[str]]:
    """Run all four sub-section calls for one AOC, return (kept_facts, errors)."""
    facts: list[dict] = []
    errors: list[str] = []
    for spec in SUBSECTIONS:
        sub_key = spec["key"]
        cahier_text = job["slices"].get(sub_key, "")
        if not cahier_text or len(cahier_text) < 200:
            continue
        wiki_hint = job["wiki_hints"].get(sub_key, "")
        system = build_prompt(spec, wiki_hint)
        try:
            raw = provider.chat(system=system, user=cahier_text, max_tokens=2000, num_ctx=8192)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{sub_key}: {e}")
            continue
        parsed, err = parse_facts_json(raw)
        if err or not parsed:
            errors.append(f"{sub_key}: parse_error: {err or 'empty response'}")
            continue
        for raw_fact in parsed.get("facts", []):
            classified = classify_fact(raw_fact, job["lien"], wiki_hint)
            if classified is not None:
                classified["subsection"] = sub_key
                facts.append(classified)
    return facts, errors


# ─────────────────────────────────────────────────── round-trip (manual) ──


def emit_todo(out_path: Path, *, skip_cached: bool, limit: int = 0) -> int:
    """Dump untreated (slug, sub-section) work items into one JSON for
    offline / external processing."""
    items: list[dict] = []
    n_aocs_emitted = 0
    for job in enumerate_aocs():
        existing = load_existing(job["slug"]) if skip_cached else None
        if not is_stale(existing, job["lien_sha"], job["wiki_meta"]["wiki_source_revision"]):
            continue
        if limit and n_aocs_emitted >= limit:
            break
        n_aocs_emitted += 1
        for spec in SUBSECTIONS:
            cahier_text = job["slices"].get(spec["key"], "")
            if not cahier_text or len(cahier_text) < 200:
                continue
            wiki_hint = job["wiki_hints"].get(spec["key"], "")
            items.append({
                "slug": job["slug"],
                "subsection": spec["key"],
                "subsection_label": spec["label"],
                "topics": spec["topics"],
                "max_bullets": spec["max_bullets"],
                "system_prompt": build_prompt(spec, wiki_hint),
                "cahier_text": cahier_text,
                "wiki_hint": wiki_hint,
                "cahier_source_sha": job["lien_sha"],
                "wiki_source_revision": job["wiki_meta"]["wiki_source_revision"],
                "facts": [],
            })
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_items": len(items),
        "items": items,
    }
    cache.write_json(out_path, payload)
    print(
        f"[02d] wrote {out_path} ({len(items)} items across "
        f"{len({i['slug'] for i in items})} AOCs)",
        file=sys.stderr,
    )
    return 0


def _facts_from_items(job: dict, slug_items: list[dict]) -> list[dict]:
    """Classify and accumulate facts from one slug's TODO items."""
    facts: list[dict] = []
    for it in slug_items:
        sub_key = it.get("subsection") or ""
        wiki_hint = job["wiki_hints"].get(sub_key, "") or it.get("wiki_hint", "")
        for raw_fact in it.get("facts") or []:
            classified = classify_fact(raw_fact, job["lien"], wiki_hint)
            if classified is not None:
                classified["subsection"] = sub_key
                facts.append(classified)
    return facts


def _import_one_slug(
    slug: str,
    slug_items: list[dict],
    aoc_index: dict,
    *,
    translator_id: str,
    translator_kind: str,
) -> str:
    """Write the cache file for one slug. Returns 'wrote' / 'sha_mismatch' /
    'unknown_slug' for caller's stats."""
    job = aoc_index.get(slug)
    if job is None:
        print(f"  skip {slug}: unknown slug (no extracted record)", file=sys.stderr)
        return "unknown_slug"
    first = slug_items[0]
    if first.get("cahier_source_sha") and first["cahier_source_sha"] != job["lien_sha"]:
        print(
            f"  skip {slug}: cahier SHA mismatch — re-run --emit-todo to refresh",
            file=sys.stderr,
        )
        return "sha_mismatch"
    write_cache(
        slug=slug,
        facts=_facts_from_items(job, slug_items),
        cahier_meta=job["cahier_meta"],
        wiki_meta=job["wiki_meta"],
        translator_id=translator_id,
        translator_kind=translator_kind,
    )
    return "wrote"


def import_todo(in_path: Path, *, translator_id: str, translator_kind: str) -> int:
    """Read a filled-in todo JSON and write per-AOC cache files."""
    if not in_path.exists():
        print(f"error: {in_path} does not exist.", file=sys.stderr)
        return 1
    try:
        payload = json.loads(in_path.read_text())
    except Exception as e:  # noqa: BLE001
        print(f"error: could not parse {in_path}: {e}", file=sys.stderr)
        return 1

    by_slug: dict[str, list[dict]] = {}
    for it in payload.get("items") or []:
        by_slug.setdefault(it["slug"], []).append(it)

    aoc_index = {j["slug"]: j for j in enumerate_aocs()}
    counts = {"wrote": 0, "sha_mismatch": 0, "unknown_slug": 0}
    for slug, slug_items in by_slug.items():
        outcome = _import_one_slug(
            slug, slug_items, aoc_index, translator_id=translator_id, translator_kind=translator_kind,
        )
        counts[outcome] += 1
    print(
        f"[02d] wrote {counts['wrote']} cache files; "
        f"skipped sha_mismatch={counts['sha_mismatch']}, "
        f"unknown_slug={counts['unknown_slug']}",
        file=sys.stderr,
    )
    return 0


# ─────────────────────────────────────────────────────────────────  main ──


def write_manifest(*, n_jobs: int, ok: int, err: int, cached: int, translator_id: str, translator_kind: str) -> None:
    cache.write_json(MANIFEST, {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_aocs": n_jobs,
        "counts": {"ok": ok, "err": err, "cached": cached},
        "translator": translator_id,
        "translator_kind": translator_kind,
        "fuzzy_threshold": FUZZY_THRESHOLD,
        "wiki_hint_char_cap": WIKI_HINT_CHAR_CAP,
    }, sort_keys=True)


def _build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--provider", default="ollama", choices=("anthropic", "ollama", "manual"),
        help="extraction backend (default: ollama)",
    )
    ap.add_argument(
        "--model", default=None,
        help=(
            "model id (default per provider: "
            f"anthropic={providers.DEFAULT_ANTHROPIC_MODEL}, ollama={providers.DEFAULT_OLLAMA_MODEL})"
        ),
    )
    ap.add_argument(
        "--ollama-url", default=providers.DEFAULT_OLLAMA_URL,
        help="Ollama chat endpoint (default: localhost:11434)",
    )
    ap.add_argument("--limit", type=int, default=0, help="cap on AOCs (0 = all)")
    ap.add_argument(
        "--slug", action="append", default=None,
        help="restrict to specific AOC slug(s); repeatable. Useful for spot-checks.",
    )
    ap.add_argument(
        "--workers", type=int, default=1,
        help=(
            "concurrent AOCs to process (default 1, sequential). For Ollama, "
            "the server must be started with OLLAMA_NUM_PARALLEL >= workers "
            "(default 4 in current Ollama) or extra requests just queue. For "
            "Anthropic, respect your account's RPM/concurrency limits."
        ),
    )
    ap.add_argument("--refresh", action="store_true", help="re-extract even if cached")
    roundtrip.add_arguments(ap)
    return ap


def _select_jobs(refresh: bool, limit: int, slugs: list[str] | None) -> list[dict]:
    jobs = enumerate_aocs()
    if slugs:
        wanted = set(slugs)
        jobs = [j for j in jobs if j["slug"] in wanted]
    if not refresh:
        jobs = [
            j for j in jobs
            if is_stale(load_existing(j["slug"]), j["lien_sha"], j["wiki_meta"]["wiki_source_revision"])
        ]
    if limit:
        jobs = jobs[:limit]
    return jobs


def _make_provider(args) -> tuple[object | None, str]:
    """Returns (provider, translator_id). provider is None for manual mode."""
    return providers.make_provider(args.provider, model=args.model, ollama_url=args.ollama_url)


def _print_manual_listing(jobs: list[dict]) -> int:
    for j in jobs:
        print(f"  missing: {j['slug']}.json", file=sys.stderr)
    print(
        f"[02d] manual provider: {len(jobs)} AOCs need extraction. "
        f"Use --emit-todo PATH to dump them, fill in facts offline, then "
        f"--import PATH --translator-id <id> to write cache files.",
        file=sys.stderr,
    )
    return 1


def _process_one_job(provider, translator_id: str, job: dict) -> tuple[int, int]:
    """Run one AOC extraction + cache write. Returns (ok, err) where each is
    0 or 1. Errors are printed to stderr; exceptions surface to the caller."""
    facts, errors = extract_one_aoc(provider, job)
    if errors and not facts:
        for e in errors[:4]:
            print(f"  err {job['slug']}: {e[:160]}", file=sys.stderr)
        return 0, 1
    write_cache(
        slug=job["slug"],
        facts=facts,
        cahier_meta=job["cahier_meta"],
        wiki_meta=job["wiki_meta"],
        translator_id=translator_id,
        translator_kind=provider.kind,
    )
    return 1, 0


def _run_extraction_loop(
    provider, translator_id: str, jobs: list[dict], workers: int = 1,
) -> tuple[int, int]:
    if workers <= 1:
        ok = err = 0
        for job in tqdm(jobs, desc="terroir-facts", leave=False):
            ok_one, err_one = _process_one_job(provider, translator_id, job)
            ok += ok_one
            err += err_one
            time.sleep(0.05)
        return ok, err
    return _run_parallel(provider, translator_id, jobs, workers)


def _run_parallel(provider, translator_id: str, jobs: list[dict], workers: int) -> tuple[int, int]:
    ok = err = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_process_one_job, provider, translator_id, j): j for j in jobs}
        for fut in tqdm(as_completed(futures), total=len(jobs),
                        desc="terroir-facts", leave=False):
            try:
                ok_one, err_one = fut.result()
            except Exception as e:  # noqa: BLE001
                print(f"  err {futures[fut]['slug']}: worker exception: {e}", file=sys.stderr)
                err += 1
                continue
            ok += ok_one
            err += err_one
    return ok, err


def _check_inputs() -> int:
    if not EXTRACTED.exists():
        print(
            "error: raw/inao/cahier-extracted is missing — run 02_extract_cahiers.py first",
            file=sys.stderr,
        )
        return 1
    if not WIKI_AOCS.exists():
        print(
            "warning: raw/wikipedia/aocs/fr is missing — bullets will be cahier-only. "
            "Run 02b_fetch_aoc_lexicon.py to enable Wikipedia salience.",
            file=sys.stderr,
        )
    return 0


def _dispatch_emit_or_import(args) -> int | None:
    """Return an exit code if the run is an emit/import sub-command, else None."""
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


def main() -> int:
    args = _build_argparser().parse_args()
    rc = _check_inputs()
    if rc:
        return rc

    sub_rc = _dispatch_emit_or_import(args)
    if sub_rc is not None:
        return sub_rc

    jobs = _select_jobs(args.refresh, args.limit, args.slug)
    if not jobs:
        print("[02d] nothing to do — all caches up to date.", file=sys.stderr)
        return 0

    provider, translator_id = _make_provider(args)
    if provider is None:
        return _print_manual_listing(jobs)

    workers = max(1, args.workers)
    print(
        f"[02d] {len(jobs)} AOCs to extract "
        f"(provider={args.provider}, model={translator_id}, workers={workers})",
        file=sys.stderr,
    )
    ok, err = _run_extraction_loop(provider, translator_id, jobs, workers=workers)
    write_manifest(
        n_jobs=len(jobs), ok=ok, err=err, cached=0,
        translator_id=translator_id, translator_kind=provider.kind,
    )
    print(
        f"[02d] extracted ok={ok} err={err}; manifest: {MANIFEST.relative_to(ROOT)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
