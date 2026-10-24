"""Stand in for ytdlp_runner in tests. Behaviour is chosen per video id.

Environment:
    FAKE_SCENARIOS  JSON {video_id: scenario}; default scenario is "ok".
    FAKE_MP3        path of a real MP3 copied into the temp dir on success.
    FAKE_TITLES     JSON {video_id: title}.
    FAKE_SEARCH     JSON {query: [{"id", "title", "channel", "duration_s"}]} for search mode.
    FAKE_FLAT       JSON {url: [{"id": ..., "title": ...}, ...]} for flat mode.
    FAKE_STATE_DIR  directory for per id attempt counters and start markers.

    FAKE_VERSION    version reported by `version` mode unless PYTHONPATH holds a version.txt.

Scenarios: ok, slow:<seconds>, error:<code>, flaky:<failures>, hang, crash.
"""

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

COVER = b"\xff\xd8\xff\xe0fakejpeg\xff\xd9"


def emit(**fields):
    sys.stdout.write(json.dumps(fields) + "\n")
    sys.stdout.flush()


def video_id_of(url):
    return (parse_qs(urlsplit(url).query).get("v") or [url])[0]


def bump(state_dir, name):
    path = Path(state_dir) / name
    count = int(path.read_text()) + 1 if path.exists() else 1
    path.write_text(str(count))
    return count


def download(args):
    vid = video_id_of(args.url)
    scenario = json.loads(os.environ.get("FAKE_SCENARIOS", "{}")).get(vid, "ok")
    state_dir = os.environ.get("FAKE_STATE_DIR")
    attempt = 1
    if state_dir:
        (Path(state_dir) / f"start_{vid}").write_text(str(os.getpid()))
        attempt = bump(state_dir, f"attempts_{vid}")
        (Path(state_dir) / f"cookies_{vid}").write_text(args.cookies or "")
        (Path(state_dir) / f"sponsorblock_{vid}").write_text(str(args.sponsorblock))
        (Path(state_dir) / f"browser_{vid}").write_text(args.cookies_from_browser or "")
    emit(type="log", line=f"fake start {vid} ({scenario})")
    emit(type="progress", pct=10.0, speed=1000.0, eta=9)

    kind, _, arg = scenario.partition(":")
    if kind == "error":
        emit(type="error", code=arg, message=f"fake {arg} error")
        return 1
    if kind == "crash":
        sys.stderr.write("boom: something exploded\n")
        return 3
    if kind == "hang":
        time.sleep(1000)
    if kind == "flaky" and attempt <= int(arg):
        emit(type="error", code="network", message="fake network error")
        return 1
    if kind == "slow":
        end = time.monotonic() + float(arg)
        while time.monotonic() < end:
            time.sleep(0.05)
            emit(type="progress", pct=50.0, speed=1000.0, eta=1)

    tmp = Path(args.tmp_dir)
    tmp.mkdir(parents=True, exist_ok=True)
    mp3 = tmp / f"{vid}.mp3"
    shutil.copy(os.environ["FAKE_MP3"], mp3)
    cover = tmp / f"{vid}.jpg"
    cover.write_bytes(COVER)
    title = json.loads(os.environ.get("FAKE_TITLES", "{}")).get(vid, f"Title {vid}")
    emit(type="progress", pct=100.0, speed=None, eta=0)
    emit(
        type="done",
        path=str(mp3),
        cover=str(cover),
        info={
            "video_id": vid,
            "title": title,
            "artist": "Some Artist - Topic",
            "duration_s": 1,
            "url": f"https://www.youtube.com/watch?v={vid}",
        },
    )
    return 0


def flat(args):
    table = json.loads(os.environ.get("FAKE_FLAT", "{}"))
    if args.url not in table:
        emit(type="error", code="unavailable", message="fake: unknown playlist")
        return 1
    count = 0
    for entry in table[args.url]:
        if entry.get("skip"):
            emit(type="skipped", video_id=entry["id"], reason=entry["skip"])
            continue
        count += 1
        emit(type="entry", video_id=entry["id"], title=entry.get("title", ""))
    emit(type="done", count=count)
    return 0


def search(args):
    table = json.loads(os.environ.get("FAKE_SEARCH", "{}"))
    if args.query not in table:
        emit(type="error", code="network", message="fake: search failed")
        return 1
    results = table[args.query][: args.limit]
    for entry in results:
        emit(
            type="entry",
            video_id=entry["id"],
            title=entry.get("title", ""),
            channel=entry.get("channel", ""),
            duration_s=entry.get("duration_s", 0),
        )
    emit(type="done", count=len(results))
    return 0


def version(_args):
    """A version.txt in a PYTHONPATH entry plays the role of an updated yt-dlp package."""
    for entry in os.environ.get("PYTHONPATH", "").split(os.pathsep):
        if entry and (Path(entry) / "broken.txt").is_file():
            emit(type="error", code="unknown", message="fake: yt_dlp failed to import")
            return 1
        marker = Path(entry) / "version.txt" if entry else None
        if marker is not None and marker.is_file():
            emit(type="done", version=marker.read_text().strip())
            return 0
    emit(type="done", version=os.environ.get("FAKE_VERSION", "2020.01.01"))
    return 0


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("version")
    dl = sub.add_parser("download")
    dl.add_argument("url")
    dl.add_argument("--tmp-dir", required=True)
    dl.add_argument("--quality", default="v0")
    dl.add_argument("--cookies")
    dl.add_argument("--sponsorblock", action="store_true")
    dl.add_argument("--cookies-from-browser")
    se = sub.add_parser("search")
    se.add_argument("--limit", type=int, default=10)
    se.add_argument("--cookies")
    se.add_argument("--cookies-from-browser")
    se.add_argument("query")
    fl = sub.add_parser("flat")
    fl.add_argument("url")
    fl.add_argument("--cookies")
    fl.add_argument("--cookies-from-browser")
    args = parser.parse_args()
    handlers = {"download": download, "flat": flat, "search": search, "version": version}
    return handlers[args.mode](args)


if __name__ == "__main__":
    raise SystemExit(main())
