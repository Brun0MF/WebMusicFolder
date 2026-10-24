"""Live queue view: the SSE stream and the per item actions."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from webmusicfolder.auth import require_auth, verify_csrf
from webmusicfolder.events import event_stream

router = APIRouter(dependencies=[Depends(require_auth)])


async def build_snapshot(request: Request) -> dict[str, Any]:
    worker = request.app.state.worker
    items = await request.app.state.store.list_queue()
    return {
        "items": [asdict(i) for i in items],
        "progress": list(worker.progress.values()),
        "paused": worker.paused_reason,
    }


@router.get("/events")
async def events(request: Request) -> StreamingResponse:
    stream = event_stream(request.app.state.bus, lambda: build_snapshot(request))
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        # no-transform and X-Accel-Buffering stop proxies from buffering the stream.
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.post("/api/queue/{item_id}/cancel", dependencies=[Depends(verify_csrf)])
async def cancel_item(request: Request, item_id: str) -> dict[str, bool]:
    try:
        await request.app.state.worker.cancel(item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown queue item") from None
    return {"ok": True}


@router.post("/api/queue/{item_id}/retry", dependencies=[Depends(verify_csrf)])
async def retry_item(request: Request, item_id: str) -> dict[str, bool]:
    try:
        await request.app.state.worker.retry(item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown queue item") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return {"ok": True}


@router.post("/api/queue/cancel_all", dependencies=[Depends(verify_csrf)])
async def cancel_all(request: Request) -> dict[str, int]:
    return {"cancelled": await request.app.state.worker.cancel_pending()}


@router.post("/api/queue/dismiss_all", dependencies=[Depends(verify_csrf)])
async def dismiss_all(request: Request) -> dict[str, int]:
    return {"dismissed": await request.app.state.worker.dismiss_finished()}


@router.post("/api/queue/retry_failed", dependencies=[Depends(verify_csrf)])
async def retry_failed(request: Request) -> dict[str, int]:
    return {"requeued": await request.app.state.worker.retry_failed()}
