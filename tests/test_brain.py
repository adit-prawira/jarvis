"""Integration tests for Brain — given/then format with respx-mocked httpx."""

import json

import httpx
import pytest
import respx
from httpx import HTTPStatusError, Response

from infrastructure.opencode.brain_client import OpenCodeBrain

BASE_URL = "http://127.0.0.1:4096"
PASSWORD = "test-password"
SESSION_ID = "session-abc123"
ASSISTANT_MESSAGE_ID = "msg-assistant-789"


@pytest.fixture
def brain() -> OpenCodeBrain:
    return OpenCodeBrain(base_url=BASE_URL, password=PASSWORD)


class _FakeAsyncStream(httpx.AsyncByteStream):
    def __init__(self, data: bytes) -> None:
        self._data = data

    def __aiter__(self):
        return self

    async def __anext__(self) -> bytes:
        if not self._data:
            raise StopAsyncIteration
        chunk = self._data[:64]
        self._data = self._data[64:]
        return chunk


def _sse_response(*lines: str) -> httpx.Response:
    return httpx.Response(200, stream=_FakeAsyncStream(("\n".join(lines)).encode()))


def _sse_line(event_type: str, data: dict) -> str:
    return "data: " + json.dumps({"id": "evt_1", "type": event_type, "data": data})


def _text_delta(session_id: str, delta: str) -> str:
    return _sse_line(
        "session.text.delta",
        {
            "sessionID": session_id,
            "assistantMessageID": ASSISTANT_MESSAGE_ID,
            "ordinal": 0,
            "delta": delta,
        },
    )


def _step_started(session_id: str) -> str:
    return _sse_line(
        "session.step.started",
        {
            "sessionID": session_id,
            "assistantMessageID": ASSISTANT_MESSAGE_ID,
            "agent": "jarvis",
            "model": {"id": "space-bunny", "providerID": "opencode-go"},
        },
    )


def _execution_succeeded(session_id: str) -> str:
    return _sse_line("session.execution.succeeded", {"sessionID": session_id})


def _execution_failed(session_id: str) -> str:
    return _sse_line("session.execution.failed", {"sessionID": session_id})


def _session_response(session_id: str) -> Response:
    return Response(
        200,
        json={
            "data": {
                "id": session_id,
                "agent": "jarvis",
                "cost": 0,
                "tokens": {
                    "input": 0,
                    "output": 0,
                    "reasoning": 0,
                    "cache": {"read": 0, "write": 0},
                },
                "time": {"created": 1, "updated": 1},
                "location": {"directory": "/workspace"},
            }
        },
    )


def _prompt_response() -> Response:
    return Response(
        200,
        json={
            "data": {
                "id": "msg_user_1",
                "sessionID": SESSION_ID,
                "type": "user",
                "payload": {"text": "Hello?"},
                "delivery": "steer",
            }
        },
    )


# — boundary: creates session on first send_turn —
@pytest.mark.asyncio
@respx.mock
async def test_given_first_turn_then_creates_session(brain):
    respx.post(f"{BASE_URL}/api/session").mock(return_value=_session_response(SESSION_ID))
    respx.post(f"{BASE_URL}/api/session/{SESSION_ID}/prompt").mock(return_value=_prompt_response())
    respx.get(f"{BASE_URL}/api/event").mock(
        return_value=_sse_response(
            _step_started(SESSION_ID),
            _text_delta(SESSION_ID, "Hello, sir."),
            _execution_succeeded(SESSION_ID),
        )
    )
    result = await brain.send_turn("Hello?")
    assert result.session_id == SESSION_ID
    assert result.text == "Hello, sir."


# — tautology trap: session is created exactly once —
@pytest.mark.asyncio
@respx.mock
async def test_given_two_turns_then_reuses_session(brain):
    session_route = respx.post(f"{BASE_URL}/api/session").mock(
        return_value=_session_response(SESSION_ID)
    )
    prompt_route = respx.post(f"{BASE_URL}/api/session/{SESSION_ID}/prompt").mock(
        return_value=_prompt_response()
    )
    respx.get(f"{BASE_URL}/api/event").mock(
        return_value=_sse_response(
            _text_delta(SESSION_ID, "Yes, sir."),
            _execution_succeeded(SESSION_ID),
        )
    )
    await brain.send_turn("One")
    await brain.send_turn("Two")
    assert session_route.call_count == 1
    assert prompt_route.call_count == 2


# — false-positive guard: same session id returned both turns —
@pytest.mark.asyncio
@respx.mock
async def test_given_two_turns_then_both_have_same_session_id(brain):
    respx.post(f"{BASE_URL}/api/session").mock(return_value=_session_response(SESSION_ID))
    respx.post(f"{BASE_URL}/api/session/{SESSION_ID}/prompt").mock(return_value=_prompt_response())
    respx.get(f"{BASE_URL}/api/event").mock(
        return_value=_sse_response(
            _text_delta(SESSION_ID, "Yes."),
            _execution_succeeded(SESSION_ID),
        )
    )
    result1 = await brain.send_turn("One")
    result2 = await brain.send_turn("Two")
    assert result1.session_id == result2.session_id


# — boundary: TurnResult.text joins all text deltas —
@pytest.mark.asyncio
@respx.mock
async def test_given_multiple_text_deltas_then_joined(brain):
    respx.post(f"{BASE_URL}/api/session").mock(return_value=_session_response(SESSION_ID))
    respx.post(f"{BASE_URL}/api/session/{SESSION_ID}/prompt").mock(return_value=_prompt_response())
    respx.get(f"{BASE_URL}/api/event").mock(
        return_value=_sse_response(
            _text_delta(SESSION_ID, "Hello, "),
            _text_delta(SESSION_ID, "sir."),
            _execution_succeeded(SESSION_ID),
        )
    )
    result = await brain.send_turn("Hi")
    assert result.text == "Hello, sir."


# — boundary: sends the model reference when configured —
@pytest.mark.asyncio
@respx.mock
async def test_given_model_then_model_ref_sent():
    brain_with_model = OpenCodeBrain(
        base_url=BASE_URL, password=PASSWORD, model="opencode-go/space-bunny"
    )
    session_mock = respx.post(f"{BASE_URL}/api/session").mock(
        return_value=_session_response(SESSION_ID)
    )
    respx.post(f"{BASE_URL}/api/session/{SESSION_ID}/prompt").mock(return_value=_prompt_response())
    respx.get(f"{BASE_URL}/api/event").mock(
        return_value=_sse_response(
            _text_delta(SESSION_ID, "ok"),
            _execution_succeeded(SESSION_ID),
        )
    )
    await brain_with_model.send_turn("Hello")
    request_body = json.loads(session_mock.calls[0].request.content)
    assert request_body["model"] == {"id": "space-bunny", "providerID": "opencode-go"}


# — boundary: sends the location when configured —
@pytest.mark.asyncio
@respx.mock
async def test_given_location_then_location_sent():
    project_path = "/Users/adityaprawira/Documents/projects/jarvis"
    brain_with_location = OpenCodeBrain(base_url=BASE_URL, password=PASSWORD, location=project_path)
    session_mock = respx.post(f"{BASE_URL}/api/session").mock(
        return_value=_session_response(SESSION_ID)
    )
    respx.post(f"{BASE_URL}/api/session/{SESSION_ID}/prompt").mock(return_value=_prompt_response())
    respx.get(f"{BASE_URL}/api/event").mock(
        return_value=_sse_response(
            _text_delta(SESSION_ID, "ok"),
            _execution_succeeded(SESSION_ID),
        )
    )
    await brain_with_location.send_turn("Hello")
    request_body = json.loads(session_mock.calls[0].request.content)
    assert request_body["location"] == {"directory": project_path}


# — boundary: abort sends correct endpoint —
@pytest.mark.asyncio
@respx.mock
async def test_given_abort_then_posts_correct_endpoint(brain):
    respx.post(f"{BASE_URL}/api/session").mock(return_value=_session_response(SESSION_ID))
    respx.post(f"{BASE_URL}/api/session/{SESSION_ID}/prompt").mock(return_value=_prompt_response())
    respx.get(f"{BASE_URL}/api/event").mock(
        return_value=_sse_response(
            _text_delta(SESSION_ID, "ok"),
            _execution_succeeded(SESSION_ID),
        )
    )
    abort_mock = respx.post(f"{BASE_URL}/api/session/{SESSION_ID}/interrupt").mock(
        return_value=Response(200, json={"interrupted": True})
    )
    await brain.send_turn("Test")
    await brain.abort()
    assert abort_mock.call_count == 1


# — tautology trap: abort without session is noop —
@pytest.mark.asyncio
@respx.mock
async def test_given_abort_before_session_then_no_request():
    brain = OpenCodeBrain(base_url=BASE_URL, password=PASSWORD)
    await brain.abort()


# — boundary: API errors propagate —
@pytest.mark.asyncio
@respx.mock
async def test_given_server_error_then_raises(brain):
    respx.post(f"{BASE_URL}/api/session").mock(
        return_value=Response(500, json={"error": "internal"})
    )
    with pytest.raises(HTTPStatusError):
        await brain.send_turn("Hello")


# — false-positive guard: no text deltas produces empty text —
@pytest.mark.asyncio
@respx.mock
async def test_given_no_text_deltas_then_text_is_empty(brain):
    respx.post(f"{BASE_URL}/api/session").mock(return_value=_session_response(SESSION_ID))
    respx.post(f"{BASE_URL}/api/session/{SESSION_ID}/prompt").mock(return_value=_prompt_response())
    respx.get(f"{BASE_URL}/api/event").mock(
        return_value=_sse_response(_execution_succeeded(SESSION_ID))
    )
    result = await brain.send_turn("What time?")
    assert result.text == ""


# — boundary: close disposes the client —
@pytest.mark.asyncio
@respx.mock
async def test_given_close_then_client_is_closed(brain):
    respx.post(f"{BASE_URL}/api/session").mock(return_value=_session_response(SESSION_ID))
    respx.post(f"{BASE_URL}/api/session/{SESSION_ID}/prompt").mock(return_value=_prompt_response())
    respx.get(f"{BASE_URL}/api/event").mock(
        return_value=_sse_response(
            _text_delta(SESSION_ID, "ok"),
            _execution_succeeded(SESSION_ID),
        )
    )
    await brain.send_turn("Test")
    await brain.close()
    assert brain._client.is_closed


# — boundary: TurnResult has all fields —
@pytest.mark.asyncio
@respx.mock
async def test_given_response_then_turnresult_fields_populated(brain):
    respx.post(f"{BASE_URL}/api/session").mock(return_value=_session_response(SESSION_ID))
    respx.post(f"{BASE_URL}/api/session/{SESSION_ID}/prompt").mock(return_value=_prompt_response())
    respx.get(f"{BASE_URL}/api/event").mock(
        return_value=_sse_response(
            _step_started(SESSION_ID),
            _text_delta(SESSION_ID, "Done."),
            _execution_succeeded(SESSION_ID),
        )
    )
    result = await brain.send_turn("Test")
    assert result.session_id == SESSION_ID
    assert result.message_id == ASSISTANT_MESSAGE_ID
    assert result.text == "Done."
    assert isinstance(result.parts, list)
    assert len(result.parts) == 0


# — stream: text deltas yield and the stream ends on execution.succeeded —
@pytest.mark.asyncio
@respx.mock
async def test_given_streamed_text_deltas_then_yields_until_execution_succeeded(brain):
    respx.post(f"{BASE_URL}/api/session").mock(return_value=_session_response(SESSION_ID))
    respx.post(f"{BASE_URL}/api/session/{SESSION_ID}/prompt").mock(return_value=_prompt_response())
    respx.get(f"{BASE_URL}/api/event").mock(
        return_value=_sse_response(
            _text_delta(SESSION_ID, "Hello, "),
            _text_delta(SESSION_ID, "sir."),
            _execution_succeeded(SESSION_ID),
        )
    )
    chunks = [chunk async for chunk in brain.stream_turn("Hello?")]
    assert chunks == ["Hello, ", "sir."]


# — filter: deltas for another session are ignored —
@pytest.mark.asyncio
@respx.mock
async def test_given_other_session_delta_then_ignored(brain):
    respx.post(f"{BASE_URL}/api/session").mock(return_value=_session_response(SESSION_ID))
    respx.post(f"{BASE_URL}/api/session/{SESSION_ID}/prompt").mock(return_value=_prompt_response())
    respx.get(f"{BASE_URL}/api/event").mock(
        return_value=_sse_response(
            _text_delta("session-other", "not mine"),
            _text_delta(SESSION_ID, "Hello, sir."),
            _execution_succeeded(SESSION_ID),
        )
    )
    chunks = [chunk async for chunk in brain.stream_turn("Hello?")]
    assert chunks == ["Hello, sir."]


# — stop: only our own session execution ends the stream —
@pytest.mark.asyncio
@respx.mock
async def test_given_other_session_execution_then_stream_continues(brain):
    respx.post(f"{BASE_URL}/api/session").mock(return_value=_session_response(SESSION_ID))
    respx.post(f"{BASE_URL}/api/session/{SESSION_ID}/prompt").mock(return_value=_prompt_response())
    respx.get(f"{BASE_URL}/api/event").mock(
        return_value=_sse_response(
            _execution_succeeded("session-other"),
            _text_delta(SESSION_ID, "still going."),
            _execution_succeeded(SESSION_ID),
        )
    )
    chunks = [chunk async for chunk in brain.stream_turn("Hello?")]
    assert chunks == ["still going."]


# — boundary: sends the message to prompt endpoint —
@pytest.mark.asyncio
@respx.mock
async def test_given_stream_turn_then_posts_prompt_with_text(brain):
    respx.post(f"{BASE_URL}/api/session").mock(return_value=_session_response(SESSION_ID))
    prompt_mock = respx.post(f"{BASE_URL}/api/session/{SESSION_ID}/prompt").mock(
        return_value=_prompt_response()
    )
    respx.get(f"{BASE_URL}/api/event").mock(
        return_value=_sse_response(_execution_succeeded(SESSION_ID))
    )
    _ = [chunk async for chunk in brain.stream_turn("Hello?")]
    request_body = json.loads(prompt_mock.calls[0].request.content)
    assert request_body["text"] == "Hello?"
