"""Health check for stage 02d terroir-fact caches.

Not a pipeline stage. Run after 02d (or on a schedule) to detect:
  - Drift: cached `cahier_source_sha` or `wiki_source_revision` no longer
    matches the current cahier / Wikipedia cache (a source was refreshed
    upstream; stage 02d should be re-run for affected AOCs).
  - Coverage erosion: per bullet, recompute fuzzy_coverage against the
    CURRENT cahier text and Wikipedia hint. If a bullet's coverage has
    dropped below the threshold, flag it (the source moved out from under
    the bullet).
  - Length cap: bullets whose text exceeds 140 chars (soft cap).
  - Provenance / sub-section / translator-kind distributions.

Outputs:
  - Per-AOC report on stderr (one line per AOC unless --verbose).
  - Aggregate summary (counts + medians) at the end.
  - Optional `--report PATH` writes the full per-AOC + per-bullet audit
    as JSON for follow-up tooling.

Exit code is non-zero only on internal errors (file I/O); audit findings
are reported but don't fail the run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TERROIR_FACTS = ROOT / "raw" / "terroir-facts"

# Per-country source dispatch. Each entry maps the country code carried in
# the terroir-facts cache to (extracted records dir, wiki cache dir,
# record-key for the lien text). Keep in sync with stage 02d's two
# variants — `scripts/02d_extract_terroir_facts.py` (FR) and
# `scripts/es/02d_extract_terroir_facts.py` (ES).
EXTRACTED_BY_COUNTRY = {
    "fr": ROOT / "raw" / "inao" / "cahier-extracted",
    "es": ROOT / "raw" / "es" / "pliegos-extracted",
}
WIKI_BY_COUNTRY = {
    "fr": ROOT / "raw" / "wikipedia" / "aocs" / "fr",
    "es": ROOT / "raw" / "wikipedia" / "aocs" / "es",
}
LIEN_FIELD_BY_COUNTRY = {
    "fr": "lien_au_terroir",
    "es": "link_to_terroir",
}

FUZZY_THRESHOLD = 0.6
BULLET_SOFT_CAP = 140
WIKI_HINT_CHAR_CAP = 1500

TOP_RE = re.compile(r"\b([1-9])°\s*[-–]\s*([A-ZÀ-Ý][^\n]{5,80})")
SUB_RE = re.compile(r"\b([a-c])\)\s*[-–]?\s*([A-ZÀ-Ý][^\n]{5,80})")

WIKI_TO_SUBSECTION_FR: dict[str, list[str]] = {
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
WIKI_TO_SUBSECTION_FR["interactions"] = WIKI_TO_SUBSECTION_FR["facteurs_naturels"]

# Spanish Wikipedia headings — mirror scripts/es/02d_extract_terroir_facts.py.
WIKI_TO_SUBSECTION_ES: dict[str, list[str]] = {
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
WIKI_TO_SUBSECTION_ES["interactions"] = WIKI_TO_SUBSECTION_ES["facteurs_naturels"]

WIKI_TO_SUBSECTION_BY_COUNTRY = {
    "fr": WIKI_TO_SUBSECTION_FR,
    "es": WIKI_TO_SUBSECTION_ES,
}


# Helpers duplicated from scripts/02d_extract_terroir_facts.py because the
# 02d module name starts with a digit and isn't directly importable. Keep in
# sync if either file changes.

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
        body_start = start + len(h) + 2
        section_text[h] = full[body_start:end].strip()
    return section_text


def _build_subsection_hint_fr(
    sub_key: str, wanted: list[str], section_text: dict[str, str]
) -> str:
    """FR wiki-hint format used by `scripts/02d_extract_terroir_facts.py`."""
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


def _build_subsection_hint_es(
    wiki_record: dict, headings: list[str]
) -> str:
    """ES wiki-hint format — mirrors `_wiki_hint_for_subsection` in
    `scripts/es/02d_extract_terroir_facts.py`. Different from the FR
    builder (lead intro always prepended; `# {h}` separator instead of
    « {h} » :; raw char-cap, no word-boundary trim) — keeping them in
    lockstep is what makes the audit's coverage check meaningful for ES
    `wiki`-only bullets."""
    full = wiki_record.get("full_text") or ""
    if not full:
        return (wiki_record.get("lead_extract") or "")[:WIKI_HINT_CHAR_CAP]
    section_text = _index_wiki_sections(full, headings)
    pieces = [section_text["__intro__"]] if section_text.get("__intro__") else []
    for h in headings:
        if h in section_text:
            pieces.append(f"# {h}\n{section_text[h]}")
    blob = "\n\n".join(pieces).strip()
    if blob:
        return blob[:WIKI_HINT_CHAR_CAP]
    return (wiki_record.get("lead_extract") or "")[:WIKI_HINT_CHAR_CAP]


def load_wiki_hints(slug: str, country: str) -> tuple[dict[str, str], dict | None]:
    wiki_dir = WIKI_BY_COUNTRY[country]
    headings_map = WIKI_TO_SUBSECTION_BY_COUNTRY[country]
    cache = wiki_dir / f"{slug}.json"
    empty = dict.fromkeys(headings_map, "")
    if not cache.exists():
        return empty, None
    data = json.loads(cache.read_text(encoding="utf-8"))
    if data.get("missing") or data.get("error"):
        return empty, data
    if country == "es":
        out = {
            sub_key: _build_subsection_hint_es(data, headings)
            for sub_key, headings in headings_map.items()
        }
        return out, data
    section_text = _index_wiki_sections(data.get("full_text", ""), data.get("sections", []))
    out = {
        sub_key: _build_subsection_hint_fr(sub_key, wanted, section_text)
        for sub_key, wanted in headings_map.items()
    }
    return out, data


# ─────────────────────────────────────────────────────────────── audit ──


def load_current_cahier(slug: str, country: str) -> tuple[str, str] | None:
    """Return (lien_text, sha) for the current cahier/pliego extract, or None."""
    extracted_dir = EXTRACTED_BY_COUNTRY[country]
    field = LIEN_FIELD_BY_COUNTRY[country]
    p = extracted_dir / f"{slug}.json"
    if not p.exists():
        return None
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    lien = (rec.get(field) or "").strip()
    return lien, cahier_sha(lien)


def audit_one(cache_path: Path) -> dict:
    """Audit one terroir-facts cache file. Returns a dict with the per-AOC
    findings (drift flags + per-bullet coverage)."""
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    slug = data.get("slug") or cache_path.stem
    country = data.get("country") or "fr"
    facts = data.get("facts") or []

    cur_cahier = load_current_cahier(slug, country)
    cur_lien = cur_cahier[0] if cur_cahier else ""
    cur_lien_sha = cur_cahier[1] if cur_cahier else ""
    cahier_drift = bool(cur_lien_sha) and cur_lien_sha != data.get("cahier_source_sha")

    wiki_hints, wiki_data = load_wiki_hints(slug, country)
    cur_wiki_rev = (wiki_data or {}).get("revision")
    wiki_drift = (
        cur_wiki_rev is not None and cur_wiki_rev != data.get("wiki_source_revision")
    )

    bullet_audits: list[dict] = []
    for f in facts:
        sub = f.get("subsection") or "facteurs_naturels"
        cov_c = fuzzy_coverage(f.get("cahier_quote", ""), cur_lien) if f.get("cahier_quote") else 0.0
        cov_w = fuzzy_coverage(f.get("wiki_quote", ""), wiki_hints.get(sub, "")) if f.get("wiki_quote") else 0.0
        cur_keep_c = cov_c >= FUZZY_THRESHOLD
        cur_keep_w = cov_w >= FUZZY_THRESHOLD
        still_grounded = cur_keep_c or cur_keep_w
        bullet_audits.append({
            "bullet": f.get("bullet", ""),
            "subsection": sub,
            "provenance": f.get("provenance", ""),
            "cached_cahier_coverage": f.get("cahier_coverage", 0.0),
            "cached_wiki_coverage": f.get("wiki_coverage", 0.0),
            "current_cahier_coverage": round(cov_c, 3),
            "current_wiki_coverage": round(cov_w, 3),
            "still_grounded": still_grounded,
            "over_length_cap": len(f.get("bullet", "")) > BULLET_SOFT_CAP,
        })
    return {
        "slug": slug,
        "n_facts": len(facts),
        "cahier_drift": cahier_drift,
        "wiki_drift": wiki_drift,
        "translator": data.get("translator") or data.get("model_id"),
        "translator_kind": data.get("translator_kind") or data.get("translator_kind"),
        "bullets": bullet_audits,
    }


def summarize(audits: list[dict]) -> dict:
    """Aggregate counters and medians over the per-AOC audits."""
    n_aocs = len(audits)
    bullets_per_aoc = [a["n_facts"] for a in audits]
    by_provenance: Counter[str] = Counter()
    by_subsection: Counter[str] = Counter()
    by_translator_kind: Counter[str] = Counter()
    over_cap = 0
    eroded_bullets = 0
    eroded_aocs: list[str] = []
    cahier_drift_n = sum(1 for a in audits if a["cahier_drift"])
    wiki_drift_n = sum(1 for a in audits if a["wiki_drift"])
    for a in audits:
        by_translator_kind[a["translator_kind"] or ""] += 1
        any_eroded = False
        for b in a["bullets"]:
            by_provenance[b["provenance"]] += 1
            by_subsection[b["subsection"]] += 1
            if b["over_length_cap"]:
                over_cap += 1
            if not b["still_grounded"]:
                eroded_bullets += 1
                any_eroded = True
        if any_eroded:
            eroded_aocs.append(a["slug"])
    return {
        "n_aocs": n_aocs,
        "bullets_total": sum(bullets_per_aoc),
        "bullets_per_aoc_median": statistics.median(bullets_per_aoc) if bullets_per_aoc else 0,
        "bullets_per_aoc_min": min(bullets_per_aoc) if bullets_per_aoc else 0,
        "bullets_per_aoc_max": max(bullets_per_aoc) if bullets_per_aoc else 0,
        "by_provenance": dict(by_provenance),
        "by_subsection": dict(by_subsection),
        "by_translator_kind": dict(by_translator_kind),
        "over_length_cap": over_cap,
        "eroded_bullets": eroded_bullets,
        "eroded_aocs": eroded_aocs,
        "cahier_drift_aocs": cahier_drift_n,
        "wiki_drift_aocs": wiki_drift_n,
    }


def print_per_aoc(audit: dict, verbose: bool) -> None:
    flags: list[str] = []
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
    flag_str = (" [" + ", ".join(flags) + "]") if flags else ""
    print(f"  {audit['slug']:40} n={audit['n_facts']:2} {audit['translator_kind'] or '-':12}{flag_str}")
    if verbose:
        for b in audit["bullets"]:
            note = ""
            if not b["still_grounded"]:
                note = (
                    f"  ⚠ eroded (now cahier={b['current_cahier_coverage']} "
                    f"wiki={b['current_wiki_coverage']})"
                )
            elif b["over_length_cap"]:
                note = "  ⚠ over length cap"
            print(f"      {b['provenance']:6} [{b['subsection'][:8]:>8}] {b['bullet'][:80]}{note}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--sample", type=int, default=0,
        help="audit only N AOCs (random sample); 0 = all (default)",
    )
    ap.add_argument(
        "--slug", action="append", default=None,
        help="restrict to specific AOC slug(s); repeatable",
    )
    ap.add_argument("--verbose", action="store_true", help="print every bullet, not just AOC summary")
    ap.add_argument("--quiet", action="store_true", help="suppress per-AOC lines (totals only)")
    ap.add_argument("--report", metavar="PATH", default=None, help="write full audit JSON to PATH")
    args = ap.parse_args()

    if not TERROIR_FACTS.exists():
        print("error: raw/terroir-facts is missing — run 02d first", file=sys.stderr)
        return 1

    files = sorted(p for p in TERROIR_FACTS.glob("*.json") if p.name != "manifest.json")
    if args.slug:
        wanted = set(args.slug)
        files = [p for p in files if p.stem in wanted]
    if args.sample and len(files) > args.sample:
        import random
        random.seed(0)
        files = sorted(random.sample(files, args.sample))

    if not files:
        print("[audit] no terroir-facts caches to audit.", file=sys.stderr)
        return 0

    print(f"[audit] {len(files)} AOC caches", file=sys.stderr)
    audits: list[dict] = []
    for p in files:
        try:
            a = audit_one(p)
        except Exception as e:  # noqa: BLE001
            print(f"  err {p.stem}: {e}", file=sys.stderr)
            continue
        audits.append(a)
        if not args.quiet:
            print_per_aoc(a, verbose=args.verbose)

    summary = summarize(audits)
    print("\n[audit] summary:", file=sys.stderr)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str), file=sys.stderr)

    if args.report:
        Path(args.report).write_text(json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "summary": summary,
            "aocs": audits,
        }, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        print(f"[audit] full report → {args.report}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
