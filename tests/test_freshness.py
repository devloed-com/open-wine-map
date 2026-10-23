"""The source-freshness probes (scripts/_lib/freshness/): verdict rules on
canned responses, never the network."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.freshness import (  # noqa: E402  # noqa: E402
    CURRENT,
    GONE,
    IN_OPPOSITION,
    NEWER,
    RELINKED,
    UNREACHABLE,
    UNVERIFIABLE,
    Cache,
    Http,
    Probe,
    eambrosia,
    generic,
    inao,
)


class FakeHttp(Http):
    """Canned answers keyed by URL; counts requests like the real one."""

    def __init__(self, heads=None, shas=None, texts=None, jsons=None, tmp=None):
        super().__init__(Cache(directory=tmp, refresh=True) if tmp else Cache(refresh=True))
        self._heads, self._shas, self._texts, self._jsons = heads or {}, shas or {}, texts or {}, jsons or {}

    def head(self, url):
        return self._heads.get(url, "ConnectionError: canned")

    def sha256(self, url, *, max_bytes=0):
        return self._shas.get(url, "ConnectionError: canned")

    def get_text(self, url):
        return self._texts.get(url, {"error": "ConnectionError: canned"})

    def get_json(self, url, *, ttl_key=None, params=None):
        return self._jsons.get(url, "ConnectionError: canned")


def test_french_dates_and_act_titles():
    assert inao.french_date("Arrêté du 2 septembre 2026 homologuant") == date(2026, 9, 2)
    assert inao.french_date("Décret n°2011-1350 du 24 octobre 2011") == date(2011, 10, 24)
    assert inao.french_date("du 1er juillet 2025") == date(2025, 7, 1)
    assert inao.french_date("27 avril 2026") == date(2026, 4, 27)
    assert inao.french_date("no date") is None
    html = "<title>INAO</title><h1>Arrêté du 8 juin 2026 homologuant le cahier des charges de l'AOC «Blagny»</h1>"
    assert inao.act_title(html).startswith("Arrêté du 8 juin 2026")


def test_inao_probe_verdicts(tmp_path):
    product = "https://www2.inao.gouv.fr/produit/1"
    show = "https://www2.inao.gouv.fr/show_texte/9"
    page = '<a href="/show_texte/9" class="x">Accéder au cahier des charges</a>'
    texte = "<h1>Arrêté du 8 juin 2026 homologuant le cahier des charges</h1>"
    http = FakeHttp(texts={product: page, show: texte}, tmp=tmp_path)
    p = inao.probe_record(http, product_url=product, show_texte_url=show, held_date_text="28 novembre 2011", id_appellation="136", name="Blagny")
    assert p.verdict == NEWER and "2026-06-08" in p.upstream and "136" in p.recipe
    p = inao.probe_record(http, product_url=product, show_texte_url=show, held_date_text="8 juin 2026", id_appellation="136", name="Blagny")
    assert p.verdict == CURRENT
    http = FakeHttp(texts={product: "<p>Une procédure nationale d'opposition est ouverte</p>"}, tmp=tmp_path)
    assert inao.probe_record(http, product_url=product, show_texte_url=show, held_date_text="x", id_appellation="1", name="A").verdict == IN_OPPOSITION
    http = FakeHttp(texts={product: {"error": "HTTP 404", "status": 404}}, tmp=tmp_path)
    assert inao.probe_record(http, product_url=product, show_texte_url=show, held_date_text="x", id_appellation="1", name="A").verdict == GONE
    http = FakeHttp(tmp=tmp_path)
    assert inao.probe_record(http, product_url=product, show_texte_url=show, held_date_text="x", id_appellation="1", name="A").verdict == UNREACHABLE


def test_generic_probe_head_sha_and_tiers(tmp_path):
    url = "https://nat.example/spec.pdf"
    http = FakeHttp(heads={url: {"status": 404, "final_url": url, "etag": "", "last_modified": "", "content_type": "", "content_length": ""}}, tmp=tmp_path)
    assert generic.probe_url(http, tier="national", source_key="national_spec_url", url=url, country="gr", slug="x").verdict == GONE
    http = FakeHttp(heads={url: {"status": 200, "final_url": url, "etag": "", "last_modified": "Mon, 01 Jun 2026 00:00:00 GMT", "content_type": "application/pdf", "content_length": "10"}}, tmp=tmp_path)
    p = generic.probe_url(http, tier="national", source_key="national_spec_url", url=url, country="gr", slug="x", fetched_at="2026-05-23T21:35:00+00:00")
    assert p.verdict == NEWER and "02f" in p.recipe
    p = generic.probe_url(http, tier="national", source_key="national_spec_url", url=url, country="gr", slug="x", fetched_at="2026-07-01T00:00:00+00:00")
    assert p.verdict == CURRENT
    http = FakeHttp(shas={url: {"status": 200, "final_url": url, "sha256": "ab" * 32, "bytes": 10, "content_type": "application/pdf"}}, tmp=tmp_path)
    assert generic.probe_url(http, tier="national", source_key="k", url=url, country="sk", slug="x", held_sha256="ab" * 32, deep=True).verdict == CURRENT
    assert generic.probe_url(http, tier="national", source_key="k", url=url, country="sk", slug="x", held_sha256="cd" * 32, deep=True).verdict == NEWER
    http = FakeHttp(heads={url: {"status": 301, "final_url": "https://other.example/x", "etag": "", "last_modified": "", "content_type": "", "content_length": ""}}, tmp=tmp_path)
    assert generic.probe_url(http, tier="regional", source_key="k", url=url, country="es", slug="x").verdict == RELINKED
    trade = "https://consorzio.example/"
    http = FakeHttp(heads={trade: {"status": 200, "final_url": trade, "etag": "", "last_modified": "", "content_type": "text/html", "content_length": ""}}, tmp=tmp_path)
    p = generic.probe_url(http, tier="trade", source_key="syndicate", url=trade, country="it", slug="x")
    assert p.verdict == CURRENT and "never a source" in p.reason
    eur = "https://eur-lex.europa.eu/eli/C/2026/565/oj/spa"
    assert generic.probe_url(FakeHttp(tmp=tmp_path), tier="eu", source_key="eur_lex_url", url=eur, country="es", slug="x").verdict == "COVERED"


def test_eambrosia_country_probe(monkeypatch, tmp_path):
    live = {"ES": {
        "PDO-ES-1": {"fileNumber": "PDO-ES-1", "modificationDate": "2026-10-01T00:00:00Z", "status": "registered", "removedFlag": False,
                     "publications": [{"text": "OJ C 1"}, {"text": "OJ C 2 (new)"}], "protectedNames": ["Uno"]},
        "PDO-ES-2": {"fileNumber": "PDO-ES-2", "modificationDate": "2026-01-01T00:00:00Z", "status": "registered", "removedFlag": False,
                     "publications": [], "protectedNames": ["Dos"], "amendmentsInProgressFlag": True},
        "PDO-ES-3": {"fileNumber": "PDO-ES-3", "modificationDate": "2026-01-01T00:00:00Z", "status": "registered", "removedFlag": True, "publications": [], "protectedNames": ["Tres"]},
        "PDO-ES-9": {"fileNumber": "PDO-ES-9", "modificationDate": "2026-01-01T00:00:00Z", "status": "registered", "removedFlag": False, "publications": [],
                     "protectedNames": ["Nuevo"], "giType": "PDO", "euProtectionDate": "2026-09-01"},
        "PDO-ES-8": {"fileNumber": "PDO-ES-8", "modificationDate": "2026-01-01T00:00:00Z", "status": "registered", "removedFlag": False, "publications": [],
                     "protectedNames": ["Dos"], "giType": "PDO", "euProtectionDate": "2007-01-01"},
    }}
    rows = [
        {"fileNumber": "PDO-ES-1", "slug": "uno", "name": "Uno", "modification_date": "2026-01-01T00:00:00Z", "publications": [{"text": "OJ C 1"}]},
        {"fileNumber": "PDO-ES-2", "slug": "dos", "name": "Dos", "modification_date": "2026-01-01T00:00:00Z", "publications": []},
        {"fileNumber": "PDO-ES-3", "slug": "tres", "name": "Tres", "modification_date": "2026-01-01T00:00:00Z", "publications": []},
        {"fileNumber": "PDO-ES-4", "slug": "cuatro", "name": "Cuatro", "modification_date": "2026-01-01T00:00:00Z", "publications": []},
    ]
    monkeypatch.setattr(eambrosia, "country_index", lambda cc: (rows, "2026-05-01T00:00:00+00:00"))
    monkeypatch.setattr(eambrosia, "document_fetched_at", lambda cc: {"uno": "2026-05-08T00:00:00+00:00"})
    ps = {p.source_key.split()[1]: p for p in eambrosia.probe_country("es", live)}
    assert ps["PDO-ES-1"].verdict == NEWER and "new publication" in ps["PDO-ES-1"].reason
    assert ps["PDO-ES-2"].verdict == IN_OPPOSITION
    assert ps["PDO-ES-3"].verdict == GONE and "cancelled_gis" in ps["PDO-ES-3"].reason
    assert ps["PDO-ES-4"].verdict == GONE
    assert ps["PDO-ES-9"].verdict == NEWER and "NEW registered" in ps["PDO-ES-9"].reason
    assert ps["PDO-ES-8"].verdict == CURRENT and "duplicate administrative registration" in ps["PDO-ES-8"].reason


def test_probe_dict_roundtrip_and_cache(tmp_path):
    p = Probe(tier="eu", source_key="k", url="u", verdict=UNVERIFIABLE, reason="r")
    d = p.as_dict()
    assert d["verdict"] == UNVERIFIABLE and d["checked_at"]
    c = Cache(directory=tmp_path)
    c.put("k", {"a": 1})
    assert c.get("k") == {"a": 1}
    assert Cache(directory=tmp_path, refresh=True).get("k") is None
