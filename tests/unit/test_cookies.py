import os
import stat
from pathlib import Path

import pytest

from webmusicfolder.cookies import CookiesError, CookieStore, normalise
from webmusicfolder.runner_client import build_download_args

ROW = ".youtube.com\tTRUE\t/\tTRUE\t1893456000\tSID\tsecretvalue123"
JAR = f"# Netscape HTTP Cookie File\n# comment\n\n{ROW}\n.google.com\tTRUE\t/\tFALSE\t0\tNID\tabc\n"


def test_valid_jar_is_accepted_and_gets_a_header():
    out = normalise(f"{ROW}\n")
    assert out.splitlines()[0] == "# Netscape HTTP Cookie File"
    assert ROW in out


def test_comments_blank_lines_crlf_and_httponly_rows():
    text = (
        "# Netscape HTTP Cookie File\r\n\r\n"
        "#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t1893456000\t__Secure-3PSID\tzzz\r\n"
    )
    assert "#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t1893456000\t__Secure-3PSID\tzzz" in normalise(
        text
    )


def test_space_separated_paste_is_converted_to_tabs():
    spaced = ".youtube.com TRUE / TRUE 1893456000 SID secretvalue123"
    assert ROW in normalise(spaced)


def test_cookie_without_value_is_accepted():
    assert "\tEMPTY\t\n" in normalise(".youtube.com\tTRUE\t/\tFALSE\t0\tEMPTY\t")


@pytest.mark.parametrize(
    "text, message",
    [
        ("", "No cookies found"),
        ("# only a comment\n", "No cookies found"),
        ("just some words\n", "Line 1"),
        (".youtube.com\tMAYBE\t/\tTRUE\t1\tSID\tv", "Line 1"),
        (".youtube.com\tTRUE\tnopath\tTRUE\t1\tSID\tv", "Line 1"),
        (".youtube.com\tTRUE\t/\tTRUE\tsoon\tSID\tv", "Line 1"),
        (f"{ROW}\nbroken row\n", "Line 2"),
        (".example.com\tTRUE\t/\tTRUE\t1\tSID\tv", "youtube.com or google.com"),
        ("a\x00b", "not text"),
        ('{"cookies": []}', "Line 1"),
    ],
)
def test_invalid_input_is_rejected_without_echoing_content(text, message):
    with pytest.raises(CookiesError, match=message) as exc:
        normalise(text)
    assert "secretvalue123" not in str(exc.value)


def test_save_writes_mode_0600_and_reports_status(tmp_path: Path):
    store = CookieStore(tmp_path / "data" / "cookies.txt")
    assert not store.status().loaded
    status = store.save(JAR)
    assert status.loaded and status.saved_at
    assert stat.S_IMODE(os.stat(store.path).st_mode) == 0o600
    assert "secretvalue123" in store.path.read_text()
    assert list(store.path.parent.glob(".*tmp")) == []


def test_mode_stays_0600_even_with_a_permissive_umask(tmp_path: Path):
    old = os.umask(0)
    try:
        store = CookieStore(tmp_path / "cookies.txt")
        store.save(JAR)
        store.save(JAR)
    finally:
        os.umask(old)
    assert stat.S_IMODE(os.stat(store.path).st_mode) == 0o600


def test_invalid_save_keeps_the_previous_file(tmp_path: Path):
    store = CookieStore(tmp_path / "cookies.txt")
    store.save(JAR)
    before = store.path.read_text()
    with pytest.raises(CookiesError):
        store.save("garbage")
    assert store.path.read_text() == before


def test_oversized_input_is_rejected(tmp_path: Path):
    store = CookieStore(tmp_path / "cookies.txt")
    with pytest.raises(CookiesError, match="too large"):
        store.save(ROW + "\n" + "#" * (600 * 1024))
    assert not store.status().loaded


def test_delete_removes_the_file(tmp_path: Path):
    store = CookieStore(tmp_path / "cookies.txt")
    store.save(JAR)
    assert store.delete() is True
    assert not store.path.exists() and not store.status().loaded
    assert store.delete() is False


def test_runner_command_line_gets_the_cookies_path_only_when_given(tmp_path: Path):
    (tmp_path / "cookies.txt").write_text("x")
    with_cookies = build_download_args("u", tmp_path, "v0", tmp_path / "cookies.txt")
    assert with_cookies[-2:] == ["--cookies", str(tmp_path / "cookies.txt")]
    assert "--cookies" not in build_download_args("u", tmp_path, "v0", None)
