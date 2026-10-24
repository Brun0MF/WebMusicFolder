# F012: Browser cookie import for local runs

- Status: done (browser check pending)
- Phase: 2
- Depends on: f011
- Requirements: FR-24

## Goal
When the app runs directly on the owner's computer (not in Docker), reuse the logged in browser session without exporting a cookies.txt.

## Description
A new optional env var `WMF_COOKIES_FROM_BROWSER` (one of brave, chrome, chromium, edge, firefox, opera, safari, vivaldi, whale; optional `:profile` suffix) makes the runner pass the yt-dlp `cookiesfrombrowser` option. An uploaded `cookies.txt` takes precedence when present, since it is an explicit choice. The value is validated at startup (fail fast). Settings shows which cookie source is active. Inside a container no browser exists, so the docs say this is for local runs only.

## Acceptance criteria
- [x] Invalid browser names fail at startup with a clear message; unset means no change in behaviour.
- [x] With the env set and no cookies.txt, download and playlist expansion receive `--cookies-from-browser`.
- [x] With a cookies.txt present, only `--cookies` is used.
- [x] Settings shows "Browser: firefox (env)" or "cookies.txt" or "none".
- [x] A browser read failure surfaces as a normal item error, not a crash.

## Steps
- [x] f012.s1: config parsing and validation (verify: unit tests)
- [x] f012.s2: runner flag and options for download and flat modes (verify: unit tests on options and arguments)
- [x] f012.s3: worker and resolver pass the source with precedence rule (verify: integration tests)
- [x] f012.s4: Settings status line and README note (verify: manual)

## Test plan
Unit and fake runner tests; a real run with a local browser is a manual check for the owner.

## Notes
Cookie values are read by yt-dlp inside the runner process and never reach the app, the state file or the logs.
