# Architecture

## Stack and justification

| Layer | Choice | Why |
|-------|--------|-----|
| Language | Python 3.12 | yt-dlp is Python, mutagen is Python; default scripting stack of the owner. |
| Web framework | FastAPI + uvicorn (single worker) | Async, small idle footprint, native SSE via `StreamingResponse`. |
| Templates | Jinja2 | Server-rendered HTML fragments for htmx. |
| Front end | htmx 2.x + Alpine.js 3.x, vendored under `static/vendor/` | No build step, no Node, no CDN at runtime. Alpine handles small local state (dialogs, tabs). |
| Styling | Hand written CSS with design tokens (custom properties) | Dark Material / JetBrains look without a framework. |
| Download | yt-dlp, run in a subprocess via `ytdlp_runner.py` | Crash isolation, easy hot update (no module reload), no resident memory when idle. |
| Audio | ffmpeg (system package) | MP3 encoding (libmp3lame), thumbnail conversion. |
| Tags | mutagen | Read and write ID3v2.4 and read duration. |
| Auth | Starlette `SessionMiddleware` (signed cookie) | Enough for one password. |
| State | One JSON file, atomic writes | Requested by the owner; volume is small (thousands of tracks). |
| Tests | pytest, pytest-asyncio, httpx | Standard. |
| Tooling | uv, ruff | Owner conventions. |
| Packaging | Docker image + docker-compose.yml | Server deployment. |

## Directory layout

```
WebMusicFolder/
  README.md
  LICENSE                       GPL-3.0
  pyproject.toml
  Dockerfile
  docker-compose.yml
  scripts/check.sh              ruff + pytest
  docs/                         planning docs (this folder)
  src/webmusicfolder/
    __init__.py
    main.py                     app factory, lifespan (start/stop worker), uvicorn entry
    config.py                   env parsing into a frozen Settings dataclass
    auth.py                     login, session dependency, rate limit, CSRF token
    paths.py                    safe path helpers, subfolder validation, filename sanitising
    store.py                    JSON state: load, atomic save, typed accessors, lock
    models.py                   dataclasses: Track, QueueItem, Settings, LibraryEntry
    urls.py                     YouTube URL validation and normalisation
    resolver.py                 expand links/playlists to video IDs (runner in flat mode)
    queue_worker.py             asyncio worker: picks items, runs runner, updates state, resume logic
    ytdlp_runner.py             standalone script run as subprocess; prints JSON lines
    runner_client.py            async client: spawns the runner, parses its lines, kills the process group
    downloader.py               download_one(): runner in a temp dir, tag, atomic move into the library
    errors.py                   error codes, message classifier, DownloadError
    tagging.py                  mutagen read/write helpers
    library.py                  scan music dir, build LibraryEntry list, in-memory cache
    events.py                   in-process pub/sub feeding SSE streams
    logs.py                     yt-dlp log ring buffer + rotating file
    ytdlp_update.py             pip install --target /data/ytdlp_pkg, version query
    cookies.py                  cookies.txt save/delete with mode 0600
    loudness.py                 ffmpeg ebur128 measurement, ReplayGain 2.0 gain and peak
    search.py                   search by name through the runner
    importer.py                 link an External MP3 to a video id (atomic tag write)
    web/
      routes_pages.py           HTML pages and fragments
      routes_api.py             JSON/HTMX endpoints (submit, retry, update, cookies)
      routes_app_settings.py    GET/POST /api/settings (sponsorblock, replaygain toggles)
      routes_search.py          POST /api/search
      routes_sse.py             /events stream
      templates/                base.html, downloads.html, library.html, logs.html, settings.html, fragments/
      static/                   css/app.css, js/app.js, vendor/htmx.min.js, vendor/alpine.min.js
  tests/
    unit/ integration/ fixtures/
```

## Module responsibilities
- **config**: reads `WMF_PASSWORD` (required), `WMF_MUSIC_DIR` (`/music`), `WMF_DATA_DIR` (`/data`), `WMF_PORT` (8080), `WMF_SECRET` (optional, else generated once and saved in data dir), `WMF_CONCURRENCY` (1), `WMF_QUALITY` (`v0` or `320k`), `WMF_COOKIES_FROM_BROWSER` (optional, `firefox` or `firefox:profile`, local runs only), `PUID`/`PGID`. Fails fast with a clear message when invalid.
- **store**: single source of truth. All mutations go through one `asyncio.Lock`; every state transition writes `state.json.tmp`, `fsync`, `os.replace`. Progress percentages live in memory only (not persisted).
- **queue_worker**: loop waiting on an `asyncio.Event` (no polling). Picks the oldest `queued` item, sets `downloading`, spawns the runner, reads its JSON lines, publishes events, on success moves the file and registers the Track.
- **ytdlp_runner**: receives URL, temp dir, quality, optional cookies path as args. Emits lines like `{"type":"progress","pct":42.1,"speed":..., "eta":...}`, `{"type":"log","line":"..."}`, `{"type":"done","path":"...","info":{...}}`, `{"type":"error","code":"private","message":"..."}`. Uses `PYTHONPATH=/data/ytdlp_pkg` first when present.
- **library**: walks the music dir (no symlink escape), reads tags with mutagen, caches by `(path, mtime, size)`; invalidated by a rescan button and after each finished download. Source is `App` when the file's video ID tag matches a Track in state, else `External`.
- **events**: bounded per-client queues; a slow client is dropped, never blocks the worker.

## Data model (`/data/state.json`)

```json
{
  "version": 1,
  "settings": {"quality": "v0", "concurrency": 1, "sponsorblock": false, "replaygain": false},
  "tracks": {
    "dQw4w9WgXcQ": {
      "video_id": "dQw4w9WgXcQ",
      "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
      "title": "Song title",
      "artist": "Channel name",
      "duration_s": 213,
      "subfolder": "geek",
      "relpath": "geek/Song title.mp3",
      "downloaded_at": "2026-10-24T12:00:00Z",
      "quality": "v0"
    }
  },
  "queue": [
    {
      "id": "uuid4",
      "video_id": "dQw4w9WgXcQ",
      "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
      "title": "Song title",
      "subfolder": "geek",
      "status": "queued",
      "attempts": 0,
      "error": null,
      "added_at": "2026-10-24T11:59:00Z",
      "overwrite": false,
      "finished_at": null
    }
  ]
}
```

Queue status values: `queued`, `downloading`, `done`, `failed`. Done items older than 7 days are pruned. Library entries for External files are not stored in JSON; they are computed from disk.

## External interfaces
HTTP (all behind auth except `/login` and `/healthz`):

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Downloads page (submit form, active list) |
| POST | `/api/submit/preview` | Resolve links, return playlist sizes and duplicates |
| POST | `/api/submit/confirm` | Create queue items with per-link skip or redownload decisions |
| POST | `/api/queue/{id}/retry`, `/api/queue/retry_failed`, `/api/queue/{id}/cancel` | Queue control |
| GET | `/events` | SSE stream: `progress`, `item`, `log`, `library` events |
| GET | `/library`, `/api/library` | Library page and filtered fragment |
| POST | `/api/library/rescan` | Force rescan |
| GET | `/library/cover/{relpath}` | Cover image extracted from tags |
| GET | `/logs` | Log tab |
| GET | `/settings`, `/api/ytdlp/version` | Settings page, installed yt-dlp version |
| POST | `/api/ytdlp/update` | Update yt-dlp (409 while downloading, 502 on failure) |
| GET/POST/DELETE | `/api/cookies` | Cookies status, save (JSON `{text}`), delete; content is never returned |
| GET | `/api/logs?item=` | Log history (ring buffer); live lines arrive as `log` events |
| POST | `/api/queue/retry_failed` | Requeue every failed item |
| GET/POST | `/api/settings` | Read or change the `sponsorblock` and `replaygain` toggles |
| POST | `/api/search` | Search YouTube by name, up to 10 results, marked when already in library or queue |
| POST | `/api/library/link` | Link an External file to a video (`{path, link}`), 404 bad file, 409 already linked, 422 bad link |
| GET | `/healthz` | Liveness, no auth |

Runner modes: `download` (`--sponsorblock`, `--cookies`, `--cookies-from-browser`), `flat`, `search`, `version`.

Runner protocol: JSON lines on stdout, one object per line, UTF-8.

## Deployment
- Image based on `python:3.12-slim` with `ffmpeg`; app installed with `uv`. Entry via a tiny init (`tini`) so SIGTERM reaches the app.
- `docker-compose.yml`: ports `8080:8080`, volumes `/srv/music:/music` and `./data:/data`, env `WMF_PASSWORD`, `PUID`, `PGID`, `TZ`.
- Intended to sit behind a reverse proxy or VPN for internet access (TLS is not handled by the app).

## Error handling strategy
- Every runner error maps to a code (`private`, `unavailable`, `age_restricted`, `login`, `network`, `ffmpeg`, `disk_full`, `unknown`) and a short human message stored on the queue item and pushed as an event.
- Network errors retry up to 3 times with backoff (30 s, 2 min, 10 min); others fail immediately and wait for the user.
- Corrupt `state.json`: load fails loudly, the previous file is kept as `state.json.bak` (written before each save of a new version once per hour) and the UI shows a blocking error. Never silently reset.
- Unexpected exceptions in the worker are logged with traceback, the item is marked `failed`, the worker keeps running.
- Disk full or unwritable music dir: item fails with `disk_full` or `permission`, queue pauses after 3 consecutive such failures and shows a banner.

## Crash recovery
On startup: load state, set every `downloading` item to `queued`, delete the contents of `/data/tmp`, then start the worker. Temp files never live in the music dir, so the library cannot contain partial files. Final move uses `os.replace` on the same filesystem when possible (otherwise copy to `<name>.tmp` in the target dir, then rename).

## Security notes
- Single password, constant-time compare, login rate limit, signed session cookie, CSRF token on POST.
- Only YouTube hosts accepted; URLs passed to the runner as arguments, never through a shell.
- Subfolder and file names sanitised in `paths.py`; all targets resolved and checked to be inside the music dir.
- `cookies.txt` is sensitive: mode 0600, never logged, never served back; the UI only shows whether one is loaded.
- Cover endpoint serves only images extracted from files inside the music dir.

## Testing strategy
- Unit: `paths` (traversal, sanitising, collisions), `urls`, `store` (atomic write, crash simulation), `tagging`, queue state machine, filename rules, `library` source detection.
- Integration: FastAPI `TestClient` for auth, submit, preview, SSE; the runner replaced by a fake script emitting scripted JSON lines (success, error, slow, killed).
- Crash test: start worker with fake runner, kill mid-item, restart, assert completion.
- Manual: real YouTube video, real playlist, a private playlist with cookies, Docker run with `docker stats` for idle numbers (NFR-01), check on a phone.
- Definition of done per feature: acceptance criteria ticked, tests passing, `scripts/check.sh` green, docs updated.
