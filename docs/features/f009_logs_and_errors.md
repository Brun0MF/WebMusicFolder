# F009: yt-dlp logs tab and error messages with retry

- Status: done (browser check pending)
- Phase: 1
- Depends on: f003, f007
- Requirements: FR-18, FR-19, FR-23

## Goal
Make failures visible and recoverable, and let the user read raw yt-dlp output.

## Description
`logs.py` keeps a ring buffer of the last 1000 lines and a rotating log file in `/data/logs` (5 MB x 3). The Logs tab shows the buffer and follows new lines via SSE, with a filter by item. Errors from the runner are mapped to codes with readable messages (private video, unavailable, age restricted, network, ffmpeg, disk full) and shown on the item in the Downloads list and as a toast. Failed items offer retry; a "Retry all failed" button exists.

## Acceptance criteria
- [x] A failing download shows its yt-dlp error lines in the Logs tab. (API and real yt-dlp verified; the tab itself awaits the browser check)
- [x] A private video without cookies shows "Private video, upload cookies" with a retry button. (message and Retry verified by tests; rendering awaits the browser check)
- [x] Log file never exceeds 5 MB x 3 files.
- [x] Retry all failed requeues every failed item.
- [x] Cookies and passwords never appear in logs.

## Steps
- [x] f009.s1: `logs.py` ring buffer and rotating file (verify: unit tests for size cap and rotation)
- [x] f009.s2: error code mapping from yt-dlp messages (verify: unit tests with real sample messages in fixtures)
- [x] f009.s3: log events over SSE and Logs tab (verify: manual with a failing link; backend verified with a real failing link, browser check pending)
- [x] f009.s4: error display, toasts, retry and retry all (verify: TestClient tests and manual; browser check pending)
- [x] f009.s5: redaction of sensitive values in logs (verify: unit test with cookie path and password in input)

## Test plan
Unit tests with fixture messages; TestClient; manual failing link, private link and offline network.

## Notes
A `login` code ("YouTube asks to sign in, upload fresh cookies") was added for the bot check and expired cookies. Item errors are stored as `<code>: <readable message>[: <raw yt-dlp text>]`; the UI shows the readable part and puts the raw text under Details.
Keep raw message alongside the mapped one so unknown errors remain debuggable.
