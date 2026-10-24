# F018: Delete tracks from the Library

- Status: done (browser check pending)
- Phase: 2
- Depends on: f008
- Requirements: new FR-29

## Goal
Let the user delete a song from the Library page.

## Acceptance criteria
- [x] Every Library row has a Delete button that asks for confirmation.
- [x] `DELETE /api/library` removes the MP3 from disk, drops its Track from state and refreshes the listing.
- [x] After deleting an App file the same link is no longer reported as a duplicate.
- [x] CSRF is required; traversal, hidden paths, non MP3, missing files and symlinks pointing outside are 404 and never touch the target.

## Steps
- [x] f018.s1: `remove_tracks_by_relpath` in the store and `DELETE /api/library` (verify: integration tests)
- [x] f018.s2: Delete button with confirm dialog in the Library UI (verify: manual, browser check)

## Notes
Empty subfolders are left in place. No trash or undo: the confirm dialog is the safeguard.
