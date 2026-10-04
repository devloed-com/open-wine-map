"""The grape-tooltip translator must be able to read every card locale it
walks, and the tooltip must be able to name every source it can produce.

2026-09-24: Roter Riesling's only Wikipedia card is German; the translator
crashed on `LOCALE_NAME['de']`, and Blauer Wildbacher, Rathay and Kraljevina
(German / Slovene cards only) never reached the chain at all, so all four
showed no tooltip in any locale. 230 Italian-sourced tooltips meanwhile
rendered "Wikipedia IT" for want of a `wiki_lang_it` label."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def _load_translator():
    spec = importlib.util.spec_from_file_location(
        "grape_tx", ROOT / "scripts" / "02b_translate_grapes.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_source_locale_has_a_prompt_name():
    tx = _load_translator()
    missing = [lang for lang in tx.SOURCE_LOCALES if lang not in tx.LOCALE_NAME]
    assert not missing, f"LOCALE_NAME lacks {missing}: the prompt would KeyError"


def test_every_source_locale_has_a_tooltip_label():
    from _lib.map_template import build_labels

    labels = build_labels(lambda s: s)
    tx = _load_translator()
    missing = [lang for lang in tx.SOURCE_LOCALES if f"wiki_lang_{lang}" not in labels]
    assert not missing, f"no wiki_lang_ label for {missing}: tooltip falls back to a code"


def test_card_only_locales_come_after_the_existing_chain():
    tx = _load_translator()
    chain = tx.source_chain("x", "fr", "it")
    assert chain.index("en") < chain.index("de") < chain.index("sl") < chain.index("bg")
    assert tx.source_chain("x", "en", "de")[0] == "de"
