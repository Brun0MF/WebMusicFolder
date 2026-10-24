"""Feature toggles stored in the state file (SponsorBlock, ReplayGain)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from webmusicfolder.auth import require_auth, verify_csrf

router = APIRouter(prefix="/api/settings", dependencies=[Depends(require_auth)])

TOGGLES = ("sponsorblock", "replaygain")


class SettingsBody(BaseModel):
    # Only the fields that are sent change.
    sponsorblock: bool | None = None
    replaygain: bool | None = None


def _public(settings: Any) -> dict[str, bool]:
    data = asdict(settings)
    return {name: bool(data[name]) for name in TOGGLES}


@router.get("")
async def get_settings(request: Request) -> dict[str, bool]:
    return _public(await request.app.state.store.get_settings())


@router.post("", dependencies=[Depends(verify_csrf)])
async def update_settings(request: Request, body: SettingsBody) -> dict[str, bool]:
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    store = request.app.state.store
    if changes:
        return _public(await store.update_settings(**changes))
    return _public(await store.get_settings())
