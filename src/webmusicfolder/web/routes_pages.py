"""HTML pages. Placeholders until their features land."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from webmusicfolder.auth import csrf_token, require_auth

router = APIRouter(dependencies=[Depends(require_auth)])

TABS = (
    ("downloads", "/", "Downloads"),
    ("library", "/library", "Library"),
    ("logs", "/logs", "Logs"),
    ("settings", "/settings", "Settings"),
)


def _page(request: Request, active: str) -> Response:
    title = next(label for key, _, label in TABS if key == active)
    return request.app.state.templates.TemplateResponse(
        request,
        f"{active}.html",
        {"tabs": TABS, "active": active, "title": title, "csrf_token": csrf_token(request)},
    )


@router.get("/")
async def downloads(request: Request) -> Response:
    return _page(request, "downloads")


@router.get("/library")
async def library(request: Request) -> Response:
    return _page(request, "library")


@router.get("/logs")
async def logs(request: Request) -> Response:
    return _page(request, "logs")


@router.get("/settings")
async def settings(request: Request) -> Response:
    return _page(request, "settings")
