"""The yt-dlp output shown in the Logs tab; live lines arrive over /events."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from webmusicfolder.auth import require_auth

router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])


@router.get("/logs")
async def get_logs(request: Request, item: str | None = None) -> dict[str, Any]:
    entries = request.app.state.logs.lines(item)
    return {"entries": entries}
