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
    URL_RE,
    VIA,
    contributor_credits,
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
        # A link only as the curator's url: an https profile address.
        if "url" in row:
            assert URL_RE.fullmatch(row["url"]), row
    assert "_doc" in json.loads(CONTRIBUTORS_PATH.read_text(encoding="utf-8"))


def test_names_are_deduped_collapsed_and_sorted(tmp_path: Path) -> None:
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"contributors": [
        {"name": "zoë  K."}, {"name": "Anna"}, {"name": "zoë K."}, {"name": "  "},
    ]}), encoding="utf-8")
    assert contributor_names(p) == ["Anna", "zoë K."]
    assert contributor_names(tmp_path / "missing.json") == []


def test_credits_keep_a_plain_https_url_and_drop_anything_else(tmp_path: Path) -> None:
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"contributors": [
        {"name": "wayne530", "url": "https://github.com/wayne530"},
        {"name": "Anna"},
        {"name": "Bob", "url": "javascript:alert(1)"},
        {"name": "Cy", "url": 'https://x.org/" onmouseover="x'},
        {"name": "Anna", "url": "https://example.org/anna"},
    ]}), encoding="utf-8")
    assert contributor_credits(p) == [
        ("Anna", "https://example.org/anna"),
        ("Bob", None),
        ("Cy", None),
        ("wayne530", "https://github.com/wayne530"),
    ]


def test_github_handles_link_to_their_profile() -> None:
    for row in load_contributors():
        if row["via"] == "github":
            assert row.get("url") == f"https://github.com/{row['name']}", row


def _labels() -> defaultdict:
    return defaultdict(str, {
        "about_thanks_h": "Thanks",
        "about_thanks_ux_html": "To {designful}, for the UX.",
        "about_thanks_html": "To the people: {names}.",
        "about_thanks_anon_html": "And the anonymous; get in touch by {email}.",
        "about_privacy_h": "Privacy",
        "about_privacy_html": "No personal data.",
        "about_privacy_credit_html": "Except a name, removed by {email}.",
        "about_contrib_h": "Contribute",
        "about_contact_h": "Get in touch",
        "about_contact_html": "Write to us by {email}.",
        "feedback_email_label": "email",
        "copy_label": "Copy",
        "copy_mail_aria": "Copy the email address",
    })


def _thanks(html: str) -> str:
    return html.split("<h3>Thanks</h3>")[1].split("</section>")[0]


def test_about_thanks_without_names_keeps_designful_and_the_anonymous(monkeypatch) -> None:
    monkeypatch.setattr(mt, "contributor_credits", lambda: [])
    html = mt._build_about_dialog(_labels())
    body = _thanks(html)
    assert '<p>To <a href="https://designful.be/" target="_blank" rel="noopener">designful.be</a>, for the UX.</p>' in body
    assert "To the people" not in body
    assert "And the anonymous; get in touch by " in body and 'class="mail-copy"' in body


def test_about_thanks_section_escapes_names_and_links_a_profile(monkeypatch) -> None:
    monkeypatch.setattr(mt, "contributor_credits", lambda: [
        ("Anna", None), ("<b>x</b>", None), ("wayne530", "https://github.com/wayne530"),
    ])
    html = mt._build_about_dialog(_labels())
    body = _thanks(html)
    assert (
        "<p>To the people: Anna, &lt;b&gt;x&lt;/b&gt;, "
        '<a href="https://github.com/wayne530" target="_blank" rel="noopener">wayne530</a>.</p>'
    ) in body
    # Designful first, the named people, then the anonymous.
    assert body.index("designful.be") < body.index("To the people") < body.index("anonymous")
    # After the contribute section, before the maker's credit line.
    assert html.index("<h3>Thanks</h3>") < html.index('class="about-credit"')


def test_privacy_paragraph_names_the_exception_and_how_to_remove_it() -> None:
    html = mt._build_about_dialog(_labels())
    assert "No personal data. Except a name, removed by " in html
    assert 'class="mail-copy"' in html.split("No personal data.")[1].split("</p>")[0]


def test_about_has_a_contact_section_with_the_split_address(monkeypatch) -> None:
    # The same "e-mail" button as the privacy and thanks sentences: it copies
    # the address, no mailto: link anywhere in the dialog, and the address is
    # never one string in the page — user and domain ride two data
    # attributes, which app.js joins on click (`button.mail-copy`).
    monkeypatch.setattr(mt, "contributor_credits", lambda: [])
    html = mt._build_about_dialog(_labels())
    contact = html.split("<h3>Get in touch</h3>")[1].split("</section>")[0]
    assert contact.startswith('<p>Write to us by <button type="button" class="mail-copy" data-feedback="about" ')
    assert f'data-u="{mt._FEEDBACK_USER}" data-d="{mt._FEEDBACK_DOMAIN}"' in contact
    assert contact.count('class="mail-copy"') == 1 and "copy-field" not in contact
    assert f"{mt._FEEDBACK_USER}@{mt._FEEDBACK_DOMAIN}" not in html
    assert "mailto" not in html and "feedback-mail" not in html and "<a href=\"#\"" not in html
    assert html.index("<h3>Contribute</h3>") < html.index("<h3>Get in touch</h3>") \
        < html.index("<h3>Thanks</h3>")


def test_no_mailto_link_anywhere() -> None:
    # Copy only since 2026-11-25: the sidebar footer, the About dialog and the
    # card's blocked-tracker line copy the address; none opens a mail client.
    labels = _labels()
    labels["sidebar_disclaimer_html"] = "Errors are possible. Flag them by {email}."
    side = mt._build_sidebar_disclaimer(labels)
    assert '<button type="button" class="mail-copy" data-feedback="email" ' in side
    assert "<a " not in side and f"{mt._FEEDBACK_USER}@{mt._FEEDBACK_DOMAIN}" not in side
    assert "'mailto:" not in APP_JS and '"mailto:' not in APP_JS and "armFeedbackMail" not in APP_JS
    # the card's line clones the sidebar's button and names its own channel
    assert "#sidebar-disclaimer button.mail-copy" in APP_JS and "b.dataset.feedback = 'card'" in APP_JS


def test_every_locale_translates_the_contact_strings() -> None:
    from _lib.i18n import compile_catalogs, load_translations

    compile_catalogs()
    fr = mt.build_labels(lambda s: s)
    for lang in ("en", "es", "nl"):
        built = mt.build_labels(load_translations(lang).gettext)
        for k in ("about_contact_h", "about_contact_html", "copy_mail_aria"):
            assert built[k] and built[k] != fr[k], f"{lang}: {k} untranslated"
        assert built["about_contact_html"].count("{email}") == 1
        assert built["feedback_blocked_html"] != fr["feedback_blocked_html"]
        assert "{aspect}" in built["feedback_blocked_html"] and "{email}" in built["feedback_blocked_html"]
        # the button's accessible name holds its visible word (WCAG 2.5.3)
        assert built["feedback_email_label"].lower() in built["copy_mail_aria"].lower()


def test_every_locale_translates_the_credit_strings() -> None:
    from _lib.i18n import compile_catalogs, load_translations

    compile_catalogs()
    keys = ("feedback_credit_label", "feedback_credit_hint", "feedback_sent_credit",
            "about_thanks_h", "about_thanks_html", "about_privacy_credit_html",
            "about_thanks_ux_html", "about_thanks_anon_html")
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
