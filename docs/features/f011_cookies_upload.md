# F011: Cookies.txt upload for private playlists

- Status: in progress (s4 needs the User's private playlist)
- Phase: 1
- Depends on: f003
- Requirements: FR-21

## Goal
Allow downloading from private playlists and age restricted videos using the owner's YouTube session.

## Description
A web page cannot read browser cookies and a container cannot see the host browser, so the user exports `cookies.txt` (Netscape format, for example with the "Get cookies.txt LOCALLY" extension) and uploads or pastes it in Settings. `cookies.py` validates the format, stores it at `/data/cookies.txt` with mode 0600, and the runner receives its path. The UI shows only whether cookies are loaded and the file date, and offers delete.

## Acceptance criteria
- [x] Upload and paste both work; invalid content is rejected with a message. (upload reads the file in the browser and posts its text, same endpoint as paste; browser check pending)
- [x] File mode is 0600; the file is never served back or logged. (also verified in Docker)
- [ ] A private playlist downloads after upload.
- [x] Delete removes the file and later downloads run without cookies.
- [x] The Settings page warns that the cookies grant access to the Google account and should come from a dedicated account if possible.

## Steps
- [x] f011.s1: `cookies.py` parse, validate, save with mode 0600, delete (verify: unit tests including mode and invalid format)
- [x] f011.s2: runner receives the cookies path when present (verify: test on built command line)
- [x] f011.s3: Settings UI with upload, paste, status, delete and warning (verify: manual; browser check pending)
- [ ] f011.s4: end to end private playlist (verify: manual with a real private playlist)

## Test plan
Unit tests, TestClient upload tests, one manual private playlist.

## Notes
Cookies expire or rotate; when yt-dlp reports a login error the error message tells the user to re-export them. Browser cookie import for local runs is backlog item f012.
