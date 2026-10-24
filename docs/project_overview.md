# Project overview

## Name
WebMusicFolder

## Pitch
A self-hosted web app that downloads music from YouTube and YouTube Music with yt-dlp, converts it to tagged MP3 files and places them in the right folder of a music library on a server.

## Problem
The owner keeps the music library on a home server. Today each song needs yt-dlp to be run by hand, the result tagged and then moved to the server. This is repetitive and error prone (duplicates, missing covers, wrong folders). The app turns it into: paste links, pick a folder, done.

## Target users
A single owner (self-hoster) running the app in Docker on a Linux server and using it from any browser on the LAN or behind a VPN or reverse proxy.

## Goals
- Paste many links (tracks and playlists) in one text box and download them in the background.
- Files land in `<music dir>/<subfolder>/<Title>.mp3` with title, artist (channel), cover and source info in the ID3 tags.
- Never download the same video twice by accident, and ask when a link is already in the library.
- The server keeps working without a browser open and resumes pending downloads after a crash or reboot.
- Very low resource use at idle (no polling, no child processes when the queue is empty).
- Modern dark UI (Material dark / JetBrains IDE feel) with live progress.
- Runs in Docker with two volumes (music, data).

## Non-goals
- Not a music player and not a streaming server.
- No multi-user accounts, no public internet hosting hardening beyond one password.
- No sources other than YouTube / YouTube Music in the MVP.
- No Spotify, no DRM bypass, no lossless claims (YouTube audio is lossy).
- No re-tagging or reorganising of files added outside the app.

## MVP definition
Phase 1 in `docs/roadmap.md` (features f001 to f011): authenticated web UI, link and playlist submission with subfolder choice, persistent resumable queue, MP3 output with tags and cover, duplicate detection with a skip or redownload dialog, live progress, library page with App/External source, yt-dlp log tab, error messages, yt-dlp update button, cookies.txt upload, Docker image.

## Glossary
- **Track**: one downloaded audio file known to the app, identified by YouTube video ID.
- **Queue item**: one video waiting to be downloaded, in progress, failed or done.
- **Subfolder**: optional folder under the music directory chosen per batch (for example `geek`, `musicas de festa`).
- **Source**: `App` for files downloaded by this app, `External` for files found in the music directory that the app did not download.
- **Music dir**: root of the library (`/music` in Docker).
- **Data dir**: app state (`/data` in Docker): JSON state, temp downloads, logs, cookies, yt-dlp package.
- **SSE**: Server-Sent Events, used to push progress to the browser.
