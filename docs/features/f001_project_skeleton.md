# F001: Project skeleton, config, auth, base UI, Docker

- Status: done
- Phase: 1
- Depends on: none
- Requirements: FR-01, FR-02, NFR-03, NFR-04, NFR-05, NFR-06, NFR-07, NFR-10

## Goal
A running, authenticated, dark themed web shell in Docker that later features plug into.

## Description
Create the Python package with `uv`, the FastAPI app factory with lifespan hook, env based configuration, password login with session cookie, CSRF and rate limit, the base template with tabs (Downloads, Library, Logs, Settings), vendored htmx and Alpine, the dark CSS tokens, `/healthz`, Dockerfile and compose file, and `scripts/check.sh`.

## Acceptance criteria
- [x] `docker compose up` serves the login page on port 8080. (verified with `docker run`; `docker-compose` segfaults on this machine, so the compose file itself is untested)
- [x] Wrong password is rejected; five failures in one minute from one IP return 429.
- [x] After login all four tabs render (placeholders) and share one base layout.
- [x] Missing `WMF_PASSWORD` stops startup with a clear message.
- [x] Container runs as `PUID:PGID`, not root.
- [x] `scripts/check.sh` passes.

## Steps
- [x] f001.s1: `pyproject.toml`, package layout, ruff config, `scripts/check.sh` (verify: `scripts/check.sh` runs and passes on an empty test)
- [x] f001.s2: `config.py` with env parsing and validation (verify: unit tests for defaults, missing password, bad port, bad quality)
- [x] f001.s3: app factory, `/healthz`, lifespan stub (verify: TestClient returns 200 on `/healthz`)
- [x] f001.s4: `auth.py` login, session, logout, constant-time compare (verify: tests for redirect, success, failure)
- [x] f001.s5: rate limit and CSRF token (verify: tests for 429 after 5 failures, POST without token rejected)
- [x] f001.s6: base template, tabs, dark CSS tokens, vendored htmx and Alpine (verify: manual check at 360 px and 1440 px, no external network requests in browser devtools)
- [x] f001.s7: Dockerfile with ffmpeg, tini, PUID/PGID handling, `docker-compose.yml` (verify: build, run, login, files in a mounted volume have the right owner)

## Test plan
Unit tests for config and auth helpers; TestClient tests for login flow and rate limit; manual UI check; Docker smoke test.

## Notes
Pin htmx and Alpine versions and record them in `static/vendor/README.md`. Session secret is generated once into `/data/secret.key` when `WMF_SECRET` is not set.
