# Requirements

Priority: must, should, could. Each requirement lists the feature that implements it.

## Functional requirements

| ID | Requirement | Priority | Acceptance criterion | Feature |
|----|-------------|----------|----------------------|---------|
| FR-01 | The app starts an HTTP server exposing the web UI on `WMF_PORT` (default 8080). | must | `GET /login` returns 200 within 2 s of container start. | f001 |
| FR-02 | Access requires a single password from `WMF_PASSWORD`; unauthenticated requests are redirected to login or get 401. | must | Request to `/` and `/api/*` without session returns 302 or 401; correct password sets a session cookie; wrong password does not. | f001 |
| FR-03 | State (tracks, queue, settings) is stored in one JSON file with atomic writes. | must | Killing the process during a write never leaves an unreadable `state.json` (test with 1000 forced kills of a write loop). | f002 |
| FR-04 | The user can paste several links (one per line, mixed videos and playlists) into a text box and submit. | must | Pasting 3 video links and 1 playlist of 10 items creates 13 queue items. | f005 |
| FR-05 | The user can pick an existing subfolder or type a new one for the batch; empty means the music dir root. | must | Files of a batch with subfolder `geek` end in `<music>/geek/`. | f005 |
| FR-06 | Subfolder names are validated: no path separators, no `..`, no leading dot, max 80 chars. | must | `../x`, `a/b`, `.hidden` are rejected with 422; no file is written outside the music dir. | f005 |
| FR-07 | Each video is downloaded as best available audio and converted to MP3 (VBR V0 by default, 320k selectable). | must | Output is a valid MP3 (ffprobe reports `mp3`); bitrate profile matches the setting. | f003 |
| FR-08 | The file name is the video title sanitised for the filesystem; on collision with a different video the video ID is appended. | must | Two different videos titled `Intro` produce `Intro.mp3` and `Intro [<id>].mp3`. | f003 |
| FR-09 | ID3v2.4 tags are written: title, artist (channel name without ` - Topic`), embedded JPEG cover, video ID and URL (custom frames). | must | `mutagen` reads back title, artist, APIC frame and the video ID of a downloaded file. | f003 |
| FR-10 | Downloads run in a background worker independent of any open browser. | must | Closing the browser tab during a download does not stop it; queue completes. | f004 |
| FR-11 | The queue is persisted on every state change; after a restart, items that were downloading return to queued and the worker continues without user action. | must | Kill the process mid-download, restart: item finishes and the file is complete and tagged. | f004 |
| FR-12 | Partial files never appear in the library: downloads go to a temp dir and are moved atomically after tagging. | must | While a download runs, the target subfolder contains no `.part` or incomplete mp3. | f003, f004 |
| FR-13 | Before queuing, links already downloaded by the app (same video ID, file still exists) are reported and the user chooses per link or for all: skip or redownload. | must | Submitting a known link shows the dialog; skip adds 0 items; redownload adds 1 item and replaces the file. | f006 |
| FR-14 | A live list shows each active item with a progress bar, status and the number of items remaining. | must | Progress updates at least every 1 s while downloading; remaining counter decreases as items finish. | f007 |
| FR-15 | A library page lists all MP3 files under the music dir with cover, title, artist, album, duration, size, subfolder and Source (`App` or `External`). | must | Page lists 500 files in under 2 s after first scan; covers shown. | f008 |
| FR-16 | For External files, missing tags are filled from the file name (title) and otherwise shown as `Unknown`. | must | A tagless `foo.mp3` shows title `foo`, artist `Unknown`. | f008 |
| FR-17 | The library page supports text search over title and artist and filtering by subfolder and source. | should | Typing in the search box filters results in under 300 ms for 5000 tracks. | f008 |
| FR-18 | A logs tab shows yt-dlp output, live, with the last 1000 lines retained and a log file rotated on disk. | must | A failing download shows the yt-dlp error lines in the tab; log file size stays under 5 MB x 3 files. | f009 |
| FR-19 | Errors (invalid link, unavailable video, private video, ffmpeg failure, disk full) are shown in the UI as a message tied to the item, with a retry button. | must | A private video without cookies shows "Private video, upload cookies" and offers retry. | f009 |
| FR-20 | A button updates yt-dlp to the latest release without rebuilding the image and shows the old and new version. | must | After clicking, the displayed version equals the latest PyPI release; the next download uses it. | f010 |
| FR-21 | The user can upload or paste a `cookies.txt`; it is stored with mode 600 and used for downloads; it can be deleted. | should | A private playlist downloads after upload; file mode is 0600; delete removes it. | f011 |
| FR-22 | Playlist links are expanded into individual items, with the playlist size shown before confirming. | must | A 10 item playlist shows "10 videos" in the confirmation step. | f005 |
| FR-23 | Failed items can be retried individually or all at once; failures never block the rest of the queue. | must | One failing item among 5 still lets the other 4 finish. | f004, f009 |
| FR-24 | With `WMF_COOKIES_FROM_BROWSER` set, yt-dlp reads cookies from that local browser; an uploaded cookies.txt takes precedence. | could | Runner receives `--cookies-from-browser` only when no cookies file exists. | f012 |
| FR-25 | An optional setting (off by default) removes sponsor, self promotion, interaction and non music segments with SponsorBlock. | could | A video with known segments is shorter after download; an unreachable SponsorBlock never fails the download. | f014 |
| FR-26 | An optional setting (off by default) writes ReplayGain track gain and peak tags without changing the audio. | could | Tags read back with mutagen; a measuring failure keeps the track. | f015 |
| FR-27 | The Downloads page can search YouTube by name and add a result to the links box. | could | A query returns up to 10 results; adding one feeds the normal preview and duplicate flow. | f016 |
| FR-28 | An External library file can be linked to a YouTube video, becoming an App file and a known duplicate. | could | Only the two custom ID3 frames are added; a failed write leaves the file untouched. | f017 |
| FR-29 | A Library track can be deleted from disk in the UI, after a confirmation. | should | The file and its Track are gone; the same link is downloadable again; unsafe paths are rejected. | f018 |
| FR-30 | The Library can create and delete subfolders (deleting removes the files inside) and move tracks between subfolders and the root. | should | Files never overwritten; unsafe names and symlinks rejected; tracks follow moved files. | f019 |
| FR-31 | The Library supports multi select with Select all, bulk move and bulk delete. | should | Partial failures are reported, the rest still applies. | f019 |
| FR-32 | Music folder, MP3 quality and parallel downloads are settings kept on the server across restarts. | should | Saved values win over the environment; empty music folder restores the default. | f019 |

## Non-functional requirements

| ID | Requirement | Priority | Acceptance criterion |
|----|-------------|----------|----------------------|
| NFR-01 | Idle footprint: with an empty queue and no browser connected, RSS under 80 MB and CPU under 1 % averaged over 10 min (measured with `docker stats`). | must | Measured and recorded in `docs/progress.md`. |
| NFR-02 | No child process (yt-dlp, ffmpeg) is running when the queue is empty. | must | `pgrep` finds none at idle. |
| NFR-03 | Image runs as non-root user with configurable UID and GID matching volume ownership. | must | Files created in `/music` belong to `PUID:PGID`. |
| NFR-04 | Docker image contains Python, ffmpeg and the app only; two volumes: `/music`, `/data`. | must | `docker compose up` works on a clean host with only those mounts. |
| NFR-05 | UI is a dark theme in the Material dark or JetBrains IDE style, usable on desktop and phone widths (360 px). | must | Manual check at 360 px and 1440 px: no horizontal scroll, readable contrast (WCAG AA for text). |
| NFR-06 | Front end needs no build step and no external CDN at runtime (htmx and Alpine vendored). | must | UI works with the host offline from the internet except for YouTube. |
| NFR-07 | Security: constant-time password compare, session cookie `HttpOnly` and `SameSite=Lax`, login rate limit (5 failures per minute per IP), CSRF protection on state-changing requests. | must | Tests cover each. |
| NFR-08 | Paths: every file operation resolves inside the music dir; symlinks pointing outside are not followed. | must | Unit tests with traversal and symlink cases. |
| NFR-09 | Only `http` and `https` URLs on YouTube hosts (`youtube.com`, `music.youtube.com`, `youtu.be`) are accepted. | must | Other hosts and schemes are rejected with an error message. |
| NFR-10 | Code quality: `ruff check`, `ruff format --check` and `pytest` all pass; core logic coverage at least 80 %. | must | CI-style script `scripts/check.sh` exits 0. |
| NFR-11 | Concurrency: one download at a time by default, configurable (`WMF_CONCURRENCY`, max 4). | should | Setting 2 runs two downloads in parallel. |
| NFR-12 | Graceful shutdown on SIGTERM: current downloads are interrupted cleanly and requeued within 10 s. | should | `docker stop` finishes in under 10 s and the item resumes on next start. |
