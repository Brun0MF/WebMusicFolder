import asyncio

import pytest

from webmusicfolder.events import EventBus, event_stream, format_sse


def test_publish_without_subscribers_keeps_nothing():
    bus = EventBus()
    bus.publish("item", {"id": "1"})
    assert not bus.has_subscribers


async def test_fan_out_to_all_subscribers_in_order():
    bus = EventBus()
    a, b = bus.subscribe(), bus.subscribe()
    bus.publish("item", {"n": 1})
    bus.publish("item", {"n": 2})
    for sub in (a, b):
        assert await sub.get(1) == ("item", {"n": 1})
        assert await sub.get(1) == ("item", {"n": 2})


async def test_slow_client_is_dropped_and_others_unaffected():
    bus = EventBus(queue_size=2)
    slow, fast = bus.subscribe(), bus.subscribe()
    for n in range(5):
        bus.publish("item", {"n": n})
        # Only the fast client keeps up.
        await fast.get(1)
    assert slow.ended and not fast.ended
    assert bus.has_subscribers
    # The slow client still drains what it had, then the stream ends.
    assert await slow.get(1) == ("item", {"n": 0})
    assert await slow.get(1) == ("item", {"n": 1})
    with pytest.raises(StopAsyncIteration):
        await slow.get(1)


async def test_get_times_out_with_none():
    sub = EventBus().subscribe()
    assert await sub.get(0.01) is None


async def test_close_ends_streams_and_late_subscribers():
    bus = EventBus()
    sub = bus.subscribe()
    bus.close()
    with pytest.raises(StopAsyncIteration):
        await sub.get(1)
    late = bus.subscribe()
    assert late.ended


async def test_stream_sends_snapshot_events_and_keepalive():
    bus = EventBus()

    async def snapshot():
        return {"items": []}

    stream = event_stream(bus, snapshot, keepalive_s=0.05)
    assert await anext(stream) == format_sse("snapshot", {"items": []})
    assert await anext(stream) == ": keepalive\n\n"
    bus.publish("item", {"id": "x"})
    assert await anext(stream) == format_sse("item", {"id": "x"})
    bus.close()
    assert [chunk async for chunk in stream] == []
    assert not bus.has_subscribers


async def test_stream_unsubscribes_when_the_client_goes_away():
    bus = EventBus()

    async def snapshot():
        return {}

    stream = event_stream(bus, snapshot)
    await anext(stream)
    assert bus.has_subscribers
    await stream.aclose()
    assert not bus.has_subscribers
    await asyncio.sleep(0)
