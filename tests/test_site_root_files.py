"""The root-level service files (search-console verification pages) are
checked in under scripts/_lib/site_root/ and copied into wiki/ by stage 04."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _lib.site_root_files import SITE_ROOT_SRC, copy_site_root_files, site_root_files  # noqa: E402

_NAVER_RE = re.compile(r"^naver[0-9a-f]{32}\.html$")
_SEZNAM_RE = re.compile(r"^seznam-wmt-([A-Za-z0-9]+)\.txt$")


def test_checked_in_files_are_verification_pages():
    files = site_root_files()
    assert files, "scripts/_lib/site_root/ holds at least the Naver file"
    for p in files:
        assert "/" not in p.name and not p.name.startswith(".")
        assert p.name not in ("index.html", "404.html", "robots.txt", "sitemap.xml", "llms.txt")
        if _NAVER_RE.match(p.name):
            assert p.read_text(encoding="utf-8").strip() == f"naver-site-verification: {p.name}"
        if m := _SEZNAM_RE.match(p.name):
            assert p.read_text(encoding="utf-8").strip() == m.group(1)
        assert _NAVER_RE.match(p.name) or _SEZNAM_RE.match(p.name), p.name


def test_copy_is_write_if_changed(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "naver0123456789abcdef0123456789abcdef.html").write_text(
        "naver-site-verification: naver0123456789abcdef0123456789abcdef.html"
    )
    (src / ".DS_Store").write_bytes(b"x")
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    assert copy_site_root_files(wiki, src) == ["naver0123456789abcdef0123456789abcdef.html"]
    dest = wiki / "naver0123456789abcdef0123456789abcdef.html"
    assert dest.read_text() == "naver-site-verification: naver0123456789abcdef0123456789abcdef.html"
    assert not (wiki / ".DS_Store").exists()
    before = dest.stat().st_mtime_ns
    assert copy_site_root_files(wiki, src) == ["naver0123456789abcdef0123456789abcdef.html"]
    assert dest.stat().st_mtime_ns == before


def test_missing_source_dir_copies_nothing(tmp_path):
    assert copy_site_root_files(tmp_path, tmp_path / "absent") == []


def test_source_dir_is_the_checked_in_one():
    assert SITE_ROOT_SRC == ROOT / "scripts" / "_lib" / "site_root"
