"""The shared summary-link rule (scripts/_lib/summary_link.py, 2026-10-24):
a single document's "Resumen del vínculo" / "Sintesi del legame" or a link
under 1,000 characters yields to a national text at least 1.5× longer and at
least 1,000 characters — the ES pliego §7 and the IT MASAF Article 9 — and
never to one of the same size under a template heading. The IT stage-04
backfill carries the same text 02d grounds on.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.augment.it import _backfill_it_nonstub_from_masaf  # noqa: E402
from _lib.summary_link import (  # noqa: E402
    NATIONAL_LINK_MIN_RATIO,
    SUMMARY_LINK_MAX_CHARS,
    is_summary_link,
    prefer_national_link,
)

SINTESI = "Categoria di prodotto vitivinicolo 3. Vino liquoroso Sintesi del legame " + "x" * 1300
LONG = "Il territorio " * 400


def test_is_summary_link_marks_both_languages_and_short_texts():
    assert is_summary_link("")
    assert is_summary_link("x" * (SUMMARY_LINK_MAX_CHARS - 1))
    assert is_summary_link(SINTESI)
    assert is_summary_link("1. Vino Resumen del vínculo La zona …" + "x" * 1200)
    assert not is_summary_link(LONG)


def test_prefer_national_only_when_substantially_longer():
    assert prefer_national_link(SINTESI, "y" * int(len(SINTESI) * NATIONAL_LINK_MIN_RATIO + 5))
    assert not prefer_national_link(SINTESI, "y" * int(len(SINTESI) * 1.2))
    assert not prefer_national_link("x" * 300, "y" * (SUMMARY_LINK_MAX_CHARS - 1))
    assert prefer_national_link("x" * 300, "y" * SUMMARY_LINK_MAX_CHARS)
    assert not prefer_national_link(LONG, "y" * (len(LONG) * 3))


def test_it_backfill_takes_article_9_over_the_sintesi():
    record = {"link_to_terroir": SINTESI, "grapes": {"principal": ["grillo"]}, "styles": ["white"]}
    sidecar = {"link_to_terroir": "cut " * 100, "link_to_terroir_full": "full " * 2000}
    assert _backfill_it_nonstub_from_masaf(record, sidecar)
    assert record["link_to_terroir"] == sidecar["link_to_terroir"]
    assert record["section_roles"]["link_to_terroir"] == sidecar["link_to_terroir"]
    assert record["masaf_link"] is True


def test_it_backfill_keeps_a_full_eu_link():
    record = {"link_to_terroir": LONG, "grapes": {"principal": ["grillo"]}, "styles": ["white"]}
    sidecar = {"link_to_terroir": "cut " * 100, "link_to_terroir_full": "full " * 5000}
    assert not _backfill_it_nonstub_from_masaf(record, sidecar)
    assert record["link_to_terroir"] == LONG
    assert "masaf_link" not in record


def test_it_backfill_still_fills_an_empty_link():
    record = {"link_to_terroir": "", "grapes": {"principal": ["grillo"]}, "styles": ["white"]}
    sidecar = {"link_to_terroir": "cut " * 100}
    assert _backfill_it_nonstub_from_masaf(record, sidecar)
    assert record["link_to_terroir"] == sidecar["link_to_terroir"]
