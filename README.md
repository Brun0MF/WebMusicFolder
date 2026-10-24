<p align="center">
  <img src="docs/assets/logo.svg" alt="WebMusicFolder logo" width="160" height="160">
</p>

<h1 align="center">WebMusicFolder (WMF)</h1>

<p align="center">
  <b>Download music from YouTube straight into your own music folder, from a web page.</b><br>
  Self-hosted, Docker ready, built for a NAS.
</p>

<p align="center">
  <a href="https://github.com/Brun0MF/WebMusicFolder">Repository</a> &middot;
  <a href="#install">Install</a> &middot;
  <a href="#user-manual">User manual</a> &middot;
  <a href="#configuration">Configuration</a>
</p>

---

A self-hosted web app that downloads music from YouTube and YouTube Music with [yt-dlp](https://github.com/yt-dlp/yt-dlp), converts it to tagged MP3 and files it in the right folder of your music library on a server or NAS. Paste links, pick a folder, and it keeps working in the background, even after a crash or a reboot.

Made by Bruno Ferreira ([Brun0MF](https://github.com/Brun0MF)). Repository: <https://github.com/Brun0MF/WebMusicFolder>

## Features

**Downloading**
- Paste many video and playlist links at once, or search YouTube by name inside the app.
- MP3 output (default VBR V5, about 130 kbps, similar to a plain yt-dlp download; V2, V0, 320k, 192k and 128k selectable in Settings) with title, artist, cover art and the source video id in the tags.
- Choose a subfolder per batch (for example `geek`, `party`).
- Persistent queue: it resumes by itself after a crash, restart or reboot, with retry and backoff for temporary errors.
- Live progress bars and a remaining counter, pushed to the browser (no polling).
- Duplicate detection: known videos open a skip or redownload dialog.
- Private playlists and age restricted videos through an uploaded `cookies.txt`, or straight from a local browser (`WMF_COOKIES_FROM_BROWSER`).
- Optional, off by default: SponsorBlock (cuts sponsor, self promotion and other non music segments) and ReplayGain loudness tags (the audio is not changed).

**Library**
- Every MP3 with cover, duration, size and folder, marked `App` (downloaded here) or `External` (already in the folder).
- Search, filter by folder and source, rescan.
- Create and delete folders (deleting a folder deletes the tracks inside), move tracks between folders or back to the root.
- Multi select with Select all, bulk move and bulk delete; single track delete with confirmation.
- Open on YouTube (new tab) for every track downloaded by the app.
- Link an `External` file to a YouTube video so it counts as a known duplicate.

**Operation**
- Logs tab with the live yt-dlp output (secrets redacted), readable error messages, Retry and Retry all failed.
- Update yt-dlp from Settings when YouTube changes, no image rebuild needed.
- Settings kept on the server: music folder, MP3 quality, parallel downloads, options, cookies, and the login password.
- Password login with CSRF protection and login rate limiting. Dark (GitHub style, blue accent) and light theme.
- Small footprint: one container, state in a JSON file, about 40 MiB of RAM when idle.

## Install

### Docker on a NAS with only a web UI (Ugreen UGOS and similar)

1. On a machine with Docker, in this repository run `scripts/export_image.sh`. It writes `dist/webmusicfolder.tar` (add `PLATFORM=linux/arm64` for an ARM NAS).
2. In the NAS Docker app: Image > local import > `webmusicfolder.tar`.
3. Create a container from `webmusicfolder:latest`:
   - port: container `8080` to a free host port
   - volumes: a music folder to `/music`, a data folder to `/data`
   - optional environment: `WMF_PASSWORD`, `PUID`, `PGID`, `TZ`
   - restart policy: always
4. Open `http://<nas-ip>:<port>`. If you did not set `WMF_PASSWORD`, a random password is created on the first start and printed in the container logs (also stored in `/data/initial_password.txt`).

More detail in [`deploy/NAS_GUIDE.md`](deploy/NAS_GUIDE.md).

### Docker with a shell

    export WMF_PASSWORD='choose-a-password'
    export WMF_MUSIC_HOST=/path/to/music
    docker compose up -d --build

`docker-compose.yml` mounts `WMF_MUSIC_HOST` (default `/srv/music`) as `/music` and `./data` as `/data`. To move a prebuilt image to another machine, run `scripts/export_image.sh` and copy `dist/` there, then run `./install.sh`.

### Local (development)

Needs Python 3.12, [uv](https://docs.astral.sh/uv/) and ffmpeg.

    uv sync
    WMF_PASSWORD=dev WMF_MUSIC_DIR=./music WMF_DATA_DIR=./data uv run python -m webmusicfolder.main
    scripts/check.sh        # ruff and the fast tests

TLS is not handled by the app: put it behind a reverse proxy or a VPN.

## Configuration

Environment variables (the defaults; Settings > General overrides music folder, quality and parallel downloads and keeps them across restarts):

| Variable | Default | Meaning |
|---|---|---|
| `WMF_PASSWORD` | none (generated in the Docker image) | Login password. Replaced by the one stored when you change it in Settings. |
| `WMF_MUSIC_DIR` | `/music` | Where the MP3 files go. |
| `WMF_DATA_DIR` | `/data` | State, logs, cookies, secret key. |
| `WMF_PORT` | `8080` | HTTP port inside the container. |
| `WMF_QUALITY` | `v5` | `v0`, `v2`, `v5`, `320k`, `192k` or `128k`. |
| `WMF_CONCURRENCY` | `1` | Parallel downloads, 1 to 4. |
| `WMF_SECRET` | generated | Session signing key. |
| `WMF_COOKIES_FROM_BROWSER` | none | Local runs only, for example `firefox` or `firefox:profile`. An uploaded cookies.txt wins. |
| `PUID`, `PGID` | `0` in the image | User and group the app runs as. |
| `TZ` | `UTC` | Time zone. |

## User manual

**Unlock.** Open the app and enter the password. Exit signs you out. The sun/moon button switches between dark and light theme.

**Downloads.**
1. Paste one link per line (videos or playlists) in the links box, or type a name in the search field and press Add on a result.
2. Optionally type or pick a subfolder (it is created if needed).
3. Press Preview. Invalid links are listed, and videos you already have open a dialog where you choose skip or redownload for each.
4. Press Add to queue. Progress is shown live under the form. Cancel or retry single items, or use Retry all failed, Dismiss all (clears finished and failed entries) and Cancel all (drops the queue and stops running downloads).

Files are saved as `<music>/<subfolder>/<title>.mp3`; if another video already has that name, ` [<video id>]` is added.

**Library.**
- Use the search box and the folder and source filters. Rescan re-reads the disk.
- Folders card: type a name and Create folder; click a folder chip to filter by it; the x deletes the folder and every track in it (confirmation shown).
- Tick tracks, or Select all for the current filter, then pick a destination and Move, or Delete selected. A destination of `(music root)` takes tracks out of a folder. Files are never overwritten: a name clash is reported and that file is skipped.
- Per track: Open on YouTube opens the original video in a new tab, Link to YouTube turns an `External` file into an `App` file, Delete removes the file after confirmation.

**Logs.** Live yt-dlp output, filterable per item. Passwords, cookies paths and the secret are redacted.

**Settings.**
- Password: change it (needs the current one, at least 8 characters). Other devices are signed out. To fall back to `WMF_PASSWORD`, delete `password.json` from the data folder.
- General: music folder (absolute path inside a mounted volume; existing files are not moved), MP3 quality, parallel downloads.
- yt-dlp: Update when downloads start failing. Waits for an idle queue.
- Download options: SponsorBlock and ReplayGain.
- YouTube cookies: export `cookies.txt` from your browser while on YouTube, upload or paste it. The cookies give access to that Google account, so a dedicated account is advised. The file is stored with mode 0600 and never shown again.

**Troubleshooting.**
- Downloads fail with a sign-in message: upload fresh cookies, or update yt-dlp.
- Files are not writable on a NAS: set `PUID` and `PGID` to a user that owns the share (the image runs as root by default).
- Forgot the password: delete `password.json` in the data folder and use `WMF_PASSWORD`, or read the generated one in `initial_password.txt`.

## Development

    scripts/check.sh               # ruff check, ruff format --check, fast tests
    uv run pytest -m slow          # crash simulation, about 2 minutes

Planning and design documents live in `docs/` (`project_overview`, `requirements`, `architecture`, `roadmap`, `progress`, `decisions`, one file per feature in `docs/features/`). Stack: Python 3.12, FastAPI, Alpine.js and htmx (vendored, no CDN), yt-dlp, mutagen, ffmpeg.

## Legal

Use it only for content you have the right to download. Downloading from YouTube may violate its terms of service or copyright law depending on the content and your country.

## License

GPL-3.0 (to be confirmed).
