"""Standalone yt-dlp wrapper run as a subprocess.

Usage:
    python -m webmusicfolder.ytdlp_runner download URL --tmp-dir DIR --quality Q
        [--cookies FILE] [--sponsorblock]  (Q: v0, v2, v5, 320k, 192k or 128k)
    python -m webmusicfolder.ytdlp_runner flat URL
    python -m webmusicfolder.ytdlp_runner search [--limit N] [--cookies FILE] -- QUERY
    python -m webmusicfolder.ytdlp_runner version

Stdout carries one JSON object per line (UTF-8):
    {"type":"progress","pct":42.1,"speed":123456.0,"eta":12}
    {"type":"stage","stage":"converting"}
    {"type":"log","line":"..."}
    {"type":"entry","video_id":"...","title":"..."}          (flat mode)
    {"type":"entry","video_id":"...","title":"...","channel":"...","duration_s":N}  (search mode)
    {"type":"skipped","video_id":"...","reason":"..."}       (flat mode)
    {"type":"done","path":"...","cover":"...","info":{...}}  (download mode)
    {"type":"done","count":N}                                (flat mode)
    {"type":"done","version":"2026.10.21"}                   (version mode)
    {"type":"error","code":"private","message":"..."}
Anything else yt-dlp prints is redirected to stderr so the protocol stays clean.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any, TextIO

from webmusicfolder.errors import (
    CODE_UNKNOWN,
    USER_MESSAGES,
    classify_error,
)

PROGRESS_MIN_INTERVAL_S = 0.25
QUALITY_TO_PREFERRED = {
    "v0": "0",
    "v2": "2",
    "v5": "5",
    "320k": "320",
    "192k": "192",
    "128k": "128",
}
# Flat playlist entries for removed videos carry these placeholder titles.
# Non music segments only. intro and outro are left alone because in music they are music.
SPONSORBLOCK_CATEGORIES = ["sponsor", "selfpromo", "interaction", "music_offtopic"]
UNAVAILABLE_TITLES = {"[private video]": "private", "[deleted video]": "unavailable"}


class Emitter:
    """Writes protocol lines to the real stdout."""

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream

    def emit(self, **fields: Any) -> None:
        self._stream.write(json.dumps(fields, ensure_ascii=False) + "\n")
        self._stream.flush()


class _Logger:
    """yt-dlp logger that forwards lines as log events."""

    def __init__(self, emitter: Emitter) -> None:
        self._emitter = emitter

    def debug(self, msg: str) -> None:
        # yt-dlp sends info messages through debug() prefixed with [debug] only in verbose mode.
        if not msg.startswith("[debug]"):
            self._emitter.emit(type="log", line=msg)

    def info(self, msg: str) -> None:
        self._emitter.emit(type="log", line=msg)

    def warning(self, msg: str) -> None:
        self._emitter.emit(type="log", line=f"WARNING: {msg}")

    def error(self, msg: str) -> None:
        # yt-dlp already prefixes its own error text.
        line = msg if msg.startswith("ERROR:") else f"ERROR: {msg}"
        self._emitter.emit(type="log", line=line)


def apply_cookies(options: dict[str, Any], cookies: Path | None, browser: str | None) -> None:
    """A cookies file wins over a browser; either one is optional."""
    if cookies is not None:
        options["cookiefile"] = str(cookies)
    elif browser:
        name, _, profile = browser.partition(":")
        options["cookiesfrombrowser"] = (name, profile or None)


def build_options(
    tmp_dir: Path,
    quality: str,
    cookies: Path | None,
    emitter: Emitter,
    sponsorblock: bool = False,
    browser: str | None = None,
) -> dict[str, Any]:
    """yt-dlp options for one audio download to MP3 with a JPEG thumbnail."""
    last_emit = [0.0]

    def on_progress(data: dict[str, Any]) -> None:
        status = data.get("status")
        if status == "finished":
            emitter.emit(type="progress", pct=100.0, speed=None, eta=0)
            return
        if status != "downloading":
            return
        now = time.monotonic()
        if now - last_emit[0] < PROGRESS_MIN_INTERVAL_S:
            return
        last_emit[0] = now
        total = data.get("total_bytes") or data.get("total_bytes_estimate")
        done = data.get("downloaded_bytes") or 0
        if total:
            pct = round(100.0 * done / total, 1)
        else:
            # Fragmented formats report no byte total, only the fragment position.
            count = data.get("fragment_count") or 0
            pct = round(100.0 * (data.get("fragment_index") or 0) / count, 1) if count else None
        emitter.emit(type="progress", pct=pct, speed=data.get("speed"), eta=data.get("eta"))

    def on_postprocess(data: dict[str, Any]) -> None:
        if data.get("status") == "started":
            emitter.emit(type="stage", stage=str(data.get("postprocessor", "")))

    options: dict[str, Any] = {
        "format": "bestaudio/best",
        "outtmpl": str(tmp_dir / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "writethumbnail": True,
        # File dates are download dates, not upload dates.
        "updatetime": False,
        "quiet": True,
        "no_color": True,
        "noprogress": True,
        "ignoreconfig": True,
        "cachedir": False,
        "logger": _Logger(emitter),
        "progress_hooks": [on_progress],
        "postprocessor_hooks": [on_postprocess],
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": QUALITY_TO_PREFERRED[quality],
            },
            {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"},
        ],
    }
    apply_cookies(options, cookies, browser)
    if sponsorblock:
        # Same order yt-dlp uses itself: look up segments, extract audio, then cut.
        pps = options["postprocessors"]
        pps.insert(
            0,
            {"key": "SponsorBlock", "categories": SPONSORBLOCK_CATEGORIES, "when": "after_filter"},
        )
        pps.append(
            {
                "key": "ModifyChapters",
                "remove_chapters_patterns": [],
                "remove_sponsor_segments": SPONSORBLOCK_CATEGORIES,
                "remove_ranges": [],
                "sponsorblock_chapter_title": "[SponsorBlock]: %(category_names)l",
                "force_keyframes": False,
            }
        )
    return options


def mp3_duration_s(path: Path) -> int | None:
    """Length of the final file in seconds; used after a cut changed it."""
    try:
        from mutagen.mp3 import MP3

        return int(round(MP3(path).info.length))
    except Exception:
        return None


def pick_artist(info: dict[str, Any]) -> str:
    """Best artist guess: explicit music metadata, then channel, then uploader."""
    artist = info.get("artist")
    if isinstance(artist, str) and artist.strip():
        return artist.split(",")[0].strip()
    for key in ("channel", "uploader"):
        value = info.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _extract(url: str, options: dict[str, Any]) -> Any:
    import yt_dlp

    with yt_dlp.YoutubeDL(options) as ydl:
        return ydl.extract_info(url, download=True)


def run_download(
    url: str,
    tmp_dir: Path,
    quality: str,
    cookies: Path | None,
    em: Emitter,
    sponsorblock: bool = False,
    browser: str | None = None,
) -> None:
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        info = _extract(url, build_options(tmp_dir, quality, cookies, em, sponsorblock, browser))
    except Exception as exc:
        # A SponsorBlock outage must not cost the download: retry once without it.
        if not sponsorblock or "sponsorblock" not in str(exc).lower():
            raise
        em.emit(type="log", line="WARNING: SponsorBlock failed, downloading without it")
        info = _extract(url, build_options(tmp_dir, quality, cookies, em, False, browser))
        sponsorblock = False
    if not isinstance(info, dict) or not info.get("id"):
        em.emit(type="error", code=CODE_UNKNOWN, message="yt-dlp returned no video info")
        return
    video_id = str(info["id"])
    mp3 = tmp_dir / f"{video_id}.mp3"
    if not mp3.is_file():
        em.emit(type="error", code="ffmpeg", message="converted MP3 file is missing")
        return
    cover = tmp_dir / f"{video_id}.jpg"
    duration = int(info.get("duration") or 0)
    if sponsorblock:
        duration = mp3_duration_s(mp3) or duration
    em.emit(
        type="done",
        path=str(mp3),
        cover=str(cover) if cover.is_file() else None,
        info={
            "video_id": video_id,
            "title": str(info.get("track") or info.get("title") or video_id),
            "artist": pick_artist(info),
            "duration_s": duration,
            "url": str(info.get("webpage_url") or url),
        },
    )


def flat_entries(info: dict[str, Any]) -> Iterable[dict[str, Any]]:
    """Entries of a flat extraction; a plain video counts as a one entry list."""
    entries = info.get("entries")
    if entries is None:
        return [info]
    return entries


def run_flat(url: str, cookies: Path | None, em: Emitter, browser: str | None = None) -> None:
    import yt_dlp

    options: dict[str, Any] = {
        "extract_flat": "in_playlist",
        "lazy_playlist": True,
        "skip_download": True,
        "quiet": True,
        "no_color": True,
        "ignoreconfig": True,
        "cachedir": False,
        "logger": _Logger(em),
    }
    apply_cookies(options, cookies, browser)
    count = 0
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
        if not isinstance(info, dict):
            em.emit(type="error", code=CODE_UNKNOWN, message="yt-dlp returned no playlist info")
            return
        for entry in flat_entries(info):
            if not isinstance(entry, dict):
                continue
            video_id = str(entry.get("id") or "")
            title = str(entry.get("title") or "")
            reason = UNAVAILABLE_TITLES.get(title.lower())
            if not video_id or reason:
                em.emit(type="skipped", video_id=video_id, reason=reason or "unavailable")
                continue
            count += 1
            em.emit(type="entry", video_id=video_id, title=title)
    em.emit(type="done", count=count)


def run_search(
    query: str, limit: int, cookies: Path | None, em: Emitter, browser: str | None = None
) -> None:
    import yt_dlp

    options: dict[str, Any] = {
        "extract_flat": "in_playlist",
        "skip_download": True,
        "quiet": True,
        "no_color": True,
        "ignoreconfig": True,
        "cachedir": False,
        "logger": _Logger(em),
    }
    apply_cookies(options, cookies, browser)
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
    count = 0
    for entry in flat_entries(info) if isinstance(info, dict) else []:
        if not isinstance(entry, dict):
            continue
        video_id = str(entry.get("id") or "")
        title = str(entry.get("title") or "")
        if not video_id or title.lower() in UNAVAILABLE_TITLES:
            continue
        count += 1
        em.emit(
            type="entry",
            video_id=video_id,
            title=title,
            channel=str(entry.get("channel") or entry.get("uploader") or ""),
            duration_s=int(entry.get("duration") or 0),
        )
    em.emit(type="done", count=count)


def run_version(em: Emitter) -> None:
    """Report the yt-dlp version this interpreter would use (after PYTHONPATH)."""
    from yt_dlp.version import __version__

    em.emit(type="done", version=str(__version__))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ytdlp_runner")
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("version")
    dl = sub.add_parser("download")
    dl.add_argument("url")
    dl.add_argument("--tmp-dir", type=Path, required=True)
    dl.add_argument("--quality", choices=sorted(QUALITY_TO_PREFERRED), default="v5")
    dl.add_argument("--cookies", type=Path)
    dl.add_argument("--sponsorblock", action="store_true")
    dl.add_argument("--cookies-from-browser")
    search = sub.add_parser("search")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--cookies", type=Path)
    search.add_argument("--cookies-from-browser")
    search.add_argument("query")
    flat = sub.add_parser("flat")
    flat.add_argument("url")
    flat.add_argument("--cookies", type=Path)
    flat.add_argument("--cookies-from-browser")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    em = Emitter(sys.stdout)
    # Keep stray prints from yt-dlp or ffmpeg wrappers out of the protocol stream.
    sys.stdout = sys.stderr
    cookie_arg = getattr(args, "cookies", None)
    cookies = cookie_arg if cookie_arg and cookie_arg.is_file() else None
    browser = getattr(args, "cookies_from_browser", None)
    try:
        if args.mode == "download":
            run_download(
                args.url, args.tmp_dir, args.quality, cookies, em, args.sponsorblock, browser
            )
        elif args.mode == "search":
            run_search(args.query, max(1, min(args.limit, 25)), cookies, em, browser)
        elif args.mode == "version":
            run_version(em)
        else:
            run_flat(args.url, cookies, em, browser)
    except Exception as exc:
        message = str(exc) or exc.__class__.__name__
        code = classify_error(message)
        em.emit(type="error", code=code, message=_short(message, code))
        return 1
    return 0


def _short(message: str, code: str) -> str:
    """Keep the raw text for diagnosis but prefix the stable user message."""
    cleaned = " ".join(message.split())
    return f"{USER_MESSAGES[code]}: {cleaned[:300]}"


if __name__ == "__main__":
    raise SystemExit(main())
