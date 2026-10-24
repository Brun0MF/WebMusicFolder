# Progress

## Current
- Phase: 1
- Next: no code is half done. The User (1) imports `dist/webmusicfolder.tar` on the NAS (delete the old container and image first; env vars are now `WMF_*`), (2) checks the UI in a browser at 360 px and 1440 px (login animation and credit, theme toggle, Library folders, multi select, Open on YouTube, Settings: password, General incl. quality select, progress bar on a real download), (3) runs f011.s4 with a real private playlist. Then plan new ideas with /plan-project (see Backlog).
- State: `scripts/check.sh` green (432 fast tests), slow crash test green (run before the last small changes). f001 to f010, f012, f014 to f019 done, f011 done except s4. Project is named WebMusicFolder (WMF), package `webmusicfolder`, repo https://github.com/Brun0MF/WebMusicFolder. A dev server may still run on port 8080 (`WMF_PASSWORD=dev`, data in `./data`, music in `./music`).
- Not done in code: the project folder is still `~/Desktop/MusicDownloader` (rename it with mv, then `rm -rf .venv && uv sync` if uv complains).

## Blocked / questions
- Manual UI check of f001.s6 (360 px and 1440 px, no external requests in devtools) not done; the User should open the app and confirm.
- `docker-compose` segfaults on this machine, so `docker-compose.yml` is untested; run `docker compose up` where the plugin works.
- f006 to f011, f014 to f017 and f012: UI not yet checked in a browser (search box and Add, Link to YouTube on an External row, the two option toggles, cookie source line, duplicate dialog, live list with a 10 item playlist, Library, Logs tab following a failing link, error toast, Retry all failed, Settings update button and cookies card at 360 px and 1440 px). Backend verified with tests, a real failing link, a real pip update and Docker (update persists across container recreation, cookies file mode 600).
- f012 with a real local browser (`WMF_COOKIES_FROM_BROWSER=firefox`) was not run here, no browser session available; the owner should try a private playlist that way.
- f011.s4: needs the User to export cookies.txt (dedicated account advised), upload it in Settings and download a real private playlist.
- No git repository yet; commits pending the User's decision.

## TODO
- f011.s4 end to end private playlist (manual, needs the User's cookies)

## IN PROGRESS
- (none; f006 to f011 only wait for the browser check, f011.s4 for a private playlist)

## DONE
- f019 Folder create/delete, move, multi select with bulk actions, persistent settings (music dir, quality, concurrency), GitHub dark UI
- f018 Delete tracks from the Library (button with confirm, DELETE /api/library)
- f012 Browser cookie import (`WMF_COOKIES_FROM_BROWSER`, cookies.txt wins)
- f014 SponsorBlock segment removal (toggle, fallback when the service fails)
- f015 ReplayGain tags (toggle, measured with ffmpeg ebur128)
- f016 Search by name
- f017 Link External files to a YouTube video
- f001 Project skeleton, config, auth, base UI, Docker
- f002 JSON state store
- f003 Download engine
- f004 Queue worker, persistence and crash resume (Docker: stop 360 ms, idle 41 MiB, 0.09% CPU)
- f005 Link and playlist submission with subfolder choice
- f006 Duplicate detection and skip or redownload dialog
- f007 Live downloads list with progress (SSE)
- f008 Library page
- f009 yt-dlp logs tab and error messages with retry (log ring buffer and rotating file, redaction, error codes with a `login` code, Logs tab over SSE, toasts, Retry all failed)
- f010 yt-dlp update button (staging dir and swap, exclusive worker, runner `version` mode)
- f011.s1 to s3 Cookies.txt upload, paste, status, delete (mode 0600)

## Backlog (out of scope ideas)
- Write the album tag when yt-dlp provides one (YouTube Music); today no album is stored and the Library hides "Unknown"
- Fix a licence (README says GPL-3.0 to be confirmed) and add a LICENSE file
- Test the Docker bundle on the real NAS (import, volumes, PUID/PGID, generated password in logs)
- Optional legacy `MD_*` environment fallback if old containers must keep working
- Live resolved count while a large playlist is being expanded (needs streaming to the browser, fits f007)
- ReplayGain for existing library files (retro tagging) and album gain
- Automatic title based suggestions for linking External files

## Session log
- 2026-10-24: project planned
- 2026-10-24: f001.s1 done (pyproject, uv, ruff, scripts/check.sh green)
- 2026-10-24: f001.s2 to s7 done (config, app factory, auth, rate limit, CSRF, base UI, Docker); 33 tests green; f001 done
- 2026-10-24: checkpoint after f001; next: f002.s1
- 2026-10-24: f002.s1 to s5 done (models, atomic store, lock and accessors, backup and corruption handling, 1000 SIGKILL crash test); f002 done
- 2026-10-24: checkpoint after f002; next: f003.s1
- 2026-10-24: f003.s1 to s6 done (paths, urls, runner protocol and client, real runner verified with ffprobe, tagging, download_one with atomic move); f003 done
- 2026-10-24: f004.s1 to s6 done (worker loop, recovery, retry with backoff, graceful stop, concurrency, kill -9 test, local idle measurement); Docker measurements pending
- 2026-10-24: f005.s1 to s5 done (folders, resolver, preview and confirm endpoints, Alpine form); real playlist verified through the API, browser check pending
- 2026-10-24: checkpoint after f005; code builds and 190 fast tests are green; next: manual checks for f004 and f005, then f006.s1
- 2026-10-24: f004 Docker checks done via plain docker run (stop 360 ms, exit 143, idle 41 MiB); f004 done; f005 browser check still pending
- 2026-10-24: f006.s1 to s4 done (duplicates.py, preview and confirm with overwrite, redownload replaces in place, dialog); f007.s1 to s5 done (EventBus, /events SSE, throttled progress, live list, cancel and retry); f008.s1 to s5 done (library scan with cache, filters, covers, page, auto refresh); 250 tests green; real download verified in Docker, docker stop with an open SSE client 3.4 s
- 2026-10-24: checkpoint after f008; 250 fast tests green, no half-done work; next: browser check of f006 to f008 by the User, then f009.s1 (read docs/features/f009_logs_and_errors.md)
- 2026-10-24: f009.s1 to s5 done (logs.py with ring buffer, rotating file and Redactor; error fixtures incl. new login code; log events and Logs tab; item error text, toast, retry all; redaction); verified with a real failing link
- 2026-10-24: f010.s1 to s4 done (runner version mode, YtdlpUpdater with staging and swap, worker exclusive(), Settings button); real pip update and offline failure verified, Docker recreate keeps ytdlp_pkg
- 2026-10-24: f011.s1 to s3 done (cookies.py, /api/cookies, Settings card); Docker verified mode 600 and delete; f011.s4 pending the User; 340 fast tests and the slow crash test green
- 2026-10-24: backlog planned (f012, f014 to f017 feature files) and implemented: settings API, SponsorBlock (real video 226 s to 209 s), loudness.py and ReplayGain tags, search mode and UI (real query verified), importer and Library action, browser cookie option; 400 fast tests and the slow crash test green; browser checks pending
- 2026-10-24: checkpoint after f012, f014 to f017; 400 fast tests and the slow crash test green, nothing half done; next: the User's browser check (360 px and 1440 px) and f011.s4 with a private playlist, then try WMF_COOKIES_FROM_BROWSER locally
- 2026-10-24: f018 added and done (no delete existed): store.remove_tracks_by_relpath, DELETE /api/library, Delete button with confirm; 409 fast tests green
- 2026-10-24: f019 done: library_ops.py, runtime.py, /api/config, folder/move/bulk endpoints, Library and Settings UI, restyled CSS; 427 fast tests green; UI not checked in a browser
- 2026-10-24: UI feedback: progress bar fixes (fragment pct, final 100 not throttled, indeterminate stripe), light/dark toggle, SVG favicon and login logo, inline form sizing, scripts/export_image.sh + deploy/ bundle (image smoke tested); 428 fast tests green
- 2026-10-24: NAS import: dist/webmusicfolder.tar, entrypoint generates a persistent password when WMF_PASSWORD is unset, PUID/PGID default 0 in the image, deploy/NAS_GUIDE.md; zero config run and restart verified
- 2026-10-24: renamed to WebMusicFolder (WMF) in UI, Docker image and docs (python package and WMF_* variables unchanged); buttons Unlock and Exit
- 2026-10-24: login credit and centered title, password change (passwords.py, /api/account/password, session version), Open on YouTube button in Library, README rewritten for GitHub; 432 fast tests green
- 2026-10-24: project renamed to WebMusicFolder (WMF) everywhere incl. Docker image, pyproject name and docs; README header with centered logo (docs/assets/logo.svg); repo https://github.com/Brun0MF/WebMusicFolder
- 2026-10-24: renamed the Python package to webmusicfolder and the MD_* variables to WMF_* (breaking for existing containers)
- 2026-10-24: Deno added to the Docker image and yt-dlp[default] (yt-dlp-ejs) for YouTube challenge solving; Library no longer shows 'Unknown' album; image rebuilt
- 2026-10-24: more MP3 quality choices (v2, v5, 192k, 128k), default now v5 (a 19 s clip: V0 331 kB, V5 121 kB); fixed Settings selects showing the first option after a reload
- 2026-10-24: checkpoint: 432 fast tests green; f018, f019, rename to WebMusicFolder, password change, theme toggle, login page, NAS image with Deno, quality options done; next: User imports dist/webmusicfolder.tar on the NAS and does the browser checks
- 2026-10-24: Dismiss all and Cancel all on the downloads list (/api/queue/dismiss_all, /api/queue/cancel_all); 435 fast tests green
