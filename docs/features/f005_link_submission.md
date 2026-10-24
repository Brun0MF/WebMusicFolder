# F005: Link and playlist submission with subfolder choice

- Status: done
- Phase: 1
- Depends on: f004
- Requirements: FR-04, FR-05, FR-06, FR-22, NFR-08, NFR-09

## Goal
Let the user paste many links, choose a subfolder, and queue everything, with playlists expanded.

## Description
Downloads page form: a textarea (one link per line), a subfolder combobox listing existing subfolders with free typing for a new one, and a Preview button. `resolver.py` runs the runner in flat mode to expand playlists into video IDs and titles. The preview step shows item counts per link and any invalid lines; confirm creates the queue items.

## Acceptance criteria
- [x] 3 video links and a 10 item playlist create 13 queue items.
- [x] Invalid lines or non-YouTube hosts are listed with a reason and not queued.
- [x] Subfolder `geek` places files in `<music>/geek/`; empty means root.
- [x] `../x`, `a/b`, `.hidden` are rejected with 422.
- [x] Duplicate video IDs inside the same batch are queued once.

## Steps
- [x] f005.s1: subfolder validation and listing existing folders (verify: unit tests, endpoint returns folders)
- [x] f005.s2: `resolver.py` flat expansion with fake runner (verify: tests for single video, playlist, unavailable item)
- [x] f005.s3: `/api/submit/preview` endpoint (verify: TestClient test for counts and invalid lines)
- [x] f005.s4: `/api/submit/confirm` creating queue items and waking the worker (verify: test that items appear and worker starts)
- [x] f005.s5: UI form with htmx and Alpine (verify: manual run with a real playlist)

## Test plan
Unit tests for validation; TestClient for endpoints with fake resolver; manual run with a real playlist.

## Notes
Large playlists (500+ items) must not block the event loop: resolution runs in the subprocess and results stream back. Show a spinner and a count while resolving.

## Implementation notes
- API is JSON (`GET /api/folders`, `POST /api/submit/preview`, `POST /api/submit/confirm`) in `web/routes_api.py`; the Alpine component `submitForm` in `static/js/app.js` renders the preview. htmx is not needed for this form. `app.js` loads before Alpine so `Alpine.data` is registered in time.
- Plain video links are not resolved over the network (title shows the video id until downloaded); only playlists use the flat runner. The preview shows a spinner message but not a live count; a streamed count can come with the SSE work (f007).
- Confirm ignores ids already queued or downloading (reported as `ignored`). Known tracks are handled by f006.
- Verified against the real service: a 182 item playlist plus two video links previews as 183 unique items, an invalid host is reported, `../x` gives 422, and confirm leads the worker to download into `geek/`.
- Manual check pending for the browser form: open Downloads at 360 px and 1440 px, paste links, pick a folder from the list, Preview, Add to queue.
