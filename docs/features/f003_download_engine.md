# F003: Download engine

- Status: done
- Phase: 1
- Depends on: f002
- Requirements: FR-07, FR-08, FR-09, FR-12, NFR-08

## Goal
Download one YouTube video to a tagged MP3 in a temp dir and then move it atomically into the library.

## Description
`ytdlp_runner.py` runs yt-dlp as a subprocess, converts to MP3 (V0 or 320k), converts the thumbnail to JPEG and prints JSON lines (progress, log, done, error). `tagging.py` writes ID3v2.4: title, artist (channel, ` - Topic` removed), APIC cover, custom frames for video ID and URL. `paths.py` sanitises names, resolves collisions and enforces the music dir boundary. A `download_one()` function wraps the runner and the final move.

## Acceptance criteria
- [x] A real video produces a valid MP3 with title, artist, cover and video ID tag.
- [x] Quality setting changes the encoder profile (V0 vs 320k) as seen by ffprobe.
- [x] File name is the sanitised title; a different video with the same title gets ` [<id>]` appended.
- [x] Nothing is written to the target folder until tagging is complete.
- [x] Runner errors map to the codes listed in `architecture.md`.

## Steps
- [x] f003.s1: `paths.py` sanitising, collision, boundary checks (verify: unit tests with traversal, symlink, unicode, reserved names, long titles)
- [x] f003.s2: `urls.py` host and scheme validation, video ID extraction (verify: unit tests with watch, youtu.be, music, shorts, playlist URLs)
- [x] f003.s3: `ytdlp_runner.py` protocol with a fake yt-dlp in tests (verify: tests parse scripted output, error mapping)
- [x] f003.s4: real runner with yt-dlp options for MP3 and thumbnail (verify: manual download of a short video, ffprobe shows mp3)
- [x] f003.s5: `tagging.py` write and read back (verify: unit test with mutagen on a generated MP3)
- [x] f003.s6: `download_one()` with temp dir and atomic move (verify: integration test with fake runner; manual check that target is empty during download)

## Test plan
Unit tests for paths, urls, tagging; fake-runner integration; one manual real download.

## Notes
yt-dlp options: `format=bestaudio/best`, `FFmpegExtractAudio(preferredcodec=mp3, preferredquality=0)` for V0 or `320` for 320k, `writethumbnail`, no playlist expansion inside the runner (the resolver already split items). Use `--no-mtime` so file dates are download dates.

## Implementation notes
- Extra modules: `errors.py` (codes, message classifier, `DownloadError`), `runner_client.py` (async subprocess client, process group kill, idle timeout), `downloader.py` (`download_one`, `atomic_move`, `existing_track_file`).
- Real download verified on a public video: ffprobe reports `mp3`, 139 kb/s average for V0 and 320000 for 320k; target folder was empty during the download; tags and cover read back.
- A watch link with a `list=` parameter is treated as the single video; only `/playlist` links expand (see D017).
