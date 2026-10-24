from webmusicfolder.resolver import resolve_links

PL = "https://www.youtube.com/playlist?list=PLabcdef123456"
VID = "https://youtu.be/dQw4w9WgXcQ"


def pl_entries(n, prefix="p"):
    return [{"id": f"{prefix}{i:010d}", "title": f"T{i}"} for i in range(n)]


async def test_single_video_needs_no_runner(fake_runner):
    res = await resolve_links(VID, fake_runner())
    assert [(link.kind, link.error) for link in res.links] == [("video", None)]
    assert res.unique_items()[0].video_id == "dQw4w9WgXcQ"
    assert res.unique_items()[0].url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


async def test_playlist_expands_and_counts_skipped(fake_runner):
    entries = pl_entries(10) + [{"id": "gone0000000", "skip": "private"}]
    res = await resolve_links(PL, fake_runner(flat={PL: entries}))
    link = res.links[0]
    assert (link.kind, len(link.items), link.skipped, link.error) == ("playlist", 10, 1, None)
    assert link.items[3].title == "T3"


async def test_unavailable_playlist_reports_error(fake_runner):
    res = await resolve_links(PL, fake_runner(flat={}))
    assert res.links[0].error and res.links[0].items == []


async def test_mixed_batch_with_invalid_and_duplicates(fake_runner):
    text = "\n".join(
        [
            VID,
            "https://example.com/x",
            "",
            "  ",
            PL,
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=5",
            "garbage",
        ]
    )
    res = await resolve_links(text, fake_runner(flat={PL: pl_entries(10)}))
    kinds = [link.kind for link in res.links]
    assert kinds == ["video", "invalid", "playlist", "video", "invalid"]
    assert "YouTube" in res.links[1].error
    assert len(res.unique_items()) == 11


async def test_playlist_overlap_with_video_is_deduplicated(fake_runner):
    entries = [{"id": "dQw4w9WgXcQ", "title": "x"}, *pl_entries(2)]
    res = await resolve_links(f"{VID}\n{PL}", fake_runner(flat={PL: entries}))
    assert len(res.unique_items()) == 3
