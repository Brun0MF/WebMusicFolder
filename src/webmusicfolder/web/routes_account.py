"""Change the login password."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from webmusicfolder.auth import client_ip, require_auth, verify_csrf
from webmusicfolder.passwords import MAX_PASSWORD_LEN, MIN_PASSWORD_LEN

router = APIRouter(prefix="/api/account", dependencies=[Depends(require_auth)])


class PasswordBody(BaseModel):
    current: str = Field(max_length=MAX_PASSWORD_LEN)
    new: str = Field(max_length=MAX_PASSWORD_LEN)


@router.post("/password", dependencies=[Depends(verify_csrf)])
async def change_password(request: Request, body: PasswordBody) -> dict[str, bool]:
    state = request.app.state
    limiter = state.rate_limiter
    key = f"pw:{client_ip(request)}"
    if limiter.blocked(key):
        raise HTTPException(status_code=429, detail="Too many attempts, try again in a minute")
    if not await asyncio.to_thread(state.password_store.verify, body.current):
        limiter.record_failure(key)
        raise HTTPException(status_code=403, detail="Current password is wrong")
    if len(body.new) < MIN_PASSWORD_LEN:
        raise HTTPException(
            status_code=422, detail=f"New password needs at least {MIN_PASSWORD_LEN} characters"
        )
    if body.new == body.current:
        raise HTTPException(status_code=422, detail="New password is the same as the current one")
    limiter.reset(key)
    version = await asyncio.to_thread(state.password_store.set, body.new)
    # Other devices are logged out by the version change; this session stays in.
    request.session["pwv"] = version
    return {"ok": True}
