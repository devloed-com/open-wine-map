"""Tiny gettext glue for the map template.

Translation catalogs live under `locale/<lang>/LC_MESSAGES/messages.po` and are
hand-edited (per CLAUDE.md, only UI chrome is translated — never cahier-derived
content). Stage 04 calls `compile_catalogs()` once per build to refresh `.mo`
files when `.po` mtimes have advanced, then `load_translations(lang)` per
locale to fetch a `gettext`.

`fr` is the source language; its catalog is identity (msgid == msgstr) and the
`Translations` fallback returns the msgid verbatim, so a missing catalog is
harmless.
"""

from __future__ import annotations

from pathlib import Path

from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po
from babel.support import NullTranslations, Translations

ROOT = Path(__file__).resolve().parent.parent.parent
LOCALE_DIR = ROOT / "locale"
LOCALES = ("fr", "en", "es", "nl")
DOMAIN = "messages"


def _po_path(lang: str) -> Path:
    return LOCALE_DIR / lang / "LC_MESSAGES" / f"{DOMAIN}.po"


def _mo_path(lang: str) -> Path:
    return LOCALE_DIR / lang / "LC_MESSAGES" / f"{DOMAIN}.mo"


def compile_catalogs() -> list[str]:
    """Recompile each locale's .mo from .po if .po is newer. Returns updated langs."""
    updated: list[str] = []
    for lang in LOCALES:
        po, mo = _po_path(lang), _mo_path(lang)
        if not po.exists():
            continue
        if mo.exists() and mo.stat().st_mtime >= po.stat().st_mtime:
            continue
        with po.open("rb") as fh:
            catalog = read_po(fh, locale=lang, domain=DOMAIN)
        with mo.open("wb") as fh:
            write_mo(fh, catalog)
        updated.append(lang)
    return updated


def load_translations(lang: str) -> NullTranslations:
    if not _mo_path(lang).exists():
        return NullTranslations()
    return Translations.load(LOCALE_DIR, locales=[lang], domain=DOMAIN)
