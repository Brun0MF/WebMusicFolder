import asyncio
import errno
from pathlib import Path

import pytest

from webmusicfolder import downloader, tagging
from webmusicfolder.downloader import DownloadContext, download_one
from webmusicfolder.errors import DownloadError
from webmusicfolder.models import QueueItem

ID_A = "aaaaaaaaaaa"
ID_B = "bbbbbbbbbbb"


def make_item(video_id=ID_A, subfolder="", item_id=None) -> QueueItem:
    return QueueItem(
        id=item_id or f"item-{video_id}",
        video_id=video_id,
        url=f"https://www.youtube.com/watch?v={video_id}",
        title="",
        subfolder=subfolder,
        added_at="2026-10-24T00:00:00Z",
    )


@pytest.fixture
def ctx(tmp_path, fake_runner):
    def build(**kw):
        return DownloadContext(
            music_dir=tmp_path / "music",
            tmp_root=tmp_path / "tmp",
            runner=fake_runner(**kw),
        )

    (tmp_path / "music").mkdir()
    return build


async def test_success_tags_and_places_file(ctx):
    c = ctx(titles={ID_A: "Great Song"})
    track = await download_one(c, make_item(subfolder="geek"), "v0")
    final = c.music_dir / "geek" / "Great Song.mp3"
    assert final.is_file()
    assert track.relpath == "geek/Great Song.mp3"
    assert track.artist == "Some Artist"
    info = tagging.read_tags(final)
    assert (info.title, info.video_id, info.has_cover) == ("Great Song", ID_A, True)
    assert not any(c.tmp_root.glob("*"))


async def test_same_title_different_video_gets_id_suffix(ctx):
    c = ctx(titles={ID_A: "Intro", ID_B: "Intro"})
    first = await download_one(c, make_item(ID_A), "v0")
    second = await download_one(c, make_item(ID_B), "v0")
    assert first.relpath == "Intro.mp3"
    assert second.relpath == f"Intro [{ID_B}].mp3"


async def test_redownload_same_video_reuses_name(ctx):
    c = ctx(titles={ID_A: "Intro"})
    await download_one(c, make_item(ID_A), "v0")
    again = await download_one(c, make_item(ID_A), "v0")
    assert again.relpath == "Intro.mp3"
    assert sorted(p.name for p in c.music_dir.iterdir()) == ["Intro.mp3"]


async def test_target_untouched_while_downloading(ctx):
    c = ctx(scenarios={ID_A: "slow:1.0"})
    task = asyncio.create_task(download_one(c, make_item(subfolder="geek"), "v0"))
    await asyncio.sleep(0.5)
    assert not task.done()
    assert list(c.music_dir.rglob("*")) == []
    await task
    assert len(list(c.music_dir.rglob("*.mp3"))) == 1


async def test_runner_error_leaves_library_empty_and_cleans_tmp(ctx):
    c = ctx(scenarios={ID_A: "error:private"})
    with pytest.raises(DownloadError) as exc:
        await download_one(c, make_item(), "v0")
    assert exc.value.code == "private"
    assert list(c.music_dir.rglob("*")) == []
    assert not any(c.tmp_root.glob("*"))


async def test_cancel_cleans_tmp(ctx):
    c = ctx(scenarios={ID_A: "hang"})
    task = asyncio.create_task(download_one(c, make_item(), "v0"))
    await asyncio.sleep(0.5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not any(c.tmp_root.glob("*"))


async def test_bad_subfolder_is_rejected_before_writing(ctx):
    c = ctx()
    with pytest.raises(DownloadError):
        await download_one(c, make_item(subfolder="../evil"), "v0")
    assert list(c.music_dir.parent.glob("evil*")) == []


async def test_symlinked_subfolder_outside_music_is_rejected(ctx, tmp_path):
    c = ctx()
    outside = tmp_path / "outside"
    outside.mkdir()
    (c.music_dir / "link").symlink_to(outside)
    with pytest.raises(DownloadError):
        await download_one(c, make_item(subfolder="link"), "v0")
    assert list(outside.iterdir()) == []


async def test_disk_full_maps_to_code(ctx, monkeypatch):
    def boom(src, dest):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(downloader, "atomic_move", boom)
    with pytest.raises(DownloadError) as exc:
        await download_one(ctx(), make_item(), "v0")
    assert exc.value.code == "disk_full"


def test_atomic_move_cross_device_fallback(tmp_path, monkeypatch):
    src = tmp_path / "src.mp3"
    src.write_bytes(b"data")
    dest = tmp_path / "dest.mp3"
    real_replace = downloader.os.replace
    calls = []

    def fake_replace(a, b):
        calls.append((Path(a).name, Path(b).name))
        if Path(a) == src:
            raise OSError(errno.EXDEV, "cross-device")
        real_replace(a, b)

    monkeypatch.setattr(downloader.os, "replace", fake_replace)
    downloader.atomic_move(src, dest)
    assert dest.read_bytes() == b"data"
    assert not src.exists()
    assert not list(tmp_path.glob(".*"))


async def test_existing_track_file_detects_by_tag(ctx):
    c = ctx(titles={ID_A: "Intro"})
    await download_one(c, make_item(ID_A), "v0")
    found = downloader.existing_track_file(c.music_dir, "", ID_A, "Intro")
    assert found == (c.music_dir / "Intro.mp3").resolve()
    assert downloader.existing_track_file(c.music_dir, "", ID_B, "Intro") is None


async def test_redownload_replaces_file_only_when_new_one_is_ready(ctx):
    c = ctx(titles={ID_A: "Intro"}, scenarios={})
    first = await download_one(c, make_item(ID_A, "geek"), "v0")
    old = c.music_dir / first.relpath
    old_bytes = old.read_bytes()

    slow = ctx(titles={ID_A: "Intro changed"}, scenarios={ID_A: "slow:1.0"})
    task = asyncio.create_task(
        download_one(slow, make_item(ID_A, "geek"), "v0", replace_relpath=first.relpath)
    )
    await asyncio.sleep(0.5)
    assert not task.done()
    assert old.read_bytes() == old_bytes
    again = await task
    # The file keeps its path even though the title changed.
    assert again.relpath == first.relpath
    assert sorted(p.name for p in (c.music_dir / "geek").iterdir()) == ["Intro.mp3"]
    assert tagging.read_tags(old).title == "Intro changed"


async def test_replace_relpath_for_another_video_is_ignored(ctx):
    c = ctx(titles={ID_A: "Intro", ID_B: "Other"})
    first = await download_one(c, make_item(ID_A), "v0")
    other = await download_one(c, make_item(ID_B), "v0", replace_relpath=first.relpath)
    assert other.relpath == "Other.mp3"
    assert tagging.read_video_id(c.music_dir / "Intro.mp3") == ID_A
