"""Greek and Cyrillic names in a Latin-language interface
(scripts/_lib/script_display.py; rules of 2026-11-17)."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from _lib.script_display import latin_name, native_html, romanise_name, script_lang

ROOT = Path(__file__).resolve().parents[1]

_TAGGED = [
    ("Мавруд", '<span lang="bg">Мавруд</span>'),
    ("Νάουσα", '<span lang="el">Νάουσα</span>'),
    # only the run in the other script is tagged
    ("Naoussa (Νάουσα)", 'Naoussa (<span lang="el">Νάουσα</span>)'),
    ("Мелник 82", '<span lang="bg">Мелник</span> 82'),
    ("Широка мелнишка лоза", '<span lang="bg">Широка мелнишка лоза</span>'),
    ("Όρος Άθως / Mount Athos", '<span lang="el">Όρος Άθως</span> / Mount Athos'),
    ("🇬🇷 Μακεδονία", '🇬🇷 <span lang="el">Μακεδονία</span>'),
    # Latin text is escaped and left alone
    ("Pineau d'Aunis <b>", "Pineau d&#39;Aunis &lt;b&gt;"),
    ("Žumić & Škrlet", "Žumić &amp; Škrlet"),
    ("", ""),
]


def test_the_original_is_language_tagged_run_by_run() -> None:
    for text, want in _TAGGED:
        assert native_html(text) == want, text


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_tagging_is_mirrored_in_app_js() -> None:
    js = (ROOT / "scripts/_lib/assets/app.js").read_text(encoding="utf-8")
    table = js[js.index("  const NATIVE_RUN_RES"):]
    table = table[:table.index("];") + 2]
    esc = js[js.index("  function escapeHtml(s) {"):]
    esc = esc[:esc.index("\n  }\n") + 5]
    fn = js[js.index("  function nativeHtml(s) {"):]
    fn = fn[:fn.index("\n  }\n") + 5]
    prog = table + "\n" + esc + fn + (
        "\nconst cases = " + json.dumps([t for t, _ in _TAGGED]) + ";"
        "\nprocess.stdout.write(JSON.stringify(cases.map(nativeHtml)));"
    )
    out = subprocess.run([shutil.which("node"), "-"], input=prog, capture_output=True,
                         text=True, check=True)
    assert json.loads(out.stdout) == [want for _t, want in _TAGGED]


def test_the_latin_form_is_the_national_standard_never_an_ascii_fold() -> None:
    # Bulgarian Streamlined System: х → h, й → y, ъ → a, ия → ia
    assert romanise_name("Ахелой") == "Aheloy"            # unidecode: Akheloi
    assert romanise_name("Хеброс") == "Hebros"            # unidecode: Khebros
    assert romanise_name("Мискет кайлъшки") == "Misket kaylashki"
    assert romanise_name("Евмолпия") == "Evmolpia"
    # ELOT 743
    assert romanise_name("Ξινόμαυρο") == "Xinomavro"      # unidecode: Xinomauro
    assert romanise_name("Αθήρι Μαύρο") == "Athiri Mavro"
    # the regulator's colour code is a code, not a letter of the name
    assert romanise_name("Αθήρι Β") == "Athiri"
    assert romanise_name("Λιάτικο Ν") == "Liatiko"
    # a Latin name has no Latin form of its own, accents or not
    assert romanise_name("Sémillon") == "" and romanise_name("Žumić") == ""


def test_the_catalogue_name_comes_before_the_standard() -> None:
    assert latin_name("Σουλτανίνα", "Sultanina") == "Sultanina"   # ELOT: Soultanina
    assert latin_name("Ахелой") == "Aheloy"
    assert latin_name("Sémillon", "Semillon") == ""


def test_one_language_per_script() -> None:
    assert script_lang("Νάουσα") == "el" and script_lang("Мавруд") == "bg"
    assert script_lang("Mercurey") == "" and script_lang("") == ""


def test_every_non_latin_name_of_the_build_is_greek_or_bulgarian() -> None:
    """The tag is chosen by script: Greek → el, Cyrillic → bg. A record in
    Cyrillic from another country (or Greek from outside Greece and Cyprus)
    would be mis-tagged — add its language to script_display and app.js."""
    bundles = sorted((ROOT / "wiki" / "data").glob("aocs.en.*.js"))
    if not bundles:
        pytest.skip("no build")
    text = bundles[-1].read_text(encoding="utf-8")
    start = text.index('"aocs":') + len('"aocs":')
    aocs, _end = json.JSONDecoder().raw_decode(text[start:].lstrip())
    wrong = []
    for slug, rec in aocs.items():
        lang = script_lang(rec.get("name") or "")
        cc = rec.get("country") or "fr"
        if (lang == "el" and cc not in ("gr", "cy")) or (lang == "bg" and cc != "bg"):
            wrong.append((slug, cc, rec.get("name")))
    assert not wrong, wrong
