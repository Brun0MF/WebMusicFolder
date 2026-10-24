"""Environment based configuration, validated once at startup."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

# VBR scale (V0 about 245 kbps, V2 about 190, V5 about 130) and constant bitrates.
VALID_QUALITIES = ("v0", "v2", "v5", "320k", "192k", "128k")
DEFAULT_QUALITY = "v5"
MAX_CONCURRENCY = 4
# Browsers yt-dlp can read cookies from.
BROWSERS = ("brave", "chrome", "chromium", "edge", "firefox", "opera", "safari", "vivaldi", "whale")


class ConfigError(ValueError):
    """Raised when the environment holds a missing or invalid value."""


@dataclass(frozen=True)
class Settings:
    password: str
    music_dir: Path
    data_dir: Path
    port: int
    secret: str | None
    concurrency: int
    quality: str
    puid: int
    pgid: int
    # 'firefox' or 'firefox:profile'; for local runs where a browser exists.
    cookies_from_browser: str | None = None


def _int(env: Mapping[str, str], name: str, default: int, low: int, high: int) -> int:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from None
    if not low <= value <= high:
        raise ConfigError(f"{name} must be between {low} and {high}, got {value}")
    return value


def _browser(env: Mapping[str, str]) -> str | None:
    raw = env.get("WMF_COOKIES_FROM_BROWSER", "").strip()
    if not raw:
        return None
    name, sep, profile = raw.partition(":")
    name = name.strip().lower()
    if name not in BROWSERS:
        raise ConfigError(
            f"WMF_COOKIES_FROM_BROWSER must start with one of {', '.join(BROWSERS)}, got {raw!r}"
        )
    profile = profile.strip()
    if sep and not profile:
        raise ConfigError("WMF_COOKIES_FROM_BROWSER has an empty profile after ':'")
    return f"{name}:{profile}" if profile else name


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build Settings from environment variables, failing fast with a clear message."""
    env = os.environ if env is None else env

    password = env.get("WMF_PASSWORD", "")
    if not password:
        raise ConfigError("WMF_PASSWORD is required: set it to the password used to log in")

    quality = env.get("WMF_QUALITY", DEFAULT_QUALITY).strip().lower() or DEFAULT_QUALITY
    if quality not in VALID_QUALITIES:
        raise ConfigError(
            f"WMF_QUALITY must be one of {', '.join(VALID_QUALITIES)}, got {quality!r}"
        )

    return Settings(
        password=password,
        music_dir=Path(env.get("WMF_MUSIC_DIR", "/music")),
        data_dir=Path(env.get("WMF_DATA_DIR", "/data")),
        port=_int(env, "WMF_PORT", 8080, 1, 65535),
        secret=env.get("WMF_SECRET") or None,
        concurrency=_int(env, "WMF_CONCURRENCY", 1, 1, MAX_CONCURRENCY),
        quality=quality,
        puid=_int(env, "PUID", 1000, 0, 2**31 - 1),
        pgid=_int(env, "PGID", 1000, 0, 2**31 - 1),
        cookies_from_browser=_browser(env),
    )
