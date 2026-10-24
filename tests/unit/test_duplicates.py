from webmusicfolder.duplicates import KIND_EXISTS, KIND_QUEUED, find_duplicates
from webmusicfolder.models import STATUS_DONE, STATUS_DOWNLOADING, QueueItem, Track


def track(video_id, relpath):
    return Track(video_id, "u", "T " + video_id, "A", 1, "", relpath, "2026-10-24T00:00:00Z", "v0")


def queued(video_id, status="queued"):
    return QueueItem("i" + video_id, video_id, "u", "Q", "", "2026-10-24T00:00:00Z", status=status)


def test_present_file_is_a_duplicate(tmp_path):
    (tmp_path / "geek").mkdir()
    (tmp_path / "geek" / "a.mp3").write_bytes(b"x")
    found = find_duplicates(
        tmp_path, {"aaaaaaaaaaa": track("aaaaaaaaaaa", "geek/a.mp3")}, [], ["aaaaaaaaaaa"]
    )
    assert found["aaaaaaaaaaa"].kind == KIND_EXISTS
    assert found["aaaaaaaaaaa"].relpath == "geek/a.mp3"


def test_missing_file_is_treated_as_new(tmp_path):
    found = find_duplicates(
        tmp_path, {"aaaaaaaaaaa": track("aaaaaaaaaaa", "gone.mp3")}, [], ["aaaaaaaaaaa"]
    )
    assert found == {}


def test_unknown_video_and_external_files_are_not_duplicates(tmp_path):
    # An external file exists on disk but has no Track in the state.
    (tmp_path / "ext.mp3").write_bytes(b"x")
    assert find_duplicates(tmp_path, {}, [], ["aaaaaaaaaaa"]) == {}


def test_queued_and_downloading_are_reported_as_in_queue(tmp_path):
    queue = [
        queued("aaaaaaaaaaa"),
        queued("bbbbbbbbbbb", STATUS_DOWNLOADING),
        queued("ccccccccccc", STATUS_DONE),
    ]
    found = find_duplicates(tmp_path, {}, queue, ["aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"])
    assert {k: v.kind for k, v in found.items()} == {
        "aaaaaaaaaaa": KIND_QUEUED,
        "bbbbbbbbbbb": KIND_QUEUED,
    }


def test_relpath_escaping_the_music_dir_is_ignored(tmp_path):
    outside = tmp_path / "outside.mp3"
    outside.write_bytes(b"x")
    music = tmp_path / "music"
    music.mkdir()
    found = find_duplicates(
        music, {"aaaaaaaaaaa": track("aaaaaaaaaaa", "../outside.mp3")}, [], ["aaaaaaaaaaa"]
    )
    assert found == {}
