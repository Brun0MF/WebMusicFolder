import pytest

from webmusicfolder.errors import DownloadError
from webmusicfolder.search import QueryError, clean_query, search

IDS = [f"vid{n:08d}" for n in range(12)]
TABLE = {
    "daft punk": [
        {"id": IDS[n], "title": f"T{n}", "channel": "Ch", "duration_s": 100 + n} for n in range(12)
    ],
    "-dash": [{"id": IDS[0], "title": "Dash"}],
    "dupes": [
        {"id": IDS[0], "title": "A"},
        {"id": IDS[0], "title": "A"},
        {"id": "bad id!", "title": "x"},
    ],
}


def test_clean_query():
    assert clean_query("  daft   punk ") == "daft punk"
    for bad in ("", "   ", "x" * 201, "a\x00b"):
        with pytest.raises(QueryError):
            clean_query(bad)


async def test_returns_at_most_ten_results_with_rebuilt_urls(fake_runner):
    found = await search("daft punk", fake_runner(search=TABLE))
    assert len(found) == 10
    assert found[0].url == f"https://www.youtube.com/watch?v={IDS[0]}"
    assert (found[0].title, found[0].channel, found[0].duration_s) == ("T0", "Ch", 100)


async def test_query_starting_with_a_dash_is_not_an_option(fake_runner):
    assert [r.title for r in await search("-dash", fake_runner(search=TABLE))] == ["Dash"]


async def test_duplicates_and_invalid_ids_are_dropped(fake_runner):
    assert [r.video_id for r in await search("dupes", fake_runner(search=TABLE))] == [IDS[0]]


async def test_runner_failure_raises_download_error(fake_runner):
    with pytest.raises(DownloadError):
        await search("unknown", fake_runner(search=TABLE))
