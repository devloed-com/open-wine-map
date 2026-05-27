"""Extract noteworthy terroir facts from each BE wine's link-to-terroir
section using a bounded LLM layer with dual-source grounding (EU single
document + Wikipedia).

BE analog of `scripts/sk/02d_extract_terroir_facts.py` with the CH-style
per-record source_lang twist: Flemish wines + Maasvallei extract from
the Dutch ENIG DOCUMENT and use `nl.wikipedia.org`; Walloon wines
extract from the French DOCUMENT UNIQUE and use `fr.wikipedia.org`.

In v1 the 4 BE wines with a fetchable EU single document (the 3 Flemish
DOPs + Maasvallei — all Dutch-language) have a parseable
`link_to_terroir`; the other 6 ship as content-stubs and 02d skips them.

Inputs per record:
  raw/be/dokumenten-extracted/<slug>.json       (BE record — source_lang,
                                                 link_to_terroir, EUR-Lex URL)
  raw/wikipedia/aocs/<lang>/<slug>.json          (Wikipedia article in
                                                 the record's source_lang)

Providers: anthropic / mistral / ollama / manual (mirrors SK/CH 02d).
Batch via `--batch --provider anthropic`.
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

EXTRACTED = ROOT / "raw" / "be" / "dokumenten-extracted"
WIKI_AOCS_ROOT = ROOT / "raw" / "wikipedia" / "aocs"
CACHE_DIR = ROOT / "raw" / "terroir-facts"
MANIFEST = CACHE_DIR / "manifest-be.json"

MIN_LIEN_CHARS = 400
FUZZY_THRESHOLD = 0.6
WIKI_HINT_CHAR_CAP = 1500


SUBSECTIONS = [
    {"key": "facteurs_naturels", "max_bullets": 5},
    {"key": "facteurs_humains", "max_bullets": 2},
    {"key": "produit", "max_bullets": 2},
    {"key": "interactions", "max_bullets": 1},
]


SUBSECTION_LABELS: dict[str, dict[str, str]] = {
    "nl": {
        "facteurs_naturels": "Natuurlijke factoren (geologie, bodems, klimaat, reliëf)",
        "facteurs_humains": "Historische en menselijke factoren (geschiedenis, praktijken)",
        "produit": "Kenmerken van het product (sensorisch profiel)",
        "interactions": "Causaal verband (terroir / wijn)",
    },
    "fr": {
        "facteurs_naturels": "Facteurs naturels (géologie, sols, climat, relief)",
        "facteurs_humains": "Facteurs historiques et humains (histoire, pratiques)",
        "produit": "Caractéristiques du produit (profil sensoriel)",
        "interactions": "Interactions causales (lien terroir / vin)",
    },
}


SUBSECTION_TOPICS: dict[str, dict[str, str]] = {
    "nl": {
        "facteurs_naturels": (
            "geologie, bodemtypes (krijt, leem, löss, zand, mergel, "
            "tuffeau), klimaat, reliëf, waterlopen, expositie, "
            "wijngaarden, gemeenten, Haspengouw, Hageland, Heuvelland, "
            "Maasvallei"
        ),
        "facteurs_humains": (
            "geschiedenis van de oorsprongsbenaming, wijnbouw- en "
            "wijnbereidingspraktijken, Belgische cultivars (Acolon, "
            "Dornfelder, Pinotin, Cabernet Cortis, Regent)"
        ),
        "produit": "kleuren, aroma's, structuur, opvoeding, sensorisch profiel van de wijnen",
        "interactions": (
            "expliciet verband tussen het terroir en het karakter van "
            "de wijn, expressie van bodem of klimaat in de wijn"
        ),
    },
    "fr": {
        "facteurs_naturels": (
            "géologie, types de sols (calcaire, limon, loess, sables, "
            "marnes, tuffeau), climat, relief, cours d'eau, exposition, "
            "vignobles, communes, Sambre, Meuse, Hesbaye, Condroz"
        ),
        "facteurs_humains": (
            "histoire de l'appellation, pratiques viticoles et "
            "œnologiques, cépages belges (Acolon, Régent, Pinotin, "
            "Solaris, Johanniter)"
        ),
        "produit": "couleurs, arômes, structure, élevage, profil sensoriel des vins",
        "interactions": "lien explicite entre le terroir et le caractère du vin, expression du sol ou du climat dans le vin",
    },
}


# Wikipedia section names that map to each subsection, per source_lang.
WIKI_TO_SUBSECTION: dict[str, dict[str, list[str]]] = {
    "nl": {
        "facteurs_naturels": [
            "Geografie", "Geologie", "Bodem", "Bodems", "Klimaat",
            "Ligging", "Wijnstreek", "Wijngaarden", "Reliëf",
            "Topografie", "Landschap",
        ],
        "facteurs_humains": [
            "Geschiedenis", "Etymologie", "Naam", "Druivenrassen",
            "Wijnbouw", "Wijnbereiding", "Wijnindustrie", "Tradities",
        ],
        "produit": [
            "Wijn", "Wijnen", "Beschrijving", "Karakter", "Stijlen",
            "Druiven",
        ],
        "interactions": [],
    },
    "fr": {
        "facteurs_naturels": [
            "Géographie", "Géologie", "Climat", "Sols", "Situation",
            "Présentation", "Aire géographique", "Aire d'appellation",
            "Vignoble", "Relief", "Hydrographie",
        ],
        "facteurs_humains": [
            "Histoire", "Étymologie", "Origines", "Cépages",
            "Encépagement", "Viticulture", "Production", "Vinification",
        ],
        "produit": [
            "Vins", "Description des vins", "Caractéristiques",
            "Types de vins", "Dégustation",
        ],
        "interactions": [],
    },
}
for _lang in ("nl", "fr"):
    WIKI_TO_SUBSECTION[_lang]["interactions"] = WIKI_TO_SUBSECTION[_lang]["facteurs_naturels"]


EXTRACT_SYSTEM: dict[str, str] = {
    "nl": """Selecteer belangrijke feiten over een Belgische wijn-oorsprongsbenaming uit TWEE bronnen: het EU enig document / productdossier (regelgevende autoriteit) en een uittreksel uit de Nederlandstalige Wikipedia (referentie voor het brede publiek, sommelier-vocabularium).

Doelpubliek: wijnliefhebbers of geïnformeerde sommeliers die geïnteresseerd zijn in specifieke eigenheden van de oorsprong. Belangrijk is: geologische formaties met hun standaardnaam, specifieke bodemtypes (löss, leem, krijt, mergel, tuffeau, alluviale grond, zandleem), lokaal klimaat en winden (zeeklimaat, gematigd maritiem klimaat), traditionele Belgische druivenrassen, kenmerkende wijnbouwpraktijken, een precies sensorisch profiel, gedateerde historische ankerpunten.

═══ BRON 1: Wikipedia-uittreksel (relevante secties) ═══
{wiki_hint}

═══ BRON 2: tekst van het enig document (in de gebruikersbericht hieronder) ═══

Behandelde subsectie: {label}
Voorkeurscategorieën: {topics}

Strenge regels:
- Elk item MOET worden ondersteund door MINSTENS ÉÉN citaat: `cahier_quote` (woordelijk uit het enig document) OF `wiki_quote` (woordelijk uit het bovenstaande Wikipedia-uittreksel). Beide zijn sterk aanbevolen wanneer beide bronnen hetzelfde feit dekken.
- Geef het enig document voorrang als primaire bron: gebruik `cahier_quote` telkens als het feit daar voorkomt.
- Voeg `wiki_quote` toe wanneer Wikipedia de standaardterm levert voor een feit dat het enig document met eigen woorden beschrijft.
- Als enkel Wikipedia een belangrijk feit vermeldt, behoud dan enkel `wiki_quote` — bij weergave wordt het aan Wikipedia toegeschreven.
- Citaten zijn WOORDELIJK (gekopieerd) uit de respectieve bron. Schrijf NOOIT tekst aan een bron toe die daar niet voorkomt.
- Geen waardeoordelen ("uitzonderlijk", "prestigieus" …).
- Geen externe conclusies. Geen cijfers die in geen van beide bronnen voorkomen.
- Maximaal {max_bullets} items, elk ≤ 140 tekens.
- Als noch het enig document noch Wikipedia een concreet belangrijk feit voor deze subsectie bevat, retourneer dan een lege lijst.

Antwoord ENKEL in JSON, zonder tekst ervoor of erna:
{{"facts": [{{"bullet": "…", "cahier_quote": "…", "wiki_quote": "…"}}, ...]}}
Gebruik een lege string "" voor een ontbrekend citaat.""",

    "fr": """Sélectionne des faits remarquables sur une appellation viticole belge à partir de DEUX sources : le document unique / cahier des charges UE (autorité réglementaire) et un extrait de Wikipédia en français (référence grand public, vocabulaire de sommelier).

Lecteur cible : amateur de vin ou sommelier informé intéressé par les spécificités de l'origine. Remarquable : formations géologiques avec leur nom standard, types de sols spécifiques (craie, limon, loess, marnes, tuffeau, sables, alluvions), climat local et vents (climat tempéré océanique), cépages traditionnels belges, pratiques viticoles marquantes, profil sensoriel précis, ancres historiques datées.

═══ SOURCE 1 : extrait Wikipédia (sections pertinentes) ═══
{wiki_hint}

═══ SOURCE 2 : texte du document unique (message utilisateur ci-dessous) ═══

Sous-section traitée : {label}
Catégories préférées : {topics}

Règles strictes :
- Chaque puce DOIT être étayée par AU MOINS UNE citation : `cahier_quote` (verbatim du document unique) OU `wiki_quote` (verbatim de l'extrait Wikipédia). Les deux sont fortement recommandées quand les deux sources couvrent le même fait.
- Privilégie le document unique comme source primaire : utilise `cahier_quote` chaque fois que le fait y figure.
- Ajoute `wiki_quote` quand Wikipédia fournit la terminologie standard pour un fait que le document décrit avec ses propres mots.
- Si seul Wikipédia mentionne un fait remarquable, ne garde que `wiki_quote` — au rendu il sera attribué à Wikipédia.
- Les citations sont VERBATIM (copier-coller) depuis leur source. N'attribue JAMAIS à une source un texte qui n'y figure pas.
- Pas de jugements de valeur ("exceptionnel", "prestigieux"…).
- Pas de conclusions externes. Pas de chiffres absents des deux sources.
- Maximum {max_bullets} puces, ≤ 140 caractères chacune.
- Si ni le document unique ni Wikipédia ne contiennent de fait concret remarquable pour cette sous-section, renvoie une liste vide.

Réponds UNIQUEMENT en JSON, sans préambule :
{{"facts": [{{"bullet": "…", "cahier_quote": "…", "wiki_quote": "…"}}, ...]}}
Utilise une chaîne vide "" pour la citation manquante.""",
}


USER_LEAD: dict[str, str] = {
    "nl": "Behandelde subsectie: {label}\n\nTekst van het enig document (Beschrijving van het verband):\n\n{lien}",
    "fr": "Sous-section traitée : {label}\n\nTexte du document unique (Description du lien) :\n\n{lien}",
}


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
    wiki_record: dict, lang: str, sub_key: str,
    char_cap: int = WIKI_HINT_CHAR_CAP,
) -> str:
    if not wiki_record or wiki_record.get("missing") or wiki_record.get("error"):
        return ""
    full = wiki_record.get("full_text") or ""
    if not full:
        return wiki_record.get("lead_extract", "")[:char_cap]
    headings = WIKI_TO_SUBSECTION.get(lang, {}).get(sub_key, [])
    sections = _index_wiki_sections(full, headings)
    pieces = [sections["__intro__"]] if sections.get("__intro__") else []
    for h in headings:
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


# ─────────────────────────────────────────── source-text + target resolution ──


def _resolve_lien_and_source(rec: dict) -> tuple[str, dict]:
    """Return (link_to_terroir text, source-provenance dict) for a BE
    record. Belgium has no national-spec fallback layer wired in v1, so
    this is just the on-disk ENIG-DOCUMENT / DOCUMENT-UNIQUE link section
    plus the EUR-Lex URL for cache attribution."""
    lien = rec.get("link_to_terroir") or ""
    src = rec.get("source") or {}
    eu_url = src.get("final_url") or src.get("source_url") or ""
    return lien, {"pdf_url": eu_url, "kind": "eu-oj"}


def collect_targets() -> list[dict]:
    out: list[dict] = []
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


def _wiki_record_for(slug: str, lang: str) -> dict:
    path = WIKI_AOCS_ROOT / lang / f"{slug}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


# ───────────────────────────────────────────────────────────── core loop ──


def _process_subsection(
    provider, model_id: str, record: dict, sub: dict, wiki_record: dict,
) -> tuple[list[dict], int, str]:
    lang = record.get("source_lang") or "nl"
    lien = record.get("link_to_terroir") or ""
    labels = SUBSECTION_LABELS[lang]
    topics = SUBSECTION_TOPICS[lang]
    label = labels[sub["key"]]
    topic = topics[sub["key"]]
    wiki_hint = _wiki_hint_for_subsection(wiki_record, lang, sub["key"])
    system = EXTRACT_SYSTEM[lang].format(
        wiki_hint=wiki_hint or "(geen Wikipedia-uittreksel beschikbaar / pas d'extrait Wikipédia disponible)",
        label=label,
        topics=topic,
        max_bullets=sub["max_bullets"],
    )
    user = USER_LEAD[lang].format(label=label, lien=lien)
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
    lang = record.get("source_lang") or "nl"
    wiki_record = _wiki_record_for(slug, lang)
    lien = record.get("link_to_terroir") or ""
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
        "country": "be",
        "source_lang": lang,
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
        "wiki_source_revision": wiki_record.get("revision") if wiki_record else None,
        "wiki_source_url": wiki_record.get("page_url") if wiki_record else None,
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
    if existing.get("country") != "be":
        return False
    cur_sha = cahier_sha(record.get("link_to_terroir") or "")
    if existing.get("cahier_source_sha") != cur_sha:
        return False
    lang = record.get("source_lang") or "nl"
    wiki = _wiki_record_for(slug, lang)
    cur_rev = wiki.get("revision") if wiki else None
    if existing.get("wiki_source_revision") != cur_rev:
        return False
    return True


# ─────────────────────────────────────────────────── round-trip (manual) ──


def _job_payload(record: dict) -> dict:
    slug = record["slug"]
    lien = record.get("link_to_terroir") or ""
    lang = record.get("source_lang") or "nl"
    wiki_record = _wiki_record_for(slug, lang)
    return {
        "slug": slug,
        "name": record.get("name") or slug,
        "lang": lang,
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
        lang = job["lang"]
        labels = SUBSECTION_LABELS[lang]
        topics = SUBSECTION_TOPICS[lang]
        for sub in SUBSECTIONS:
            wiki_hint = _wiki_hint_for_subsection(job["wiki_record"], lang, sub["key"])
            label = labels[sub["key"]]
            items.append({
                "slug": job["slug"],
                "lang": lang,
                "subsection": sub["key"],
                "subsection_label": label,
                "topics": topics[sub["key"]],
                "max_bullets": sub["max_bullets"],
                "system_prompt": EXTRACT_SYSTEM[lang].format(
                    wiki_hint=wiki_hint or "(no Wikipedia extract)",
                    label=label,
                    topics=topics[sub["key"]],
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
        "n_items": len(items),
        "items": items,
    }
    cache.write_json(out_path, payload)
    print(f"[02d/be] wrote {out_path} ({len(items)} items across "
          f"{len({i['slug'] for i in items})} wines)", file=sys.stderr)
    return 0


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
        return "unknown_slug"
    lien = rec.get("link_to_terroir") or ""
    cur_sha = cahier_sha(lien)
    first = slug_items[0]
    if first.get("cahier_source_sha") and first["cahier_source_sha"] != cur_sha:
        return "sha_mismatch"
    lang = rec.get("source_lang") or "nl"
    wiki_record = _wiki_record_for(slug, lang)
    facts = _classify_imported_facts(slug_items, lien)
    payload = {
        "country": "be",
        "source_lang": lang,
        "slug": slug,
        "name": rec.get("name") or slug,
        "facts": facts,
        "model": translator_id,
        "model_kind": translator_kind,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cahier_source_sha": cur_sha,
        "cahier_source_pdf_url": (rec.get("_terroir_source") or {}).get("pdf_url") or "",
        "cahier_source_kind": (rec.get("_terroir_source") or {}).get("kind") or "",
        "wiki_source_revision": wiki_record.get("revision") if wiki_record else None,
        "wiki_source_url": wiki_record.get("page_url") if wiki_record else None,
    }
    cache.write_json(CACHE_DIR / f"{slug}.json", payload)
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
    print(f"[02d/be] wrote {counts['wrote']} cache files; "
          f"skipped sha_mismatch={counts['sha_mismatch']}, "
          f"unknown_slug={counts['unknown_slug']}", file=sys.stderr)
    return 0


# ─────────────────────────────────────────────────────────────────  main ──


def _build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--provider", default="ollama",
        choices=("anthropic", "mistral", "ollama", "manual"),
    )
    ap.add_argument("--model", default=None)
    ap.add_argument("--ollama-url", default=providers.DEFAULT_OLLAMA_URL)
    ap.add_argument("--mistral-url", default=providers.DEFAULT_MISTRAL_URL)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument(
        "--batch", action="store_true",
        help="submit all wines to the provider Batch API",
    )
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
        print("[02d/be] batch: nothing to do.", file=sys.stderr)
        return 0
    print(f"[02d/be] batch: {len(targets)} wines (provider={args.provider}, "
          f"model={model_id})", file=sys.stderr)

    def run_loop(prov):
        global CACHE_DIR
        if getattr(prov, "kind", "") == "collecting":
            keep = CACHE_DIR
            CACHE_DIR = Path(tempfile.mkdtemp(prefix="batch-02d-be-"))
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
        sidecar=ROOT / "raw" / ".batch" / "02d-be.json",
        run_loop=run_loop,
    )
    return 0


def main() -> int:
    args = _build_argparser().parse_args()
    if not EXTRACTED.exists():
        print(f"error: {EXTRACTED} missing — run scripts/be/02_extract_pliegos.py first",
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
        print("[02d/be] nothing to do — all caches valid.", file=sys.stderr)
        return 0

    provider, model_id = providers.make_provider(
        args.provider, model=args.model, ollama_url=args.ollama_url,
        mistral_url=args.mistral_url,
    )
    if provider is None:
        print(f"[02d/be] manual provider: {len(targets)} wines need extraction. "
              f"Use --emit-todo PATH, fill facts offline, then --import PATH "
              f"--translator-id <id> to write cache files.", file=sys.stderr)
        return 1

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    workers = max(1, args.workers)
    print(f"[02d/be] {len(targets)} BE wines to extract "
          f"(provider={args.provider}, model={model_id}, workers={workers})",
          file=sys.stderr)
    n_done = 0
    n_facts = 0
    t0 = time.time()
    if workers <= 1:
        for rec in tqdm(targets, desc="terroir-be", leave=False):
            res = _process_record(provider, model_id, rec)
            n_done += 1
            n_facts += len(res.get("facts", []))
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(_process_record, provider, model_id, r): r for r in targets}
            for fut in tqdm(as_completed(futures), total=len(targets), desc="terroir-be", leave=False):
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
    print(f"[02d/be] done: {n_done} wines, {n_facts} facts, "
          f"{elapsed/60:.1f} min ({elapsed/max(1,n_done):.1f} s/wine)",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
