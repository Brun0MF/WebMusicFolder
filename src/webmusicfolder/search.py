"""Search YouTube by name through the runner and return video candidates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from webmusicfolder.runner_client import RunnerSpec, cookie_args, run_runner
from webmusicfolder.urls import is_video_id, video_url

MAX_QUERY_CHARS = 200
RESULT_LIMIT = 10


class QueryError(ValueError):
    """The search text is not acceptable; the message is shown to the user."""


@dataclass(frozen=True)
class SearchResult:
    video_id: str
    url: str
    title: str
    channel: str
    duration_s: int


def clean_query(raw: str) -> str:
    text = " ".join(raw.split())
    if not text:
        raise QueryError("type something to search for")
    if len(text) > MAX_QUERY_CHARS:
        raise QueryError(f"search text is longer than {MAX_QUERY_CHARS} characters")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        raise QueryError("search text contains control characters")
    return text


async def search(
    query: str,
    spec: RunnerSpec,
    cookies: Path | None = None,
    limit: int = RESULT_LIMIT,
    browser: str | None = None,
) -> list[SearchResult]:
    """Run a search. Raises QueryError for bad text and DownloadError when yt-dlp fails."""
    text = clean_query(query)
    # `--` keeps a query that starts with a dash from being read as an option.
    args = ["search", "--limit", str(limit), *cookie_args(cookies, browser), "--", text]
    results: list[SearchResult] = []
    seen: set[str] = set()

    def on_event(event: dict) -> None:
        if event.get("type") != "entry":
            return
        video_id = str(event.get("video_id", ""))
        # The URL is rebuilt from the id; nothing else from the result is trusted.
        if not is_video_id(video_id) or video_id in seen:
            return
        seen.add(video_id)
        results.append(
            SearchResult(
                video_id=video_id,
                url=video_url(video_id),
                title=str(event.get("title", "")),
                channel=str(event.get("channel", "")),
                duration_s=int(event.get("duration_s") or 0),
            )
        )

    await run_runner(spec, args, on_event)
    return results[:limit]
