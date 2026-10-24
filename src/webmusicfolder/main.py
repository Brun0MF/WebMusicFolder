"""App factory, lifespan and uvicorn entry point."""

from __future__ import annotations

import os
import secrets
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from webmusicfolder import __version__, auth
from webmusicfolder.config import ConfigError, Settings, load_settings
from webmusicfolder.cookies import COOKIES_FILE_NAME, CookieStore
from webmusicfolder.downloader import DownloadContext
from webmusicfolder.events import EventBus
from webmusicfolder.library import Library
from webmusicfolder.logs import LogBuffer, Redactor
from webmusicfolder.passwords import PASSWORD_FILE_NAME, PasswordStore
from webmusicfolder.queue_worker import QueueWorker, tmp_root_for
from webmusicfolder.runner_client import RunnerSpec
from webmusicfolder.runtime import apply_settings
from webmusicfolder.store import StateCorruptError, StateStore
from webmusicfolder.web import (
    routes_account,
    routes_api,
    routes_app_settings,
    routes_config,
    routes_cookies,
    routes_library,
    routes_live,
    routes_logs,
    routes_pages,
    routes_search,
    routes_settings,
)
from webmusicfolder.ytdlp_update import YtdlpUpdater, package_dir_for

WEB_DIR = Path(__file__).parent / "web"
SESSION_MAX_AGE_S = 30 * 24 * 3600


def load_or_create_secret(settings: Settings) -> str:
    """Return WMF_SECRET, or a key generated once and kept in the data dir."""
    if settings.secret:
        return settings.secret
    path = settings.data_dir / "secret.key"
    if path.exists():
        return path.read_text().strip()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    key = secrets.token_urlsafe(48)
    # O_EXCL avoids clobbering a key written by a concurrent start.
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path.read_text().strip()
    with os.fdopen(fd, "w") as fh:
        fh.write(key)
    return key


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    worker: QueueWorker = app.state.worker
    await worker.recover()
    await worker.start()
    try:
        yield
    finally:
        # Close SSE streams first so open browsers do not hold up the shutdown.
        app.state.bus.close()
        await worker.stop()
        app.state.logs.close()


def create_app(settings: Settings | None = None, runner: RunnerSpec | None = None) -> FastAPI:
    """Build the app. `runner` replaces the yt-dlp subprocess command (used by tests)."""
    settings = settings or load_settings()
    app = FastAPI(title="WebMusicFolder", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.env_settings = settings
    app.state.password_store = PasswordStore(
        settings.data_dir / PASSWORD_FILE_NAME, settings.password
    )
    store = StateStore(settings.data_dir / "state.json")
    store.load()
    app.state.store = store
    ctx = DownloadContext(
        music_dir=settings.music_dir,
        tmp_root=tmp_root_for(settings.data_dir),
        runner=runner or RunnerSpec(extra_pythonpath=settings.data_dir / "ytdlp_pkg"),
        cookies=settings.data_dir / COOKIES_FILE_NAME,
        cookies_from_browser=settings.cookies_from_browser,
    )
    app.state.download_ctx = ctx
    app.state.cookies = CookieStore(settings.data_dir / COOKIES_FILE_NAME)
    app.state.updater = YtdlpUpdater(package_dir_for(settings.data_dir), ctx.runner)
    bus = EventBus()
    app.state.bus = bus
    app.state.library = Library(settings.music_dir)
    secret_key = load_or_create_secret(settings)
    redact = Redactor(
        [
            settings.password,
            str(settings.data_dir / PASSWORD_FILE_NAME),
            secret_key,
            str(ctx.cookies) if ctx.cookies else "",
        ]
    )
    logs = LogBuffer(settings.data_dir / "logs", sink=bus.publish, redact=redact)
    app.state.logs = logs
    app.state.worker = QueueWorker(
        store,
        ctx,
        concurrency=settings.concurrency,
        quality=lambda: app.state.settings.quality,
        on_event=bus.publish,
        on_log=lambda item, line: logs.add(line, item.id, item.title),
        redact=redact,
    )
    apply_settings(app, store.settings_snapshot())
    app.state.rate_limiter = auth.RateLimiter()
    app.state.templates = Jinja2Templates(directory=WEB_DIR / "templates")

    app.add_middleware(
        SessionMiddleware,
        secret_key=secret_key,
        max_age=SESSION_MAX_AGE_S,
        same_site="lax",
        https_only=False,
    )
    app.add_exception_handler(auth.NotAuthenticated, auth.not_authenticated_handler)
    app.add_exception_handler(auth.CsrfError, auth.csrf_error_handler)

    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
    app.include_router(auth.router)
    app.include_router(routes_pages.router)
    app.include_router(routes_api.router)
    app.include_router(routes_live.router)
    app.include_router(routes_library.router)
    app.include_router(routes_logs.router)
    app.include_router(routes_settings.router)
    app.include_router(routes_app_settings.router)
    app.include_router(routes_config.router)
    app.include_router(routes_account.router)
    app.include_router(routes_search.router)
    app.include_router(routes_cookies.router)

    @app.get("/healthz", response_class=PlainTextResponse)
    async def healthz() -> str:
        return "ok"

    return app


def run() -> None:
    import uvicorn

    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    try:
        app = create_app(settings)
    except StateCorruptError as exc:
        print(f"State error: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    # Open SSE streams are cut after 3 s so SIGTERM never waits on a browser tab.
    uvicorn.run(app, host="0.0.0.0", port=settings.port, workers=1, timeout_graceful_shutdown=3)


if __name__ == "__main__":
    run()
