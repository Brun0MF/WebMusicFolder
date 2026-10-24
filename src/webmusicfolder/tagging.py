"""ID3v2.4 tag writing and reading with mutagen."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mutagen.id3 import APIC, ID3, TIT2, TPE1, TXXX, ID3NoHeaderError
from mutagen.mp3 import MP3

DESC_VIDEO_ID = "youtube_id"
DESC_URL = "youtube_url"
DESC_RG_GAIN = "REPLAYGAIN_TRACK_GAIN"
DESC_RG_PEAK = "REPLAYGAIN_TRACK_PEAK"
TOPIC_SUFFIX = " - Topic"
ID3_VERSION = 4
APIC_FRONT_COVER = 3


@dataclass(frozen=True)
class TagInfo:
    title: str
    artist: str
    video_id: str | None
    url: str | None
    has_cover: bool
    duration_s: int


def clean_artist(name: str) -> str:
    """Drop the ' - Topic' suffix YouTube adds to auto generated artist channels."""
    cleaned = name.strip()
    if cleaned.endswith(TOPIC_SUFFIX):
        cleaned = cleaned[: -len(TOPIC_SUFFIX)].rstrip()
    return cleaned


def write_tags(
    path: Path,
    title: str,
    artist: str,
    video_id: str,
    url: str,
    cover: bytes | None = None,
    replaygain: tuple[str, str] | None = None,
) -> None:
    """Replace the file's ID3 tag with ours and save it as ID3v2.4.

    `replaygain` is the (gain, peak) text pair for the REPLAYGAIN_TRACK_* frames.
    """
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()
    tags.delall("TIT2")
    tags.delall("TPE1")
    tags.delall("APIC")
    tags.delall(f"TXXX:{DESC_VIDEO_ID}")
    tags.delall(f"TXXX:{DESC_URL}")
    tags.delall(f"TXXX:{DESC_RG_GAIN}")
    tags.delall(f"TXXX:{DESC_RG_PEAK}")
    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=clean_artist(artist)))
    tags.add(TXXX(encoding=3, desc=DESC_VIDEO_ID, text=video_id))
    tags.add(TXXX(encoding=3, desc=DESC_URL, text=url))
    if replaygain:
        tags.add(TXXX(encoding=3, desc=DESC_RG_GAIN, text=replaygain[0]))
        tags.add(TXXX(encoding=3, desc=DESC_RG_PEAK, text=replaygain[1]))
    if cover:
        tags.add(
            APIC(encoding=3, mime="image/jpeg", type=APIC_FRONT_COVER, desc="Cover", data=cover)
        )
    tags.save(path, v2_version=ID3_VERSION)


def _text(tags: ID3, frame: str) -> str:
    found = tags.get(frame)
    return str(found.text[0]) if found is not None and found.text else ""


def read_tags(path: Path) -> TagInfo:
    """Read the tags we write; missing frames come back empty or None."""
    audio = MP3(path)
    tags = audio.tags if audio.tags is not None else ID3()
    video_id = _text(tags, f"TXXX:{DESC_VIDEO_ID}") or None
    url = _text(tags, f"TXXX:{DESC_URL}") or None
    return TagInfo(
        title=_text(tags, "TIT2"),
        artist=_text(tags, "TPE1"),
        video_id=video_id,
        url=url,
        has_cover=bool(tags.getall("APIC")),
        duration_s=int(round(audio.info.length)),
    )


def read_video_id(path: Path) -> str | None:
    """Video id stored in the file, or None when absent or the file is unreadable."""
    try:
        return read_tags(path).video_id
    except Exception:
        return None
