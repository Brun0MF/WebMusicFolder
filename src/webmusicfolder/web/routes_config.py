"""Persistent settings: music folder, default quality and parallel downloads."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from webmusicfolder.auth import require_auth, verify_csrf
from webmusicfolder.config import MAX_CONCURRENCY, VALID_QUALITIES
from webmusicfolder.models import STATUS_DOWNLOADING
from webmusicfolder.runtime import (
    ConfigValueError,
    apply_settings,
    validate_concurrency,
    validate_music_dir,
    validate_quality,
)

router = APIRouter(prefix="/api/config", dependencies=[Depends(require_auth)])


class ConfigBody(BaseModel):
    # Only the fields that are sent change; an empty music_dir restores the default.
    music_dir: str | None = None
    quality: str | None = None
    concurrency: int | None = None


def _view(request: Request) -> dict:
    state = request.app.state
    return {
        "music_dir": str(state.settings.music_dir),
        "default_music_dir": str(state.env_settings.music_dir),
        "quality": state.settings.quality,
        "concurrency": state.settings.concurrency,
        "qualities": list(VALID_QUALITIES),
        "max_concurrency": MAX_CONCURRENCY,
        "data_dir": str(state.settings.data_dir),
    }


@router.get("")
async def get_config(request: Request) -> dict:
    return _view(request)


@router.post("", dependencies=[Depends(verify_csrf)])
async def update_config(request: Request, body: ConfigBody) -> dict:
    state = request.app.state
    changes: dict = {}
    try:
        if body.music_dir is not None:
            changes["music_dir"] = validate_music_dir(body.music_dir)
        if body.quality is not None:
            changes["default_quality"] = validate_quality(body.quality)
        if body.concurrency is not None:
            changes["default_concurrency"] = validate_concurrency(body.concurrency)
    except ConfigValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if "music_dir" in changes:
        queue = await state.store.list_queue()
        if any(item.status == STATUS_DOWNLOADING for item in queue):
            raise HTTPException(
                status_code=409, detail="A download is running; change the folder when it is idle"
            )
    if changes:
        saved = await state.store.update_settings(**changes)
        apply_settings(request.app, saved)
    return _view(request)
