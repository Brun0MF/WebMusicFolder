import pytest

from webmusicfolder.urls import (
    KIND_PLAYLIST,
    KIND_VIDEO,
    UrlError,
    is_video_id,
    parse_youtube_url,
)

VID = "dQw4w9WgXcQ"
CANON = f"https://www.youtube.com/watch?v={VID}"


@pytest.mark.parametrize(
    "raw",
    [
        f"https://www.youtube.com/watch?v={VID}",
        f"http://youtube.com/watch?v={VID}&t=42s",
        f"https://m.youtube.com/watch?v={VID}",
        f"https://music.youtube.com/watch?v={VID}&si=abc",
        f"https://youtu.be/{VID}",
        f"https://youtu.be/{VID}?si=xyz",
        f"https://www.youtube.com/shorts/{VID}",
        f"https://www.youtube.com/embed/{VID}",
        f"https://www.youtube.com/live/{VID}",
        f"  https://www.youtube.com/watch?v={VID}  ",
        f"HTTPS://WWW.YOUTUBE.COM/watch?v={VID}",
        f"https://www.youtube.com/watch?v={VID}&list=PLabcdef123456",
    ],
)
def test_video_urls(raw):
    parsed = parse_youtube_url(raw)
    assert (parsed.kind, parsed.id, parsed.url) == (KIND_VIDEO, VID, CANON)


@pytest.mark.parametrize(
    "raw",
    [
        "https://www.youtube.com/playlist?list=PLabcdef123456",
        "https://music.youtube.com/playlist?list=PLabcdef123456&si=1",
    ],
)
def test_playlist_urls(raw):
    parsed = parse_youtube_url(raw)
    assert parsed.kind == KIND_PLAYLIST
    assert parsed.id == "PLabcdef123456"
    assert parsed.url == "https://www.youtube.com/playlist?list=PLabcdef123456"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "not a url",
        "ftp://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "javascript:alert(1)",
        "https://example.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com.evil.com/watch?v=dQw4w9WgXcQ",
        "https://evil.com/?u=youtube.com",
        "https://user:pw@www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch",
        "https://www.youtube.com/watch?v=short",
        "https://www.youtube.com/playlist",
        "https://www.youtube.com/playlist?list=",
        "https://www.youtube.com/@channel",
        "https://www.youtube.com/",
        "https://youtu.be/",
        "https://[::1/",
    ],
)
def test_rejected(raw):
    with pytest.raises(UrlError):
        parse_youtube_url(raw)


def test_is_video_id():
    assert is_video_id(VID)
    assert not is_video_id("short")
    assert not is_video_id("has space!!")
