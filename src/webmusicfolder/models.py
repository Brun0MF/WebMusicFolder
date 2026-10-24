"""State dataclasses and their JSON (de)serialisation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any

STATUS_QUEUED = "queued"
STATUS_DOWNLOADING = "downloading"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
QUEUE_STATUSES = (STATUS_QUEUED, STATUS_DOWNLOADING, STATUS_DONE, STATUS_FAILED)


def _build[T](cls: type[T], data: dict[str, Any]) -> T:
    """Build a dataclass from a dict, ignoring unknown keys so newer files still load."""
    if not isinstance(data, dict):
        raise ValueError(f"{cls.__name__} must be an object, got {type(data).__name__}")
    known = {f.name for f in fields(cls)}  # type: ignore[arg-type]
    return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class AppSettings:
    quality: str = "v0"
    concurrency: int = 1
    sponsorblock: bool = False
    replaygain: bool = False
    # Persistent overrides of the environment defaults; empty or 0 means "use the environment".
    music_dir: str = ""
    default_quality: str = ""
    default_concurrency: int = 0


@dataclass
class Track:
    video_id: str
    url: str
    title: str
    artist: str
    duration_s: int
    subfolder: str
    relpath: str
    downloaded_at: str
    quality: str


@dataclass
class QueueItem:
    id: str
    video_id: str
    url: str
    title: str
    subfolder: str
    added_at: str
    status: str = STATUS_QUEUED
    attempts: int = 0
    error: str | None = None
    overwrite: bool = False
    # Set when the item reaches done or failed; drives the 7 day pruning.
    finished_at: str | None = None

    def __post_init__(self) -> None:
        if self.status not in QUEUE_STATUSES:
            raise ValueError(f"invalid queue status {self.status!r}")


@dataclass
class State:
    version: int = 1
    settings: AppSettings = field(default_factory=AppSettings)
    tracks: dict[str, Track] = field(default_factory=dict)
    queue: list[QueueItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> State:
        if not isinstance(data, dict):
            raise ValueError("state root must be an object")
        tracks = data.get("tracks", {})
        queue = data.get("queue", [])
        if not isinstance(tracks, dict):
            raise ValueError("tracks must be an object")
        if not isinstance(queue, list):
            raise ValueError("queue must be a list")
        return cls(
            version=data["version"],
            settings=_build(AppSettings, data.get("settings", {})),
            tracks={str(k): _build(Track, v) for k, v in tracks.items()},
            queue=[_build(QueueItem, v) for v in queue],
        )
