#!/usr/bin/env python3
"""Stage 02 of the drinks pipeline: one extracted record per drink GI.

Reads the index (stage 00) and the documents stage 01 fetched, and writes
raw/drinks/extracted/<slug>.json + _index.json:

- a GI with a technical file is sliced by `_lib/drinks/technical_file.py`
  from the application-language PDF (`pdftotext -layout`): description,
  geographical area + the NUTS units of section 4b, method, link, labelling.
  The Commission's English copy, where the register serves one, is sliced
  the same way into `translations.en` — an official translation, attributed
  as such on the card and used for the English locale in place of a machine
  one.
- a GI whose only document is an OJ publication (a registration after 2017:
  the single document of Reg. (EU) 2019/787, or a cider's Food-class single
  document) is read from the EUR-Lex HTML stage 01b cached under
  raw/drinks/oj-pages/ (`_lib/drinks/single_document.py`); without the page
  it is a stub that cites the publication.
- a GI with a curator-pinned national specification
  (raw/drinks/manual_overrides.json) and no register document is a stub that
  cites it; its area, when the pin states one (`geo_nuts`), still draws it.

The record contract is the wine pipelines' (country, slug, name, kind,
file_number, sections, section_roles, link_to_terroir, grapes, styles,
source, stub …) plus `pipeline: "drinks"`, `product_class`,
`drink_category`, `country_aliases` and `geo_nuts`. A drink's one style is
its category; `grapes` is empty here (the method section is scanned for
grape names in stage 04 for the grape-derived categories).

    .venv/bin/python scripts/drinks/02_extract_technical_files.py [--only SLUG …]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib import extract_index  # noqa: E402
from _lib.drinks import single_document as sd  # noqa: E402
from _lib.drinks import technical_file as tf  # noqa: E402

INDEX_PATH = ROOT / "raw" / "drinks" / "eambrosia" / "index.json"
FILES_DIR = ROOT / "raw" / "drinks" / "technical-files"
TEXT_DIR = FILES_DIR / ".text"
MANIFEST_PATH = FILES_DIR / "manifest.json"
OJ_DIR = ROOT / "raw" / "drinks" / "oj-pages"
NATIONAL_DIR = ROOT / "raw" / "drinks" / "national-specs"
DETAIL_DIR = ROOT / "raw" / "drinks" / "register-detail"
OVERRIDES_PATH = ROOT / "raw" / "drinks" / "manual_overrides.json"
OUT_DIR = ROOT / "raw" / "drinks" / "extracted"
OUT_INDEX = OUT_DIR / "_index.json"

# The language a country's regulator writes in, for a document too short to
# tell (and for a stub).
COUNTRY_LANG = {
    "fr": "fr", "es": "es", "pt": "pt", "it": "it", "at": "de", "de": "de", "si": "sl",
    "hr": "hr", "hu": "hu", "ro": "ro", "bg": "bg", "gr": "el", "cy": "el", "sk": "sk",
    "cz": "cs", "lu": "fr", "be": "nl", "nl": "nl", "mt": "en",
}

SUMMARY_MAX = 480


def pdf_text(pdf: Path, layout: bool = True) -> str:
    """`pdftotext -layout` (or, with `layout=False`, its reading-order
    conversion), cached beside the PDFs (keyed on mtime)."""
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    cache = TEXT_DIR / (pdf.stem + (".txt" if layout else ".flow.txt"))
    if cache.exists() and cache.stat().st_mtime >= pdf.stat().st_mtime:
        return cache.read_text(encoding="utf-8", errors="replace")
    out = subprocess.run(
        ["pdftotext", *(["-layout"] if layout else []), str(pdf), "-"],
        capture_output=True, check=True,
    ).stdout.decode("utf-8", errors="replace")
    cache.write_text(out, encoding="utf-8")
    return out


def parse_pdf(pdf: Path, text: str, labels: frozenset[str]) -> tuple[dict, str]:
    """(parse, text mode). The layout conversion is what the e-form's tables
    need; a file printed in two columns — Grappa's is the page of the Gazzetta
    Ufficiale that carries its decree — comes out of it with the columns
    interleaved and next to no section, so a word-processor file that yields
    under three of the four text sections (description, area, method, link)
    is read again in reading order and the richer parse kept."""
    def weight(p: dict) -> int:
        return sum(1 for k in ("description", "geo_area", "method", "link") if p["roles"].get(k))

    parsed = tf.parse(text, labels)
    if parsed["layout"] != "form" or weight(parsed) >= 3:
        return parsed, "layout"
    flow = tf.parse(pdf_text(pdf, layout=False), labels)
    if weight(flow) > weight(parsed):
        return flow, "reading-order"
    return parsed, "layout"


def summary_of(description: str, link: str) -> str:
    """A one-paragraph blurb: the opening sentences of the description (the
    link's when there is none), cut at a sentence end."""
    text = re.sub(r"\s+", " ", description or link or "").strip()
    if len(text) <= SUMMARY_MAX:
        return text
    cut = text[:SUMMARY_MAX]
    stop = max(cut.rfind(". "), cut.rfind("; "), cut.rfind(": "))
    return (cut[: stop + 1] if stop > SUMMARY_MAX // 3 else cut.rsplit(" ", 1)[0] + " …").strip()


def app_unique_id(file_number: str) -> str:
    """The register's public identifier of a GI ("EUGI00000017290"), read
    from the detail record stage 01 cached — the id the other pipelines carry
    as `id_eambrosia` and the register's detail page is addressed by (the
    numeric `id` of the listing is the API's own)."""
    path = DETAIL_DIR / f"{file_number}.json"
    if not file_number or not path.exists():
        return ""
    try:
        return str(json.loads(path.read_text(encoding="utf-8")).get("appUniqueId") or "")
    except (ValueError, OSError):
        return ""


def base_record(entry: dict, meta: dict) -> dict:
    return {
        "pipeline": "drinks",
        "country": entry["country"],
        **({"country_aliases": entry["country_aliases"]} if entry["country_aliases"] else {}),
        "product_class": entry["product_class"],
        "drink_category": entry["drink_category"],
        "register_category": entry["register_category"],
        "kind": entry["kind"],
        "file_number": entry["file_number"],
        "id_eambrosia": app_unique_id(entry["file_number"]) if entry.get("register") is None else "",
        "name": entry["name"],
        **({"name_latin": entry["name_latin"]} if entry["name_latin"] else {}),
        **({"name_aliases": entry["name_aliases"]} if entry["name_aliases"] else {}),
        "registered_name": entry["registered_name"],
        "slug": entry["slug"],
        "source_lang": entry.get("source_lang") or COUNTRY_LANG.get(entry["country"], ""),
        "is_sub_denomination": False,
        "producer_group": meta.get("producer_group", ""),
        "publications": meta.get("publications") or [],
        "sections": {},
        "section_titles": {},
        "section_roles": {},
        "geo_area_brief": "",
        "geo_nuts": [],
        "link_to_terroir": "",
        "summary": "",
        "grapes": {"principal": [], "accessory": [], "observation": [], "details": []},
        "styles": [entry["drink_category"]],
        "stub": True,
    }


def national_parse(national: dict) -> dict | None:
    """The parse of a national specification stage 01 stored under
    raw/drinks/national-specs/, or None when it cannot be read."""
    path = NATIONAL_DIR / (national.get("filename") or "")
    if not national.get("filename") or not path.exists():
        return None
    fmt = (national.get("format") or path.suffix.lstrip(".")).lower()
    if fmt == "pdf":
        text = pdf_text(path)
        parsed, _mode = parse_pdf(path, text, frozenset())
        parsed["lang"] = tf.detect_language(text)
        return parsed
    if fmt in ("html", "htm"):
        return sd.parse(path.read_text(encoding="utf-8", errors="replace"))
    return None


def fill_roles(record: dict, parsed: dict) -> None:
    roles = parsed.get("roles") or {}
    record["sections"] = {k: v for k, v in roles.items() if k in tf.ROLES and v}
    record["section_titles"] = parsed.get("section_titles") or {}
    record["section_roles"] = {
        k: v for k, v in {
            "description": roles.get("description", ""),
            "geo_area": roles.get("geo_area", ""),
            "method": roles.get("method", ""),
            "link_to_terroir": roles.get("link", ""),
            "labelling": roles.get("labelling", ""),
        }.items() if v
    }
    record["geo_area_brief"] = roles.get("geo_area", "")
    record["geo_nuts"] = parsed.get("geo_nuts") or []
    record["link_to_terroir"] = roles.get("link", "")
    record["summary"] = summary_of(roles.get("description", ""), roles.get("link", ""))
    record["stub"] = not (roles.get("description") or roles.get("link") or roles.get("geo_area"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", default=[], help="slug (repeatable)")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    for path in (INDEX_PATH, MANIFEST_PATH):
        if not path.exists():
            print(f"error: {path} missing — run stages 00 and 01 first", file=sys.stderr)
            return 1
    entries = json.loads(INDEX_PATH.read_text(encoding="utf-8"))["drinks"]
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    overrides: dict = {}
    if OVERRIDES_PATH.exists():
        overrides = {k: v for k, v in json.loads(OVERRIDES_PATH.read_text(encoding="utf-8")).items()
                     if not k.startswith("_")}

    # Pass 1 — read every native technical file, to learn the e-form's row
    # labels per language over the whole corpus (a `--only` run included).
    native_text: dict[str, str] = {}
    lang_of: dict[str, str] = {}
    eform_by_lang: dict[str, list[str]] = defaultdict(list)
    for entry in entries:
        meta = manifest.get(entry["slug"]) or {}
        native = next((f for f in meta.get("files") or [] if f.get("lang") == "native"), None)
        if native is None:
            continue
        pdf = FILES_DIR / native["filename"]
        if not pdf.exists():
            continue
        text = pdf_text(pdf)
        native_text[entry["slug"]] = text
        lang = tf.detect_language(text) or COUNTRY_LANG.get(entry["country"], "")
        lang_of[entry["slug"]] = lang
        if tf.parse(text)["layout"].startswith("eform"):
            eform_by_lang[lang].append(entry["slug"])
    labels = {
        lang: tf.learn_labels([native_text[s] for s in slugs])
        for lang, slugs in eform_by_lang.items()
    }
    en_slugs = [
        e["slug"] for e in entries
        if any(f.get("lang") == "en" for f in (manifest.get(e["slug"]) or {}).get("files") or [])
    ]
    en_text = {}
    for slug in en_slugs:
        f = next(f for f in manifest[slug]["files"] if f.get("lang") == "en")
        pdf = FILES_DIR / f["filename"]
        if pdf.exists():
            en_text[slug] = pdf_text(pdf)
    en_labels = tf.learn_labels(
        [t for t in en_text.values() if tf.parse(t)["layout"].startswith("eform")]
    )

    selected = entries
    if args.only:
        wanted = set(args.only)
        selected = [e for e in entries if e["slug"] in wanted]
    if args.limit:
        selected = selected[: args.limit]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index: dict[str, dict] = {}
    counts: Counter = Counter()
    for entry in selected:
        slug = entry["slug"]
        meta = manifest.get(slug) or {}
        record = base_record(entry, meta)
        source: dict = {
            "kind": "",
            "register_url": (
                "https://ec.europa.eu/agriculture/eambrosia/geographical-indications-register/details/"
                + record["id_eambrosia"]
            ) if record["id_eambrosia"] else "",
            "publications": meta.get("publications") or [],
            "product_specification_link": meta.get("product_specification_link", ""),
        }
        native = next((f for f in meta.get("files") or [] if f.get("lang") == "native"), None)
        if slug in native_text and native is not None:
            lang = lang_of[slug]
            parsed, text_mode = parse_pdf(
                FILES_DIR / native["filename"], native_text[slug], labels.get(lang, frozenset())
            )
            fill_roles(record, parsed)
            record["source_lang"] = lang or record["source_lang"]
            source.update({
                "kind": "eambrosia-register-technical-file",
                "layout": parsed["layout"],
                **({"text_mode": text_mode} if text_mode != "layout" else {}),
                "ref": native.get("ref", ""),
                "attachment_uri": native.get("uri", ""),
                "attachment_url": native.get("url", ""),
                "filename": native.get("filename", ""),
                "sha256": native.get("sha256", ""),
                "bytes": native.get("bytes", 0),
                "fetched_at": native.get("fetched_at", ""),
            })
            others = [f for f in meta.get("files") or [] if f.get("lang") != "native"]
            if others:
                source["translations"] = [
                    {"lang": f["lang"], "ref": f.get("ref", ""), "attachment_uri": f.get("uri", ""),
                     "attachment_url": f.get("url", ""), "sha256": f.get("sha256", "")}
                    for f in others
                ]
            if slug in en_text and record["source_lang"] != "en":
                en_file = next(f for f in meta["files"] if f.get("lang") == "en")
                en, _mode = parse_pdf(FILES_DIR / en_file["filename"], en_text[slug], en_labels)
                en_roles = en.get("roles") or {}
                tr = {
                    "description": en_roles.get("description", ""),
                    "geo_area": en_roles.get("geo_area", ""),
                    "method": en_roles.get("method", ""),
                    "link_to_terroir": en_roles.get("link", ""),
                }
                tr = {k: v for k, v in tr.items() if v}
                if tr:
                    tr["summary"] = summary_of(tr.get("description", ""), tr.get("link_to_terroir", ""))
                    record["translations"] = {"en": tr}
            counts["technical-file"] += 1
        else:
            page = sd.cached_page(OJ_DIR, slug)
            parsed = sd.parse(page["html"], page.get("lang", "")) if page else None
            if parsed and (parsed["roles"].get("link") or parsed["roles"].get("description")):
                fill_roles(record, parsed)
                record["source_lang"] = page.get("lang") or record["source_lang"]
                source.update({
                    "kind": "eur-lex-single-document",
                    "layout": parsed["layout"],
                    "source_url": page.get("source_url", ""),
                    "final_url": page.get("final_url", ""),
                    "ref": page.get("ref", ""),
                    "sha256": page.get("sha256", ""),
                    "fetched_at": page.get("fetched_at", ""),
                })
                counts["single-document"] += 1
            else:
                record["stub_reason"] = (
                    "oj-publication-not-read" if meta.get("publications") else "no-register-document"
                )
                counts[record["stub_reason"]] += 1
        national = meta.get("national_spec")
        if national:
            source["national_spec"] = {
                k: national.get(k, "") for k in
                ("url", "final_url", "format", "source_org", "note", "sha256", "fetched_at")
            }
            if not source["kind"]:
                source["kind"] = "national-specification"
                # the national specification is the record's only document:
                # read it (a PDF with the form reader, an HTML page with the
                # single-document one)
                parsed = national_parse(national)
                if parsed and any(parsed["roles"].get(k) for k in ("link", "description", "geo_area")):
                    fill_roles(record, parsed)
                    record["source_lang"] = parsed.get("lang") or record["source_lang"]
                    record.pop("stub_reason", None)
                    source["layout"] = parsed["layout"]
                    counts["national-specification"] += 1
                    counts[("oj-publication-not-read" if meta.get("publications")
                            else "no-register-document")] -= 1
        if meta.get("register") == "gov-uk":
            source["register_url"] = meta.get("register_url", "")
            source["register"] = "gov-uk"
            record["source_lang"] = "en"
        if meta.get("register") == "ofag":
            source["register_url"] = meta.get("register_url", "")
            source["register"] = "ofag"
            record["source_lang"] = entry.get("source_lang") or record["source_lang"]
            link_doc = meta.get("national_link")
            if link_doc:
                # the cahier has no history or link section: they are sections
                # 7 and 8 of the summary of the application
                parsed = national_parse(link_doc)
                link = ((parsed or {}).get("roles") or {}).get("link", "")
                if link:
                    record["link_to_terroir"] = link
                    record["section_roles"]["link_to_terroir"] = link
                    record["sections"]["link"] = link
                    record["stub"] = False
                source["national_link"] = {
                    k: link_doc.get(k, "") for k in ("url", "final_url", "format", "source_org", "note", "sha256", "fetched_at")
                }
        pin = overrides.get(slug) or {}
        if pin.get("geo_nuts") and not record["geo_nuts"]:
            # the area a curator read from the pinned national specification
            record["geo_nuts"] = [{"code": c, "name": ""} for c in pin["geo_nuts"]]
            record["geo_nuts_source"] = "manual-override"
        if pin.get("geo_area_brief") and not record["geo_area_brief"]:
            record["geo_area_brief"] = pin["geo_area_brief"]
        record["source"] = source
        (OUT_DIR / f"{slug}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        index[slug] = {
            "country": record["country"],
            "file_number": record["file_number"],
            "name": record["name"],
            "slug": slug,
            "filename": f"{slug}.json",
            "product_class": record["product_class"],
            "drink_category": record["drink_category"],
            "kind": record["kind"],
            "stub": record["stub"],
            "source_kind": source["kind"],
            "sections_present": sorted(record["section_roles"]),
            "n_nuts": len(record["geo_nuts"]),
        }

    partial = extract_index.is_partial(args)
    extract_index.write_index(OUT_INDEX, index, partial=partial)
    if not partial:
        # a record that left the index (a GI the register no longer lists as
        # registered, a renamed slug) leaves the directory too
        for path in OUT_DIR.glob("*.json"):
            if path.name != "_index.json" and path.stem not in index:
                print(f"[prune] {path.name}: no longer in the index", file=sys.stderr)
                path.unlink()
    stubs = sum(1 for v in index.values() if v["stub"])
    no_link = [s for s, v in index.items() if not v["stub"] and "link_to_terroir" not in v["sections_present"]]
    no_area = [s for s, v in index.items() if "geo_area" not in v["sections_present"] and not v["n_nuts"]]
    print(f"[done] {len(index)} records ({dict(counts)}); stubs={stubs}; "
          f"no link section: {len(no_link)}; no area text or NUTS: {len(no_area)} "
          f"-> {OUT_DIR}", file=sys.stderr)
    for slug in no_link:
        print(f"[queue] {slug}: no link section read", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
