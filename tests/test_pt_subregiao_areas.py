"""PT sub-regiões drawn from the national act that delimits them
(scripts/_lib/pt/subregiao_areas.json, scripts/_lib/pt/subregiao_areas.py).

The table is a transcription of the act — Vinho Verde's nine sub-regiões
from Portaria n.º 668/2010, Anexo I, as republished by Portaria n.º 152/2015.
These tests hold it to the act and to the map: every name is printed in the
PDF stage 00 fetched, the PDF is the pinned one, the caderno cites no act the
entry has not reviewed, and the sub-regiões draw without a miss, inside their
appellation, without overlapping. Checks that need raw/ data skip on a
checkout without it.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import itertools
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.pt.subregiao_areas import (  # noqa: E402
    act_key,
    area_km2,
    cited_acts,
    legal_reference,
    load_table,
    outside_km2,
    pieces_for,
    unreviewed_acts,
)

TABLE = load_table()
EXTRACTED = ROOT / "raw" / "pt" / "cadernos-extracted"
DRE = ROOT / "raw" / "pt" / "dre"
CAOP = ROOT / "raw" / "pt" / "caop"


def _record(slug: str) -> dict | None:
    p = EXTRACTED / f"{slug}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def test_table_shape():
    assert TABLE, "subregiao_areas.json has no entry"
    for parent, entry in TABLE.items():
        for key in ("act", "act_label", "act_detail", "url", "file", "sha256", "pages",
                    "reviewed_acts", "verified", "subregioes"):
            assert entry.get(key), f"{parent}: {key} missing"
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry["verified"])
        for a in entry["reviewed_acts"]:
            assert a.get("act"), f"{parent}: reviewed act without a citation"
            assert a.get("effect"), f"{parent}: {a['act']} without its effect"
            assert cited_acts(a["act"]), f"{parent}: not an act citation: {a['act']}"
        for slug, sub in entry["subregioes"].items():
            assert slug.startswith(parent + "-"), slug
            assert sub.get("name"), slug
            assert sub.get("rows"), slug
            for row in sub["rows"]:
                assert row.get("distrito"), (slug, row)
                assert row.get("concelho"), (slug, row)
            for name, printed in (sub.get("printed_as") or {}).items():
                assert any(name in (r.get("freguesias") or []) for r in sub["rows"]), name
                assert printed, name
                assert all(isinstance(p, str) for p in printed), name


def test_pieces_follow_the_rows():
    sub = TABLE["vinho-verde"]["subregioes"]["vinho-verde-paiva"]
    pieces = pieces_for(sub)
    assert [(p.kind, p.name) for p in pieces] == [("concelho", "Castelo de Paiva"),
                                                  ("freguesias", "Cinfães")]
    assert [i.name for i in pieces[1].items] == ["Souselo", "Travanca"]


def test_cited_acts_reads_a_legal_reference():
    ref = ("Portaria n.º 668/2010, de 11 de agosto, alterada pela Portaria n.º\n949/2010, "
           "(retificada pela Declaração de Retificação n. º27/2015, de 12\nde junho) e Portaria "
           "nº 333/2016 e complementada com o Aviso\nn.º 7945/2022, de 19 de abril.")
    assert cited_acts(ref) == ["portaria 668/2010", "portaria 949/2010",
                               "declaracao de retificacao 27/2015", "portaria 333/2016",
                               "aviso 7945/2022"]
    assert act_key("Declaração de Retificação", "47", "2014") == "declaracao de retificacao 47/2014"


def test_cited_acts_reads_lists_and_loose_forms():
    """Code review 2026-10-13: an unreviewed act cited in any of these forms
    must still reach the STALE check."""
    assert cited_acts("Portarias n.os 668/2010 e 949/2010") == [
        "portaria 668/2010", "portaria 949/2010"]
    assert cited_acts("Portaria n.º 668/2010 e n.º 949/2010") == [
        "portaria 668/2010", "portaria 949/2010"]
    assert cited_acts("Portaria 333/2016") == ["portaria 333/2016"]
    assert cited_acts("Decretos-Leis n.os 263/99, 449/99 e 93/2006") == [
        "decreto-lei 263/1999", "decreto-lei 449/1999", "decreto-lei 93/2006"]
    assert cited_acts("Decreto Lei n.º 61/2020") == ["decreto-lei 61/2020"]
    assert cited_acts("Decreto-\nLei n.º 61/2020") == ["decreto-lei 61/2020"]
    assert cited_acts("Declaração de Retifica-\nção n.º 27/2015") == [
        "declaracao de retificacao 27/2015"]
    assert cited_acts("Aviso n.º 21430/2026/2, de 31 de agosto") == ["aviso 21430/2026"]


def test_legal_reference_ends_at_the_next_heading_only():
    record = {"sections": {"other": (
        "b) Decisão nacional de aprovação:\nReferência jurídica: Portaria n.º 1/2020, "
        "alterada (alínea\nc) do artigo 3.º) pela Portaria n.º 2/2021\n\n"
        "c) Outros documentos:\nDecreto-Lei n.º 61/2020")}}
    assert cited_acts(legal_reference(record)) == ["portaria 1/2020", "portaria 2/2021"]
    assert legal_reference({"sections": {"other": "no reference here"}}) is None


@pytest.mark.skipif(not EXTRACTED.exists(), reason="raw/pt/cadernos-extracted not present")
def test_every_sub_region_is_a_record_of_its_parent():
    for parent, entry in TABLE.items():
        for slug, sub in entry["subregioes"].items():
            rec = _record(slug)
            assert rec is not None, f"{slug}: no extracted record"
            assert rec.get("parent_slug") == parent, slug
            assert rec.get("is_sub_denomination"), slug
            assert rec.get("name") == sub["name"], (slug, rec.get("name"), sub["name"])


@pytest.mark.skipif(not EXTRACTED.exists(), reason="raw/pt/cadernos-extracted not present")
def test_caderno_cites_no_unreviewed_act():
    """An act the caderno's legal reference cites may have changed the
    table: every one must have been read for its effect on it."""
    for parent, entry in TABLE.items():
        rec = _record(parent)
        assert rec is not None, parent
        assert unreviewed_acts(rec, entry) == [], parent


def _act_text(entry: dict) -> str:
    pdf = DRE / entry["file"]
    first, last = entry["pages"]
    out = subprocess.run(["pdftotext", "-f", str(first), "-l", str(last), str(pdf), "-"],
                         capture_output=True, text=True, check=True).stdout
    # hyphenated line breaks joined, whitespace collapsed: a table cell that
    # wraps over several lines reads as one name
    return re.sub(r"\s+", " ", re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", out))


def _pdf_present(entry: dict) -> bool:
    return (DRE / entry["file"]).exists() and shutil.which("pdftotext") is not None


@pytest.mark.parametrize("parent", sorted(TABLE))
def test_pdf_is_the_pinned_one(parent):
    entry = TABLE[parent]
    if not (DRE / entry["file"]).exists():
        pytest.skip(f"raw/pt/dre/{entry['file']} not present")
    sha = hashlib.sha256((DRE / entry["file"]).read_bytes()).hexdigest()
    assert sha == entry["sha256"]


def _table_blocks(entry: dict) -> dict[str, str]:
    """Each "Sub-região de X" table of the act, keyed by X: the table pages
    read column by column (two tables side by side), dotted leaders and the
    "(*) Todo o concelho." footnote dropped."""
    pdf = DRE / entry["file"]
    first, last = entry["pages"]
    names = sorted((s["name"] for s in entry["subregioes"].values()), key=len, reverse=True)
    blocks: dict[str, str] = {}
    for page in range(first, last + 1):
        for x in (0, 298):
            out = subprocess.run(
                ["pdftotext", "-f", str(page), "-l", str(page), "-x", str(x), "-y", "0",
                 "-W", "298", "-H", "842", str(pdf), "-"],
                capture_output=True, text=True, check=True).stdout
            text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", out)
            text = re.sub(r"(?:\s*\.){2,}", " ", text).replace("(*) Todo o concelho.", "")
            text = re.sub(r"\s+", " ", text)
            for part in text.split("Sub-região de ")[1:]:
                name = next((n for n in names if part.startswith(n + " ")), None)
                if name is not None:
                    blocks[name] = part[len(name):]
    return blocks


@pytest.mark.parametrize("parent", sorted(TABLE))
def test_every_name_is_printed_in_its_own_table(parent):
    """Each name is an entry of its own sub-região's table — after the
    previous entry, the "(*)" column or its município, never inside a longer
    name ("Tendais" in "Ferreiros de Tendais") — and the table prints as many
    freguesia entries and "(*)" rows as the transcription carries."""
    entry = TABLE[parent]
    if not _pdf_present(entry):
        pytest.skip(f"raw/pt/dre/{entry['file']} or pdftotext not present")
    blocks = _table_blocks(entry)
    for slug, sub in entry["subregioes"].items():
        block = blocks.get(sub["name"])
        assert block is not None, f"{slug}: no table «Sub-região de {sub['name']}»"
        printed = sub.get("printed_as") or {}
        n_entries = 0
        for row in sub["rows"]:
            concelho = re.escape(row["concelho"])
            assert re.search(rf"(?:^|\s){concelho}(?:\s|$)", block), (slug, row["concelho"])
            for name in row.get("freguesias") or []:
                # the print splits or misspells it: its own form is there
                forms = printed.get(name, [name])
                n_entries += len(forms)
                seq = re.escape(". ".join(forms) + ".")
                assert re.search(rf"(?:^|\.\s|\)\s|{concelho}\s){seq}", block), (slug, name)
        assert len(re.findall(r"\.(?=\s|$)", block)) == n_entries, slug
        whole = sum(1 for row in sub["rows"] if not row.get("freguesias"))
        assert block.count("(*)") == whole, slug


@pytest.fixture(scope="module")
def pt_index():
    if not (CAOP.exists() and any(CAOP.glob("*.gpkg")) and EXTRACTED.exists()):
        pytest.skip("raw/pt/caop or raw/pt/cadernos-extracted not present")
    from _lib.pt.freguesias import apply_overrides, load_overrides
    from _lib.pt.geometry import PTPolygonIndex

    idx = PTPolygonIndex(ROOT / "raw" / "es" / "figshare" / "EU_PDO.gpkg",
                         sorted(CAOP.glob("*.gpkg")))
    apply_overrides(idx, load_overrides())
    return idx


def _resolve(idx, parsed: dict, slug: str = ""):
    with contextlib.redirect_stderr(io.StringIO()):
        return idx.resolve_area_units(parsed, slug=slug)


def test_sub_regions_draw_whole_inside_their_appellation_without_overlap(pt_index):
    from _lib.pt.area_units import parse_area_units

    for parent, entry in TABLE.items():
        appellation = _resolve(pt_index, parse_area_units(
            (_record(parent).get("sections") or {}).get("area", ""))).geom
        drawn = {}
        for slug, sub in entry["subregioes"].items():
            res = _resolve(pt_index, {"pieces": pieces_for(sub)}, slug)
            assert res.unmatched == [], slug
            assert res.exclusions_unresolved == [], slug
            assert res.partial == [], slug
            assert res.proxied == [], slug
            drawn[slug] = res.geom
        for slug, geom in drawn.items():
            assert outside_km2(geom, appellation) < 0.01, slug
        for a, b in itertools.combinations(drawn, 2):
            assert area_km2(drawn[a].intersection(drawn[b])) < 0.01, (a, b)


VINHO_VERDE_ARTICLE_3 = "abcdefghi"  # alíneas a)–i), in the order of the table's sub-regiões


def test_table_draws_what_article_3_says(pt_index):
    """Artigo 3.º n.º 1 states the nine sub-regiões in prose, the table in
    rows; read by the clause parser, the prose must draw the same units. The
    republication prints "Santa Eulália em de Santo Adrião" in b), read as
    the 2010 original's "Santa Eulália e de Santo Adrião"."""
    from _lib.pt.area_units import parse_area_units

    entry = TABLE["vinho-verde"]
    if not _pdf_present(entry):
        pytest.skip(f"raw/pt/dre/{entry['file']} or pdftotext not present")
    pdf = DRE / entry["file"]
    out = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True,
                         check=True).stdout
    text = re.sub(r"\s+", " ", re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", out))
    # the second "Sub-regiões produtoras" is the republished article
    start = [m.start() for m in re.finditer("Sub-regiões produtoras", text)][1]
    article = text[start:text.index("2 — Os produtos com indicação", start)]
    items = dict(re.findall(r"\b([a-i])\) (.+?[;.])(?= [a-i]\) |\s*$)", article))
    items["b"] = items["b"].replace("Santa Eulália em de Santo Adrião",
                                    "Santa Eulália e de Santo Adrião")
    for letter, (slug, sub) in zip(VINHO_VERDE_ARTICLE_3, entry["subregioes"].items()):
        assert items[letter].startswith(sub["name"] + ","), (letter, slug)
        prose = _resolve(pt_index, parse_area_units(items[letter]), slug)
        table = _resolve(pt_index, {"pieces": pieces_for(sub)}, slug)
        assert prose.unmatched == [], slug
        assert prose.exclusions_unresolved == [], slug
        assert area_km2(prose.geom.symmetric_difference(table.geom)) < 0.001, slug
