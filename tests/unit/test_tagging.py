import shutil

from mutagen.id3 import ID3
from mutagen.mp3 import MP3

from webmusicfolder import tagging

COVER = b"\xff\xd8\xff\xe0cover\xff\xd9"


def test_write_and_read_back(sample_mp3, tmp_path):
    target = tmp_path / "a.mp3"
    shutil.copy(sample_mp3, target)
    tagging.write_tags(target, "Song", "Band - Topic", "dQw4w9WgXcQ", "https://y/x", COVER)

    info = tagging.read_tags(target)
    assert info.title == "Song"
    assert info.artist == "Band"
    assert info.video_id == "dQw4w9WgXcQ"
    assert info.url == "https://y/x"
    assert info.has_cover
    assert info.duration_s == 1
    assert ID3(target).version[:2] == (2, 4)
    assert MP3(target).tags.getall("APIC")[0].data == COVER
    assert tagging.read_video_id(target) == "dQw4w9WgXcQ"


def test_rewrite_replaces_old_frames(sample_mp3, tmp_path):
    target = tmp_path / "a.mp3"
    shutil.copy(sample_mp3, target)
    tagging.write_tags(target, "One", "A", "aaaaaaaaaaa", "u1", COVER)
    tagging.write_tags(target, "Two", "B", "bbbbbbbbbbb", "u2", None)
    info = tagging.read_tags(target)
    assert (info.title, info.artist, info.video_id) == ("Two", "B", "bbbbbbbbbbb")
    assert not info.has_cover
    assert len(ID3(target).getall("TIT2")) == 1


def test_unicode_and_clean_artist():
    assert tagging.clean_artist("  Daft Punk - Topic ") == "Daft Punk"
    assert tagging.clean_artist("Topic") == "Topic"


def test_read_video_id_untagged_or_broken(sample_mp3, tmp_path):
    plain = tmp_path / "plain.mp3"
    shutil.copy(sample_mp3, plain)
    assert tagging.read_video_id(plain) is None
    broken = tmp_path / "broken.mp3"
    broken.write_bytes(b"not an mp3")
    assert tagging.read_video_id(broken) is None
