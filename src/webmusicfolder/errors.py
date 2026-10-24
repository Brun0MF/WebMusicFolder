"""Download error codes shared by the runner, the client and the worker."""

from __future__ import annotations

CODE_PRIVATE = "private"
CODE_UNAVAILABLE = "unavailable"
CODE_AGE_RESTRICTED = "age_restricted"
CODE_LOGIN = "login"
CODE_NETWORK = "network"
CODE_FFMPEG = "ffmpeg"
CODE_DISK_FULL = "disk_full"
CODE_PERMISSION = "permission"
CODE_UNKNOWN = "unknown"

ERROR_CODES = (
    CODE_PRIVATE,
    CODE_UNAVAILABLE,
    CODE_AGE_RESTRICTED,
    CODE_LOGIN,
    CODE_NETWORK,
    CODE_FFMPEG,
    CODE_DISK_FULL,
    CODE_PERMISSION,
    CODE_UNKNOWN,
)

# Only these are worth retrying automatically.
RETRYABLE_CODES = frozenset({CODE_NETWORK})

USER_MESSAGES = {
    CODE_PRIVATE: "Private video, upload cookies",
    CODE_UNAVAILABLE: "Video unavailable",
    CODE_AGE_RESTRICTED: "Age restricted video, upload cookies",
    CODE_LOGIN: "YouTube asks to sign in, upload fresh cookies",
    CODE_NETWORK: "Network error",
    CODE_FFMPEG: "Audio conversion failed",
    CODE_DISK_FULL: "Disk full",
    CODE_PERMISSION: "Cannot write to the music folder",
    CODE_UNKNOWN: "Download failed",
}

# Checked in order: the first group with a matching phrase wins.
_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (CODE_DISK_FULL, ("no space left", "disk quota")),
    (CODE_PERMISSION, ("permission denied", "read-only file system")),
    (CODE_AGE_RESTRICTED, ("confirm your age", "age-restricted", "age restricted")),
    (
        CODE_LOGIN,
        (
            "not a bot",
            "cookies are no longer valid",
            "login required",
            "use --cookies-from-browser or --cookies",
        ),
    ),
    (
        CODE_PRIVATE,
        (
            "private video",
            "video is private",
            "granted access to this video",
            "private playlist",
            "this playlist is private",
            "members-only",
            "join this channel",
        ),
    ),
    (
        CODE_UNAVAILABLE,
        (
            "video unavailable",
            "video is unavailable",
            "this video is not available",
            "has been removed",
            "account associated with this video has been terminated",
            "this video is no longer available",
            "premieres in",
            "live event will begin",
            "does not exist",
            "copyright",
            "not made this video available in your country",
            "unsupported url",
            "is not a valid url",
        ),
    ),
    (CODE_FFMPEG, ("ffmpeg", "ffprobe", "postprocessing", "conversion failed")),
    (
        CODE_NETWORK,
        (
            "unable to download",
            "timed out",
            "timeout",
            "connection",
            "temporary failure",
            "name or service not known",
            "getaddrinfo",
            "http error 5",
            "http error 429",
            "too many requests",
            "network is unreachable",
            "ssl",
            "incomplete read",
        ),
    ),
)


def classify_error(message: str) -> str:
    """Map a yt-dlp or system error message to one of ERROR_CODES."""
    text = message.lower()
    for code, phrases in _PATTERNS:
        if any(p in text for p in phrases):
            return code
    return CODE_UNKNOWN


class DownloadError(Exception):
    """A failed download with a stable code and a short message for the UI."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code if code in ERROR_CODES else CODE_UNKNOWN
        self.message = message

    @property
    def retryable(self) -> bool:
        return self.code in RETRYABLE_CODES
