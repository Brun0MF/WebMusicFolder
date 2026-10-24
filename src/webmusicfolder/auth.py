"""Password login, session, CSRF token and login rate limit."""

from __future__ import annotations

import hmac
import secrets
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

MAX_FAILURES = 5
WINDOW_S = 60.0

router = APIRouter()


class NotAuthenticated(Exception):
    """Raised by require_auth when the session holds no login."""


class RateLimiter:
    """Counts failures per key inside a sliding window."""

    def __init__(
        self,
        max_failures: int = MAX_FAILURES,
        window_s: float = WINDOW_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_failures = max_failures
        self.window_s = window_s
        self.clock = clock
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str) -> deque[float]:
        events = self._failures[key]
        cutoff = self.clock() - self.window_s
        while events and events[0] <= cutoff:
            events.popleft()
        if not events:
            self._failures.pop(key, None)
        return events

    def blocked(self, key: str) -> bool:
        return len(self._prune(key)) >= self.max_failures

    def record_failure(self, key: str) -> None:
        self._prune(key)
        self._failures[key].append(self.clock())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)


def passwords_match(supplied: str, expected: str) -> bool:
    """Constant-time comparison of UTF-8 encoded passwords."""
    return hmac.compare_digest(supplied.encode(), expected.encode())


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token


class CsrfError(Exception):
    pass


async def verify_csrf(request: Request) -> None:
    """Dependency: the session token must come back in a header or form field."""
    expected = request.session.get("csrf", "")
    supplied = request.headers.get("x-csrf-token", "")
    if not supplied:
        form = await request.form()
        value = form.get("csrf_token", "")
        supplied = value if isinstance(value, str) else ""
    if not expected or not supplied or not hmac.compare_digest(supplied, expected):
        raise CsrfError


def require_auth(request: Request) -> None:
    # The version check logs out sessions that predate a password change.
    store = request.app.state.password_store
    if not request.session.get("auth") or request.session.get("pwv", "") != store.version:
        raise NotAuthenticated


def not_authenticated_handler(request: Request, exc: Exception) -> Response:
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    return RedirectResponse("/login", status_code=303)


def csrf_error_handler(request: Request, exc: Exception) -> Response:
    return JSONResponse({"detail": "Invalid CSRF token"}, status_code=403)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _render_login(request: Request, error: str | None, status_code: int = 200) -> Response:
    return request.app.state.templates.TemplateResponse(
        request,
        "login.html",
        {"csrf_token": csrf_token(request), "error": error},
        status_code=status_code,
    )


@router.get("/login")
async def login_page(request: Request) -> Response:
    if request.session.get("auth") and request.session.get("pwv", "") == (
        request.app.state.password_store.version
    ):
        return RedirectResponse("/", status_code=303)
    return _render_login(request, None)


@router.post("/login", dependencies=[Depends(verify_csrf)])
async def login_submit(request: Request) -> Response:
    store = request.app.state.password_store
    limiter: RateLimiter = request.app.state.rate_limiter
    ip = client_ip(request)

    if limiter.blocked(ip):
        return _render_login(request, "Too many attempts, try again in a minute", 429)

    form = await request.form()
    password = form.get("password", "")
    if not isinstance(password, str) or not store.verify(password):
        limiter.record_failure(ip)
        return _render_login(request, "Wrong password", 401)

    limiter.reset(ip)
    # Fresh session on login prevents fixation; a new CSRF token is issued on next render.
    request.session.clear()
    request.session["auth"] = True
    request.session["pwv"] = store.version
    return RedirectResponse("/", status_code=303)


@router.post("/logout", dependencies=[Depends(require_auth), Depends(verify_csrf)])
async def logout(request: Request) -> Response:
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
