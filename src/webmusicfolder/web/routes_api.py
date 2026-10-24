"""JSON endpoints used by the pages."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from webmusicfolder.auth import require_auth, verify_csrf
from webmusicfolder.duplicates import find_duplicates
from webmusicfolder.models import STATUS_DOWNLOADING, STATUS_QUEUED, QueueItem
from webmusicfolder.paths import PathError, list_subfolders, validate_subfolder
from webmusicfolder.resolver import MAX_LINES, resolve_links
from webmusicfolder.urls import is_video_id, video_url

router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])

MAX_LINKS_CHARS = 200_000
MAX_CONFIRM_ITEMS = 5000


class PreviewBody(BaseModel):
    links: str = Field(max_length=MAX_LINKS_CHARS)
    subfolder: str = ""


class ConfirmItem(BaseModel):
    video_id: str
    title: str = Field(default="", max_length=300)
    # Redownload a video the app already has, replacing its file.
    overwrite: bool = False


class ConfirmBody(BaseModel):
    subfolder: str = ""
    items: list[ConfirmItem] = Field(max_length=MAX_CONFIRM_ITEMS)


def _subfolder_or_422(raw: str) -> str:
    try:
        return validate_subfolder(raw)
    except PathError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.get("/folders")
async def folders(request: Request) -> dict[str, list[str]]:
    return {"folders": list_subfolders(request.app.state.settings.music_dir)}


@router.post("/submit/preview", dependencies=[Depends(verify_csrf)])
async def submit_preview(request: Request, body: PreviewBody) -> dict:
    subfolder = _subfolder_or_422(body.subfolder)
    ctx = request.app.state.download_ctx
    resolution = await resolve_links(body.links, ctx.runner, ctx.cookies, ctx.cookies_from_browser)
    items = resolution.unique_items()
    store = request.app.state.store
    music_dir = request.app.state.settings.music_dir
    found = await asyncio.to_thread(
        find_duplicates,
        music_dir,
        {t.video_id: t for t in await store.list_tracks()},
        await store.list_queue(),
        [i.video_id for i in items],
    )
    return {
        "subfolder": subfolder,
        "links": [
            {
                "line": link.line,
                "kind": link.kind,
                "count": len(link.items),
                "skipped": link.skipped,
                "error": link.error,
            }
            for link in resolution.links
        ],
        "total": len(items),
        "truncated": len(body.links.splitlines()) > MAX_LINES,
        "items": [{"video_id": i.video_id, "title": i.title} for i in items],
        "duplicates": [
            {
                "video_id": d.video_id,
                "kind": d.kind,
                "title": d.title or next(i.title for i in items if i.video_id == d.video_id),
                "path": d.relpath,
            }
            for d in found.values()
        ],
    }


@router.post("/submit/confirm", dependencies=[Depends(verify_csrf)])
async def submit_confirm(request: Request, body: ConfirmBody) -> dict[str, int]:
    subfolder = _subfolder_or_422(body.subfolder)
    for entry in body.items:
        if not is_video_id(entry.video_id):
            raise HTTPException(status_code=422, detail=f"invalid video id {entry.video_id!r}")

    store = request.app.state.store
    active = {
        i.video_id
        for i in await store.list_queue()
        if i.status in (STATUS_QUEUED, STATUS_DOWNLOADING)
    }
    music_dir = request.app.state.settings.music_dir
    tracks = {t.video_id: t for t in await store.list_tracks()}
    on_disk = await asyncio.to_thread(
        find_duplicates, music_dir, tracks, [], [e.video_id for e in body.items]
    )
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    seen: set[str] = set()
    new_items = []
    for entry in body.items:
        if entry.video_id in seen or entry.video_id in active:
            continue
        seen.add(entry.video_id)
        item_folder = subfolder
        overwrite = entry.video_id in on_disk
        if overwrite:
            # A known file is only touched on an explicit redownload, in its own folder.
            if not entry.overwrite:
                continue
            item_folder = tracks[entry.video_id].subfolder
        new_items.append(
            QueueItem(
                id=str(uuid.uuid4()),
                video_id=entry.video_id,
                url=video_url(entry.video_id),
                title=entry.title or entry.video_id,
                subfolder=item_folder,
                added_at=now,
                overwrite=overwrite,
            )
        )
    if new_items:
        await store.add_queue_items(new_items)
        for item in new_items:
            request.app.state.bus.publish("item", asdict(item))
        request.app.state.worker.wake()
    return {"queued": len(new_items), "ignored": len(body.items) - len(new_items)}
