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


# — boundary: parses V2 session.text.delta event —
@pytest.mark.asyncio
async def test_given_v2_text_delta_event_then_yields_it():
    response = _make_async_response(
        'data: {"id":"evt_1","type":"session.text.delta",'
        '"data":{"sessionID":"ses_1","assistantMessageID":"msg_1","ordinal":0,"delta":"Hello"}}',
    )
    events = [event async for event in parse(response)]
    assert len(events) == 1
    assert events[0].type == "session.text.delta"
    assert events[0].data["data"]["delta"] == "Hello"


# — boundary: parses V2 session.execution.succeeded event —
@pytest.mark.asyncio
async def test_given_v2_execution_succeeded_event_then_yields_it():
    response = _make_async_response(
        'data: {"id":"evt_2","type":"session.execution.succeeded","data":{"sessionID":"ses_1"}}',
    )
    events = [event async for event in parse(response)]
    assert len(events) == 1
    assert events[0].type == "session.execution.succeeded"
    assert events[0].data["data"]["sessionID"] == "ses_1"


# — boundary: parses V2 session.step.started event —
@pytest.mark.asyncio
async def test_given_v2_step_started_event_then_yields_it():
    response = _make_async_response(
        'data: {"id":"evt_3","type":"session.step.started",'
        '"data":{"sessionID":"ses_1","assistantMessageID":"msg_1","agent":"jarvis"}}',
    )
    events = [event async for event in parse(response)]
    assert len(events) == 1
    assert events[0].type == "session.step.started"
    assert events[0].data["data"]["assistantMessageID"] == "msg_1"


# — boundary: heartbeat lines are ignored —
@pytest.mark.asyncio
async def test_given_heartbeat_line_then_ignored():
    response = _make_async_response(
        ": heartbeat",
        'data: {"id":"evt_1","type":"session.text.delta",'
        '"data":{"sessionID":"ses_1","assistantMessageID":"msg_1","ordinal":0,"delta":"Hello"}}',
    )
    events = [event async for event in parse(response)]
    assert len(events) == 1
    assert events[0].type == "session.text.delta"


# — boundary: JSON decode errors are skipped —
@pytest.mark.asyncio
async def test_given_invalid_json_then_skipped():
    response = _make_async_response(
        "data: not valid json",
        'data: {"id":"evt_1","type":"session.text.delta",'
        '"data":{"sessionID":"ses_1","assistantMessageID":"msg_1","ordinal":0,"delta":"Hello"}}',
    )
    events = [event async for event in parse(response)]
    assert len(events) == 1
    assert events[0].type == "session.text.delta"


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
        'data: {"id":"evt_1","type":"session.text.delta",'
        '"data":{"sessionID":"ses_1","assistantMessageID":"msg_1","ordinal":0,"delta":"Hello"}}',
    )
    events = [event async for event in parse(response)]
    assert len(events) == 1
    assert events[0].type == "session.text.delta"


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
        'data: {"id":"evt_1","type":"session.text.delta",'
        '"data":{"sessionID":"ses_1","assistantMessageID":"msg_1","ordinal":0,"delta":"Hello"}}',
    )
    events = [event async for event in parse(response)]
    assert len(events) == 1
    assert events[0].data["id"] == "evt_1"
    assert events[0].data["data"]["sessionID"] == "ses_1"


# — tautology trap: data field defaults to empty dict —
def test_event_dataclass_defaults():
    event = Event(type="session.text.delta")
    assert event.data == {}
    assert event.type == "session.text.delta"


# — boundary: multiple V2 events in order —
@pytest.mark.asyncio
async def test_given_multiple_v2_events_then_yields_all_in_order():
    response = _make_async_response(
        'data: {"id":"evt_1","type":"server.connected","data":{}}',
        'data: {"id":"evt_2","type":"session.text.delta",'
        '"data":{"sessionID":"ses_1","assistantMessageID":"msg_1","ordinal":0,"delta":"Hello"}}',
        'data: {"id":"evt_3","type":"session.execution.succeeded","data":{"sessionID":"ses_1"}}',
    )
    events = [event async for event in parse(response)]
    assert len(events) == 3
    assert events[0].type == "server.connected"
    assert events[1].type == "session.text.delta"
    assert events[2].type == "session.execution.succeeded"
