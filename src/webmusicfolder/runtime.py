"""Apply the persistent settings (music dir, quality, concurrency) to the running app."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI

from webmusicfolder.config import MAX_CONCURRENCY, VALID_QUALITIES, Settings
from webmusicfolder.models import AppSettings


class ConfigValueError(ValueError):
    """A submitted setting is not acceptable."""


def validate_music_dir(raw: str) -> str:
    """Return a cleaned absolute path, '' meaning the environment default."""
    value = raw.strip()
    if not value:
        return ""
    if "\x00" in value or len(value) > 1024:
        raise ConfigValueError("Music folder path is not valid")
    path = Path(value)
    if not path.is_absolute():
        raise ConfigValueError("Music folder must be an absolute path, e.g. /music")
    if ".." in path.parts:
        raise ConfigValueError("Music folder cannot contain '..'")
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigValueError(f"Cannot create the folder: {exc.strerror or exc}") from None
    if not path.is_dir() or not os.access(path, os.R_OK | os.W_OK | os.X_OK):
        raise ConfigValueError("The folder must exist and be readable and writable")
    return str(path)


def validate_quality(value: str) -> str:
    if value not in VALID_QUALITIES:
        raise ConfigValueError(f"Quality must be one of {', '.join(VALID_QUALITIES)}")
    return value


def validate_concurrency(value: int) -> int:
    if not 1 <= value <= MAX_CONCURRENCY:
        raise ConfigValueError(f"Parallel downloads must be between 1 and {MAX_CONCURRENCY}")
    return value


def effective(env: Settings, saved: AppSettings) -> Settings:
    return replace(
        env,
        music_dir=Path(saved.music_dir) if saved.music_dir else env.music_dir,
        quality=saved.default_quality or env.quality,
        concurrency=saved.default_concurrency or env.concurrency,
    )


def apply_settings(app: FastAPI, saved: AppSettings) -> Settings:
    """Make the running app use the saved values on top of the environment ones."""
    state = app.state
    settings = effective(state.env_settings, saved)
    state.settings = settings
    state.download_ctx = replace(state.download_ctx, music_dir=settings.music_dir)
    state.worker.ctx = state.download_ctx
    state.worker.concurrency = settings.concurrency
    if state.library.music_dir != settings.music_dir:
        state.library.music_dir = settings.music_dir
        state.library.invalidate()
    return settings
