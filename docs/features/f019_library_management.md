# F019: Folder management, multi select and persistent settings

- Status: done (browser check pending)
- Phase: 2
- Depends on: f008, f018
- Requirements: FR-30, FR-31, FR-32

## Goal
Manage subfolders and many tracks at once from the Library, and keep the important settings on the server.

## Acceptance criteria
- [x] Folders can be created and deleted; deleting a folder deletes every file in it and forgets their tracks (symlinks and `..` rejected, refused while downloads for it are queued).
- [x] Tracks can be moved into a subfolder or back to the music root, never overwriting; Track relpath follows the file so duplicate detection keeps working.
- [x] Library rows have checkboxes, Select all (current filter), bulk Move and bulk Delete with confirmation; partial failures are reported.
- [x] Settings has a General card: music folder, MP3 quality, parallel downloads; saved in the state file, applied live and kept across restarts; empty music folder restores the environment default; folder change refused while a download runs.
- [x] Refreshed GitHub dark / JetBrains style UI with a blue accent.

## Steps
- [x] f019.s1: `library_ops.py`, store move/remove helpers, folder/move/bulk delete endpoints (integration tests)
- [x] f019.s2: `runtime.py` and `/api/config`, live apply at startup and on save (integration tests)
- [x] f019.s3: Library UI (folder chips, checkboxes, bulk bar), Settings General card, new CSS (manual, browser check)

## Notes
Only first level subfolders are managed (matches the download form). Changing the music folder does not move files.
