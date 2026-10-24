"""Turn pasted lines into video entries; playlists are expanded with the runner in flat mode."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from webmusicfolder.errors import DownloadError
from webmusicfolder.runner_client import RunnerSpec, cookie_args, run_runner
from webmusicfolder.urls import KIND_PLAYLIST, UrlError, parse_youtube_url, video_url

KIND_INVALID = "invalid"
MAX_LINES = 500


@dataclass(frozen=True)
class ResolvedItem:
    video_id: str
    url: str
    title: str


@dataclass
class LinkResult:
    line: str
    # 'video', 'playlist' or 'invalid'
    kind: str
    items: list[ResolvedItem] = field(default_factory=list)
    # Playlist entries that are private or deleted and cannot be downloaded.
    skipped: int = 0
    error: str | None = None


@dataclass
class Resolution:
    links: list[LinkResult]

    def unique_items(self) -> list[ResolvedItem]:
        """All items in input order, each video id once."""
        seen: set[str] = set()
        unique = []
        for link in self.links:
            for entry in link.items:
                if entry.video_id not in seen:
                    seen.add(entry.video_id)
                    unique.append(entry)
        return unique


def split_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


async def _expand_playlist(
    line: str, url: str, spec: RunnerSpec, cookies: Path | None, browser: str | None
) -> LinkResult:
    result = LinkResult(line=line, kind=KIND_PLAYLIST)
    args = ["flat", url, *cookie_args(cookies, browser)]

    def on_event(event: dict) -> None:
        kind = event.get("type")
        if kind == "entry":
            video_id = str(event.get("video_id", ""))
            result.items.append(
                ResolvedItem(video_id, video_url(video_id), str(event.get("title", "")))
            )
        elif kind == "skipped":
            result.skipped += 1

    try:
        await run_runner(spec, args, on_event)
    except DownloadError as exc:
        result.error = exc.message
        result.items.clear()
    return result


async def resolve_links(
    text: str, spec: RunnerSpec, cookies: Path | None = None, browser: str | None = None
) -> Resolution:
    """Classify every non empty line. Videos need no network; playlists run the runner."""
    results = []
    for line in split_lines(text)[:MAX_LINES]:
        try:
            parsed = parse_youtube_url(line)
        except UrlError as exc:
            results.append(LinkResult(line=line, kind=KIND_INVALID, error=str(exc)))
            continue
        if parsed.kind == KIND_PLAYLIST:
            results.append(await _expand_playlist(line, parsed.url, spec, cookies, browser))
        else:
            results.append(
                LinkResult(
                    line=line,
                    kind="video",
                    items=[ResolvedItem(parsed.id, parsed.url, "")],
                )
            )
    return Resolution(results)
