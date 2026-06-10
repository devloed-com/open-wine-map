"""Generic extractor for the EU-register **fiche technique** (single
document), driven by a per-country config. Replaces the per-country copy
(cf. the CZ proof in `scripts/cz/02g_register_fiches.py`).

For each wine of `--country <cc>`: resolve the `singleDocTechFile`
attachment (`scripts/_lib/eambrosia_register.py`), download the PDF, slice
the product-specification block with the shared `parse_fiche_sections`
(anchor differs by fiche family — Family A nests the spec under
`I. <single document>`, Family B under `III. <product specification>`),
route the numbered sections with the country's own `SECTION_ROLE_KEYWORDS`,
and write a per-DOP sidecar with summary / grapes / geo_area /
link_to_terroir to `raw/<cc>/register-fiches-extracted/`.

Usage:
    .venv/bin/python scripts/extract_register_fiches.py --country cz --all
    .venv/bin/python scripts/extract_register_fiches.py --country sk --only nitrianska
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from _lib import eambrosia_register as er  # noqa: E402
from _lib.fiche_technique import parse_fiche_sections  # noqa: E402
from _lib.grape_entity import (  # noqa: E402
    flush_unknowns_queue,
    match_variety,
    set_pliego_context,
)

# Per-country config. `anchor` = the spec-block heading term(s); `end` =
# the heading that closes it (optional — the monotonic 1→N run stops at the
# numbering restart anyway). `kw` = dotted path to the module exposing
# SECTION_ROLE_KEYWORDS.
COUNTRY_CONFIG: dict[str, dict] = {
    # Family A — spec is the `I. <single document>` block
    "cz": {"anchor": ("JEDINÝ DOKLAD", "JEDNOTNÝ DOKUMENT"), "end": ("DALŠÍ INFORMACE",),
           "kw": "_lib.cz.jednotny_dokument"},
    "hr": {"anchor": ("JEDINSTVENI DOKUMENT", "SINGLE DOCUMENT"), "end": ("OTHER INFORMATION", "OSTALE INFORMACIJE", "DRUGI PODACI"),
           "kw": "_lib.hr.jedinstveni_dokument"},
    "hu": {"anchor": ("ÖSSZEFOGLALÓ DOKUMENTUM", "EGYSÉGES DOKUMENTUM"), "end": ("EGYÉB INFORMÁCIÓK",),
           "kw": "_lib.hu.egyseges_dokumentum"},
    # Family B — spec is nested under `III. <product specification>`. The
    # per-country EU-OJ keyword tables miss the fiche's section titles, so
    # supply them as `extra_kw` (merged in `_route`, country libs untouched).
    "sk": {"anchor": ("ŠPECIFIKÁCIA VÝROBKU",), "end": (),
           "kw": "_lib.sk.jednotny_dokument",
           "extra_kw": {"geo_area": ["vymedzená oblasť"], "grape_varieties": ["vinič hroznorodý"],
                        "link_to_terroir": ["spojenie so zemepisnou oblasťou"]}},
    "si": {"anchor": ("SPECIFIKACIJA PROIZVODA", "ENOTNI DOKUMENT"), "end": (),
           "kw": "_lib.si.enotni_dokument",
           "extra_kw": {"geo_area": ["opredeljeno območje"], "grape_varieties": ["vinsko grozdje"],
                        "link_to_terroir": ["povezava z geografskim območjem"]}},
    "bg": {"anchor": ("СПЕЦИФИКАЦИЯ НА ПРОДУКТА", "ЕДИНЕН ДОКУМЕНТ"), "end": (),
           "kw": "_lib.bg.edinen_dokument",
           "extra_kw": {"geo_area": ["определен район"], "grape_varieties": ["винен сорт лоза"],
                        "link_to_terroir": ["връзка с географския район"]}},
    "gr": {"anchor": ("ΠΡΟΔΙΑΓΡΑΦΕΣ ΠΡΟΪΟΝΤΟΣ", "ΕΝΙΑΙΟ ΕΓΓΡΑΦΟ"), "end": (),
           "kw": "_lib.gr.eniaio_engrafo",
           "extra_kw": {"geo_area": ["οριοθετημένη περιοχή"], "grape_varieties": ["οινοποιήσιμες ποικιλίες αμπέλου"],
                        "link_to_terroir": ["δεσμός με την γεωγραφική περιοχή"]}},
    "ro": {"anchor": ("CAIETUL DE SARCINI AL PRODUSULUI", "DOCUMENT UNIC"), "end": (),
           "kw": "_lib.ro.document_unic",
           "extra_kw": {"geo_area": ["zonă delimitată"], "grape_varieties": ["struguri de vinificaţie"],
                        "link_to_terroir": ["legătura cu zona geografică"]}},
}

_PAREN_RE = re.compile(r"\s*\(.*?\)\s*")
# The §6 list is numbered/bulleted: "* 01 Müller Thurgau", "01. SAVATIANO",
# "** 01. Fetească albă". Strip the leading bullets + ordinal so the real
# variety name reaches the matcher.
_LIST_PREFIX_RE = re.compile(r"^[\s*•·∙‣◦\-–—]*(?:\d{1,3}[.)]\s*|\d{1,3}\s+)?[\s*•·∙‣◦\-–—]*")
# §6 sub-structure headers + OIV/EU/national catch-all phrases + register
# page furniture that are not varieties (multilingual stoplist).
_NON_VARIETY = (
    "inventory", "súpis", "popis osnovnih", "apogr", "απογρ", "inventar",
    "списък", "seznam", "soupis",
    "oiv", "organiz", "organisation", "mednarodn", "medzinárodn", "международн",
    "internațion", "internation", "διεθν", "organizáci",
    "všechny další", "všetky odrody", "all other", "ostatní", "iné odrody",
    "druge sorte", "други сортове", "alte soiuri", "λοιπές", "άλλες ποικιλ", "egyéb fajt",
    "stvoreno dana", "tehnička dokumentacija", "vytvoř", "създаден",
    "e-bacchus", "e bacchus", "podklady", "podpůrné", "supporting",
)


def _norm(s: str) -> str:
    """Casefold + strip combining accents + fold Greek final sigma, so
    title↔keyword matching is robust across Latin-accented / Greek /
    Cyrillic scripts (the GR/BG section titles carry accents/final-σ)."""
    import unicodedata
    s = unicodedata.normalize("NFKD", s.casefold())
    return "".join(c for c in s if not unicodedata.combining(c)).replace("ς", "σ")


def _pdftotext(pdf: Path) -> str:
    try:
        r = subprocess.run(
            ["pdftotext", "-layout", str(pdf), "-"],
            capture_output=True, text=True, encoding="utf-8", timeout=60, check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return ""
    return r.stdout or ""


def _route(sections, titles, role_keywords, extra_kw=None):
    norm_titles = {n: _norm(t) for n, t in titles.items()}
    routed = {}
    for role in set(role_keywords) | set(extra_kw or {}):
        kws = list(role_keywords.get(role, ())) + list((extra_kw or {}).get(role, ()))
        for kw in kws:
            nkw = _norm(kw)
            hit = next((n for n, nt in norm_titles.items() if nkw in nt), None)
            if hit is not None:
                routed[role] = sections.get(hit, "")
                break
    return routed


def _parse_grapes(section_text):
    out = {"principal": [], "accessory": [], "observation": [], "details": []}
    seen = set()
    for line in (section_text or "").splitlines():
        low = line.lower()
        if any(p in low for p in _NON_VARIETY):
            continue
        cand = _PAREN_RE.sub(" ", line)
        cand = _LIST_PREFIX_RE.sub("", cand).strip(" .,;:\t·–-")
        if len(cand) < 3 or cand.startswith(("PDO-", "PGI-")) or len(cand) > 45:
            continue
        m = match_variety(cand)
        if m is None or m.slug in seen:
            continue
        seen.add(m.slug)
        out["principal"].append(m.slug)
        out["details"].append({"slug": m.slug, "name": cand, "role": "principal", "colour": m.colour})
    return out


def _summary(text, max_chars=600):
    t = re.sub(r"\s+", " ", text or "").strip()
    return t if len(t) <= max_chars else t[:max_chars].rsplit(". ", 1)[0] + "."


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--country", required=True, choices=sorted(COUNTRY_CONFIG))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    cfg = COUNTRY_CONFIG[args.country]
    role_keywords = importlib.import_module(cfg["kw"]).SECTION_ROLE_KEYWORDS
    pdf_dir = ROOT / "raw" / args.country / "register-fiches"
    out_dir = ROOT / "raw" / args.country / "register-fiches-extracted"
    index_in = ROOT / "raw" / args.country / "eambrosia" / "index.json"

    wines = json.loads(index_in.read_text(encoding="utf-8"))["wines"]
    if args.only:
        needles = [s.lower() for s in args.only]
        wines = [w for w in wines if any(n in w["slug"].lower() for n in needles)]
    elif not args.all:
        print("pass --all or --only <slug>", file=sys.stderr)
        return 2

    session = requests.Session()
    id_map = er.load_id_map(session=session)
    out_dir.mkdir(parents=True, exist_ok=True)
    index = {}
    n_ok = n_grapes = n_terroir = n_miss = 0
    for w in tqdm(wines, desc=f"{args.country}-register-fiches", leave=False):
        slug = w["slug"]
        set_pliego_context(f"{args.country}:{slug}")
        refs = er.attachment_refs(w["fileNumber"], id_map, session=session)
        uri = refs.get("single_doc_uri") if refs else None
        if not uri:
            n_miss += 1
            continue
        pdf = pdf_dir / f"{slug}.pdf"
        if args.refresh or not pdf.exists():
            if not er.fetch_attachment(uri, pdf, session=session):
                print(f"[warn] fetch failed: {slug}", file=sys.stderr)
                n_miss += 1
                continue
        sections, titles = parse_fiche_sections(_pdftotext(pdf), cfg["anchor"], cfg["end"])
        if not sections:
            print(f"[warn] no spec-block sections: {slug}", file=sys.stderr)
            n_miss += 1
            continue
        routed = _route(sections, titles, role_keywords, cfg.get("extra_kw"))
        grapes = _parse_grapes(routed.get("grape_varieties", ""))
        link = routed.get("link_to_terroir", "")
        (out_dir / f"{slug}.json").write_text(json.dumps({
            "country": args.country, "slug": slug, "name": w["name"],
            "file_number": w["fileNumber"],
            "summary": _summary(routed.get("description") or routed.get("geo_area") or ""),
            "grapes": grapes, "geo_area": routed.get("geo_area", ""),
            "link_to_terroir": link, "section_titles": titles,
            "source": {
                "kind": "eambrosia-register-fiche", "attachment_uri": uri,
                "ref": refs.get("single_doc_ref"), "url": er.ATTACHMENT_URL.format(uri=uri),
                "parser_template": "eu-fiche-technique-v1",
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        index[slug] = {"slug": slug, "file_number": w["fileNumber"],
                       "n_grapes": len(grapes["principal"]), "terroir_chars": len(link)}
        n_ok += 1
        n_grapes += bool(grapes["principal"])
        n_terroir += bool(link)

    set_pliego_context(None)
    (out_dir / "_index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    n_unknown = flush_unknowns_queue(
        ROOT / "raw" / args.country / "extraction-unknowns-register-fiches.json")
    print(
        f"[{args.country}] ok={n_ok} with_grapes={n_grapes} with_terroir={n_terroir} "
        f"miss={n_miss} unknown_varieties={n_unknown}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
