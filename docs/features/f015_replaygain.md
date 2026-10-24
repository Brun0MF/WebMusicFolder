# F015: Loudness normalisation via ReplayGain tags

- Status: done (browser check pending)
- Phase: 2
- Depends on: f003, f014.s1 (settings endpoint)
- Requirements: new FR-26

## Goal
Make tracks play at a similar loudness in players that honour ReplayGain, without re-encoding or altering the audio.

## Description
A toggle in Settings (off by default) stored in `AppSettings.replaygain`. When on, after the runner finishes, `loudness.py` measures the MP3 with ffmpeg `ebur128` (integrated loudness and sample peak), computes the ReplayGain 2.0 gain against the -18 LUFS reference, and `tagging.py` writes `REPLAYGAIN_TRACK_GAIN` (`-3.21 dB`) and `REPLAYGAIN_TRACK_PEAK` (linear, 6 decimals) as TXXX frames in the same save as the other tags. The audio stream is never touched. A measuring failure logs a warning and the track is kept without the tags.

## Acceptance criteria
- [x] Toggle persists and is off by default; off means no extra ffmpeg run.
- [x] A known test tone gives the expected gain within 1 dB and a sample peak (can exceed 1.0 on real lossy tracks, as the measured -8.9 dB / 1.17 example showed).
- [x] Tags read back with mutagen; existing tags (title, artist, cover, video id) are unchanged.
- [x] If ffmpeg measurement fails the download still succeeds.
- [x] The MP3 audio bytes are identical with and without the feature.

## Steps
- [x] f015.s1: `loudness.py` measure and gain maths (verify: unit tests with generated sine at known level)
- [x] f015.s2: `tagging.write_tags` accepts optional replaygain values (verify: unit tests)
- [x] f015.s3: downloader runs the measurement when enabled, worker passes the setting (verify: integration tests incl. failure case)
- [x] f015.s4: Settings UI toggle (verify: manual)

## Test plan
Unit tests with ffmpeg generated tones, integration through the fake runner.

## Notes
Track gain only; album gain would need album grouping and is out of scope. Existing library files are not retro tagged.
