"""Guards for stage 01's eAmbrosia register fallback tier.

Offline: the register client is never called. What is pinned here is the
*shape* of a register-sourced manifest entry — the provenance keys, the
promotion of the cached attachment into the content-addressed cahiers dir,
and the fact that `fetched_at` comes from the cache rather than the clock, so
a re-run cannot churn the manifest.
"""

from __future__ import annotations

import hashlib
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _lib.fr.register_cahier import RegisterCahier  # noqa: E402

m01 = importlib.import_module("01_scrape_cahiers")

PDF_BYTES = b"%PDF-1.4\nfake cahier\n"
SHA = hashlib.sha256(PDF_BYTES).hexdigest()
FETCHED_AT = "2026-08-29T09:00:00+00:00"


def _cahier(tmp_path: Path) -> tuple[RegisterCahier, Path]:
    src = tmp_path / "register-cache"
    src.mkdir()
    (src / f"{SHA}.pdf").write_bytes(PDF_BYTES)
    cahier = RegisterCahier(
        file_number="PDO-FR-A0571",
        attachment_uri="4685",
        attachment_url="https://example.invalid/attachments/4685",
        attachment_name="CDC_Batard-Montrachet.pdf",
        single_doc_ref="Ares(2011)1350579",
        filename=f"{SHA}.pdf",
        sha256=SHA,
        bytes=len(PDF_BYTES),
        fetched_at=FETCHED_AT,
    )
    return cahier, src


class _Tier:
    """Minimal stand-in for RegisterTier — no network, no resolved.json."""

    def __init__(self, cahier, binding):
        self._cahier = cahier
        self.resolved = {"130": binding}
        self.enabled = True

    def cahier_for(self, id_appellation):
        return self._cahier if id_appellation in self.resolved else None


def _patch_dirs(monkeypatch, tmp_path, cache_dir):
    """Point the register cache at `cache_dir` and the cahiers dir at a temp
    one, so nothing touches raw/."""
    out = tmp_path / "cahiers"
    monkeypatch.setattr(m01, "OUT_DIR", out)
    monkeypatch.setattr(m01.rc, "PDF_DIR", cache_dir)
    return out


def test_register_tier_writes_provenance_and_promotes_the_pdf(monkeypatch, tmp_path):
    cahier, cache = _cahier(tmp_path)
    out = _patch_dirs(monkeypatch, tmp_path, cache)
    app = m01.Appellation(id_appellation="130", name="Bâtard-Montrachet", products=[])
    manifest: dict = {}

    status, extra = m01._register_tier(
        app, manifest, m01._stub_meta(app),
        _Tier(cahier, {"register_name": "Bâtard-Montrachet", "matched_via": "full"}),
        {}, fallback=("missed", 0),
    )

    assert (status, extra) == ("register", 0)
    entry = manifest["130"]
    assert entry["source_kind"] == "eambrosia-register"
    assert entry["register_file_number"] == "PDO-FR-A0571"
    assert entry["register_attachment_uri"] == "4685"
    assert entry["register_attachment_name"] == "CDC_Batard-Montrachet.pdf"
    assert entry["register_protected_name"] == "Bâtard-Montrachet"
    assert entry["register_matched_via"] == "full"
    assert entry["boagri_url"] == "", "a register attachment did not come from BO Agri"
    assert entry["register_attachment_url"].endswith("/4685")
    assert entry["sha256"] == SHA
    assert entry["filename"] == f"{SHA}.pdf"
    assert entry["fetched_at"] == FETCHED_AT, "must come from the cache, not the clock"
    assert (out / f"{SHA}.pdf").read_bytes() == PDF_BYTES


def test_register_tier_is_inert_without_a_binding(monkeypatch, tmp_path):
    cahier, cache = _cahier(tmp_path)
    _patch_dirs(monkeypatch, tmp_path, cache)
    app = m01.Appellation(id_appellation="999", name="Nowhere", products=[])
    manifest: dict = {}

    assert m01._register_tier(
        app, manifest, m01._stub_meta(app), _Tier(cahier, {}), {},
        fallback=("missed", 0),
    ) == ("missed", 0)
    assert manifest == {}


def test_register_tier_is_inert_when_disabled(monkeypatch, tmp_path):
    app = m01.Appellation(id_appellation="130", name="Bâtard-Montrachet", products=[])
    manifest: dict = {}
    assert m01._register_tier(
        app, manifest, m01._stub_meta(app), None, {}, fallback=None
    ) == (None, 0)
    assert manifest == {}


def test_promotion_is_idempotent(monkeypatch, tmp_path):
    cahier, cache = _cahier(tmp_path)
    out = _patch_dirs(monkeypatch, tmp_path, cache)
    out.mkdir()
    (out / f"{SHA}.pdf").write_bytes(PDF_BYTES)
    mtime = (out / f"{SHA}.pdf").stat().st_mtime_ns

    m01._promote_register_pdf(cahier)

    assert (out / f"{SHA}.pdf").stat().st_mtime_ns == mtime


def test_stub_meta_carries_no_register_keys():
    """A miss that the register cannot fill must leave a plain entry, so an
    appellation still on BO Agri keeps a byte-identical manifest entry."""
    app = m01.Appellation(id_appellation="1", name="X", products=[])
    assert not any(k.startswith("register_") for k in m01._stub_meta(app))
    assert "source_kind" not in m01._stub_meta(app)


def test_cached_rejects_a_pdf_that_no_longer_hashes_to_its_name(monkeypatch, tmp_path):
    """The cached file is fed to the stage-02 extractor as if it were the
    regulator's document, so corruption must fail loudly."""
    from _lib.fr import register_cahier as regc

    cahier, cache = _cahier(tmp_path)
    monkeypatch.setattr(regc, "PDF_DIR", cache)
    manifest = {cahier.file_number: {"status": "ok", **_asdict(cahier)}}

    assert regc.cached(cahier.file_number, manifest) is not None
    (cache / cahier.filename).write_bytes(PDF_BYTES[:5])
    assert regc.cached(cahier.file_number, manifest) is None


def test_sticky_miss_is_remembered_and_transient_failure_is_not(tmp_path):
    from _lib.fr import register_cahier as regc

    assert regc.recorded_miss("X", {"X": {"status": "no-cahier"}}) == "no-cahier"
    assert regc.recorded_miss("X", {"X": {"status": "unresolved"}}) == "unresolved"
    assert regc.recorded_miss("X", {"X": {"status": "fetch-failed"}}) is None
    assert regc.recorded_miss("X", {}) is None


def test_legacy_manifest_entries_without_status_still_resolve(monkeypatch, tmp_path):
    from _lib.fr import register_cahier as regc

    cahier, cache = _cahier(tmp_path)
    monkeypatch.setattr(regc, "PDF_DIR", cache)
    legacy = {cahier.file_number: _asdict(cahier)}  # written before `status` existed
    assert regc.cached(cahier.file_number, legacy) is not None


def _asdict(cahier):
    from dataclasses import asdict

    return asdict(cahier)


def test_register_tier_never_re_sources_an_appellation_that_has_a_cahier(
    monkeypatch, tmp_path,
):
    """A transient INAO outage is not an upstream change: `resolve_cahier` and
    `_download_first_pdf` both return None for a 5xx or a timeout, so the tier
    must leave a working entry exactly as it found it."""
    cahier, cache = _cahier(tmp_path)
    out = _patch_dirs(monkeypatch, tmp_path, cache)
    out.mkdir()
    (out / "aaaa.pdf").write_bytes(b"%PDF-1.4\nthe canonical BO Agri cahier\n")
    prior = {
        "name": "Bâtard-Montrachet",
        "boagri_url": "https://info.agriculture.gouv.fr/.../telechargement",
        "filename": "aaaa.pdf",
        "sha256": "aaaa",
        "fetched_at": "2026-05-01T00:00:00+00:00",
    }
    manifest = {"130": dict(prior)}
    app = m01.Appellation(id_appellation="130", name="Bâtard-Montrachet", products=[])

    assert m01._register_tier(
        app, manifest, m01._stub_meta(app, prior),
        _Tier(cahier, {"register_name": "Bâtard-Montrachet", "matched_via": "full"}),
        prior, fallback=("missed", 0),
    ) == ("missed", 0)
    assert manifest["130"] == prior


def test_stub_meta_carries_prior_inao_metadata_forward():
    """Failing to reach www2.inao.gouv.fr is not evidence that the product
    page or the Légifrance trail ceased to exist."""
    app = m01.Appellation(id_appellation="1", name="X", products=[])
    prior = {
        "product_url": "https://www2.inao.gouv.fr/produit/42",
        "show_texte_url": "https://www2.inao.gouv.fr/show_texte/9",
        "show_texte_paths": ["/show_texte/9"],
        "boagri_url_candidates": ["https://info.agriculture.gouv.fr/a"],
        "legifrance_jorftext_ids": ["JORFTEXT000000000001"],
        "canonical_idproduit": "42",
        "canonical_produit": "X rouge",
    }
    meta = m01._stub_meta(app, prior)
    for key, value in prior.items():
        assert meta[key] == value
    assert meta["boagri_url"] == ""


def test_absent_id_map_does_not_record_a_sticky_miss(monkeypatch, tmp_path):
    """A listing that failed to load says nothing about any individual GI, so
    one bad network moment must not blank the tier permanently."""
    from _lib.fr import register_cahier as regc

    manifest: dict = {}
    monkeypatch.setattr(regc, "MANIFEST_PATH", tmp_path / "manifest.json")
    assert regc.fetch("PDO-FR-A0571", {}, manifest) == (None, "unresolved")
    assert manifest == {}

    assert regc.fetch("PDO-FR-A0571", {"PDO-FR-OTHER": 1}, manifest) == (None, "unresolved")
    assert manifest["PDO-FR-A0571"]["status"] == "unresolved"
