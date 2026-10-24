"""Library page data: the file list and embedded covers."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from webmusicfolder.auth import require_auth, verify_csrf
from webmusicfolder.importer import ImportConflictError, link_file
from webmusicfolder.library import SOURCE_APP, SOURCE_EXTERNAL, filter_entries
from webmusicfolder.library_ops import create_folder, delete_files, delete_folder, move_files
from webmusicfolder.models import STATUS_DOWNLOADING, STATUS_QUEUED
from webmusicfolder.paths import PathError, list_subfolders, validate_subfolder
from webmusicfolder.urls import KIND_VIDEO, UrlError, parse_youtube_url

router = APIRouter(prefix="/api/library", dependencies=[Depends(require_auth)])

MAX_BATCH = 5000
PLACEHOLDER_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<rect width="64" height="64" fill="#393b40"/>'
    '<path d="M26 18v22.5a6 6 0 1 0 4 5.6V26h14v-8z" fill="#9da0a8"/></svg>'
)


async def _entries(request: Request) -> list:
    tracks = {t.video_id: t for t in await request.app.state.store.list_tracks()}
    return await asyncio.to_thread(request.app.state.library.scan, tracks)


@router.get("")
async def list_library(
    request: Request,
    q: str = Query("", max_length=200),
    subfolder: str | None = Query(None, max_length=200),
    source: Literal["App", "External"] | None = None,
) -> dict:
    entries = await _entries(request)
    shown = filter_entries(entries, q, subfolder, source)
    counts: dict[str, int] = {
        name: 0 for name in list_subfolders(request.app.state.settings.music_dir)
    }
    for e in entries:
        top = e.subfolder.split("/", 1)[0]
        if top:
            counts[top] = counts.get(top, 0) + 1
    return {
        "folders": [{"name": n, "count": counts[n]} for n in sorted(counts, key=str.casefold)],
        "total": len(entries),
        "count": len(shown),
        "sources": [SOURCE_APP, SOURCE_EXTERNAL],
        "subfolders": sorted({e.subfolder for e in entries}, key=str.casefold),
        "entries": [asdict(e) for e in shown],
    }


@router.post("/rescan", dependencies=[Depends(verify_csrf)])
async def rescan(request: Request) -> dict[str, int]:
    request.app.state.library.invalidate()
    return {"total": len(await _entries(request))}


class LinkBody(BaseModel):
    path: str = Field(max_length=1024)
    link: str = Field(max_length=500)


@router.post("/link", dependencies=[Depends(verify_csrf)])
async def link_external(request: Request, body: LinkBody) -> dict:
    """Make an External file an App file by tagging it with a YouTube video id."""
    try:
        parsed = parse_youtube_url(body.link)
    except UrlError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if parsed.kind != KIND_VIDEO:
        raise HTTPException(status_code=422, detail="Paste a link to one video, not a playlist")
    state = request.app.state
    tracks = {t.video_id: t for t in await state.store.list_tracks()}
    try:
        track = await asyncio.to_thread(
            link_file, state.settings.music_dir, body.path, parsed.id, tracks
        )
    except PathError:
        raise HTTPException(status_code=404, detail="file not found") from None
    except ImportConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not write the file: {exc}") from None
    await state.store.upsert_track(track)
    state.library.invalidate()
    return {"video_id": track.video_id, "path": track.relpath}


class DeleteBody(BaseModel):
    path: str = Field(max_length=1024)


class PathsBody(BaseModel):
    paths: list[str] = Field(min_length=1, max_length=MAX_BATCH)


class MoveBody(PathsBody):
    # '' moves the files to the music root.
    subfolder: str = Field("", max_length=200)


class FolderBody(BaseModel):
    name: str = Field(max_length=200)


def _batch_view(result) -> dict:
    return {
        "done": len(result.done),
        "failed": [{"path": p, "reason": r} for p, r in result.failed],
    }


@router.delete("", dependencies=[Depends(verify_csrf)])
async def delete_track(request: Request, body: DeleteBody) -> dict[str, int]:
    """Delete one MP3 from disk and forget its Track so the link can be downloaded again."""
    state = request.app.state
    result = await asyncio.to_thread(delete_files, state.settings.music_dir, [body.path])
    if not result.done:
        raise HTTPException(status_code=404, detail="file not found")
    removed = await state.store.remove_tracks_by_relpath(body.path)
    state.library.invalidate()
    return {"removed_tracks": removed}


@router.post("/delete", dependencies=[Depends(verify_csrf)])
async def delete_tracks(request: Request, body: PathsBody) -> dict:
    """Delete many MP3s; files that cannot be deleted are reported, the rest still go."""
    state = request.app.state
    result = await asyncio.to_thread(delete_files, state.settings.music_dir, body.paths)
    gone = set(result.done)
    await state.store.remove_tracks_where(lambda t: t.relpath in gone)
    state.library.invalidate()
    return _batch_view(result)


@router.post("/move", dependencies=[Depends(verify_csrf)])
async def move_tracks(request: Request, body: MoveBody) -> dict:
    """Move MP3s into a subfolder ('' for the root); tracks keep their identity."""
    state = request.app.state
    try:
        result = await asyncio.to_thread(
            move_files, state.settings.music_dir, body.paths, body.subfolder
        )
    except PathError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if result.moved:
        await state.store.move_tracks(result.moved)
    state.library.invalidate()
    return _batch_view(result)


@router.post("/folders", dependencies=[Depends(verify_csrf)])
async def add_folder(request: Request, body: FolderBody) -> dict[str, str]:
    try:
        name = await asyncio.to_thread(
            create_folder, request.app.state.settings.music_dir, body.name
        )
    except PathError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not create the folder: {exc}") from None
    return {"name": name}


@router.delete("/folders", dependencies=[Depends(verify_csrf)])
async def remove_folder(request: Request, body: FolderBody) -> dict[str, int]:
    """Delete a subfolder together with every file in it."""
    state = request.app.state
    try:
        name = validate_subfolder(body.name)
    except PathError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    queue = await state.store.list_queue()
    if any(i.subfolder == name and i.status in (STATUS_QUEUED, STATUS_DOWNLOADING) for i in queue):
        raise HTTPException(status_code=409, detail="Downloads for this folder are still queued")
    try:
        count = await asyncio.to_thread(delete_folder, state.settings.music_dir, name)
    except PathError:
        raise HTTPException(status_code=404, detail="folder not found") from None
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not delete the folder: {exc}") from None
    prefix = f"{name}/"
    await state.store.remove_tracks_where(lambda t: t.relpath.startswith(prefix))
    state.library.invalidate()
    return {"deleted_tracks": count}


@router.get("/cover")
async def cover(request: Request, path: str = Query(max_length=1024)) -> Response:
    try:
        found = await asyncio.to_thread(request.app.state.library.cover, path)
    except PathError:
        raise HTTPException(status_code=404, detail="file not found") from None
    if found is None:
        return Response(
            PLACEHOLDER_SVG, media_type="image/svg+xml", headers={"Cache-Control": "max-age=3600"}
        )
    return Response(
        found.data,
        media_type=found.mime,
        # nosniff keeps a browser from treating embedded bytes as anything but an image.
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )
