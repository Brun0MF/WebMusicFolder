"""Search by name; results are candidates the user adds to the links box."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from webmusicfolder.auth import require_auth, verify_csrf
from webmusicfolder.duplicates import find_duplicates
from webmusicfolder.errors import DownloadError
from webmusicfolder.search import MAX_QUERY_CHARS, QueryError, search

router = APIRouter(prefix="/api/search", dependencies=[Depends(require_auth)])


class SearchBody(BaseModel):
    # Looser than the real limit so the friendly message comes from clean_query.
    q: str = Field(max_length=MAX_QUERY_CHARS * 2)


@router.post("", dependencies=[Depends(verify_csrf)])
async def search_videos(request: Request, body: SearchBody) -> dict[str, Any]:
    ctx = request.app.state.download_ctx
    try:
        found = await search(body.q, ctx.runner, ctx.cookies, browser=ctx.cookies_from_browser)
    except QueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except DownloadError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from None
    store = request.app.state.store
    dupes = await asyncio.to_thread(
        find_duplicates,
        request.app.state.settings.music_dir,
        {t.video_id: t for t in await store.list_tracks()},
        await store.list_queue(),
        [r.video_id for r in found],
    )
    return {
        "results": [
            {**asdict(r), "state": dupes[r.video_id].kind if r.video_id in dupes else None}
            for r in found
        ]
    }
