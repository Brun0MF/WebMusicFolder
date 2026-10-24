"""Settings page actions: yt-dlp version and update."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from webmusicfolder.auth import require_auth, verify_csrf
from webmusicfolder.queue_worker import WorkerBusyError
from webmusicfolder.ytdlp_update import UpdateBusyError, UpdateError

router = APIRouter(prefix="/api/ytdlp", dependencies=[Depends(require_auth)])


@router.get("/version")
async def ytdlp_version(request: Request) -> dict[str, Any]:
    updater = request.app.state.updater
    try:
        version = await updater.version()
    except UpdateError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    return {"version": version, "updating": updater.updating}


@router.post("/update", dependencies=[Depends(verify_csrf)])
async def ytdlp_update(request: Request) -> dict[str, Any]:
    updater = request.app.state.updater
    try:
        # The queue stays idle while the package the runner imports is replaced.
        async with request.app.state.worker.exclusive():
            result = await updater.update()
    except WorkerBusyError as exc:
        raise HTTPException(
            status_code=409, detail=f"Cannot update now ({exc}); try again when the queue is idle"
        ) from None
    except UpdateBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except UpdateError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    return {"old": result.old, "new": result.new, "changed": result.changed}
