# F014: SponsorBlock segment removal

- Status: done (browser check pending)
- Phase: 2
- Depends on: f003
- Requirements: new FR-25

## Goal
Optionally cut non music segments (sponsor reads, self promotion, interaction reminders, non music parts of music videos) out of the MP3 while downloading.

## Description
A toggle in Settings (off by default) stored in `AppSettings.sponsorblock`. A new `GET/POST /api/settings` pair exposes the two toggles (this feature adds the endpoint, f015 reuses it). When on, the worker passes `--sponsorblock` to the runner, which adds the yt-dlp `SponsorBlock` postprocessor (after filter) and `ModifyChapters` (after `FFmpegExtractAudio`, as yt-dlp itself orders them) for the categories `sponsor`, `selfpromo`, `interaction` and `music_offtopic`. Intro and outro are not removed because in music they are often music. Because the cut changes the length, the runner reports the duration read from the final MP3. A SponsorBlock API failure must not fail the download.

## Acceptance criteria
- [x] Toggle in Settings persists across restarts and is off by default.
- [x] With the toggle off the runner command line and options are exactly as before.
- [x] With the toggle on the runner receives `--sponsorblock` and builds the two postprocessors in the right order.
- [x] The tagged duration matches the final file after a cut.
- [x] A video with no segments, or an unreachable SponsorBlock API, still downloads normally.

## Steps
- [x] f014.s1: `GET/POST /api/settings` for `sponsorblock` and `replaygain` with CSRF and validation (verify: integration tests)
- [x] f014.s2: runner `--sponsorblock` flag, options and duration from the MP3 (verify: unit tests on `build_options`, fake runner test)
- [x] f014.s3: worker and downloader pass the flag from settings (verify: test on the built command line)
- [x] f014.s4: Settings UI toggle (verify: manual, browser check pending)
- [x] f014.s5: real download of a video with known segments (verified: Dua Lipa video ZjBZ8MUnB0E went from 226 s to 209 s with 2 segments removed)

## Test plan
Unit tests for option building, integration tests for the settings API and command line, one real network download.

## Notes
Category list is a decision recorded in decisions.md.
