from pathlib import Path

import pytest

from webmusicfolder.config import ConfigError, load_settings


def test_defaults():
    s = load_settings({"WMF_PASSWORD": "pw"})
    assert s.password == "pw"
    assert s.music_dir == Path("/music")
    assert s.data_dir == Path("/data")
    assert s.port == 8080
    assert s.secret is None
    assert s.concurrency == 1
    assert s.quality == "v5"


def test_overrides():
    s = load_settings(
        {
            "WMF_PASSWORD": "pw",
            "WMF_PORT": "9000",
            "WMF_QUALITY": "320K",
            "WMF_CONCURRENCY": "3",
            "WMF_SECRET": "abc",
            "PUID": "1001",
            "PGID": "1002",
        }
    )
    assert (s.port, s.quality, s.concurrency, s.secret) == (9000, "320k", 3, "abc")
    assert (s.puid, s.pgid) == (1001, 1002)


@pytest.mark.parametrize("env", [{}, {"WMF_PASSWORD": ""}])
def test_missing_password(env):
    with pytest.raises(ConfigError, match="WMF_PASSWORD"):
        load_settings(env)


@pytest.mark.parametrize("port", ["abc", "0", "70000", "-1"])
def test_bad_port(port):
    with pytest.raises(ConfigError, match="WMF_PORT"):
        load_settings({"WMF_PASSWORD": "pw", "WMF_PORT": port})


def test_bad_quality():
    with pytest.raises(ConfigError, match="WMF_QUALITY"):
        load_settings({"WMF_PASSWORD": "pw", "WMF_QUALITY": "flac"})


@pytest.mark.parametrize("value", ["0", "5", "x"])
def test_bad_concurrency(value):
    with pytest.raises(ConfigError, match="WMF_CONCURRENCY"):
        load_settings({"WMF_PASSWORD": "pw", "WMF_CONCURRENCY": value})


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", None),
        ("firefox", "firefox"),
        (" Chrome ", "chrome"),
        ("firefox:default-release", "firefox:default-release"),
    ],
)
def test_cookies_from_browser_valid(raw, expected):
    env = {"WMF_PASSWORD": "pw", "WMF_COOKIES_FROM_BROWSER": raw}
    assert load_settings(env).cookies_from_browser == expected


@pytest.mark.parametrize("raw", ["netscape", "firefox:", ":profile", "../firefox"])
def test_cookies_from_browser_invalid(raw):
    with pytest.raises(ConfigError, match="WMF_COOKIES_FROM_BROWSER"):
        load_settings({"WMF_PASSWORD": "pw", "WMF_COOKIES_FROM_BROWSER": raw})
