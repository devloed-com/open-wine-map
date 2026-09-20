"""One build, two hosts (2026-09-16): the per-host maps in .env are parsed the
same way for Plausible and CARTO, and the deploy environments cannot share a
zone by default — a beta command must never land on production."""
from __future__ import annotations

import hashlib
import importlib.util
import pathlib

from _lib import env

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_host_map_parsing(monkeypatch):
    monkeypatch.setenv(
        "OWM_TEST_MAP", " WWW.Beta.openwinemap.com=k1 , localhost=k2 ,garbage, =k3, x= "
    )
    assert env._host_map("OWM_TEST_MAP") == {"beta.openwinemap.com": "k1", "localhost": "k2"}
    monkeypatch.setenv("OWM_TEST_MAP", "")
    assert env._host_map("OWM_TEST_MAP") == {}


def test_plausible_default_survives_and_carto_map_is_optional(monkeypatch):
    monkeypatch.setenv("PLAUSIBLE_SITES", "beta.openwinemap.com=pa-beta")
    sites = env.plausible_sites()
    assert sites["openwinemap.com"] == "pa-QAprx84urDZKvC3I6r6bc"
    assert sites["beta.openwinemap.com"] == "pa-beta"
    monkeypatch.setenv("CARTO_BASEMAP_KEYS", "beta.openwinemap.com=cb1_x")
    assert env.carto_basemap_keys() == {"beta.openwinemap.com": "cb1_x"}
    # An empty value is the "no entries" case: an *unset* variable is re-filled
    # from the repo-root .env by load_dotenv (environment wins, .env fills gaps).
    monkeypatch.setenv("CARTO_BASEMAP_KEYS", "")
    assert env.carto_basemap_keys() == {}


def test_deploy_environments_are_disjoint_and_beta_is_not_indexable():
    deploy = _load("deploy")
    snapshot = _load("snapshot_deployed")
    for envs in (deploy._ENVS, snapshot._ENVS):
        assert set(envs) == {"prod", "beta"}
        assert len({e["zone"] for e in envs.values()}) == len(envs)
        assert len({e["host"] for e in envs.values()}) == len(envs)
        assert len({e["suffix"] for e in envs.values()}) == len(envs)
        assert envs["prod"]["suffix"] == ""
    assert deploy._ENVS["prod"]["indexable"] and deploy._ENVS["prod"]["apex"]
    assert not deploy._ENVS["beta"]["indexable"] and not deploy._ENVS["beta"]["apex"]
    assert deploy._NOINDEX_ROBOTS.startswith(b"User-agent: *\n") and b"Disallow: /\n" in deploy._NOINDEX_ROBOTS
    assert deploy._ENVS["prod"]["host"] == deploy._CANONICAL_HOST


def test_hash_local_hashes_overrides_from_their_body(tmp_path):
    deploy = _load("deploy")
    (tmp_path / "robots.txt").write_text("User-agent: *\nAllow: /\n")
    (tmp_path / "index.html").write_text("<p>x</p>")
    (tmp_path / ".DS_Store").write_bytes(b"junk")
    plain = deploy.hash_local(tmp_path, {})
    assert set(plain) == {"robots.txt", "index.html"}
    beta = deploy.hash_local(tmp_path, {"robots.txt": deploy._NOINDEX_ROBOTS})
    assert beta["robots.txt"] == hashlib.sha256(deploy._NOINDEX_ROBOTS).hexdigest()
    assert beta["robots.txt"] != plain["robots.txt"]
    assert beta["index.html"] == plain["index.html"]


def test_indexnow_skips_pages_changed_only_by_an_asset_hash(tmp_path):
    deploy = _load("deploy")
    page = tmp_path / "en" / "santenay" / "index.html"
    page.parent.mkdir(parents=True)
    page.write_text('<script src="/assets/app.en.0123456789.js"></script><p>Santenay</p>')
    before = deploy.fingerprint_pages(tmp_path, ["en/santenay/index.html"])
    page.write_text('<script src="/assets/app.en.abcdefabcd.js"></script><p>Santenay</p>')
    after = deploy.fingerprint_pages(tmp_path, ["en/santenay/index.html"])
    assert before == after
    page.write_text('<script src="/assets/app.en.abcdefabcd.js"></script><p>Santenay AOC</p>')
    edited = deploy.fingerprint_pages(tmp_path, ["en/santenay/index.html"])
    assert edited != after

    to_upload = ["en/santenay/index.html", "assets/app.en.abcdefabcd.js"]
    # Previous deploy known → only the content change (and any deletion) goes out.
    rels, skipped = deploy.pages_to_submit(to_upload, ["fr/old/index.html"], after, before)
    assert rels == ["fr/old/index.html"] and skipped == 1
    rels, skipped = deploy.pages_to_submit(to_upload, [], edited, before)
    assert rels == ["en/santenay/index.html"] and skipped == 0
    # First deploy from this checkout → everything changed is submitted.
    rels, skipped = deploy.pages_to_submit(to_upload, [], after, {})
    assert rels == ["en/santenay/index.html"] and skipped == 0
    # Non-page files never reach IndexNow.
    assert "assets/app.en.abcdefabcd.js" not in rels
