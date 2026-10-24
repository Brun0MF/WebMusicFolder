# Decisions

## D001: Web app served by the backend, no desktop UI
- Date: 2026-10-24
- Decision: the program exposes an HTTP endpoint and the UI is used from a browser.
- Reason: the library lives on a server; the owner wants to add songs from any device without running tools locally.
- Alternatives: TUI (ratatui), GUI (iced), CLI. Rejected because they require a session on the server or a local install.

## D002: FastAPI with htmx and Alpine, no build step
- Date: 2026-10-24
- Decision: Python FastAPI, Jinja2 templates, htmx and Alpine vendored, hand written dark CSS, SSE for live updates.
- Reason: lowest idle resource use, one container, no Node toolchain, enough interactivity for this UI.
- Alternatives: SPA with Svelte or Vue (needs a build, more complexity), NiceGUI (heavier in idle, less visual control).

## D003: yt-dlp runs as a subprocess
- Date: 2026-10-24
- Decision: a small `ytdlp_runner.py` script uses the yt-dlp library and reports JSON lines; the app never imports yt-dlp.
- Reason: crash isolation, hot update without reloading modules (via `PYTHONPATH=/data/ytdlp_pkg`), zero memory held while idle.
- Alternatives: import yt-dlp in-process (simpler progress hooks, but updates need a restart and a crash can take the app down), call the yt-dlp CLI (harder to get structured progress).

## D004: MP3 output, VBR V0 by default
- Date: 2026-10-24
- Decision: convert to MP3; default V0 (about 245 kbps), 320k selectable.
- Reason: owner requested MP3 for compatibility. YouTube audio is Opus or AAC at roughly 130 to 160 kbps, so 320k adds size but no quality.
- Alternatives: keep original Opus or M4A (best quality, rejected for compatibility), FLAC (pointless from a lossy source).

## D005: Flat folders and title-only file names
- Date: 2026-10-24
- Decision: `<music>/<subfolder>/<Title>.mp3`; artist lives only in the tags; collisions get the video ID appended.
- Reason: most players read tags; simple names are easier to browse. Subfolders act as the owner's categories (for example `geek`, `musicas de festa`).
- Alternatives: `Artist - Title.mp3`, `Artist/Album/Track` (YouTube rarely has reliable album data).

## D006: Authentication with one password from the environment
- Date: 2026-10-24
- Decision: single password, signed session cookie, CSRF token, login rate limit.
- Reason: personal use on a server; proportionate security.
- Alternatives: no auth (only safe on a trusted LAN), token in header (awkward in a browser).

## D007: JSON state file with atomic writes
- Date: 2026-10-24
- Decision: one `state.json` holds tracks, queue and settings; progress is memory only.
- Reason: owner request; the volume is small. Atomic replace plus a backup guards against corruption.
- Alternatives: PostgreSQL (the default stack, but overkill for one user and adds a second container), SQLite (robust, but the owner asked for JSON).

## D008: Resume after crash and independence from the browser
- Date: 2026-10-24
- Decision: queue persisted on every transition; on startup `downloading` items go back to `queued`, temp dir is cleaned; the worker lives in the backend lifespan.
- Reason: the server may power off mid-task and nobody keeps a browser tab open.
- Alternatives: client-driven queue (rejected, needs the page open).

## D009: Duplicates by video ID, only for app downloads
- Date: 2026-10-24
- Decision: duplicate detection uses the YouTube video ID of tracks the app downloaded. External files are indexed in the library but never trigger the duplicate dialog.
- Reason: owner chose to ignore pre-existing files for dedup while still listing them.
- Alternatives: match by title and artist (fuzzy, many false positives).

## D010: External files shown with source and fallbacks
- Date: 2026-10-24
- Decision: every MP3 in the music dir is listed; `source` is `App` or `External`; missing tags fall back to the file name for the title and `Unknown` for other fields.
- Reason: the owner adds songs by other means and wants one complete view.
- Alternatives: list only app downloads.

## D011: Cookies by file upload, not browser harvesting
- Date: 2026-10-24
- Decision: the user uploads or pastes `cookies.txt`; stored with mode 0600. Direct browser import is backlog (local only).
- Reason: a web page cannot read other sites' cookies, and a container cannot see the host browser profile.
- Alternatives: `--cookies-from-browser` (works only when the browser runs on the same machine as the app).

## D012: License GPL-3.0
- Date: 2026-10-24
- Decision: GPL-3.0 (suggested, to be confirmed by the owner before publishing).
- Reason: FOSS preference of the owner.
- Alternatives: MIT, Apache-2.0.

## D013: Legal note
- Date: 2026-10-24
- Decision: README states that the tool is for content the user has the right to download.
- Reason: downloading from YouTube may violate its terms of service or copyright law depending on content and country.
- Alternatives: none.

## D014: SponsorBlock and loudness normalisation as optional toggles
- Date: 2026-10-24
- Decision: both are Phase 2 features (f014, f015), each with an on/off switch in Settings stored as `sponsorblock` and `replaygain` in `state.json`, both off by default. Normalisation uses ReplayGain tags (track gain, non destructive) rather than re-encoding.
- Reason: owner wants them but must be able to disable them; SponsorBlock can cut wrongly marked segments and `loudnorm` would add a second lossy encode.
- Alternatives: always on (rejected), ffmpeg `loudnorm` re-encode (can be offered later as a separate mode).

## D015: Container drops privileges after tini and a small entrypoint
- Date: 2026-10-24
- Decision: `tini` is PID 1 as root, runs `entrypoint.sh`, which chowns `/data` and execs the app with `setpriv` as `PUID:PGID`. The app process never runs as root. `/music` ownership is left to the host.
- Reason: arbitrary UID/GID without creating users in the image and without adding gosu.
- Alternatives: `user:` in compose (no chown of a fresh `./data`), gosu or su-exec (extra dependency).

## D016: Copy-on-write mutations and finished_at on queue items
- Date: 2026-10-24
- Decision: `StateStore.mutate` edits a deep copy, saves it, then swaps it in; reads return copies. `QueueItem.finished_at` is stamped when an item becomes done or failed and drives the 7 day pruning. The crash test is marked `slow` and kept out of `scripts/check.sh`.
- Reason: a failed save (disk full) must not leave memory ahead of disk; pruning needs a finish time, `added_at` would drop long queued items early. The crash test takes about 2 minutes.
- Alternatives: in place mutation with rollback (error prone), prune by `added_at` (wrong for items that waited long).

## D017: Link classification, error text format and runner client
- Date: 2026-10-24
- Decision: a watch or youtu.be link that also carries `list=` is queued as the single video; only `/playlist?list=` links are expanded. Queue item `error` is stored as `<code>: <message>` so the UI can branch on the code. The runner is driven by `runner_client.py` (own process group, SIGTERM then SIGKILL after 3 s, 300 s idle timeout mapped to a retryable network error). Plain video links are not resolved over the network; only playlists run the runner in flat mode.
- Reason: pasted music links often carry a playlist context the user did not mean to download; a code prefix avoids a new state field; a process group also stops ffmpeg children; resolving plain videos would add a slow request per link for no benefit.
- Alternatives: expand watch links with a list (surprising bulk downloads), separate error code field (schema change), in process yt-dlp (no crash isolation).

## D018: Retry bookkeeping lives in memory
- Date: 2026-10-24
- Decision: network retries leave the item `queued` with `attempts` incremented and the next eligible time in an in-memory dict; the worker wakes by timer. Interrupted attempts (shutdown) do not count. After a restart, waiting items are eligible immediately. The worker pauses itself after 3 consecutive `disk_full` or `permission` failures.
- Reason: no extra state fields, backoff does not hold a download slot.
- Alternatives: persist `not_before` (schema change), sleep inside the slot (blocks other items).

## D019: Duplicates, redownload and live updates
- Date: 2026-10-24
- Decision: a duplicate is a Track in state whose file still exists inside the music dir; hand copied files never count. The server also ignores a known video without `overwrite`, so skip is the safe default for any client. A redownload keeps the old file path (even if the title changed) and runs in the folder of the existing track; the old file is swapped with an atomic rename only when the new one is complete. Live updates use one in-process `EventBus` with bounded per client queues; a client that falls behind is dropped and reconnects to get a fresh snapshot. Progress is throttled to 1 event per second per item in the worker. uvicorn runs with `timeout_graceful_shutdown=3` and the bus is closed on shutdown so open SSE tabs never delay `docker stop`.
- Reason: keeps the worker independent of any browser, predictable file names for players, and a bounded memory cost.
- Alternatives: websockets (more code, no benefit for one way updates), polling (constant idle cost), unbounded client queues (a dead tab would grow memory).

## D020: Library scan and cache
- Date: 2026-10-24
- Decision: `library.py` walks the music dir without following symlinks (files that resolve outside are skipped), caches tags per path by `(mtime_ns, size)` and recomputes the `App` or `External` source on every scan from the state. Only `.mp3` is indexed; hidden files and folders are ignored. Filtering is done server side. Covers are served from the embedded APIC frame up to 5 MB, otherwise an SVG placeholder. The page reloads itself when a download finishes while it is open.
- Reason: second scans stay fast, source stays correct when state changes, no path can leave the music dir.
- Alternatives: persistent index in state.json (more writes, stale risk), client side filtering (large payloads for big libraries are still sent, but filtering server side keeps the API testable).

## D021: Logs, error text and redaction
- Date: 2026-10-24
- Decision: `logs.py` keeps the last 1000 lines in memory and writes a rotating file `/data/logs/ytdlp.log` (5 MB, 3 files). Every line passes a `Redactor` before it is stored, written or sent over SSE: the login password, the session secret, the cookies path, Cookie and Authorization headers, `key=value` credentials and Netscape cookie rows. Queue item errors are scrubbed the same way. Item errors are stored as `<code>: <readable message>[: <raw text>]`. A new code `login` covers "confirm you are not a bot" and expired cookies. Log lines travel as `log` events on the existing `/events` stream; the Logs page loads history from `/api/logs` and de-duplicates by sequence number.
- Reason: raw yt-dlp output must stay debuggable but must never leak a credential into a file or a browser; one stream keeps one connection per tab.
- Alternatives: a second SSE endpoint for logs (extra connection), logging unredacted to disk only (a leaked log file would expose the session).

## D022: yt-dlp update by staging directory and exclusive worker
- Date: 2026-10-24
- Decision: `pip install --target /data/ytdlp_pkg.new`, check that the runner can import it, then two renames into `/data/ytdlp_pkg` (a crash between them is recovered at startup). `pip` became a runtime dependency because the uv virtualenv has none. The update runs inside `QueueWorker.exclusive()`, which refuses while a download is active and keeps the worker from claiming items until it ends. The version comes from a `version` mode of the runner so it reflects what downloads will really use.
- Reason: yt-dlp loads extractor modules lazily from disk, so replacing the directory under a running runner could break that download; a failed or broken install must never replace a working one.
- Alternatives: update in place (not atomic), `uv pip` (not in the spec and would need uv at runtime), queueing the update until idle (more state).

## D023: Cookies are validated, normalised and written 0600
- Date: 2026-10-24
- Decision: `cookies.py` accepts Netscape rows (also with spaces instead of tabs and `#HttpOnly_` rows), requires at least one youtube.com or google.com cookie, rewrites the file with a header and tabs, and writes it through an `O_EXCL` temp file created with mode 0600 and an atomic replace. Upload is read in the browser and posted as text to the same JSON endpoint as paste. The API only returns `loaded` and the save time. The worker passes `--cookies` only while the file exists.
- Reason: a bad file should fail at upload, not at the next download; the secret is never readable by others, even for an instant.
- Alternatives: multipart upload (second code path), storing the file as received (yt-dlp then fails with an obscure parse error).

## D024: SponsorBlock categories and fallback
- Date: 2026-10-24
- Decision: remove `sponsor`, `selfpromo`, `interaction` and `music_offtopic`; keep `intro` and `outro`. Postprocessors follow yt-dlp's own order (SponsorBlock, extract audio, ModifyChapters). After a cut the duration is read from the MP3. If the download fails with a SponsorBlock error it is retried once without it.
- Reason: intros and outros are usually music; a community database outage must not cost a download.
- Alternatives: all categories (cuts real music), failing the item (annoying for an optional feature).

## D025: ReplayGain is track gain written as tags
- Date: 2026-10-24
- Decision: ffmpeg `ebur128=peak=sample` measures the finished MP3, gain is -18 LUFS minus the integrated loudness, written as `REPLAYGAIN_TRACK_GAIN` and `REPLAYGAIN_TRACK_PEAK` TXXX frames in the normal tag save. Peak is a sample peak and may exceed 1.0 for lossy files. A failure logs a warning and keeps the track. Existing files are not retro tagged.
- Reason: no re-encoding, players apply the gain; album gain needs album grouping.
- Alternatives: loudnorm re-encode (quality loss), `rsgain` or `mp3gain` (extra dependency).

## D026: Search feeds the links box
- Date: 2026-10-24
- Decision: `POST /api/search` runs the runner's `search` mode (`ytsearch10:` flat). A result's Add button appends its URL to the links textarea; queuing still goes through preview, duplicates and subfolder. The query is passed after `--`, only the video id of a result is trusted.
- Reason: one way to queue, so duplicate rules and folder choice cannot be bypassed.
- Alternatives: queue directly from results (second path with its own rules).

## D027: Linking an External file asks for the video link
- Date: 2026-10-24
- Decision: `POST /api/library/link` takes a single video link from the user, adds only the `youtube_id` and `youtube_url` frames to a copy of the file (same ID3 version), swaps it in atomically and registers a Track with quality `imported`. Refused when the file is linked already or the video already has a file.
- Reason: a Track needs a video id and a file without one cannot be matched safely; guessing by title would modify files silently.
- Alternatives: automatic matching by title (wrong guesses), state-only index without tagging (App/External is derived from the tag).

## D028: Browser cookies are an env option, cookies.txt wins
- Date: 2026-10-24
- Decision: `WMF_COOKIES_FROM_BROWSER` is validated at startup against yt-dlp's browser list and passed to the runner (`--cookies-from-browser`) for download, playlist expansion and search, but only while no cookies.txt exists.
- Reason: an uploaded file is an explicit choice; browser reading only works outside a container.
- Alternatives: browser first (surprising after an upload), a Settings field (cannot work in Docker, would persist a path to profiles).

## Rename, Docker for NAS and quality default
- Date: 2026-10-24
- Decision: the project is WebMusicFolder (WMF) everywhere: package `webmusicfolder`, env vars `WMF_*`, image `webmusicfolder`. The image runs as root by default (PUID/PGID 0), creates a persistent random password when `WMF_PASSWORD` is unset (shown in the logs, stored in `/data/initial_password.txt`), and bundles Deno plus yt-dlp-ejs. A password changed in Settings is stored as a scrypt hash in `password.json` and wins over the environment; the change signs out other sessions through a session version.
- Reason: the target is a NAS with only a Docker web UI, so the image must work with import and run, no shell and no config.
- Alternatives: keeping MD_* names (kept the old brand), PUID 1000 default (share not writable on a NAS), a fixed default password (insecure).
- Date: 2026-10-24
- Decision: default MP3 quality is V5 (about 130 kbps); V0, V2, 320k, 192k and 128k stay selectable. Measured on a 19 s clip: V0 331 kB, V5 121 kB.
- Reason: YouTube audio is already lossy at about 130 to 160 kbps, so V0 only inflates files; it matches a plain yt-dlp download.
- Alternatives: keep V0 (files about 1.6 to 2.7 times larger for no audible gain), copy the original audio stream (not MP3).
