# Roadmap

Status values: todo, in progress, done.

## Phase 1: MVP

| ID | Feature | Depends on | Status |
|----|---------|------------|--------|
| f001 | Project skeleton, config, auth, base UI, Docker | none | done |
| f002 | JSON state store | f001 | done |
| f003 | Download engine (runner, MP3, tags, cover, file naming) | f002 | done |
| f004 | Queue worker, persistence and crash resume | f003 | done |
| f005 | Link and playlist submission with subfolder choice | f004 | done |
| f006 | Duplicate detection and skip or redownload dialog | f005 | done (browser check pending) |
| f007 | Live downloads list with progress (SSE) | f004, f005 | done (browser check pending) |
| f008 | Library page (App vs External, Unknown fields) | f002, f003 | done (browser check pending) |
| f009 | yt-dlp logs tab and error messages with retry | f003, f007 | done (browser check pending) |
| f010 | yt-dlp update button | f001, f003 | done (browser check pending) |
| f011 | Cookies.txt upload for private playlists | f003 | in progress (s4 manual) |

Order rationale: infrastructure first (f001, f002), then the core download path (f003, f004) which can be tested end to end with a CLI-free fake runner, then the user facing input (f005, f006), then visibility (f007, f008, f009), then maintenance features (f010, f011).

## Phase 2: Later

| ID | Feature | Depends on | Status |
|----|---------|------------|--------|
| f012 | Browser cookie import (local runs only, `--cookies-from-browser`) | f011 | done (browser check pending) |
| f014 | SponsorBlock removal of non-music segments (toggle in Settings, off by default) | f003 | done (browser check pending) |
| f015 | Loudness normalisation via ReplayGain tags (toggle in Settings, off by default) | f003 | done (browser check pending) |
| f016 | Search by name inside the app | f005 | done (browser check pending) |
| f017 | Manual import of External files into the App index | f008 | done (browser check pending) |
| f018 | Delete tracks from the Library | f008 | done (browser check pending) |
| f019 | Folder management, multi select, persistent settings, new look | f018 | done (browser check pending) |
