import os
import time

import pytest

from webmusicfolder.library import (
    MAX_COVER_BYTES,
    SOURCE_APP,
    SOURCE_EXTERNAL,
    Library,
    filter_entries,
)
from webmusicfolder.models import Track
from webmusicfolder.paths import PathError

JPEG = b"\xff\xd8\xff\xe0cover\xff\xd9"


def app_track(video_id):
    return {video_id: Track(video_id, "u", "T", "A", 1, "", "x.mp3", "2026-10-24T00:00:00Z", "v0")}


def scan(root, tracks=None):
    return {e.path: e for e in Library(root).scan(tracks or {})}


def test_tagless_file_falls_back_to_file_name(tmp_path, make_mp3):
    make_mp3(tmp_path / "foo.mp3")
    entry = scan(tmp_path)["foo.mp3"]
    assert (entry.title, entry.artist, entry.album) == ("foo", "Unknown", "Unknown")
    assert entry.source == SOURCE_EXTERNAL and entry.duration_s == 1 and not entry.has_cover


def test_partial_tags_fill_only_the_gaps(tmp_path, make_mp3):
    make_mp3(tmp_path / "x.mp3", title="Real Title")
    entry = scan(tmp_path)["x.mp3"]
    assert (entry.title, entry.artist) == ("Real Title", "Unknown")


def test_full_tags_subfolder_and_cover_flag(tmp_path, make_mp3):
    make_mp3(tmp_path / "geek" / "a.mp3", "T", "Art", "Alb", cover=JPEG)
    entry = scan(tmp_path)["geek/a.mp3"]
    assert (entry.title, entry.artist, entry.album, entry.subfolder) == ("T", "Art", "Alb", "geek")
    assert entry.has_cover and entry.size > 0


def test_corrupt_file_still_listed(tmp_path):
    (tmp_path / "broken.mp3").write_bytes(b"not an mp3 at all")
    entry = scan(tmp_path)["broken.mp3"]
    assert entry.title == "broken" and entry.duration_s == 0


def test_non_mp3_hidden_and_part_files_are_ignored(tmp_path, make_mp3):
    make_mp3(tmp_path / "ok.mp3", "ok")
    (tmp_path / "note.txt").write_text("x")
    make_mp3(tmp_path / ".hidden.mp3", "h")
    make_mp3(tmp_path / ".hiddendir" / "a.mp3", "h")
    (tmp_path / ".Song.mp3.part").write_bytes(b"x")
    assert list(scan(tmp_path)) == ["ok.mp3"]


def test_source_app_only_when_video_id_matches_a_track(tmp_path, make_mp3):
    make_mp3(tmp_path / "mine.mp3", "m", video_id="aaaaaaaaaaa")
    make_mp3(tmp_path / "other.mp3", "o", video_id="bbbbbbbbbbb")
    make_mp3(tmp_path / "hand.mp3", "h")
    entries = scan(tmp_path, app_track("aaaaaaaaaaa"))
    assert entries["mine.mp3"].source == SOURCE_APP
    assert entries["other.mp3"].source == SOURCE_EXTERNAL
    assert entries["hand.mp3"].source == SOURCE_EXTERNAL


def test_source_follows_state_even_with_cached_tags(tmp_path, make_mp3):
    make_mp3(tmp_path / "a.mp3", "a", video_id="aaaaaaaaaaa")
    lib = Library(tmp_path)
    assert lib.scan({})[0].source == SOURCE_EXTERNAL
    assert lib.scan(app_track("aaaaaaaaaaa"))[0].source == SOURCE_APP


def test_cache_reuses_unchanged_files_and_rereads_changed_ones(tmp_path, make_mp3, monkeypatch):
    from webmusicfolder import library

    path = make_mp3(tmp_path / "a.mp3", "Old")
    make_mp3(tmp_path / "b.mp3", "B")
    lib = Library(tmp_path)
    lib.scan({})
    calls = []
    real = library.read_library_tags
    monkeypatch.setattr(library, "read_library_tags", lambda p: calls.append(p.name) or real(p))
    lib.scan({})
    assert calls == []
    make_mp3(path, "New Title")
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    entries = {e.path: e for e in lib.scan({})}
    assert calls == ["a.mp3"] and entries["a.mp3"].title == "New Title"


def test_invalidate_forces_a_full_reread(tmp_path, make_mp3, monkeypatch):
    from webmusicfolder import library

    make_mp3(tmp_path / "a.mp3", "A")
    lib = Library(tmp_path)
    lib.scan({})
    lib.invalidate()
    calls = []
    real = library.read_library_tags
    monkeypatch.setattr(library, "read_library_tags", lambda p: calls.append(p.name) or real(p))
    lib.scan({})
    assert calls == ["a.mp3"]


def test_deleted_file_disappears(tmp_path, make_mp3):
    path = make_mp3(tmp_path / "a.mp3", "A")
    lib = Library(tmp_path)
    assert len(lib.scan({})) == 1
    path.unlink()
    assert lib.scan({}) == []


def test_symlinks_pointing_outside_are_not_followed(tmp_path, make_mp3):
    music = tmp_path / "music"
    outside = tmp_path / "outside"
    make_mp3(outside / "secret.mp3", "secret")
    make_mp3(music / "inside.mp3", "inside")
    os.symlink(outside, music / "linked_dir")
    os.symlink(outside / "secret.mp3", music / "linked_file.mp3")
    assert list(scan(music)) == ["inside.mp3"]


def test_missing_music_dir_gives_empty_library(tmp_path):
    assert Library(tmp_path / "nope").scan({}) == []


def test_filters_combine(tmp_path, make_mp3):
    make_mp3(tmp_path / "geek" / "a.mp3", "Alpha Song", "Zed", video_id="aaaaaaaaaaa")
    make_mp3(tmp_path / "geek" / "b.mp3", "Beta", "alpha band")
    make_mp3(tmp_path / "c.mp3", "Gamma", "Zed")
    entries = Library(tmp_path).scan(app_track("aaaaaaaaaaa"))
    paths = lambda **kw: sorted(e.path for e in filter_entries(entries, **kw))  # noqa: E731
    assert paths(query="ALPHA") == ["geek/a.mp3", "geek/b.mp3"]
    assert paths(query="zed", subfolder="") == ["c.mp3"]
    assert paths(query="alpha", source=SOURCE_APP) == ["geek/a.mp3"]
    assert paths(subfolder="geek", source=SOURCE_EXTERNAL) == ["geek/b.mp3"]
    assert paths(query="nothing") == []
    assert paths(query="Alpha Song") == ["geek/a.mp3"]


def test_cover_extraction_placeholder_and_limits(tmp_path, make_mp3):
    make_mp3(tmp_path / "with.mp3", "w", cover=JPEG)
    make_mp3(tmp_path / "without.mp3", "n")
    make_mp3(tmp_path / "huge.mp3", "h", cover=b"\xff" * (MAX_COVER_BYTES + 1))
    lib = Library(tmp_path)
    found = lib.cover("with.mp3")
    assert found is not None and found.data == JPEG and found.mime == "image/jpeg"
    assert lib.cover("without.mp3") is None
    assert lib.cover("huge.mp3") is None


@pytest.mark.parametrize(
    "bad", ["../x.mp3", "/etc/passwd", "a/../../x.mp3", "x.txt", "missing.mp3"]
)
def test_cover_rejects_bad_paths(tmp_path, bad):
    with pytest.raises(PathError):
        Library(tmp_path).cover(bad)


def test_performance_500_files(tmp_path, make_mp3):
    first = make_mp3(tmp_path / "f0.mp3", "T0", "A")
    for i in range(1, 500):
        (tmp_path / f"f{i}.mp3").write_bytes(first.read_bytes())
    lib = Library(tmp_path)
    start = time.perf_counter()
    assert len(lib.scan({})) == 500
    cold = time.perf_counter() - start
    start = time.perf_counter()
    lib.scan({})
    warm = time.perf_counter() - start
    assert cold < 2.0 and warm < 0.3
