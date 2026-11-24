"""Swiss rosters an ordinance leaves to an administrative ruling
(scripts/_lib/ch/roster_rulings.json): the table's shape, the reader, and
the transcription against the PDF stage 01 caches."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

import pytest
from _lib.ch import roster_rulings as rr
from _lib.grape_entity import match_variety

ROOT = Path(__file__).resolve().parents[1]
EXTRACTED = ROOT / "raw" / "ch" / "dokumente-extracted"
TABLE = rr.load()


def test_table_is_well_formed():
    assert set(TABLE) == {"schwyz", "zurichsee", "zurich", "jura", "glarus",
                          "appenzell-innerrhoden", "appenzell-ausserrhoden"}
    for slug, entry in TABLE.items():
        for key in ("ruling", "url", "sha256", "delegation", "clause", "annex", "verified"):
            assert entry.get(key), (slug, key)
        assert entry["url"].startswith("https://") and len(entry["sha256"]) == 64
        names = entry["varieties"]
        assert len(names) == len(set(names)) >= 40, slug
        assert entry["layout"] in ("table", "prose") and entry["annex_marker"], slug
        assert set(entry.get("read_as") or {}) <= set(names), slug


def test_an_identical_annex_points_at_the_list_it_repeats():
    raw = json.loads(rr.TABLE.read_text(encoding="utf-8"))
    assert raw["zurichsee"]["same_annex_as"] == "schwyz" and "varieties" not in raw["zurichsee"]
    assert TABLE["zurichsee"]["varieties"] == TABLE["schwyz"]["varieties"]


def test_jura_roster_is_the_directives_annex():
    """Jura's ordinance names no variety (Art. 12: the OIV list for
    Switzerland, the cadastre); the Département's directives of 11 April 2019
    do, in Annexe 1 — two columns, whites then reds."""
    jura = TABLE["jura"]
    assert "916.141.1" in jura["ruling"] and "annexe 1" in jura["clause"]
    assert len(jura["varieties"]) == 45
    got = {v["slug"]: v["name"] for v in rr.varieties(jura, match_variety)}
    assert got["pinot-noir"] == "Pinot noir" and got["muller-thurgau"] == "Riesling-sylvaner"
    assert {"pinot-gris", "gewurztraminer", "solaris", "johanniter", "divico", "gamaret",
            "garanoir", "cabernet-jura", "leon-millot", "marechal-foch"} <= set(got)
    # a bare breeder family name is no variety
    assert "Seibel" not in got.values()
    assert rr.source(jura)["url"] == "https://rsju.jura.ch/fr/viewdocument.html?idn=20192&id=38250"


def test_a_misprint_is_read_and_the_print_kept():
    glarus = TABLE["glarus"]
    assert "Läon Millot" in glarus["varieties"] and glarus["read_as"]["Läon Millot"] == "Léon Millot"
    got = {v["slug"]: v["name"] for v in rr.varieties(glarus, match_variety)}
    assert got.get("leon-millot") == "Léon Millot" and "marechal-foch" in got


def test_reader_resolves_names_and_skips_breeder_codes():
    got = {v["slug"]: v for v in rr.varieties(TABLE["schwyz"], match_variety)}
    # the regulator's spellings bind their varieties
    assert got["pinot-noir"]["name"] == "Blauburgunder"
    assert got["muller-thurgau"]["name"] == "Riesling-Silvaner"
    assert got["chasselas"]["name"] == "Gutedel"
    assert got["savagnin"]["name"] == "Heida"            # "Savagnin blanc" is the same pill
    assert got["irsai-oliver"]["name"] == "Muskat Oliver"
    assert {"raeuschling", "completer", "divico", "souvignier-gris", "zweigelt"} <= set(got)
    assert all(v["role"] == "principal" for v in got.values())
    # a breeder code is no variety name
    assert not any(re.match(r"^(CAL|VB|Lac) ?\d", v["name"]) for v in got.values())
    assert len(got) >= 95


def test_zurich_reads_its_own_annex():
    """Zürich's list (Sept. 2022) is not Schwyz's (July 2025): it writes
    "Cabaret noir" and "Elbling rot" / "Elbling weiss", and has Caberneuf and
    Muscat blanc where Schwyz has Heida and Gelber Muskateller."""
    zh, sz = TABLE["zurich"]["varieties"], TABLE["schwyz"]["varieties"]
    assert len(zh) == 130 and "Caberneuf" in zh and "Heida" not in zh and "Heida" in sz
    got = {v["slug"] for v in rr.varieties(TABLE["zurich"], match_variety)}
    assert {"pinot-noir", "raeuschling", "muller-thurgau", "cabaret-noir", "elbling"} <= got
    assert len(got) >= 95


def test_source_cites_the_ruling_and_the_clause():
    src = rr.source(TABLE["zurichsee"])
    assert src["kind"] == "cantonal-reglement-roster"
    assert "Allgemeinverfügung «AOC Zürichsee» vom 28. Juli 2025" in src["label"]
    assert src["applied_by"].startswith("Ziff. 2.4 Rebsortenverzeichnis")
    assert "not read" not in src["applied_by"]


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", s)


@pytest.mark.parametrize("slug", sorted(TABLE))
def test_transcription_matches_the_cached_pdf(slug):
    """Every transcribed entry is on the annex pages of the PDF, and the
    pages hold no entry the transcription lacks. A scanned annex (Schwyz) is
    read with tesseract, a text PDF (Zürich) with pdftotext; letters and
    digits only, a near match accepted."""
    pdf = rr.RULINGS_DIR / f"{slug}.pdf"
    entry = TABLE[slug]
    if not pdf.exists() or not shutil.which("pdftoppm") or not (
            entry.get("text_layer") or shutil.which("tesseract")):
        pytest.skip("ruling PDF not fetched, or no OCR tools")
    from rapidfuzz import fuzz, process

    assert hashlib.sha256(pdf.read_bytes()).hexdigest() == entry["sha256"], \
        f"{slug}: the ruling changed — re-read the annex and update roster_rulings.json"
    first, last = str(entry["annex_pages"][0]), str(entry["annex_pages"][-1])
    if entry.get("text_layer"):
        text = subprocess.run(["pdftotext", "-layout", "-f", first, "-l", last, str(pdf), "-"],
                              check=True, capture_output=True, text=True).stdout
    else:
        tmp = pdf.parent / f".ocrtmp-{slug}"
        tmp.mkdir(exist_ok=True)
        try:
            subprocess.run(["pdftoppm", "-r", "300", "-f", first, "-l", last, "-gray", "-png",
                            str(pdf), str(tmp / "p")], check=True, capture_output=True)
            text = "\n".join(
                subprocess.run(["tesseract", str(png), "stdout", "-l", "deu", "--psm", "6",
                                "-c", "preserve_interword_spaces=1"],
                               check=True, capture_output=True, text=True).stdout
                for png in sorted(tmp.glob("p*.png")))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    body = text.split(entry["annex_marker"], 1)[1]
    if entry.get("annex_end"):
        body = body.split(entry["annex_end"], 1)[0]
    skip = set(entry.get("annex_skip") or [])
    if entry["layout"] == "prose":
        # a comma list: a hyphenated line break closed, "und" before the last
        flat = re.sub(r"-\n\s*(?=[a-zäöüé])", "", body.split("\f")[0])
        flat = re.sub(r"\s+und\s+", ", ", re.sub(r"\s+", " ", flat)).strip().rstrip(".")
        cells = [c.strip() for c in flat.split(",")]
    else:
        cells = [m.group(0) for line in body.splitlines()
                 for m in re.finditer(r"\S+(?: \S+)*", line)]
        # a cell wrapped inside its bracket ("VB 85-1 (Léon Millot x Maréchal" / "Foch)")
        joined: list[str] = []
        for c in cells:
            if joined and joined[-1].count("(") > joined[-1].count(")"):
                joined[-1] += " " + c
            else:
                joined.append(c)
        cells = joined
    # a cell is a name: a page number folds to a bare digit; running heads
    # and column headers are listed in `annex_skip`
    cells = [c for c in cells if c not in skip and re.search(r"[a-z]", _fold(c))]
    printed = [_fold(c) for c in cells]
    wanted = [_fold(n) for n in entry["varieties"]]
    assert len(printed) == len(wanted), (len(printed), len(wanted))
    for name, key in zip(entry["varieties"], wanted):
        hit = process.extractOne(key, printed, scorer=fuzz.ratio)
        assert hit and hit[1] >= 80, f"{slug}: «{name}» is not on the annex page (best {hit})"
    for cell, key in zip(cells, printed):
        hit = process.extractOne(key, wanted, scorer=fuzz.ratio)
        assert hit and hit[1] >= 80, f"{slug}: the page prints «{cell}», the table lacks it"


def test_records_take_the_ruling_roster():
    if not (EXTRACTED / "schwyz.json").exists():
        pytest.skip("CH records not extracted")
    for slug in TABLE:
        rec = json.loads((EXTRACTED / f"{slug}.json").read_text(encoding="utf-8"))
        assert rec["n_grapes"] >= 25, slug
        roster = [s for s in rec["sources"] if s["kind"] == "cantonal-reglement-roster"]
        assert len(roster) == 1, slug
        assert roster[0]["url"] == (TABLE[slug].get("page_url") or TABLE[slug]["url"]), slug


def test_no_cached_reglement_is_an_app_shell():
    """Uri's LexFind link answered with its app shell, cached as
    reglement.pdf from May to November 2026: the card cited a document
    nobody had read."""
    base = ROOT / "raw" / "ch" / "reglements"
    if not base.exists():
        pytest.skip("CH règlements not fetched")
    bad = [str(p.relative_to(ROOT)) for p in base.glob("*/reglement.pdf")
           if p.read_bytes().lstrip()[:5] != b"%PDF-"]
    assert not bad, bad


def test_an_entry_naming_two_varieties_is_read_as_both():
    """«Elbling (rot und weiss)» (Schwyz, Zürichsee, Glarus) is the white
    Elbling and its red mutation; read whole, the gloss was dropped and the
    card showed the white one alone (card validator, 2026-11-17)."""
    for slug in ("schwyz", "glarus"):
        entry = TABLE[slug]
        assert entry["read_as"]["Elbling (rot und weiss)"] == ["Elbling weiss", "Elbling rot"]
        slugs = {v["slug"] for v in rr.varieties(entry, match_variety)}
        assert {"elbling", "roter-elbling"} <= slugs


def test_breeder_codes_are_told_from_names():
    code = rr._is_breeder_code
    for name in ("CAL 1-28", "VB 91-26-26", "Lac 1/02-05-35", "IRAC 2060",
                 "VB 85-1 (Léon Millot x Maréchal Foch)"):
        assert code(name), name
    for name in ("Seibel 9110", "VB Jura 25", "Cabernet VB", "Merlot", "Cabernello (MRAC 40)",
                 "Riesling-Silvaner"):
        assert not code(name), name


def test_coverage_counts_what_the_card_leaves_out():
    cov = rr.coverage(TABLE["jura"], match_variety)
    shown = rr.varieties(TABLE["jura"], match_variety)
    assert cov["entries"] == len(TABLE["jura"]["varieties"]) == 45
    assert cov["varieties"] == len({v["slug"] for v in shown})
    # nine selection numbers; a bare family name and a selection named after
    # the canton are the two names no entry resolves
    assert cov["codes"] == 9 and cov["unknown_names"] == ["Seibel", "VB Jura 25"]
    # every entry is shown, a code or an unknown name; two entries can be one variety
    assert cov["varieties"] + cov["codes"] + cov["unknown"] <= cov["entries"]
    # a list read whole has nothing to disclose
    whole = {"varieties": ["Merlot", "Pinot noir"]}
    assert rr.coverage(whole, match_variety) == {
        "entries": 2, "varieties": 2, "codes": 0, "unknown": 0, "unknown_names": []}


def test_records_carry_the_coverage_the_card_prints():
    rec_dir = EXTRACTED
    if not (rec_dir / "schwyz.json").exists():
        pytest.skip("no extracted CH corpus")
    rec = json.loads((rec_dir / "schwyz.json").read_text(encoding="utf-8"))
    cov = rec.get("roster_coverage") or {}
    assert cov.get("entries") == 132 and cov.get("codes") and cov.get("unknown")
    assert cov["varieties"] == len({g["slug"] for g in rec["grapes"]["details"]})


def test_a_code_vivc_files_under_a_named_variety_is_that_variety():
    """Jura's Annexe 1 prints «VB 32-7», «VB 85-1 (Léon Millot x Maréchal
    Foch)» and «VB 91-26-29»: VIVC files the codes as synonyms of Ravel blanc
    #22331, Millot Foch #25055 and Satin noir #23826 (read 2026-11-17). They
    counted as breeder codes and were left off the card."""
    got = {v["slug"]: v["name"] for v in rr.varieties(TABLE["jura"], match_variety)}
    assert got["sauvignon-soyhieres"] == "VB 32-7"
    assert got["millot-foch"] == "VB 85-1"
    assert got["satin-noir"] == "VB 91-26-29"
    # a selection number VIVC files under no named variety stays a code
    assert not {"VB 91-26-26", "CAL 1-28", "VB SH-15"} & set(got.values())


def test_the_station_and_number_of_a_named_variety_is_read_as_it():
    """Glarus prints «Weinsberg (WE 88-101-13)», Zürich's later annex
    «Sauvitage (WE 88-101-13)»."""
    glarus = TABLE["glarus"]
    assert glarus["read_as"]["Weinsberg (WE 88-101-13)"] == "Sauvitage"
    assert "Sauvitage (WE 88-101-13)" in TABLE["zurich"]["varieties"]
    assert "sauvitage" in {v["slug"] for v in rr.varieties(glarus, match_variety)}


def test_the_lists_names_the_lexicon_lacked_are_read():
    """Lexicon pass of 2026-11-17 (live VIVC): what a list still leaves out
    is its breeder codes and one or two names VIVC does not hold."""
    left = {slug: rr.coverage(e, match_variety)["unknown_names"] for slug, e in TABLE.items()}
    assert left == {
        "schwyz": ["VB Cabernet"], "zurichsee": ["VB Cabernet"], "zurich": ["VB Cabernet"],
        "glarus": ["VB Cabernet"], "jura": ["Seibel", "VB Jura 25"],
        "appenzell-innerrhoden": ["Cabernet VB"], "appenzell-ausserrhoden": ["Muskat Tramin"]}
    got = {v["slug"]: v["name"] for v in rr.varieties(TABLE["schwyz"], match_variety)}
    # the red mutations are rows of their own (VIVC #24686, #24627)
    assert {"muller-thurgau", "roter-muller-thurgau", "raeuschling", "roter-raeuschling"} <= set(got)
    # «Cornalin / Landroter» is the Valais variety (OVV art. 56; VIVC #10240)
    assert got["rouge-du-pays"] == "Cornalin"
    assert {"millot-foch", "leon-millot", "marechal-foch"} <= set(got)
    ar = {v["slug"]: v["name"] for v in rr.varieties(TABLE["appenzell-ausserrhoden"], match_variety)}
    assert ar["verdelet"] == "Seibel 9110" and ar["de-chaunac"] == "De Chaunac"


def test_wine_types_are_read_from_the_acts_own_clauses():
    """Schwyz Ziff. 2.2 / 2.9 / 2.10, Zürich Ziff. III / VII / VIII; the
    Jura directives and the Appenzell and Glarus acts name no wine type."""
    want = {"white", "red", "rose", "sparkling", "semi-sparkling", "vin-de-liqueur",
            "vendanges-tardives", "grains-nobles"}
    for slug in ("schwyz", "zurichsee", "zurich"):
        stated = rr.styles(TABLE[slug])
        assert set(stated) == want, slug
        assert stated["sparkling"]["quote"].startswith("Auch Schaum-")
        assert "Rotweine" in stated["red"]["quote"] and "Roséwein" in stated["rose"]["quote"]
    assert "Ziff. 2.2" in rr.styles(TABLE["schwyz"])["sparkling"]["clause"]
    assert "Ziff. III" in rr.styles(TABLE["zurich"])["sparkling"]["clause"]
    for slug in ("jura", "glarus", "appenzell-innerrhoden", "appenzell-ausserrhoden"):
        assert rr.styles(TABLE[slug]) == {} and rr.types_source(TABLE[slug]) is None
    # the Zürich clauses sit in the ruling itself, its annex being published apart
    src = rr.types_source(TABLE["zurich"])
    assert src["kind"] == "cantonal-ruling" and src["url"].endswith("id=607")
    assert rr.types_source(TABLE["schwyz"]) is None


@pytest.mark.parametrize("slug", ["schwyz", "zurichsee", "zurich"])
def test_wine_type_clauses_match_the_cached_pdf(slug):
    """Every transcribed clause is on the pages of the act it is cited
    from (tesseract for the Schwyz scans, the OCR text layer for Zürich)."""
    entry = TABLE[slug]
    types = entry["wine_types"]
    doc = types.get("document")
    pdf = rr.RULINGS_DIR / (f"{slug}.types.pdf" if doc else f"{slug}.pdf")
    text_layer = bool((doc or entry).get("text_layer"))
    if not pdf.exists() or not shutil.which("pdftoppm") or not (
            text_layer or shutil.which("tesseract")):
        pytest.skip("ruling PDF not fetched, or no OCR tools")
    from rapidfuzz import fuzz

    assert hashlib.sha256(pdf.read_bytes()).hexdigest() == (doc or entry)["sha256"], slug
    first, last = str(types["pages"][0]), str(types["pages"][-1])
    if text_layer:
        text = subprocess.run(["pdftotext", "-layout", "-f", first, "-l", last, str(pdf), "-"],
                              check=True, capture_output=True, text=True).stdout
    else:
        tmp = pdf.parent / f".ocrtmp-types-{slug}"
        tmp.mkdir(exist_ok=True)
        try:
            subprocess.run(["pdftoppm", "-r", "300", "-f", first, "-l", last, "-gray", "-png",
                            str(pdf), str(tmp / "p")], check=True, capture_output=True)
            text = "\n".join(
                subprocess.run(["tesseract", str(png), "stdout", "-l", "deu", "--psm", "4"],
                               check=True, capture_output=True, text=True).stdout
                for png in sorted(tmp.glob("p*.png")))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    page = _fold(re.sub(r"-\n\s*", "", text))
    for item in types["clauses"]:
        score = fuzz.partial_ratio(_fold(item["quote"]), page)
        assert score >= 90, f"{slug}: {item['clause']} is not on pages {first}–{last} ({score:.0f})"


def test_records_carry_the_styles_the_act_states():
    if not (EXTRACTED / "schwyz.json").exists():
        pytest.skip("no extracted CH corpus")
    for slug in ("schwyz", "zurichsee", "zurich"):
        rec = json.loads((EXTRACTED / f"{slug}.json").read_text(encoding="utf-8"))
        assert {"white", "red", "rose", "sparkling", "vin-de-liqueur"} <= set(rec["styles"]), slug
        assert set(rec["styles_evidence"]) == set(rec["styles"]), slug
    zurich = json.loads((EXTRACTED / "zurich.json").read_text(encoding="utf-8"))
    assert [s["url"] for s in zurich["sources"] if s["kind"] == "cantonal-ruling"] == [
        TABLE["zurich"]["wine_types"]["document"]["url"]]
    jura = json.loads((EXTRACTED / "jura.json").read_text(encoding="utf-8"))
    assert not jura.get("styles")
