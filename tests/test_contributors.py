"""The public credit for visitor feedback: the table a curator fills at
triage (scripts/_lib/contributors.json), the About dialog's thanks list built
from it, and the card's optional name field that offers a credit."""
from __future__ import annotations

import datetime
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import _lib.map_template as mt  # noqa: E402
from _lib.contributors import (  # noqa: E402
    CONTRIBUTORS_PATH,
    NAME_MAX,
    VIA,
    contributor_names,
    load_contributors,
)

APP_JS = (ROOT / "scripts" / "_lib" / "assets" / "app.js").read_text(encoding="utf-8")


def test_table_entries_are_well_formed() -> None:
    seen: set[str] = set()
    for row in load_contributors():
        name = row["name"]
        assert name == " ".join(name.split()) and 0 < len(name) <= NAME_MAX, row
        # A name or pseudonym, never contact details or a link.
        assert "@" not in name and "://" not in name and "www." not in name.lower(), row
        assert name.casefold() not in seen, f"listed twice: {name}"
        seen.add(name.casefold())
        datetime.date.fromisoformat(row["added"])
        assert row["via"] in VIA, row
        assert isinstance(row.get("slugs", []), list), row
        assert row.get("report", "").strip(), f"{name}: say what the report led to"
    assert "_doc" in json.loads(CONTRIBUTORS_PATH.read_text(encoding="utf-8"))


def test_names_are_deduped_collapsed_and_sorted(tmp_path: Path) -> None:
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"contributors": [
        {"name": "zoë  K."}, {"name": "Anna"}, {"name": "zoë K."}, {"name": "  "},
    ]}), encoding="utf-8")
    assert contributor_names(p) == ["Anna", "zoë K."]
    assert contributor_names(tmp_path / "missing.json") == []


def _labels() -> defaultdict:
    return defaultdict(str, {
        "about_thanks_h": "Thanks",
        "about_thanks_html": "To the people: {names}.",
        "about_privacy_h": "Privacy",
        "about_privacy_html": "No personal data.",
        "about_privacy_credit_html": "Except a name, removed by {email}.",
        "feedback_email_label": "email",
    })


def test_about_has_no_thanks_section_without_names(monkeypatch) -> None:
    monkeypatch.setattr(mt, "contributor_names", lambda: [])
    html = mt._build_about_dialog(_labels())
    assert "<h3>Thanks</h3>" not in html


def test_about_thanks_section_escapes_names(monkeypatch) -> None:
    monkeypatch.setattr(mt, "contributor_names", lambda: ["Anna", "<b>x</b>"])
    html = mt._build_about_dialog(_labels())
    assert "<section><h3>Thanks</h3><p>To the people: Anna, &lt;b&gt;x&lt;/b&gt;.</p></section>" in html
    # After the contribute section, before the maker's credit line.
    assert html.index("<h3>Thanks</h3>") < html.index('class="about-credit"')


def test_privacy_paragraph_names_the_exception_and_how_to_remove_it() -> None:
    html = mt._build_about_dialog(_labels())
    assert "No personal data. Except a name, removed by " in html
    assert 'class="feedback-mail"' in html.split("No personal data.")[1].split("</p>")[0]


def test_every_locale_translates_the_credit_strings() -> None:
    from _lib.i18n import compile_catalogs, load_translations

    compile_catalogs()
    keys = ("feedback_credit_label", "feedback_credit_hint", "feedback_sent_credit",
            "about_thanks_h", "about_thanks_html", "about_privacy_credit_html")
    fr = mt.build_labels(lambda s: s)
    for lang in ("en", "es", "nl"):
        built = mt.build_labels(load_translations(lang).gettext)
        for k in keys:
            assert built[k] and built[k] != fr[k], f"{lang}: {k} untranslated"
        assert "{name}" in built["feedback_sent_credit"]
        assert "{names}" in built["about_thanks_html"]
        assert "{email}" in built["about_privacy_credit_html"]


def test_card_offers_the_name_with_its_public_hint_and_sends_it_as_credit() -> None:
    # The field sits in the box a chip tap opens (no extra step), is described
    # by the hint that says it is public, and travels with Send only.
    assert 'class="fb-credit-input"' in APP_JS
    assert 'aria-describedby="${escapeAttr(hintId)}"' in APP_JS
    assert "LABELS.feedback_credit_hint" in APP_JS
    assert "if (credit) props.credit = credit;" in APP_JS
    assert "maxlength=\"${FEEDBACK_CREDIT_MAX}\"" in APP_JS
    assert f"const FEEDBACK_CREDIT_MAX = {NAME_MAX};" in APP_JS
    # Never sent from a chip tap: the flag event carries no credit.
    flagged = APP_JS[APP_JS.index("track('Feedback Flagged'"):]
    assert "credit" not in flagged[:flagged.index("});")]
