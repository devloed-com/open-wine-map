"""Extract noteworthy terroir facts from each CH wine's Wikipedia article
using a bounded LLM layer with Wikipedia-primary grounding.

CH analog of `scripts/at/02d_extract_terroir_facts.py` with one big
structural delta: cantonal règlements / Reglemente / regolamenti are
regulatory texts (variety lists, yields, area definitions) that do NOT
carry a "Beschreibung des Zusammenhangs" / "lien au terroir" narrative
section like EU single documents do. CH's terroir story is told on the
Wikipedia article (when one exists), so for Switzerland Wikipedia is the
**primary** grounding source, not a salience hint.

Inputs per record:
  raw/ch/dokumente-extracted/<slug>.json       (CH record — source_lang,
                                                 canton, règlement source URL)
  raw/wikipedia/aocs/<lang>/<slug>.json        (Wikipedia article for the
                                                 record's source_lang; required)

The 4-subsection structure + JSON schema match AT exactly so stage 04
renders CH facts through the same code path. The prompt is built in
the record's source language (fr / de / it) — first country in the
corpus where per-record source_lang varies.

Records without a usable Wikipedia article are skipped (CH-specific:
the règlement has no terroir narrative to fall back on). Sub-
denominations are skipped — they inherit the parent's bullets at the
rendering layer.

Providers: anthropic / mistral / ollama / manual (mirrors AT/DE 02d).
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

from _lib import batch, cache, llm_json, providers, roundtrip, terroir_verbatim  # noqa: E402

EXTRACTED = ROOT / "raw" / "ch" / "dokumente-extracted"
WIKI_AOCS_ROOT = ROOT / "raw" / "wikipedia" / "aocs"
CACHE_DIR = ROOT / "raw" / "terroir-facts"
MANIFEST = CACHE_DIR / "manifest-ch.json"

MIN_WIKI_CHARS = 600
FUZZY_THRESHOLD = 0.6
WIKI_HINT_CHAR_CAP = 2500


# Same 4-subsection structure as FR/AT — keeps the stage-04 render path
# identical. CH terroir vocabulary is described in 3 source languages
# below (matching the per-record source_lang).
SUBSECTIONS = [
    {"key": "facteurs_naturels", "max_bullets": 5},
    {"key": "facteurs_humains", "max_bullets": 2},
    {"key": "produit", "max_bullets": 2},
    {"key": "interactions", "max_bullets": 1},
]


SUBSECTION_LABELS: dict[str, dict[str, str]] = {
    "fr": {
        "facteurs_naturels": "Facteurs naturels (géologie, sols, climat, relief)",
        "facteurs_humains": "Facteurs historiques et humains (histoire, pratiques)",
        "produit": "Caractéristiques du produit (profil sensoriel)",
        "interactions": "Interactions causales (lien terroir / vin)",
    },
    "de": {
        "facteurs_naturels": "Natürliche Faktoren (Geologie, Böden, Klima, Relief)",
        "facteurs_humains": "Geschichtliche und menschliche Faktoren (Geschichte, Praktiken)",
        "produit": "Merkmale des Erzeugnisses (sensorisches Profil)",
        "interactions": "Kausale Wechselwirkungen (Zusammenhang Terroir / Wein)",
    },
    "it": {
        "facteurs_naturels": "Fattori naturali (geologia, suoli, clima, rilievo)",
        "facteurs_humains": "Fattori storici e umani (storia, pratiche)",
        "produit": "Caratteristiche del prodotto (profilo sensoriale)",
        "interactions": "Interazioni causali (legame terroir / vino)",
    },
}


SUBSECTION_TOPICS: dict[str, dict[str, str]] = {
    "fr": {
        "facteurs_naturels": "géologie, nature des sols, climat, relief, cours d'eau, exposition, climats / lieux-dits / communes",
        "facteurs_humains": "histoire de l'appellation, pratiques viticoles et œnologiques, cépages traditionnels suisses (Chasselas/Fendant, Petite Arvine, Humagne, Cornalin, Amigne, …)",
        "produit": "couleurs, arômes, structure, élevage, profil sensoriel des vins",
        "interactions": "lien explicite entre le terroir et le caractère du vin, expression du sol ou du climat dans le vin",
    },
    "de": {
        "facteurs_naturels": "Geologie, Bodenbeschaffenheit, Klima, Relief, Gewässer, Exposition, Lagen und Gemeinden",
        "facteurs_humains": "Geschichte der Ursprungsbezeichnung, weinbauliche und önologische Praktiken, schweizer Rebsorten (Riesling-Sylvaner / Müller-Thurgau, Blauburgunder, Räuschling, Completer, Heida, …)",
        "produit": "Farben, Aromen, Struktur, Reifung, sensorisches Profil der Weine",
        "interactions": "expliziter Zusammenhang zwischen dem Terroir und dem Charakter des Weins, Ausdruck von Boden oder Klima im Wein",
    },
    "it": {
        "facteurs_naturels": "geologia, natura dei suoli, clima, rilievo, corsi d'acqua, esposizione, zone e comuni",
        "facteurs_humains": "storia della denominazione, pratiche viticole ed enologiche, vitigni svizzeri (Merlot ticinese, Bondola, Americana, …)",
        "produit": "colori, aromi, struttura, affinamento, profilo sensoriale dei vini",
        "interactions": "legame esplicito fra il terroir e il carattere del vino, espressione del suolo o del clima nel vino",
    },
}


# Wikipedia section names that map to each subsection, per source-lang.
WIKI_TO_SUBSECTION: dict[str, dict[str, list[str]]] = {
    "fr": {
        "facteurs_naturels": [
            "Géographie", "Géologie", "Climat", "Sols", "Situation",
            "Présentation", "Aire géographique", "Aire d'appellation",
            "Vignoble", "Histoire géologique", "Relief", "Hydrographie",
        ],
        "facteurs_humains": [
            "Histoire", "Étymologie", "Origines", "Cépages",
            "Encépagement", "Viticulture", "Production", "Vinification",
        ],
        "produit": [
            "Vins", "Description des vins", "Caractéristiques",
            "Types de vins", "Dégustation", "Appellations",
        ],
        "interactions": [],
    },
    "de": {
        "facteurs_naturels": [
            "Geografie", "Geographie", "Geologie", "Lage", "Boden",
            "Böden", "Klima", "Weinbaugebiet", "Anbaugebiet", "Reblage",
            "Rebsorten", "Landschaft", "Topografie",
        ],
        "facteurs_humains": [
            "Geschichte", "Geschichtliches", "Etymologie",
            "Namensherkunft", "Rebsorten", "Weinbau", "Tradition",
            "Weinkultur",
        ],
        "produit": [
            "Weine", "Weintypen", "Weinstile", "Charakteristik",
            "Sensorik", "Wein",
        ],
        "interactions": [],
    },
    "it": {
        "facteurs_naturels": [
            "Geografia", "Geologia", "Suolo", "Suoli", "Clima",
            "Territorio", "Zona", "Vigneti",
        ],
        "facteurs_humains": [
            "Storia", "Etimologia", "Vitigni", "Vitivinicoltura",
            "Tradizione", "Produzione",
        ],
        "produit": [
            "Vini", "Caratteristiche", "Profilo", "Tipologie",
        ],
        "interactions": [],
    },
}
for lang in ("fr", "de", "it"):
    WIKI_TO_SUBSECTION[lang]["interactions"] = WIKI_TO_SUBSECTION[lang]["facteurs_naturels"]


EXTRACT_SYSTEM: dict[str, str] = {
    "fr": """Tu extrais des faits remarquables sur une appellation viticole suisse à partir de l'article Wikipédia francophone (source principale) et du contexte du règlement cantonal (variétés autorisées, communes de production, canton).

Lecteur cible: amateur de vin ou sommelier informé. Bemerkenswert: formations géologiques avec leur nom standard, types de sols spécifiques (calcaire, schiste, gneiss, molasse, moraines, limons, alluvions), climat local et vents (foehn, brises lacustres), cépages traditionnels suisses, pratiques viticoles marquantes, profil sensoriel précis, ancres historiques datées.

═══ SOURCE 1: Extrait Wikipédia (sections pertinentes) ═══
{wiki_hint}

═══ SOURCE 2: Contexte règlement cantonal (utilisateur ci-dessous) ═══

Sous-section traitée: {label}
Catégories préférées: {topics}

Règles strictes:
- Chaque puce DOIT être étayée par AU MOINS UNE citation: `wiki_quote` (verbatim de l'extrait Wikipédia) OU `cahier_quote` (verbatim du contexte règlement). Privilégie `wiki_quote` quand Wikipédia couvre le fait.
- Si seul Wikipédia mentionne un fait remarquable, ne garde que `wiki_quote` — il sera attribué à Wikipédia au rendu.
- Les citations sont VERBATIM (copier-coller) depuis leur source. N'attribue JAMAIS à une source un texte qui n'y figure pas.
- Pas de jugements de valeur ("exceptionnel", "prestigieux"…).
- Pas de chiffres absents des deux sources.
- Maximum {max_bullets} puces, ≤ 140 caractères chacune.
- Si ni Wikipédia ni le règlement ne contiennent de fait concret remarquable pour cette sous-section, renvoie une liste vide.

Réponds UNIQUEMENT en JSON, sans préambule:
{{"facts": [{{"bullet": "…", "cahier_quote": "…", "wiki_quote": "…"}}, ...]}}
Utilise une chaîne vide "" pour la citation manquante.""",

    "de": """Extrahiere bemerkenswerte Fakten über eine schweizerische Wein-Ursprungsbezeichnung aus dem deutschsprachigen Wikipedia-Artikel (Hauptquelle) und dem Kontext der kantonalen Verordnung (zugelassene Rebsorten, Produktionsgemeinden, Kanton).

Zielleser: Weinliebhaber oder informierte Sommeliers. Bemerkenswert: geologische Formationen mit Standardnamen, spezifische Bodentypen (Kalk, Schiefer, Gneis, Molasse, Moränen, Lehm, Alluvialböden), Lokalklima und Winde (Föhn, Seebrisen), traditionelle Schweizer Rebsorten, markante weinbauliche Praktiken, präzises sensorisches Profil, datierte historische Anker.

═══ QUELLE 1: Wikipedia-Auszug (relevante Abschnitte) ═══
{wiki_hint}

═══ QUELLE 2: Kontext der kantonalen Verordnung (Nutzernachricht unten) ═══

Behandelter Unterabschnitt: {label}
Bevorzugte Kategorien: {topics}

Strenge Regeln:
- Jeder Eintrag MUSS durch MINDESTENS EIN Zitat gestützt sein: `wiki_quote` (wörtlich aus dem Wikipedia-Auszug) ODER `cahier_quote` (wörtlich aus dem Verordnungs-Kontext). Bevorzuge `wiki_quote`, wenn Wikipedia den Fakt abdeckt.
- Wenn nur Wikipedia einen bemerkenswerten Fakt nennt, behalte nur `wiki_quote` — er wird Wikipedia zugeschrieben.
- Zitate sind WÖRTLICH (kopieren und einfügen). Schreibe NIEMALS einer Quelle einen Text zu, der dort nicht vorkommt.
- Keine Werturteile ("aussergewöhnlich", "prestigeträchtig"…).
- Keine Zahlen, die in keiner der beiden Quellen stehen.
- Maximal {max_bullets} Einträge, je ≤ 140 Zeichen.
- Wenn weder Wikipedia noch die Verordnung einen konkreten bemerkenswerten Fakt enthalten, gib eine leere Liste zurück.

Antworte NUR in JSON, ohne Text davor oder danach:
{{"facts": [{{"bullet": "…", "cahier_quote": "…", "wiki_quote": "…"}}, ...]}}
Verwende einen leeren String "" für das fehlende Zitat.""",

    "it": """Estrai fatti rilevanti su una denominazione vinicola svizzera dall'articolo Wikipedia in italiano (fonte principale) e dal contesto del regolamento cantonale (vitigni autorizzati, comuni di produzione, cantone).

Lettore target: appassionato di vino o sommelier informato. Rilevante: formazioni geologiche con il loro nome standard, tipi di suolo specifici (calcare, scisto, gneiss, molassa, morena, limo, alluvioni), clima locale e venti (föhn, brezze lacustri), vitigni tradizionali svizzeri, pratiche viticole marcate, profilo sensoriale preciso, ancore storiche datate.

═══ FONTE 1: Estratto Wikipedia (sezioni pertinenti) ═══
{wiki_hint}

═══ FONTE 2: Contesto del regolamento cantonale (messaggio utente sotto) ═══

Sottosezione trattata: {label}
Categorie preferite: {topics}

Regole rigorose:
- Ogni punto DEVE essere supportato da ALMENO UNA citazione: `wiki_quote` (testuale dall'estratto Wikipedia) O `cahier_quote` (testuale dal contesto del regolamento). Preferisci `wiki_quote` quando Wikipedia copre il fatto.
- Se solo Wikipedia menziona un fatto, tieni solo `wiki_quote` — sarà attribuito a Wikipedia.
- Le citazioni sono TESTUALI (copia-incolla). NON attribuire MAI a una fonte un testo che non vi compare.
- Niente giudizi di valore ("eccezionale", "prestigioso"…).
- Niente cifre assenti da entrambe le fonti.
- Massimo {max_bullets} voci, ≤ 140 caratteri ciascuna.
- Se né Wikipedia né il regolamento contengono un fatto concreto rilevante per questa sottosezione, restituisci una lista vuota.

Rispondi SOLO in JSON, senza testo prima o dopo:
{{"facts": [{{"bullet": "…", "cahier_quote": "…", "wiki_quote": "…"}}, ...]}}
Usa una stringa vuota "" per la citazione mancante.""",
}


USER_LEAD: dict[str, str] = {
    "fr": "Sous-section: {label}\n\nContexte règlement cantonal:\n\n{ctx}",
    "de": "Unterabschnitt: {label}\n\nKontext der kantonalen Verordnung:\n\n{ctx}",
    "it": "Sottosezione: {label}\n\nContesto del regolamento cantonale:\n\n{ctx}",
}


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
    wiki_record: dict, lang: str, sub_key: str, char_cap: int = WIKI_HINT_CHAR_CAP,
) -> str:
    """Pull relevant Wikipedia section text for a sub-section in lang."""
    if not wiki_record or wiki_record.get("missing") or wiki_record.get("error"):
        return ""
    full = wiki_record.get("full_text") or ""
    if not full:
        return (wiki_record.get("lead_extract") or wiki_record.get("extract", ""))[:char_cap]
    headings = WIKI_TO_SUBSECTION.get(lang, {}).get(sub_key, [])
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
    """Filter LLM facts that fail dual-source grounding (cahier OR wiki)."""
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
    """For CH there's no `link_to_terroir` section; the regulatory
    context is canton + variety list + commune list + règlement summary.
    Bullets sourced from this block carry `provenance=cahier`."""
    pieces: list[str] = []
    pieces.append(
        f"Canton: {(record.get('canton') or '').upper()} — "
        f"{record.get('region') or ''}"
    )
    summary = (record.get("section_roles") or {}).get("summary") or ""
    if summary:
        pieces.append(f"Résumé règlement: {summary}")
    grapes = (record.get("grapes") or {}).get("details") or []
    if grapes:
        names = ", ".join(g.get("name") or g.get("slug") for g in grapes[:30])
        pieces.append(f"Variétés autorisées: {names}")
    communes = record.get("geo_communes") or []
    if communes:
        names = ", ".join(c.get("name") or "" for c in communes[:30])
        pieces.append(f"Communes de production: {names}")
    sources_list = record.get("sources") or []
    reglement = next((s for s in sources_list
                      if s.get("kind") == "cantonal-reglement"), {})
    if reglement:
        pieces.append(
            f"Règlement: {reglement.get('label') or ''} "
            f"({reglement.get('shelf') or ''})"
        )
    return "\n".join(pieces)


def _wiki_record_for(slug: str, lang: str) -> dict:
    path = WIKI_AOCS_ROOT / lang / f"{slug}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def _has_usable_wiki(rec: dict) -> bool:
    """A wiki record is usable if it has either full_text or
    lead_extract above MIN_WIKI_CHARS."""
    if not rec or rec.get("missing") or rec.get("error"):
        return False
    full = rec.get("full_text") or ""
    if len(full) >= MIN_WIKI_CHARS:
        return True
    extract = rec.get("lead_extract") or rec.get("extract", "")
    return len(extract) >= MIN_WIKI_CHARS


def collect_targets() -> list[dict]:
    """Parent CH records that have a usable Wikipedia article in their
    source_lang. Sub-denominations inherit from parents and are skipped."""
    out: list[dict] = []
    for jp in sorted(EXTRACTED.glob("*.json")):
        if jp.name.startswith("_"):
            continue
        rec = json.loads(jp.read_text(encoding="utf-8"))
        if rec.get("is_sub_denomination"):
            continue
        lang = rec.get("source_lang") or "fr"
        wiki = _wiki_record_for(rec["slug"], lang)
        if not _has_usable_wiki(wiki):
            continue
        rec["_wiki_record"] = wiki
        rec["_cahier_ctx"] = _cahier_context(rec)
        out.append(rec)
    return out


# ─────────────────────────────────────────────────────────────── core loop ──


def _process_subsection(
    provider, model_id: str, record: dict, sub: dict,
) -> tuple[list[dict], int, str]:
    lang = record.get("source_lang") or "fr"
    labels = SUBSECTION_LABELS.get(lang, SUBSECTION_LABELS["fr"])
    topics = SUBSECTION_TOPICS.get(lang, SUBSECTION_TOPICS["fr"])
    label = labels[sub["key"]]
    topic = topics[sub["key"]]
    wiki = record.get("_wiki_record") or {}
    cahier_ctx = record.get("_cahier_ctx") or ""
    wiki_hint = _wiki_hint_for_subsection(wiki, lang, sub["key"])
    system = EXTRACT_SYSTEM[lang].format(
        wiki_hint=wiki_hint or "(aucun extrait Wikipédia disponible / kein Wikipedia-Auszug verfügbar / nessun estratto Wikipedia disponibile)",
        label=label,
        topics=topic,
        max_bullets=sub["max_bullets"],
    )
    user = USER_LEAD[lang].format(label=label, ctx=cahier_ctx)
    try:
        raw = provider.chat(system=system, user=user, max_tokens=1500, num_ctx=8192)
    except Exception as e:  # noqa: BLE001
        return [], 0, str(e)
    payload, perr = llm_json.parse_facts(raw)
    if payload is None:
        return [], 0, perr or "no JSON in response"
    raw_facts = payload.get("facts") or []
    kept, dropped = _ground_facts(raw_facts, cahier_ctx, wiki_hint)
    return kept, dropped, ""


def _process_record(provider, model_id: str, record: dict) -> dict:
    slug = record["slug"]
    lang = record.get("source_lang") or "fr"
    wiki = record.get("_wiki_record") or {}
    cahier_ctx = record.get("_cahier_ctx") or ""

    all_facts: list[dict] = []
    n_dropped_total = 0
    sub_errors: list[tuple[str, str]] = []
    for sub in SUBSECTIONS:
        kept, dropped, err = _process_subsection(
            provider, model_id, record, sub,
        )
        n_dropped_total += dropped
        if err:
            sub_errors.append((sub["key"], err))
            continue
        for f in kept:
            f["subsection"] = sub["key"]
            all_facts.append(f)

    sources_list = record.get("sources") or []
    reglement = next((s for s in sources_list
                      if s.get("kind") == "cantonal-reglement"), {})
    payload = {
        "country": "ch",
        "source_lang": lang,
        "slug": slug,
        "name": record.get("name") or slug,
        "facts": all_facts,
        "n_dropped": n_dropped_total,
        "model": model_id,
        "model_kind": provider.kind,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cahier_source_sha": wiki_sha(cahier_ctx),
        "cahier_source_pdf_url": reglement.get("url", ""),
        "cahier_source_kind": "cantonal-reglement",
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
    if existing.get("country") != "ch":
        return False
    cur_sha = wiki_sha(record.get("_cahier_ctx") or "")
    if existing.get("cahier_source_sha") != cur_sha:
        return False
    wiki = record.get("_wiki_record") or {}
    if existing.get("wiki_source_revision") != wiki.get("revision"):
        return False
    return True


# ─────────────────────────────────────────────────────── round-trip flow ──


def _job_payload(record: dict) -> dict:
    return {
        "slug": record["slug"],
        "name": record.get("name") or record["slug"],
        "lang": record.get("source_lang") or "fr",
        "cahier_ctx": record.get("_cahier_ctx") or "",
        "wiki_record": record.get("_wiki_record") or {},
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
        labels = SUBSECTION_LABELS.get(lang, SUBSECTION_LABELS["fr"])
        topics = SUBSECTION_TOPICS.get(lang, SUBSECTION_TOPICS["fr"])
        for sub in SUBSECTIONS:
            wiki_hint = _wiki_hint_for_subsection(job["wiki_record"], lang, sub["key"])
            label = labels[sub["key"]]
            items.append({
                "slug": job["slug"],
                "lang": lang,
                "subsection": sub["key"],
                "subsection_label": label,
                "max_bullets": sub["max_bullets"],
                "system_prompt": EXTRACT_SYSTEM[lang].format(
                    wiki_hint=wiki_hint or "(no Wikipedia extract)",
                    label=label,
                    topics=topics[sub["key"]],
                    max_bullets=sub["max_bullets"],
                ),
                "cahier_ctx": job["cahier_ctx"],
                "wiki_hint": wiki_hint,
                "cahier_source_sha": wiki_sha(job["cahier_ctx"]),
                "wiki_source_revision": (job["wiki_record"] or {}).get("revision"),
                "facts": [],
            })
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_items": len(items),
        "items": items,
    }
    cache.write_json(out_path, payload)
    print(f"[02d/ch] wrote {out_path} ({len(items)} items across "
          f"{len({i['slug'] for i in items})} wines)", file=sys.stderr)
    return 0


def _write_imported_cache(*, slug: str, name: str, lang: str, facts: list[dict],
                          cahier_ctx: str, wiki_record: dict,
                          translator_id: str, translator_kind: str,
                          reglement_url: str) -> None:
    payload = {
        "country": "ch",
        "source_lang": lang,
        "slug": slug,
        "name": name,
        "facts": facts,
        "model": translator_id,
        "model_kind": translator_kind,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cahier_source_sha": wiki_sha(cahier_ctx),
        "cahier_source_pdf_url": reglement_url,
        "cahier_source_kind": "cantonal-reglement",
        "wiki_source_revision": wiki_record.get("revision"),
        "wiki_source_url": wiki_record.get("page_url"),
    }
    cache.write_json(CACHE_DIR / f"{slug}.json", payload)


def _classify_imported_facts(slug_items: list[dict], cahier_ctx: str) -> list[dict]:
    out: list[dict] = []
    for it in slug_items:
        wiki_hint = it.get("wiki_hint") or ""
        sub_key = it.get("subsection") or "facteurs_naturels"
        kept, _ = _ground_facts(it.get("facts") or [], cahier_ctx, wiki_hint)
        for f in kept:
            f["subsection"] = sub_key
            out.append(f)
    return out


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
        rec = record_index.get(slug)
        if rec is None:
            counts["unknown_slug"] += 1
            continue
        cahier_ctx = rec.get("_cahier_ctx") or ""
        first = slug_items[0]
        if first.get("cahier_source_sha") and first["cahier_source_sha"] != wiki_sha(cahier_ctx):
            counts["sha_mismatch"] += 1
            continue
        sources_list = rec.get("sources") or []
        reglement = next((s for s in sources_list
                          if s.get("kind") == "cantonal-reglement"), {})
        facts = _classify_imported_facts(slug_items, cahier_ctx)
        _write_imported_cache(
            slug=slug,
            name=rec.get("name") or slug,
            lang=rec.get("source_lang") or "fr",
            facts=facts,
            cahier_ctx=cahier_ctx,
            wiki_record=rec.get("_wiki_record") or {},
            translator_id=translator_id,
            translator_kind=translator_kind,
            reglement_url=reglement.get("url", ""),
        )
        counts["wrote"] += 1
    print(f"[02d/ch] wrote {counts['wrote']} cache files; "
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
        print("[02d/ch] batch: nothing to do.", file=sys.stderr)
        return 0
    print(f"[02d/ch] batch: {len(targets)} wines (provider={args.provider}, "
          f"model={model_id})", file=sys.stderr)

    def run_loop(prov):
        global CACHE_DIR
        if getattr(prov, "kind", "") == "collecting":
            keep = CACHE_DIR
            CACHE_DIR = Path(tempfile.mkdtemp(prefix="batch-02d-ch-"))
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
        sidecar=ROOT / "raw" / ".batch" / "02d-ch.json",
        run_loop=run_loop,
    )
    return 0


def main() -> int:
    args = _build_argparser().parse_args()
    if not EXTRACTED.exists():
        print(f"error: {EXTRACTED} missing — run scripts/ch/02_extract_reglements.py first",
              file=sys.stderr)
        return 1

    sub_rc = _dispatch_emit_or_import(args)
    if sub_rc is not None:
        return sub_rc

    terroir_verbatim.emit_for_country(
        country="ch", extracted_dir=EXTRACTED, cache_dir=CACHE_DIR,
        default_source_lang="fr", cahier_source_kind="cantonal-reglement",
        only=args.only, log_prefix="[02d/ch]",
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
        print("[02d/ch] nothing to do — all caches valid.", file=sys.stderr)
        return 0

    provider, model_id = providers.make_provider(
        args.provider, model=args.model, ollama_url=args.ollama_url,
        mistral_url=args.mistral_url,
    )
    if provider is None:
        print(f"[02d/ch] manual provider: {len(targets)} wines need extraction.",
              file=sys.stderr)
        return 1

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[02d/ch] {len(targets)} CH wines to extract "
          f"(provider={args.provider}, model={model_id}, workers={args.workers})",
          file=sys.stderr)

    workers = max(1, args.workers)
    n_done = 0
    n_facts = 0
    t0 = time.time()
    if workers <= 1:
        for rec in tqdm(targets, desc="terroir-ch", leave=False):
            res = _process_record(provider, model_id, rec)
            n_done += 1
            n_facts += len(res.get("facts", []))
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(_process_record, provider, model_id, r): r for r in targets}
            for fut in tqdm(as_completed(futures), total=len(targets), desc="terroir-ch", leave=False):
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
    print(f"[02d/ch] done: {n_done} wines, {n_facts} facts, "
          f"{elapsed/60:.1f} min ({elapsed/max(1,n_done):.1f} s/wine)",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
