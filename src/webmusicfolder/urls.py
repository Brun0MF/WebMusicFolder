"""YouTube URL validation, classification and normalisation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

ALLOWED_HOSTS = frozenset(
    {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
)
KIND_VIDEO = "video"
KIND_PLAYLIST = "playlist"

_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_PLAYLIST_ID = re.compile(r"^[A-Za-z0-9_-]{2,64}$")
# Path prefixes whose next segment is a video id.
_ID_PREFIXES = ("shorts", "embed", "live", "v")


class UrlError(ValueError):
    """The text is not an acceptable YouTube link; the message is shown to the user."""


@dataclass(frozen=True)
class ParsedUrl:
    kind: str
    # Video id for videos, playlist id for playlists.
    id: str
    # Canonical URL passed to the runner.
    url: str


def video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def playlist_url(playlist_id: str) -> str:
    return f"https://www.youtube.com/playlist?list={playlist_id}"


def parse_youtube_url(raw: str) -> ParsedUrl:
    """Validate a user supplied link and return its kind, id and canonical URL.

    A watch link that also carries a list parameter is treated as the single video;
    only /playlist links expand into playlists.
    """
    text = raw.strip()
    if not text:
        raise UrlError("empty line")
    try:
        parts = urlsplit(text)
        host = (parts.hostname or "").lower()
    except ValueError:
        raise UrlError("not a valid URL") from None
    if parts.scheme.lower() not in ("http", "https"):
        raise UrlError("only http and https links are accepted")
    if parts.username is not None or parts.password is not None:
        raise UrlError("links with credentials are not accepted")
    if host not in ALLOWED_HOSTS:
        raise UrlError("only YouTube links are accepted")

    query = parse_qs(parts.query)
    segments = [s for s in parts.path.split("/") if s]

    if host == "youtu.be":
        return _video(segments[0] if segments else "")

    if segments and segments[0] == "watch":
        return _video((query.get("v") or [""])[0])
    if len(segments) >= 2 and segments[0] in _ID_PREFIXES:
        return _video(segments[1])
    if segments and segments[0] == "playlist":
        playlist_id = (query.get("list") or [""])[0]
        if not _PLAYLIST_ID.match(playlist_id):
            raise UrlError("playlist link has no valid list id")
        return ParsedUrl(KIND_PLAYLIST, playlist_id, playlist_url(playlist_id))
    raise UrlError("not a video or playlist link")


def _video(candidate: str) -> ParsedUrl:
    if not _VIDEO_ID.match(candidate):
        raise UrlError("video link has no valid video id")
    return ParsedUrl(KIND_VIDEO, candidate, video_url(candidate))


def is_video_id(value: str) -> bool:
    return bool(_VIDEO_ID.match(value))
