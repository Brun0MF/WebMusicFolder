# F016: Search by name inside the app

- Status: done (browser check pending)
- Phase: 2
- Depends on: f005
- Requirements: new FR-27

## Goal
Find a song by typing its name, without leaving the app to copy a link from YouTube.

## Description
A new runner mode `search QUERY --limit N` uses yt-dlp `ytsearchN:` in flat mode and emits `entry` events with video id, title, channel and duration. `POST /api/search` (CSRF, query max 200 chars, limit fixed at 10) returns them. The Downloads page gets a search box above the links box; each result has an "Add" button that appends its canonical URL to the links textarea, so the existing preview, duplicate dialog and subfolder flow stays the only way to queue. Results already in the library are marked.

## Acceptance criteria
- [x] A query returns up to 10 results with title, channel, duration.
- [x] "Add" puts the link in the textarea without duplicating it.
- [x] Results already downloaded are labelled.
- [x] Empty, over long or control character queries are rejected with 422; the query is passed as one argument, never through a shell.
- [x] Errors (network, yt-dlp) show a message and never block the page.

## Steps
- [x] f016.s1: runner `search` mode and fake runner support (verify: unit tests)
- [x] f016.s2: `search.py` and `POST /api/search` with duplicate marking (verify: integration tests)
- [x] f016.s3: Downloads page search box and results list (verify: manual, browser check)
- [x] f016.s4: real search (verified: 5 results with channel and duration for a real query)

## Test plan
Fake runner scenarios, API tests, one real query.

## Notes
Only the video id is trusted from the result; the URL is rebuilt with `video_url()`.
