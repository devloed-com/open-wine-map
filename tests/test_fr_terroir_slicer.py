"""FR stage 02d: a record in a shared cahier is graded against its own chapter."""
from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "02d_extract_terroir_facts.py"
spec = importlib.util.spec_from_file_location("fr02d", SCRIPT)
fr02d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr02d)

PAD = " Texte de remplissage sur les sols et le climat de ce cru, répété pour dépasser le seuil." * 8


def chapter(name: str, body: str) -> str:
    return (
        f"                 « Alsace grand cru {name} »\n\n"
        f"1°– Informations sur la zone géographique\n\na) - Description des facteurs naturels\n\n{body}{PAD}\n\n"
        f"b) - Description des facteurs humains\n\nVendanges manuelles.{PAD}\n\n"
        f"2°– Informations sur la qualité et les caractéristiques des produits\n\nVins blancs secs.{PAD}\n\n"
        f"3°– Interactions causales\n\nLe lien au terroir.{PAD}\n\n"
    )


LIEN = chapter("Kastelberg", "Schistes de Steige.") + chapter("Rangen", "Sols volcaniques.") + chapter("Zotzenberg", "Marnes denses.")


def record(name: str, slug: str, lien: str = LIEN) -> dict:
    return {"name": name, "slug": slug, "lien_au_terroir": lien, "source": {}}


def test_shared_cahier_job_is_windowed_to_the_own_chapter():
    job = fr02d._job_from_record(record("Alsace grand cru Rangen", "alsace-grand-cru-rangen"))
    assert job is not None
    assert "Sols volcaniques" in job["lien"]
    assert "Marnes denses" not in job["lien"] and "Schistes" not in job["lien"]
    assert set(job["slices"]) >= {"facteurs_naturels", "facteurs_humains", "produit", "interactions"}
    assert job["lien_sha"] == fr02d.cahier_sha(job["lien"])


def test_shared_cahier_without_own_chapter_is_skipped(capsys):
    assert fr02d._job_from_record(record("Alsace grand cru Sporen", "alsace-grand-cru-sporen")) is None
    assert "no own chapter" in capsys.readouterr().err


def test_single_chapter_cahier_keeps_the_whole_lien():
    single = chapter("Rangen", "Sols volcaniques.")
    job = fr02d._job_from_record(record("Alsace grand cru Rangen", "alsace-grand-cru-rangen", single))
    assert job is not None and job["lien"] == single.strip()
