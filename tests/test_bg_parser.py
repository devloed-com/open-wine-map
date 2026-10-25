"""Fixture-based regression tests for the Bulgaria (BG) parsers.

Bulgaria is the first CYRILLIC-script corpus. The load-bearing invariant
that distinguishes BG from every Latin-script country: string handling
never goes through NFKD-ASCII (which collapses Cyrillic to the empty
string) — slugs route through `unidecode`, and commune matching uses
`.casefold()`. See the Cyrillic-handling note in CLAUDE.md.

Three target modules, each a seam that has regressed historically (and
that the BG section of CLAUDE.md enumerates):

  - scripts/bg/02_extract_pliegos.py + scripts/_lib/bg/edinen_dokument.py
    — the EU-OJ "ЕДИНЕН ДОКУМЕНТ" HTML driver. Slice from the anchor,
    find numbered `ti-grseq-1` headers, route by Bulgarian title keyword.
    The HU/BG monotonic-number + role-keyword guard in `extract_sections`
    filters per-style / per-variety subsections nested inside section 4
    (the same nested-`ti-grseq-1` decoy issue as Hungary) so the real
    sections 5–9 are not shadowed.
  - scripts/_lib/bg/specifikacija.py — the IAVV national-spec template
    (numbered 1–8). §5 colour split (за бели вина / за червени вина и
    розе / розе), §6 terroir (а) Природни / б) Човешки).
  - scripts/_lib/bg/commune.py — Cyrillic-preserving obshtina matching:
    `.casefold()` (NOT NFKD-ASCII), settlement-tier prefixes (с./гр./
    село/град) dropped, област markers consumed with their trailing name.
  - scripts/_lib/bg/geometry.py + scripts/_lib/bg/region.py — the two
    hand-curated PGI-membership / region tables, which must agree (a PDO
    filed under the wrong PGI draws a detached part in that PGI union).

Real cached docs live under raw/bg/{oj-pages,national-specs}/ (gitignored).
The HTML/text fixtures here are short redacted excerpts under
tests/fixtures/bg_* (the melnik / specifikacija slices preserve real
load-bearing Cyrillic; the nested-subsections HTML mirrors the
dunavska-ravnina section-4 decoy structure).

Assertions are on STRUCTURE (routed roles incl. the nested-subsection
guard, Cyrillic→slug variety sets, colour split, commune casefold), not
on full-output snapshots. Where a test pins ACTUAL behaviour that diverges
from the docstring's ideal (the section-9 "Други основни условия" drop,
the "находящи се" participle leak), the divergence is called out inline.
"""
from __future__ import annotations

import importlib
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.bg import commune  # noqa: E402
from _lib.bg.commune import _normalise_commune, parse_commune_list  # noqa: E402
from _lib.bg.edinen_dokument import (  # noqa: E402
    _GEO_AREA_TITLE_BLOCKLIST,
    SECTION_ROLE_KEYWORDS,
)
from _lib.bg.geometry import BG_PGI_MEMBER_PDOS  # noqa: E402
from _lib.bg.region import (  # noqa: E402
    _REGION_BY_FILE_NUMBER,
    REGIONS,
    region_for_file_number,
)
from _lib.bg.specifikacija import parse_specifikacija  # noqa: E402

# 02_extract_pliegos starts with a digit, so import it by module path.
extract = importlib.import_module("bg.02_extract_pliegos")


def _route_html(html: str) -> tuple[dict, dict, dict]:
    """Slice → extract numbered sections → route, the way build_record
    drives them. Returns (sections, titles, routed)."""
    doc = extract.slice_document_unic(html)
    assert doc is not None, "ЕДИНЕН ДОКУМЕНТ anchor must be found"
    sections, titles = extract.extract_sections(doc)
    routed = extract.route_sections(sections, titles)
    return sections, titles, routed


# ==========================================================================
# ЕДИНЕН ДОКУМЕНТ HTML driver — anchor slice + section routing
# ==========================================================================

def test_anchor_slice_drops_preamble(fixture_text):
    html = fixture_text("bg_edinen_dokument_melnik.html")
    doc = extract.slice_document_unic(html)
    # The modification/communication preamble before ЕДИНЕН ДОКУМЕНТ is dropped.
    assert "COMMUNICATION preamble" not in doc
    assert "да се отреже" not in doc
    # The slice starts at the anchor paragraph itself.
    assert doc.lstrip().startswith("<p")
    assert "ЕДИНЕН ДОКУМЕНТ" in doc[:120]


def test_section_routing_melnik(fixture_text):
    _sections, _titles, routed = _route_html(
        fixture_text("bg_edinen_dokument_melnik.html")
    )
    # The four semantic roles downstream consumers depend on, plus name.
    for role in ("name", "geo_area", "grape_varieties", "link_to_terroir"):
        assert role in routed, role
    # Section 1 → name.
    assert routed["name"] == "Мелник"
    # Section 6 body lands in geo_area (commune list), not terroir prose.
    assert "Районът за производство" in routed["geo_area"]
    assert "община Сандански" in routed["geo_area"]
    # Section 7 body lands in grape_varieties.
    assert "Каберне Совиньон" in routed["grape_varieties"]
    # Section 8 body lands in link_to_terroir.
    assert "Югозападна България" in routed["link_to_terroir"]


def test_clean_numbering_keeps_all_nine_sections(fixture_text):
    """The melnik fixture has clean 1→9 numbering with no nested decoys;
    every numbered section is kept and routed (including section 9, whose
    "Други специфични изисквания" title matches the additional_conditions
    keyword table)."""
    sections, titles, routed = _route_html(
        fixture_text("bg_edinen_dokument_melnik.html")
    )
    assert sorted(titles, key=lambda k: int(k)) == list("123456789")
    # All section keys are number-prefixed (no all-caps anchor decoy survives).
    for num in sections:
        assert num[0].isdigit(), f"section key {num!r} must be number-prefixed"
    assert "additional_conditions" in routed


# ==========================================================================
# Regression: nested per-style subsections inside section 4 (the HU/BG
# monotonic-number + role-keyword guard)
# ==========================================================================

def test_regression_nested_section4_subsections_do_not_shadow_5_to_9(fixture_text):
    """Section 4 (Описание на виното) nests `<p class="ti-grseq-1">`
    headers numbered 1.→4. (Бели вина / Вина розе / Червени вина /
    Качествени пенливи вина — per-wine-type subsections that restart the
    numbering at 1). A naive first-occurrence dedupe would let those decoy
    bodies shadow the real sections 5–9. `extract_sections`'s guard —
    monotonic top-level number (must not go backwards) + the title must
    contain a section-role keyword — filters them. (Same nested-ti-grseq-1
    decoy issue as Hungary.)"""
    sections, titles, routed = _route_html(
        fixture_text("bg_edinen_dokument_nested_subsections.html")
    )
    # The nested 1.→4. colour-bucket decoys never registered as top-level
    # sections: section 4's title is the real "Описание …", not a colour.
    assert titles["4"].startswith("Описание на виното")
    for decoy in ("Бели вина", "Вина розе", "Червени вина", "Качествени пенливи вина"):
        assert decoy not in titles.values(), decoy
    # Sections 5–8 survived with their real roles (not shadowed by section
    # 4's per-style subsection bodies).
    assert titles["5"].startswith("Винопроизводствени практики")
    assert titles["6"].startswith("Определен географски район")
    assert titles["7"].startswith("Винен сорт")
    assert titles["8"].startswith("Описание на връзката")
    assert "viticultural_practices" in routed
    assert "geo_area" in routed
    assert "grape_varieties" in routed
    assert "link_to_terroir" in routed
    # The geo_area body is section 6's obshtina list — NOT a wine-style
    # description body that a shadowing bug would have left there.
    assert "община Свищов" in routed["geo_area"]
    assert "Бели вина" not in routed["geo_area"]
    # Grapes come from the real section 7 (the colour-bucket decoy bodies
    # in section 4 carry no variety names).
    assert "kadarka" in set(routed and extract.parse_grapes(
        routed["grape_varieties"])["principal"])


def test_actual_section9_other_conditions_title_kept(fixture_text):
    """The nested fixture's section 9 is titled "Други основни условия (…)":
    "основни" sits between the two words of "други условия", so until
    2026-10-24 the substring missed and the section was dropped, so the link
    section before it ran on through it (Дунавска равнина). The keyword
    table carries the phrase now."""
    _sections, titles, routed = _route_html(
        fixture_text("bg_edinen_dokument_nested_subsections.html")
    )
    assert "9" in titles
    assert "additional_conditions" in routed


# ==========================================================================
# Grape parsing — Cyrillic → slug, em-dash synonym split, colour
# ==========================================================================

def test_grape_parsing_cyrillic_to_slug_and_synonym_split(fixture_text):
    """Section 7 is a flat per-line list. `Name - synonym` (plain hyphen
    with spaces) keeps the canonical Bulgarian name and drops the Latin
    synonym blob. Cyrillic names resolve to English-canonical slugs via the
    shared lexicon; the Latin-script "Viognier" line resolves too."""
    _sections, _titles, routed = _route_html(
        fixture_text("bg_edinen_dokument_melnik.html")
    )
    grapes = extract.parse_grapes(routed["grape_varieties"])
    slugs = set(grapes["principal"])
    # Cyrillic → English-canonical slugs.
    assert {"grenache", "cabernet-sauvignon", "cabernet-franc", "merlot",
            "chardonnay", "muscat-ottonel"} <= slugs
    # Latin-script line in a Cyrillic doc still resolves.
    assert "viognier" in slugs
    # Bulgarian native varieties keep their own slugs.
    assert "kerasuda" in slugs               # Керацуда
    assert "shiroka-melnishka-loza" in slugs  # Широка мелнишка лоза
    # `Тамянка` folds to muscat-blanc-a-petits-grains (VIVC synonym chain).
    assert "muscat-a-petits-grains" in slugs
    # Display name is the segment BEFORE " - " (synonym dropped).
    by_slug = {d["slug"]: d for d in grapes["details"]}
    assert by_slug["sandanski-misket"]["name"] == "Мискет сандански"
    assert "Мускат" not in by_slug["sandanski-misket"]["name"]
    assert by_slug["shiroka-melnishka-loza"]["name"] == "Широка мелнишка лоза"
    # Colour comes from the lexicon match.
    assert by_slug["cabernet-sauvignon"]["colour"] == "noir"
    assert by_slug["chardonnay"]["colour"] == "blanc"
    # BG single document has no principal/accessory split — all principal.
    assert grapes["accessory"] == []


def test_grape_parsing_gamza_folds_to_kadarka(fixture_text):
    """`Гъмза` (same DNA as Kadarka) folds to the `kadarka` slug — pinned
    because it is one of the BG → international folds listed in CLAUDE.md."""
    _sections, _titles, routed = _route_html(
        fixture_text("bg_edinen_dokument_nested_subsections.html")
    )
    grapes = extract.parse_grapes(routed["grape_varieties"])
    by_slug = {d["slug"]: d for d in grapes["details"]}
    assert "kadarka" in grapes["principal"]
    assert by_slug["kadarka"]["name"] == "Гъмза"


# ==========================================================================
# geo_area blocklist — section 2 ("Вид на географското означение") decoy
# ==========================================================================

def test_geo_area_blocklist_table_present():
    # Section 2's title carries "географско" but its body is just ЗНП/ЗГУ;
    # the blocklist must keep it out of geo_area. A missing entry re-opens
    # the regression.
    assert "вид на географското означение" in _GEO_AREA_TITLE_BLOCKLIST
    assert "вид на географското указание" in _GEO_AREA_TITLE_BLOCKLIST


def test_regression_section2_kind_not_routed_to_geo_area(fixture_text):
    """Section 2 "Вид на географското означение" (body "ЗНП — …") carries
    the inflected "географското" so it would otherwise shadow the real
    area in section 6. The blocklist keeps geo_area on section 6 (commune
    list), not the ЗНП/ЗГУ kind decoy."""
    _sections, _titles, routed = _route_html(
        fixture_text("bg_edinen_dokument_melnik.html")
    )
    geo = routed.get("geo_area", "")
    assert geo.strip() != "ЗНП — Защитено наименование за произход"
    assert not geo.startswith("ЗНП")
    # The real section-6 area landed.
    assert "Районът за производство" in geo


def test_geo_area_keyword_table_most_specific_first():
    # The most-specific area title is listed first so it wins over the
    # bare "географски район" / "географска зона" forms.
    geo_keywords = SECTION_ROLE_KEYWORDS["geo_area"]
    assert geo_keywords[0] == "определен географски район"


# ==========================================================================
# geo_area → commune list (Cyrillic-preserving obshtina parse)
# ==========================================================================

def test_section6_geo_communes_settlements_dropped(fixture_text):
    """The section-6 area body lists obshtini (`в община NAME`) each
    followed by their settlements (`с. X`, `гр. X`). parse_commune_list
    keeps only the 4 obshtini and drops every settlement."""
    _sections, _titles, routed = _route_html(
        fixture_text("bg_edinen_dokument_melnik.html")
    )
    communes = parse_commune_list(routed["geo_area"])
    assert communes == ["Сандански", "Петрич", "Струмяни", "Кресна"]
    # No settlement (с./гр. prefixed) leaked through as a commune.
    for c in communes:
        assert not c.startswith("с.") and not c.startswith("гр.")


# ==========================================================================
# commune.py — Cyrillic-preserving normalisation + tier handling
# ==========================================================================

def test_casefold_preserves_cyrillic_unlike_nfkd_ascii():
    """The core BG invariant: NFKD-ASCII folding (the RO/Latin path) erases
    Cyrillic entirely; the BG normaliser uses .casefold(), which keeps it.
    A regression to the NFKD path would silently produce empty keys → zero
    commune matches → every BG wine falls off the obshtina-union geometry."""
    name = "Сливен"
    nfkd_ascii = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    assert nfkd_ascii == "", "NFKD-ASCII must erase Cyrillic (the trap)"
    # The BG normaliser keeps Cyrillic, just casefolded + tier-stripped.
    assert _normalise_commune("община " + name) == "сливен"
    assert _normalise_commune(name) == "сливен"


def test_normalise_strips_settlement_and_tier_prefix():
    # Both община (obshtina tier) and гр./с. (settlement tier) prefixes are
    # stripped; the bare Cyrillic name (two words preserved) remains.
    assert _normalise_commune("община Велико Търново") == "велико търново"
    assert _normalise_commune("гр. Сандански") == "сандански"
    assert _normalise_commune("с. Лехово") == "лехово"


def test_commune_oblast_marker_consumed_with_trailing_name():
    # `в област NAME` is consumed together with its province name so the
    # province does not bleed in as an obshtina candidate.
    out = parse_commune_list(
        "землищата на гр. Сливен в община Сливен, находящи се в област Сливен."
    )
    # The obshtina "Сливен" survives (from `в община Сливен`); both the
    # settlement `гр. Сливен` and the province `област Сливен` are stripped.
    assert "Сливен" in out


def test_commune_plural_obshtini_sublist_keeps_two_word_name():
    # `в общините NAME, NAME и NAME` introduces a sub-list; a two-word
    # obshtina (Велико Търново) survives intact.
    out = parse_commune_list("в общините Велико Търново, Свищов и Павликени.")
    assert out == ["Велико Търново", "Свищов", "Павликени"]


def test_commune_province_name_obshtina_survives():
    # 28 of 265 obshtini share their name with their parent province. The
    # province occurrence (`област Пловдив`) is consumed, but the obshtina
    # of the same name after `общините` survives.
    out = parse_commune_list("в област Пловдив, в общините Пловдив, Асеновград и Сопот.")
    assert "Пловдив" in out
    assert "Асеновград" in out and "Сопот" in out


def test_commune_settlement_only_chunk_dropped():
    # A list of bare settlements (с. X) with no parent obshtina names yields
    # nothing — settlements are LAU3, not in the GISCO LAU obshtina index.
    out = parse_commune_list("с. Лехово, с. Петрово, с. Яново.")
    assert out == []


def test_actual_participle_leak_находящи_се():
    """DISCREPANCY pin: `находящи се` ("located in", a participle phrase
    preceding `в област …`) is NOT in _PROSE_TOKENS, so when the area body
    is just `гр. X, находящи се в област Y` the participle survives as a
    spurious commune candidate (matching the real nova-zagora extraction,
    whose geo_communes are ['Шивачево', 'находящи се']). Pinned so a future
    _PROSE_TOKENS edit that filters it is a conscious change, not an
    accident."""
    out = parse_commune_list("землищата на гр. Сливен, находящи се в област Сливен.")
    assert "находящи се" in out


def test_commune_oblast_names_table_casefolded():
    # The province-name table is casefolded Cyrillic (not ASCII), so it
    # actually matches the casefolded commune keys.
    assert "пловдив" in commune._OBLAST_NAMES
    assert "велико търново" in commune._OBLAST_NAMES
    # No entry is empty (which an NFKD-ASCII fold would have produced).
    assert all(n for n in commune._OBLAST_NAMES)


# ==========================================================================
# specifikacija.py — IAVV national-spec template (numbered 1–8)
# ==========================================================================

def test_specifikacija_numbered_sections_and_template(fixture_text):
    text = fixture_text("bg_specifikacija_sliven.txt")
    out = parse_specifikacija(text, "sliven")
    assert out["parser_template"] == "iavv-specifikacija-v1"
    # 8 numbered sections sliced on the `N.` line anchors.
    assert out["n_sections"] == 8
    # Roles routed by leading-text keyword scan.
    for role in ("description", "geo_area", "grape_varieties", "link_to_terroir"):
        assert role in out["section_roles"], role


def test_specifikacija_section5_colour_split(fixture_text):
    """§5 groups varieties under Bulgarian colour markers. `за бели вина:`
    → blanc; `за червени вина и розе:` → noir (the whole marker — incl. the
    `и розе` second-colour suffix — is consumed so `розе` is NOT later
    treated as a variety separator). Every variety carries its bucket
    colour; there is no principal/accessory split (all principal)."""
    text = fixture_text("bg_specifikacija_sliven.txt")
    out = parse_specifikacija(text, "sliven")
    by_slug = {d["slug"]: d for d in out["grapes"]["details"]}
    # Whites
    for slug in ("rkatsiteli", "chardonnay", "ugni-blanc", "muscat-ottonel",
                 "cherven-misket", "dimyat", "aligote"):
        assert by_slug[slug]["colour"] == "blanc", slug
    # Reds (incl. the Bulgarian crossing Шевка → shevka). The `и розе`
    # suffix did not produce a spurious "розе" variety.
    for slug in ("cabernet-sauvignon", "merlot", "pinot-noir", "pamid", "shevka"):
        assert by_slug[slug]["colour"] == "noir", slug
    assert "rose" not in by_slug  # "и розе" suffix not parsed as a variety
    # No principal/accessory split.
    assert out["grapes"]["accessory"] == []
    assert set(out["grapes"]["principal"]) == set(by_slug)
    # 7 white + 5 red.
    assert len([d for d in out["grapes"]["details"] if d["colour"] == "blanc"]) == 7
    assert len([d for d in out["grapes"]["details"] if d["colour"] == "noir"]) == 5


def test_specifikacija_section6_terroir_natural_and_human(fixture_text):
    """§6 "Връзка с географския район." carries the `а) Природни фактори` /
    `б) Човешки фактори` subsections — both must land in link_to_terroir."""
    text = fixture_text("bg_specifikacija_sliven.txt")
    out = parse_specifikacija(text, "sliven")
    link = out["link_to_terroir"]
    assert "Природни фактори" in link
    assert "Човешки фактори" in link
    assert "умереноконтинентален климат" in link
    # The terroir text did NOT swallow the next section (§7 requirements).
    assert "Приложими изисквания" not in link


def test_specifikacija_geo_area_is_section3(fixture_text):
    # §3 (Районът за производство …) routes to geo_area, distinct from the
    # §6 terroir text.
    text = fixture_text("bg_specifikacija_sliven.txt")
    out = parse_specifikacija(text, "sliven")
    assert "Районът за производство" in out["geo_area_brief"]
    assert "Сливен" in out["geo_area_brief"]


def test_specifikacija_styles_from_grape_colours(fixture_text):
    # With both white and red varieties present, colour-derived styles are
    # blanc + rouge (the §2 sparkling marker is redacted out of this
    # excerpt, so only the colour bases assert).
    text = fixture_text("bg_specifikacija_sliven.txt")
    out = parse_specifikacija(text, "sliven")
    assert "blanc" in out["styles"]
    assert "rouge" in out["styles"]


# ==========================================================================
# geometry.py / region.py — PGI member tables ↔ region facet consistency
# ==========================================================================

def test_pgi_member_tables_partition_the_pdos():
    """Every BG PDO is a member of exactly one of the 2 PGIs, and the
    membership agrees with the curated region facet: Дунавска равнина
    members carry the Дунавска равнина region, Тракийска низина members
    one of the 4 southern regions. A PDO under both PGIs is drawn twice;
    one under neither drops out of its PGI polygon."""
    north = set(BG_PGI_MEMBER_PDOS["PGI-BG-A1538"])
    south = set(BG_PGI_MEMBER_PDOS["PGI-BG-A1552"])
    assert not north & south
    pdos = {fn for fn in _REGION_BY_FILE_NUMBER if fn.startswith("PDO-")}
    assert north | south == pdos
    for fn in north:
        assert region_for_file_number(fn) == "Дунавска равнина", fn
    for fn in south:
        assert region_for_file_number(fn) in REGIONS[1:], fn


def test_regression_oriakhovitsa_is_a_trakiiska_nizina_member():
    """PDO-BG-A1344 Оряховица sat in the Дунавска равнина group — confused
    with Горна Оряховица (област Велико Търново), which the Дунавска
    равнина PGI text does list. The ИАЛВ spec §3 delimits the wine to
    "с. Дълбоки, с. Оряховица, с. Братя Кунчеви и с. Колена, находящи се в
    област Стара Загора" — south of Stara Planina, inside the Тракийска
    низина PGI (whose spec lists област Стара Загора). The wrong entry put
    the whole 1,076 km² Bétard polygon as a detached part of the Дунавска
    равнина union."""
    assert "PDO-BG-A1344" in BG_PGI_MEMBER_PDOS["PGI-BG-A1552"]
    assert "PDO-BG-A1344" not in BG_PGI_MEMBER_PDOS["PGI-BG-A1538"]
    assert region_for_file_number("PDO-BG-A1344") == "Тракийска низина"


# ==========================================================================
# The PGI template: obshtini under „Област X:" headers (2026-10-24)
# ==========================================================================

# Redacted from Дунавска равнина's ЕДИНЕН ДОКУМЕНТ §6 (raw/bg/dokumenti-
# extracted/dunavska-ravnina.json) and Тракийска низина's ИАЛВ spec §3.
_DUNAVSKA_AREA = (
    "Районът за производство на вино със ЗГУ „Дунавска равнина“ е очертан при "
    "следните граници на землищата на населените места: Област Плевен: Белене, "
    "Червен бряг, Д. Митрополия, Долни Дъбник. Област Русе: Бяла, Борово. "
    "Област Варна: Аксаково, Бяла, Вълчидол. Следните землища на населени места, "
    "както са изброени по общини, се изключват от очертанията на района: "
    "Община Белене: с. Петокладенци. Община Аксаково: с. Кичево."
)
_TRAKIISKA_AREA = (
    "Районът за производство на вино със ЗГУ “Тракийска низина” е очертан при "
    "следните граници на землищата на населените места, включени в общините: "
    "Област Пазарджик: Пазарджик, Пещера, Септември, Стрелча. Област Смолян: "
    "Баните - само землищата на с. Вишнево и с. Гълъбово, Мадан - само землищата "
    "на с. Лещак, с. Цирка и с. Равнил, Златоград - само землищата на с. Пресока "
    "и Златоград. Област Стара Загора: Гълъбово, Казанлък."
)


def test_parse_area_scopes_each_name_to_its_oblast():
    """Two obshtini are called Бяла (Русе, Варна) and the Дунавска равнина
    text names both; the legacy parse deduped the second away and the
    unscoped matcher dropped both as ambiguous."""
    area = commune.parse_area(_DUNAVSKA_AREA)
    assert ("Бяла", "RSE") in area["members"] and ("Бяла", "VAR") in area["members"]
    assert ("Д. Митрополия", "PVN") in area["members"]
    assert len(area["members"]) == 9


def test_parse_area_exclusion_clause_marks_partial_not_members():
    """The villages after "се изключват" are cut out of their obshtina: the
    obshtina stays a member (drawn whole, disclosed as partial) and no
    village becomes a member."""
    area = commune.parse_area(_DUNAVSKA_AREA)
    names = [n for n, _ in area["members"]]
    assert "Петокладенци" not in names and "Кичево" not in names
    assert set(area["partial"]) == {"Белене", "Аксаково"}


def test_parse_area_only_some_villages_and_the_septemvri_obshtina():
    """"Баните - само землищата на с. …" is an obshtina held in part, its
    villages (Гълъбово among them — also an obshtina of Стара Загора) are
    not members; "Септември" is the Pazardzhik obshtina, not the month the
    legacy filter drops."""
    area = commune.parse_area(_TRAKIISKA_AREA)
    assert ("Септември", "PAZ") in area["members"]
    assert {"Баните", "Мадан", "Златоград"} <= set(area["partial"])
    sml = [n for n, c in area["members"] if c == "SML"]
    assert sml == ["Баните", "Мадан", "Златоград"]
    assert ("Гълъбово", "SZR") in area["members"]
    assert "септември" not in [commune._normalise_commune(n) for n in parse_commune_list(
        "публикувано на 3 септември 2020")]


def test_parse_area_is_none_for_a_settlement_list():
    """A PDO's spec lists settlements, which no obshtina layer can draw."""
    assert commune.parse_area(
        "Районът ... е очертан при следните граници на землищата на населените "
        "места – гр. Поморие, с. Бата, с. Горица, находящи се в обл. Бургас.") is None
    assert "geo_communes_scoped" not in commune.area_fields("с. Брестник, област Пловдив.")


def _toy_index():
    from _lib.bg.geometry import BGPolygonIndex
    from shapely.geometry import box
    idx = BGPolygonIndex(Path("/nonexistent.gpkg"), None)
    units = [("Бяла", "RSE"), ("Бяла", "VAR"), ("Долна Митрополия", "PVN"),
             ("Долни Дъбник", "PVN"), ("Вълчи дол", "VAR"), ("Белене", "PVN")]
    for i, (name, ob) in enumerate(units):
        key = commune._normalise_commune(name)
        idx._lau.append((key, ob, box(i, 0, i + 1, 1)))
        idx._lau_by_name.setdefault(key, []).append(i)
        idx._lau_by_compact.setdefault(key.replace(" ", ""), []).append(i)
    idx._pdo_polygons["PDO-BG-A1425"] = box(100, 0, 101, 1)  # Русе, a member PDO
    return idx


def test_bg_resolver_oblast_scope_compact_and_abbreviation():
    idx = _toy_index()
    assert idx._candidates("Бяла", None)[0] == [0, 1]
    assert idx._candidates("Бяла", "VAR") == ([1], "exact")
    assert idx._candidates("Вълчидол", "VAR") == ([4], "compact")
    assert idx._candidates("Д. Митрополия", "PVN") == ([2], "abbreviation")
    assert idx._candidates("Белене", "VAR") == ([], "outside-oblast")


def test_bg_pgi_drawn_from_its_list_union_only_as_fallback():
    idx = _toy_index()
    scoped = [("Бяла", "RSE"), ("Бяла", "VAR"), ("Д. Митрополия", "PVN"), ("Белене", "PVN")]
    geom, src, stats = idx.resolve("PGI-BG-A1538", [n for n, _ in scoped], scoped, ["Белене"])
    assert src == "gisco-commune-list" and stats["matched"] == 4
    assert stats["partial"] == ["Белене"]
    # a list most of whose names miss is not drawn: the member-PDO union is
    bad = [("Икс", "PVN"), ("Игрек", "PVN"), ("Белене", "PVN")]
    geom, src, stats = idx.resolve("PGI-BG-A1538", [n for n, _ in bad], bad)
    assert src == "region-pdo-union" and stats["list_rejected"]["unmatched"] == 2


def test_dobrich_is_the_city_and_the_rural_obshtina_around_it():
    """The ИАЛВ files the city and Добричка's villages under one "Община
    Добрич"; drawn as the city alone, Дунавска равнина had an undrawn ring
    around an island (2026-10-24). Only under област Добрич."""
    from _lib.bg.geometry import BGPolygonIndex
    from shapely.geometry import box
    idx = BGPolygonIndex(Path("/nonexistent.gpkg"), None)
    for i, (name, ob) in enumerate([("Добрич", "DOB"), ("Добрич-селска", "DOB"), ("Каварна", "DOB")]):
        key = commune._normalise_commune(name)
        idx._lau.append((key, ob, box(i, 0, i + 1, 1)))
        idx._lau_by_name.setdefault(key, []).append(i)
        idx._lau_by_compact.setdefault(key.replace(" ", ""), []).append(i)
    geom, stats = idx.commune_union([], [("Добрич", "DOB"), ("Каварна", "DOB")])
    assert stats["matched"] == 3 and abs(geom.area - 3.0) < 1e-9
    _, stats = idx.commune_union([], [("Добрич", None)])
    assert stats["matched"] == 1
