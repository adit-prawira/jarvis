"""Unit tests for SSE event stream parser — given/then format."""

import httpx
import pytest

from infrastructure.opencode.event_stream import Event, EventStream

parse = EventStream.parse_event


class _FakeAsyncStream(httpx.AsyncByteStream):
    def __init__(self, data: bytes) -> None:
        self._data = data

    def __aiter__(self):
        return self

    async def __anext__(self) -> bytes:
        if self._data:
            chunk = self._data[:64]
            self._data = self._data[64:]
            return chunk
        raise StopAsyncIteration


def _make_async_response(*lines: str) -> httpx.Response:
    text = "\n".join(lines)
    return httpx.Response(200, stream=_FakeAsyncStream(text.encode()))


# — boundary: parses message.updated event —
@pytest.mark.asyncio
async def test_given_message_updated_event_then_yields_correct_type():
    response = _make_async_response(
        'data: {"type": "message.updated", "message": {"id": "abc"}}',
    )
    events = [event async for event in parse(response)]
    assert len(events) == 1
    assert events[0].type == "message.updated"


# — boundary: parses session.idle event —
@pytest.mark.asyncio
async def test_given_session_idle_event_then_yields_idle():
    response = _make_async_response(
        'data: {"type": "session.idle"}',
    )
    events = [event async for event in parse(response)]
    assert len(events) == 1
    assert events[0].type == "session.idle"


# — boundary: parses session.error event —
@pytest.mark.asyncio
async def test_given_session_error_event_then_yields_error():
    response = _make_async_response(
        'data: {"type": "session.error", "error": "something broke"}',
    )
    events = [event async for event in parse(response)]
    assert len(events) == 1
    assert events[0].type == "session.error"


# — boundary: parses server.connected event —
@pytest.mark.asyncio
async def test_given_server_connected_event_then_yields_it():
    response = _make_async_response(
        'data: {"type": "server.connected"}',
    )
    events = [event async for event in parse(response)]
    assert len(events) == 1
    assert events[0].type == "server.connected"


# — boundary: [DONE] stops the stream —
@pytest.mark.asyncio
async def test_given_done_marker_then_stops_yielding():
    response = _make_async_response(
        'data: {"type": "message.updated", "message": {"id": "1"}}',
        "data: [DONE]",
        'data: {"type": "message.updated", "message": {"id": "2"}}',
    )
    events = [event async for event in parse(response)]
    assert len(events) == 1


# — false-positive guard: [DONE] yields no events —
@pytest.mark.asyncio
async def test_given_done_marker_then_stream_ends_not_errors():
    response = _make_async_response("data: [DONE]")
    events = [event async for event in parse(response)]
    assert len(events) == 0


# — boundary: unknown event types are skipped —
@pytest.mark.asyncio
async def test_given_unknown_event_type_then_skipped():
    response = _make_async_response(
        'data: {"type": "unknown.event", "payload": "ignored"}',
        'data: {"type": "session.idle"}',
    )
    events = [event async for event in parse(response)]
    assert len(events) == 1
    assert events[0].type == "session.idle"


# — false-positive guard: unknown type does NOT become an event —
@pytest.mark.asyncio
async def test_given_only_unknown_events_then_yields_nothing():
    response = _make_async_response(
        'data: {"type": "some.other.event"}',
        'data: {"type": "another.one"}',
    )
    events = [event async for event in parse(response)]
    assert len(events) == 0


# — boundary: JSON decode errors are skipped —
@pytest.mark.asyncio
async def test_given_invalid_json_then_skipped():
    response = _make_async_response(
        "data: not valid json",
        'data: {"type": "session.idle"}',
    )
    events = [event async for event in parse(response)]
    assert len(events) == 1
    assert events[0].type == "session.idle"


# — false-positive guard: invalid JSON does not crash —
@pytest.mark.asyncio
async def test_given_json_decode_error_then_does_not_raise():
    response = _make_async_response("data: {{{{broken")
    events = [event async for event in parse(response)]
    assert len(events) == 0


# — boundary: non-data lines are skipped —
@pytest.mark.asyncio
async def test_given_non_data_lines_then_skipped():
    response = _make_async_response(
        "event: ping",
        ": comment line",
        'data: {"type": "message.updated", "message": {"id": "x"}}',
    )
    events = [event async for event in parse(response)]
    assert len(events) == 1
    assert events[0].type == "message.updated"


# — false-positive guard: empty response produces no events —
@pytest.mark.asyncio
async def test_given_empty_response_then_yields_nothing():
    response = _make_async_response("")
    events = [event async for event in parse(response)]
    assert len(events) == 0


# — boundary: data payload is stored —
@pytest.mark.asyncio
async def test_given_event_then_data_dict_is_populated():
    response = _make_async_response(
        'data: {"type": "message.updated", "message": {"id": "msg1", "role": "assistant"}}',
    )
    events = [event async for event in parse(response)]
    assert len(events) == 1
    assert events[0].data["message"]["id"] == "msg1"
    assert events[0].data["message"]["role"] == "assistant"


# — tautology trap: data field defaults to empty dict —
def test_event_dataclass_defaults():
    event = Event(type="session.idle")
    assert event.data == {}
    assert event.type == "session.idle"


# — boundary: multiple events in order —
@pytest.mark.asyncio
async def test_given_multiple_events_then_yields_all_in_order():
    response = _make_async_response(
        'data: {"type": "server.connected"}',
        'data: {"type": "message.updated", "message": {"id": "a"}}',
        'data: {"type": "session.idle"}',
    )
    events = [event async for event in parse(response)]
    assert len(events) == 3
    assert events[0].type == "server.connected"
    assert events[1].type == "message.updated"
    assert events[2].type == "session.idle"
