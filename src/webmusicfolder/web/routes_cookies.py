"""Upload, status and removal of the cookies.txt. The content is never returned."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from webmusicfolder.auth import require_auth, verify_csrf
from webmusicfolder.cookies import MAX_COOKIES_BYTES, CookiesError

router = APIRouter(prefix="/api/cookies", dependencies=[Depends(require_auth)])


class CookiesBody(BaseModel):
    # Characters, not bytes; the store enforces the byte limit.
    text: str = Field(max_length=MAX_COOKIES_BYTES)


def _status(request: Request) -> dict[str, Any]:
    """File status plus the browser the app was configured to read cookies from, if any."""
    browser = request.app.state.download_ctx.cookies_from_browser
    return {**asdict(request.app.state.cookies.status()), "browser": browser}


@router.get("")
async def cookies_status(request: Request) -> dict[str, Any]:
    return _status(request)


@router.post("", dependencies=[Depends(verify_csrf)])
async def cookies_save(request: Request, body: CookiesBody) -> dict[str, Any]:
    try:
        request.app.state.cookies.save(body.text)
    except CookiesError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return _status(request)


@router.delete("", dependencies=[Depends(verify_csrf)])
async def cookies_delete(request: Request) -> dict[str, Any]:
    request.app.state.cookies.delete()
    return _status(request)
