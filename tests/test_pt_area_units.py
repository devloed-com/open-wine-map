"""Freguesia-precision reading of PT area sections (scripts/_lib/pt/area_units.py)
and its CAOP resolver (scripts/_lib/pt/freguesias.py).

The parser cases are excerpts of the cadernos' "Área geográfica delimitada"
sections (IVV), each the shape that went wrong at município level: a
município restricted to some freguesias was drawn whole, an excluded
freguesia was ignored, a freguesia named on its own was lost. The resolver
cases run on a synthetic index of unit boxes, so they need no CAOP data.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from shapely.geometry import box
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.pt.area_units import parse_area_units  # noqa: E402
from _lib.pt.freguesias import Freguesia, _Gazetteer, unit_keys  # noqa: E402
from _lib.pt.geometry import (  # noqa: E402
    PTPolygonIndex,
    _Concelho,
    _loose_concelho,
    _normalise_concelho,
)


def _summary(text: str) -> dict:
    """{kind: [...]} of the parsed pieces, names folded for comparison."""
    out: dict[str, list] = {"concelho": [], "freguesias": [], "distrito": [], "macro": []}
    for p in parse_area_units(text)["pieces"]:
        if p.kind == "concelho":
            excl = [("-" + i.name + ("*" if i.part else "")) for i in p.items if i.role == "exclude"]
            out["concelho"].append((p.name + (" (part)" if p.part else ""), tuple(excl)))
        elif p.kind == "freguesias":
            out["freguesias"].append((p.name, tuple(
                ({"include": "", "union_tail": "~"}[i.role]) + i.name + ("*" if i.part else "")
                for i in p.items if i.role != "locality")))
            if any(i.role == "locality" for i in p.items):
                out.setdefault("lugares", []).append(
                    (p.name, tuple(i.name for i in p.items if i.role == "locality")))
        elif p.kind == "distrito":
            out["distrito"].append((p.name, tuple(p.excluded_concelhos),
                                    tuple(p.excluded_freguesias)))
        else:
            out["macro"].append(p.name)
    return out


# ---------------------------------------------------------------- parser --


def test_vinho_verde_ossela_included_and_barro_excluded():
    """Ossela is a freguesia named on its own; Barrô is excluded from
    Resende (visitor boundary flag 2026-10-13: the 123 km² Minho × Douro
    overlap)."""
    s = _summary(
        "A área geográfica de produção da DO “Vinho Verde” abrange as seguintes divisões\n"
        "administrativas:\n"
        "a) Todos os municípios dos distritos de Braga e de Viana do Castelo;\n"
        "b) Do distrito de Aveiro, os municípios de Arouca, Castelo de Paiva e Vale de Cambra "
        "e a freguesia\nde Ossela, do município de Oliveira de Azeméis;\n"
        "d) Do distrito de Vila Real, os municípios de Mondim de Basto e Ribeira de Pena;\n"
        "e) Do distrito de Viseu, os municípios de Cinfães e Resende, com exceção da "
        "freguesia de Barrô.\n"
    )
    assert s["distrito"] == [("Braga", (), ()), ("Viana do Castelo", (), ())]
    assert ("Oliveira de Azeméis", ("Ossela",)) in s["freguesias"]
    assert ("Resende", ("-Barrô",)) in s["concelho"]
    assert ("Ribeira de Pena", ()) in s["concelho"]
    assert ("Cinfães", ()) in s["concelho"]


def test_lagoa_restricts_loule_and_silves_to_their_listed_freguesias():
    s = _summary(
        "A área geográfica correspondente à Denominação de Origem Controlada Lagoa abrange os\n"
        "concelho de Albufeira, Lagoa e Loulé (freguesias de Almancil, Boliqueime, Quarteira, São\n"
        "Clemente e São Sebastião e parte das freguesias de Alte, Querença e Salir) e Silves, as\n"
        "(freguesias de Alcantarilha, Armação de Pêra e parte das freguesias de São Bartolomeu de\n"
        "Messines e Silves).\n"
    )
    assert [c for c, _ in s["concelho"]] == ["Albufeira", "Lagoa"]
    assert ("Loulé", ("Almancil", "Boliqueime", "Quarteira", "São Clemente", "São Sebastião",
                      "Alte*", "Querença*", "Salir*")) in s["freguesias"]
    assert ("Silves", ("Alcantarilha", "Armação de Pêra", "São Bartolomeu de Messines*",
                       "Silves*")) in s["freguesias"]


def test_tavira_part_of_the_freguesia_of_the_same_name():
    s = _summary(
        "abrange os concelhos de Faro, Olhão, São Brás de Alportel (parte da freguesia do mesmo "
        "nome), Castro Marim (parte da freguesia do mesmo nome), Tavira (freguesias da Luz e "
        "Santiago e parte das freguesias de Conceição, Santa Catarina, Santa Marta e Santo "
        "Estêvão) e Vila Real de Santo António (a freguesia de Vila Nova da Cacela).\n"
    )
    assert [c for c, _ in s["concelho"]] == ["Faro", "Olhão"]
    assert ("São Brás de Alportel", ("São Brás de Alportel*",)) in s["freguesias"]
    assert ("Vila Real de Santo António", ("Vila Nova da Cacela",)) in s["freguesias"]


def test_bairrada_former_freguesia_taken_out_of_a_union():
    s = _summary(
        "b) Do município de Águeda, a b r a n g e a União das freguesias de Recardães e\n"
        "Espinhel, da União das freguesias de Travassô e Óis da Ribeira,\n"
        "apenas a freguesia de Óis da Ribeira, e as freguesias de Aguada de Cima, Fermentelos "
        "e Valongo do Vouga;\n"
    )
    assert s["freguesias"] == [("Águeda", ("Recardães", "Espinhel", "Óis da Ribeira",
                                          "Aguada de Cima", "Fermentelos", "Valongo do Vouga"))]


def test_union_tail_after_a_former_freguesia():
    """"Malpartida da União de Freguesias de Malpartida e Vale de Coelha":
    the union's names follow as context, not members."""
    s = _summary(
        " Do município de Almeida, as freguesias de Almeida, Castelo Bom, a União das "
        "Freguesias\nde Junça e Naves, e Malpartida da União de Freguesias de Malpartida e "
        "Vale de Coelha;\n"
    )
    assert s["freguesias"] == [("Almeida", ("Almeida", "Castelo Bom", "Junça", "Naves",
                                           "Malpartida", "~Malpartida", "~Vale de Coelha"))]


def test_freguesia_that_holds_former_ones():
    """"Coura e Tões da freguesia de Armamar": Armamar is the unit that now
    holds them (a holder tail), not a member."""
    pieces = parse_area_units(
        "• Armamar: União das Freguesias de Aricera e Goujoim, Coura e Tões da freguesia de "
        "Armamar,\nUnião das Freguesias de São Romão e Santiago, Cimbres;\n")["pieces"]
    (p,) = pieces
    assert p.name == "Armamar"
    names = [(i.name, i.role, i.holder) for i in p.items]
    assert ("Armamar", "union_tail", True) in names
    assert ("Coura", "include", False) in names and ("Tões", "include", False) in names
    assert ("Cimbres", "include", False) in names


def test_semicolon_lists_compound_names_and_abbreviations():
    """Trás-os-Montes writes "as freguesias de A; B; …"; "Água Revés e Crasto"
    mid-list is one former parish; "Torre D. Chama" keeps its initial."""
    s = _summary(
        "Valpaços:\n"
        "No concelho de Mirandela, as freguesias de Abambres, Aguieiras; Avantos (excluindo\n"
        "as propriedades da Sociedade Clemente Meneres); Torre D. Chama; Vale de Telhas;\n"
        "No concelho de Valpaços, as freguesias de Água Revés e Crasto; Argeriz; Vassal e "
        "Vilarandelo;\n"
    )
    assert ("Mirandela", ("Abambres", "Aguieiras", "Avantos*", "Torre D. Chama",
                          "Vale de Telhas")) in s["freguesias"]
    assert ("Valpaços", ("Água Revés e Crasto", "Argeriz", "Vassal", "Vilarandelo")) \
        in s["freguesias"]


def test_transmontano_inclusion_and_partial_exclusion_parentheses():
    s = _summary(
        "O distrito de Bragança: os concelhos de Alfândega da Fé (as freguesias de Agrobom;\n"
        "Cerejais); Bragança; Mirandela (excluindo as propriedades que foram de D. Maria "
        "Angélica, na freguesia de Frechas e as da Sociedade Clemente Meneres, nas freguesias "
        "de Avantos e Romeu);Mogadouro; Vila Flor (as freguesias de Benlhevai; Samões e Vilas "
        "Boas excluindo as Quintas da Peça e das Trigueiras); Vimioso e Vinhais;\n"
    )
    assert s["distrito"] == []
    assert ("Mirandela", ("-Frechas*", "-Avantos*", "-Romeu*")) in s["concelho"]
    assert ("Vila Flor", ("Benlhevai", "Samões", "Vilas Boas*")) in s["freguesias"]
    assert [c for c, _ in s["concelho"]] == ["Bragança", "Mirandela", "Mogadouro",
                                             "Vimioso", "Vinhais"]


def test_distrito_exception_with_a_freguesia():
    """Beira Atlântico takes Ossela out of the distrito de Aveiro — Minho
    and Vinho Verde draw it."""
    s = _summary(
        "a) O distrito de Aveiro, com exceção dos municípios de Arouca, Castelo de Paiva e "
        "Vale de\nCambra e, do município de Oliveira de Azeméis, a freguesia de Ossela;\n"
        "c) Do distrito de Leiria, os municípios de Alvaiázere, Ansião e Pombal (apenas as "
        "freguesias de Abiul, Pelariga, Redinha e Vila Cã).\n"
    )
    assert s["distrito"] == [("Aveiro", ("Arouca", "Castelo de Paiva", "Vale de Cambra"),
                              (("Ossela", "Oliveira de Azeméis"),))]
    assert ("Pombal", ("Abiul", "Pelariga", "Redinha", "Vila Cã")) in s["freguesias"]


def test_freguesia_exceptions_inside_a_concelho_list():
    s = _summary(
        "• O distrito de Lisboa, à exceção do concelho de Azambuja;\n"
        " • Do distrito de Leiria, abrange os concelhos de Alcobaça, Pombal, exceto as\n"
        "freguesias de Abiul, Pelariga, Redinha e Vila Cã, e o concelho de Porto de Mós;\n"
        "- Do distrito de Leiria, os concelhos de Batalha, Pombal — exceto as freguesias de "
        "Abiul e Vila Cã — e Porto de Mós;\n"
    )
    assert s["distrito"] == [("Lisboa", ("Azambuja",), ())]
    assert ("Pombal", ("-Abiul", "-Pelariga", "-Redinha", "-Vila Cã")) in s["concelho"]
    assert ("Pombal", ("-Abiul", "-Vila Cã")) in s["concelho"]
    assert ("Porto de Mós", ()) in s["concelho"]


def test_whole_distritos_written_as_all_their_concelhos():
    """Alentejano had been drawn as the Évora and Portalegre concelhos
    (1,754 km²) instead of three distritos."""
    s = _summary("A área geográfica de produção compreende todos os concelhos dos distritos "
                 "de Beja, Évora e\nPortalegre.\n")
    assert [d for d, _, _ in s["distrito"]] == ["Beja", "Évora", "Portalegre"]
    s = _summary(" Todas as freguesias de todos os concelhos do distrito de Castelo Branco;\n"
                 " Do distrito da Guarda, inclui os municípios de Almeida, Figueira de Castelo "
                 "Rodrigo (excluída a freguesia de Escalhão), Pinhel.\n")
    assert s["distrito"] == [("Castelo Branco", (), ())]
    assert ("Figueira de Castelo Rodrigo", ("-Escalhão",)) in s["concelho"]


def test_boundary_prose_sub_regions_are_reported():
    r = parse_area_units(
        "a) Sub-região Borba - os limites sul e sueste são definidos pela serra d’Ossa e pelos "
        "seus\ncontrafortes, seguindo a referida estrada até ao limite do concelho de Estremoz.\n"
        "c) Sub-região Granja/Amareleja - é delimitada pela linha limite do concelho de Mourão "
        "(a área\ntotal das três freguesias: Mourão, Granja e Luz) e a área total das freguesias "
        "de Póvoa de São\nMiguel e Amareleja, do concelho de Moura.\n"
        "h) Sub-região Vidigueira - os limites da sub-região correspondem aos limites dos "
        "concelhos de\nAlvito, Cuba e Vidigueira.\n"
    )
    assert r["prose_subregions"] == ["Borba"]
    assert "Vidigueira" not in r["prose_cut_subregions"]
    by_sub = {}
    for p in r["pieces"]:
        by_sub.setdefault(p.subregion, []).append((p.kind, p.name))
    assert by_sub["Vidigueira"] == [("concelho", "Alvito"), ("concelho", "Cuba"),
                                    ("concelho", "Vidigueira")]
    assert ("concelho", "Mourão") in by_sub["Granja/Amareleja"]
    assert ("freguesias", "Moura") in by_sub["Granja/Amareleja"]


def test_note_on_other_sub_regions_does_not_taint_the_last_section():
    r = parse_area_units(
        "a) Sub -região Almeirim: Os concelhos de Almeirim, Alpiarça e Salvaterra de Magos;\n"
        "b) Sub -região Cartaxo: Os concelhos da Azambuja e Cartaxo;\n"
        "f) Sub -região Tomar: Os concelhos de Tomar e Torres Novas; Alcanena, Entroncamento.\n"
        "O limite natural que separa a sub -região de Almeirim das do Cartaxo e Santarém é o "
        "rio Tejo.\n"
    )
    assert r["prose_cut_subregions"] == []
    tomar = [p.name for p in r["pieces"] if p.subregion == "Tomar"]
    assert tomar == ["Tomar", "Torres Novas", "Alcanena", "Entroncamento"]


def test_noun_enumeration_is_no_list_and_limits_section_is_dropped():
    s = _summary(
        "Os contornos das parcelas, freguesias, concelhos e distritos referidos no número "
        "anterior\ncorrespondem rigorosamente ao disposto na legislação em vigor à data de "
        "aprovação do\nDecreto nº 7934, de 10 de Dezembro de 1921.\n")
    assert s == {"concelho": [], "freguesias": [], "distrito": [], "macro": []}
    s = _summary(
        "Do concelho de Oeiras, parte da freguesia de Oeiras e São Julião da Barra (lugares de "
        "Ribeira\nda Laje, Cacilhas e Porto Salvo) e da freguesia de Paço de Arcos a faixa "
        "confinante com a\nfreguesia de Oeiras e São Julião da Barra até à ribeira de Porto "
        "Salvo.\nOs limites da região são os seguintes:\na) A norte: a linha que separa o "
        "concelho de Cascais do concelho de Sintra;\n")
    assert s["freguesias"] == [("Oeiras", ("Oeiras e São Julião da Barra*", "Paço de Arcos*"))]
    assert s["lugares"] == [("Oeiras", ("Ribeira da Laje", "Cacilhas", "Porto Salvo"))]
    assert s["concelho"] == []


def test_altitude_limit_makes_the_municipio_partial():
    s = _summary("a) No município da Madalena, em áreas de altitude igual ou inferior a 100 m;\n"
                 "b) No município de São Roque, a freguesia de Santa Luzia e parte da freguesia "
                 "da Prainha, lugar da Baía\nde Canas, em áreas de altitude igual ou inferior "
                 "a 100 m;\n")
    assert s["concelho"] == [("Madalena (part)", ())]
    assert s["freguesias"] == [("São Roque", ("Santa Luzia*", "Prainha*"))]
    assert s["lugares"] == [("São Roque", ("Baía de Canas",))]


# ------------------------------------------------------------------ keys --


def test_unit_keys_of_caop_unions():
    parts, keys = unit_keys("União das freguesias de Travassô e Óis da Ribeira",
                            "Travassô e Óis da Ribeira")
    assert parts == ["Travassô", "Óis da Ribeira"]
    assert keys["ois da ribeira"] == frozenset({"ois da ribeira"})
    assert keys["travasso e ois da ribeira"] == frozenset({"travasso", "ois da ribeira"})
    parts, keys = unit_keys("Lamego (Almacave e Sé)", "Lamego (Almacave e Sé)")
    assert parts == ["Almacave", "Sé"]
    assert "lamego se" in keys and "almacave" in keys
    parts, _ = unit_keys(
        "União das freguesias de Celorico (São Pedro e Santa Maria) e Vila Boa do Mondego",
        "Celorico (São Pedro e Santa Maria) e Vila Boa do Mondego")
    assert parts == ["Celorico (São Pedro)", "Celorico (Santa Maria)", "Vila Boa do Mondego"]
    parts, keys = unit_keys(
        "Vidago (União das freguesias de Vidago, Arcossó, Selhariz e Vilarinho das Paranheiras)",
        "Vidago (Vidago, Arcossó, Selhariz e Vilarinho das Paranheiras)")
    assert parts == ["Vidago", "Arcossó", "Selhariz", "Vilarinho das Paranheiras"]
    parts, _ = unit_keys("Barrô", "Barrô")
    assert parts == []


def _fregs(names: list[str], concelho: str = "X") -> list[Freguesia]:
    out = []
    for j, n in enumerate(names):
        parts, keys = unit_keys(n, re.sub(r"^União das freguesias d[ae]s? ", "", n))
        out.append(Freguesia(code=f"{concelho}-{j}", name=n, short=n, concelho=concelho,
                             distrito="D", geom=box(j, 0, j + 1, 1), parts=parts, keys=keys))
    return out


def test_gazetteer_match_rules():
    g = _Gazetteer(_fregs([
        "Santa Catarina da Fonte do Bispo", "Tavira (Santa Maria e Santiago)", "Luz de Tavira",
        "Vila da Rua", "Algeriz", "Vilar de Maçada", "São Mamede de Ribatua", "Conceição",
        "Cabanas de Tavira",
    ]))
    assert g.match("Santiago").freg.name == "Tavira (Santa Maria e Santiago)"
    assert g.match("Santiago").named == frozenset({"santiago"})
    assert g.match("Santa Catarina").how == "affix"
    assert g.match("Rua").freg.name == "Vila da Rua"
    assert g.match("Argeriz").how == "typo"
    assert g.match("Vilar da Maçada").how == "loose"
    assert g.match("São Mamede de Riba Tua").how == "nospace"
    assert g.match("Odiáxere") is None


def test_gazetteer_refuses_an_ambiguous_name():
    g = _Gazetteer(_fregs(["Vila Nova de Cima", "Vila Nova de Baixo"]))
    assert g.match("Vila Nova") is None


# --------------------------------------------------------------- resolver --


def _index(spec: dict[tuple[str, str], list[str]]) -> PTPolygonIndex:
    """A PTPolygonIndex whose freguesias are unit boxes laid side by side."""
    idx = PTPolygonIndex(Path("/nonexistent/EU_PDO.gpkg"), [])
    x = 0
    for (cname, distrito), names in spec.items():
        c = _Concelho(geom=box(0, 0, 0, 0), name=cname, norm=_normalise_concelho(cname),
                      distrito=distrito)
        for j, n in enumerate(names):
            parts, keys = unit_keys(n, re.sub(r"^União das freguesias d[ae]s? ", "", n))
            c.freguesias.append(Freguesia(
                code=f"{cname}-{j}", name=n, short=re.sub(r"^União das freguesias d[ae]s? ", "", n),
                concelho=cname, distrito=distrito, geom=box(x, 0, x + 1, 1),
                parts=parts, keys=keys))
            x += 1
        c.geom = unary_union([f.geom for f in c.freguesias])
        idx._concelho_by_key[f"{cname}|{distrito}"] = c
        idx._concelho_by_norm.setdefault(c.norm, []).append(c)
        idx._names_by_loose.setdefault(_loose_concelho(cname), set()).add(cname)
        idx._concelhos_by_distrito.setdefault(_normalise_concelho(distrito), []).append(c)
    return idx


def test_resolver_draws_freguesias_subtracts_exclusions_and_discloses():
    idx = _index({
        ("Resende", "Viseu"): ["Barrô", "Cárquere", "Resende"],
        ("Oliveira de Azeméis", "Aveiro"): ["Ossela", "Cesar", "Pindelo"],
        ("Águeda", "Aveiro"): ["União das freguesias de Travassô e Óis da Ribeira", "Fermentelos"],
        ("Loulé", "Faro"): ["Almancil", "Alte", "Loulé (São Clemente)"],
    })
    parsed = parse_area_units(
        "e) Do distrito de Viseu, os municípios de Resende, com exceção da freguesia de Barrô.\n"
        "b) Do distrito de Aveiro, a freguesia de Ossela, do município de Oliveira de Azeméis;\n"
        "b) Do município de Águeda, da União das freguesias de Travassô e Óis da Ribeira, "
        "apenas a freguesia de Óis da Ribeira, e as freguesias de Fermentelos;\n"
        "Do concelho de Loulé, as freguesias de Almancil e São Clemente e parte da freguesia "
        "de Alte.\n")
    res = idx.resolve_area_units(parsed)
    assert res.source == "caop-freguesia-union"
    drawn = set(res.freguesias)
    assert "Barrô" not in drawn and {"Cárquere", "Resende"} <= drawn
    assert "Ossela" in drawn and "Cesar" not in drawn
    # every unit of Águeda and Loulé is drawn: their município polygons
    assert set(res.concelhos_whole) == {"Águeda", "Loulé"}
    assert res.proxied == ["Óis da Ribeira → União das freguesias de Travassô e Óis da Ribeira"]
    assert res.partial == ["Alte (Loulé)"]
    assert res.unmatched == []
    assert abs(res.geom.area - 8.0) < 1e-9  # 2 Resende + Ossela + 2 Águeda + 3 Loulé


def test_resolver_keeps_a_union_an_exclusion_only_partly_names():
    """Terras da Beira excludes "Meda" and "Fonte Longa" from Mêda, whose
    CAOP unit also holds Outeiro de Gatos: the union stays, in part."""
    idx = _index({("Mêda", "Guarda"): ["Mêda, Outeiro de Gatos e Fonte Longa", "Longroiva",
                                        "Marialva"]})
    parsed = parse_area_units("Do distrito da Guarda, inclui os municípios de Meda (excluídas "
                              "as freguesias de Fonte Longa, Longroiva e Meda).\n")
    res = idx.resolve_area_units(parsed)
    drawn = set(res.freguesias)
    assert drawn == {"Mêda, Outeiro de Gatos e Fonte Longa", "Marialva"}
    assert res.partial == ["Mêda, Outeiro de Gatos e Fonte Longa (Mêda)"]


def test_resolver_exact_municipio_beats_a_longer_name():
    """"Paredes" is Paredes (Porto), not Paredes de Coura — Vinho Verde had
    lost Paredes to the tie."""
    idx = _index({("Paredes", "Porto"): ["Baltar"], ("Paredes de Coura", "Viana do Castelo"):
                  ["Coura"], ("Penafiel", "Porto"): ["Rio Mau"]})
    parsed = parse_area_units("Do distrito do Porto, os municípios de Paredes e Penafiel;\n"
                              "Todos os municípios do distrito de Viana do Castelo;\n")
    res = idx.resolve_area_units(parsed)
    assert res.unmatched == []
    assert set(res.concelhos_whole) == {"Paredes", "Penafiel", "Paredes de Coura"}


def test_resolver_binds_names_a_holder_tail_names():
    idx = _index({("Armamar", "Viseu"): ["Armamar", "Cimbres", "Aldeias",
                                         "União das freguesias de São Romão e Santiago"]})
    parsed = parse_area_units(
        "• Armamar: Coura e Tões da freguesia de Armamar, União das Freguesias de São Romão "
        "e Santiago, Cimbres;\n")
    res = idx.resolve_area_units(parsed)
    assert res.unmatched == []
    assert set(res.freguesias) == {"Armamar", "Cimbres",
                                   "União das freguesias de São Romão e Santiago"}


def test_partial_parish_stays_disclosed_inside_a_union_drawn_whole():
    """Douro names Vilarinho das Azenhas whole and only some quintas of
    Vilas Boas — one União in CAOP. The union is drawn whole; the card must
    still say Vilas Boas is included only in part (verification finding,
    2026-10-13)."""
    idx = _index({("Vila Flor", "Bragança"): [
        "União das freguesias de Vilas Boas e Vilarinho das Azenhas", "Freixiel", "Roios"]})
    parsed = parse_area_units(
        "as freguesias de Freixiel, Vale Frechoso e Vilarinho das Azenhas, as Quintas da Peça e "
        "das Trigueiras e as propriedades de Vimieiro, situadas na freguesia de Vilas Boas, e "
        "Roios, do concelho de Vila Flor;\n")
    res = idx.resolve_area_units(parsed)
    assert res.partial == ["Vilas Boas (Vila Flor)"]
    assert res.proxied == []  # both former parishes of the union are named


def test_lugar_that_is_a_freguesia_today_is_drawn_in_part():
    """Carcavelos includes "parte da freguesia de Oeiras e São Julião da
    Barra (lugares de … Porto Salvo)"; Porto Salvo is a freguesia of Oeiras
    in CAOP 2025."""
    idx = _index({("Oeiras", "Lisboa"): [
        "União das freguesias de Oeiras e São Julião da Barra, Paço de Arcos e Caxias",
        "Porto Salvo", "Barcarena"]})
    parsed = parse_area_units(
        "Do concelho de Oeiras, parte da freguesia de Oeiras e São Julião da Barra (lugares de "
        "Ribeira\nda Laje, Cacilhas e Porto Salvo).\n")
    res = idx.resolve_area_units(parsed)
    assert set(res.freguesias) == {
        "União das freguesias de Oeiras e São Julião da Barra, Paço de Arcos e Caxias",
        "Porto Salvo"}
    assert res.partial == ["Oeiras e São Julião da Barra, Porto Salvo (Oeiras)"]


def test_islands_only_drops_the_far_islands():
    from _lib.pt.freguesias import _islands_only
    from shapely.geometry import MultiPolygon

    main = box(-17.2, 32.6, -16.7, 32.9)  # Madeira-sized, in degrees
    islet = box(-16.69, 32.75, -16.68, 32.76)  # ~1 km off the tip
    desertas = box(-16.55, 32.40, -16.50, 32.55)  # ~15 km off
    selvagens = box(-15.90, 30.10, -15.85, 30.15)  # ~280 km south
    kept = _islands_only(MultiPolygon([main, islet, desertas, selvagens]), [main])
    parts = list(getattr(kept, "geoms", [kept]))
    assert len(parts) == 2
    assert all(p.bounds[1] > 32.5 for p in parts)


def test_quintas_after_a_comma_open_a_new_item():
    """", as Quintas da Peça …" does not make the parish before the comma
    partial; "Piedade, nos lugares de …" does."""
    s = _summary("as freguesias de Freixiel e Vilarinho das Azenhas, as Quintas da Peça, "
                 "situadas na freguesia de Vilas Boas, do concelho de Vila Flor;\n"
                 "c) No município das Lajes, a freguesia da Piedade, nos lugares de Engrade "
                 "e Manhenha;\n")
    assert ("Vila Flor", ("Freixiel", "Vilarinho das Azenhas", "Vilas Boas*")) in s["freguesias"]
    assert ("Lajes", ("Piedade*",)) in s["freguesias"]


def test_union_name_drawn_as_its_parts_once_caop_split_it():
    """Portaria n.º 668/2010, Anexo I writes "União das freguesias de Campo e
    Sobrado"; CAOP 2025 has re-created Campo and Sobrado. Read whole, the name
    matched Sobrado by suffix and lost Campo. A union CAOP still carries is
    drawn as itself."""
    from _lib.pt.area_units import Item, Piece

    idx = _index({
        ("Valongo", "Porto"): ["Alfena", "Campo", "Ermesinde", "Sobrado", "Valongo"],
        ("Resende", "Viseu"): ["União das freguesias de Anreade e São Romão de Aregos", "Barrô"],
    })
    res = idx.resolve_area_units({"pieces": [
        Piece(kind="freguesias", name="Valongo",
              items=[Item("União das freguesias de Campo e Sobrado")]),
        Piece(kind="freguesias", name="Resende",
              items=[Item("União das freguesias de Anreade e São Romão de Aregos")]),
    ]})
    assert res.unmatched == [] and res.proxied == []
    assert set(res.freguesias) == {"Campo", "Sobrado",
                                   "União das freguesias de Anreade e São Romão de Aregos"}


def test_town_parish_answers_to_the_name_the_act_writes():
    """CAOP's "Vizela (São Paio)" is the act's "São Paio de Vizela", and
    "Caldas de Vizela (São Miguel)" its "São Miguel das Caldas de Vizela"."""
    from _lib.pt.area_units import Item, Piece

    _, keys = unit_keys("Vizela (São Paio)", "Vizela (São Paio)")
    assert "sao paio de vizela" in keys
    idx = _index({("Vizela", "Braga"): [
        "Vizela (São Paio)", "Vizela (Santo Adrião)", "Tagilde", "Infias", "Santa Eulália",
        "União das freguesias de Caldas de Vizela (São Miguel e São João)"]})
    res = idx.resolve_area_units({"pieces": [Piece(kind="freguesias", name="Vizela", items=[
        Item("União das freguesias de Tagilde e São Paio de Vizela"),
        Item("Santo Adrião de Vizela"),
        Item("São Miguel das Caldas de Vizela")])]})
    assert res.unmatched == []
    assert set(res.freguesias) == {
        "Tagilde", "Vizela (São Paio)", "Vizela (Santo Adrião)",
        "União das freguesias de Caldas de Vizela (São Miguel e São João)"}
    assert res.proxied == ["São Miguel das Caldas de Vizela → "
                           "União das freguesias de Caldas de Vizela (São Miguel e São João)"]


def test_excluded_union_written_in_another_order_goes_whole():
    """An exclusion that names a union CAOP orders differently ("Panchorra e
    Ovadas" for "Ovadas e Panchorra") reaches it part by part; the parts are
    gathered per unit, so the union is excluded, not kept in part (code
    review, 2026-10-13)."""
    from _lib.pt.area_units import Item, Piece

    idx = _index({("Resende", "Viseu"): [
        "União das freguesias de Ovadas e Panchorra", "Barrô", "Cárquere"]})
    res = idx.resolve_area_units({"pieces": [Piece(kind="concelho", name="Resende", items=[
        Item("União das freguesias de Panchorra e Ovadas", role="exclude")])]})
    assert set(res.freguesias) == {"Barrô", "Cárquere"}
    assert res.partial == []
    assert res.exclusions_unresolved == []
