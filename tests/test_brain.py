"""Integration tests for Brain — given/then format with respx-mocked httpx."""

import pytest
import respx
from httpx import Response

from core.brain import Brain, TurnResult


BASE_URL = "http://127.0.0.1:4096"
PASSWORD = "test-password"
SESSION_ID = "session-abc123"
MESSAGE_ID = "msg-xyz789"


@pytest.fixture
def brain() -> Brain:
    return Brain(base_url=BASE_URL, password=PASSWORD)


# — boundary: creates session on first send_turn —
@pytest.mark.asyncio
@respx.mock
async def test_given_first_turn_then_creates_session(brain):
    respx.post(f"{BASE_URL}/session").mock(
        return_value=Response(200, json={"id": SESSION_ID})
    )
    respx.post(f"{BASE_URL}/session/{SESSION_ID}/message").mock(
        return_value=Response(200, json={
            "info": {"id": MESSAGE_ID},
            "parts": [{"type": "text", "text": "Hello, sir."}],
        })
    )
    result = await brain.send_turn("Hello?")
    assert result.session_id == SESSION_ID
    assert result.text == "Hello, sir."


# — tautology trap: session is created exactly once —
@pytest.mark.asyncio
@respx.mock
async def test_given_two_turns_then_reuses_session(brain):
    session_route = respx.post(f"{BASE_URL}/session").mock(
        return_value=Response(200, json={"id": SESSION_ID})
    )
    message_route = respx.post(f"{BASE_URL}/session/{SESSION_ID}/message").mock(
        return_value=Response(200, json={
            "info": {"id": MESSAGE_ID},
            "parts": [{"type": "text", "text": "Yes, sir."}],
        })
    )
    await brain.send_turn("One")
    await brain.send_turn("Two")
    assert session_route.call_count == 1
    assert message_route.call_count == 2


# — false-positive guard: same session id returned both turns —
@pytest.mark.asyncio
@respx.mock
async def test_given_two_turns_then_both_have_same_session_id(brain):
    respx.post(f"{BASE_URL}/session").mock(
        return_value=Response(200, json={"id": SESSION_ID})
    )
    respx.post(f"{BASE_URL}/session/{SESSION_ID}/message").mock(
        return_value=Response(200, json={
            "info": {"id": MESSAGE_ID},
            "parts": [{"type": "text", "text": "Yes."}],
        })
    )
    result1 = await brain.send_turn("One")
    result2 = await brain.send_turn("Two")
    assert result1.session_id == result2.session_id


# — boundary: TurnResult.text joins all text parts —
@pytest.mark.asyncio
@respx.mock
async def test_given_multiple_text_parts_then_joined(brain):
    respx.post(f"{BASE_URL}/session").mock(
        return_value=Response(200, json={"id": SESSION_ID})
    )
    respx.post(f"{BASE_URL}/session/{SESSION_ID}/message").mock(
        return_value=Response(200, json={
            "info": {"id": MESSAGE_ID},
            "parts": [
                {"type": "text", "text": "Hello, "},
                {"type": "text", "text": "sir."},
            ],
        })
    )
    result = await brain.send_turn("Hi")
    assert result.text == "Hello, sir."


# — false-positive guard: non-text parts ignored in text field —
@pytest.mark.asyncio
@respx.mock
async def test_given_mixed_parts_then_only_text_joined(brain):
    respx.post(f"{BASE_URL}/session").mock(
        return_value=Response(200, json={"id": SESSION_ID})
    )
    respx.post(f"{BASE_URL}/session/{SESSION_ID}/message").mock(
        return_value=Response(200, json={
            "info": {"id": MESSAGE_ID},
            "parts": [
                {"type": "tool_call", "name": "get_time"},
                {"type": "text", "text": "It is 2pm, sir."},
            ],
        })
    )
    result = await brain.send_turn("What time is it?")
    assert result.text == "It is 2pm, sir."
    assert "tool_call" in [part["type"] for part in result.parts]


# — boundary: sends persona when provided —
@pytest.mark.asyncio
@respx.mock
async def test_given_persona_then_system_field_sent():
    persona_content = "You are JARVIS. Address user as sir."
    respx.post(f"{BASE_URL}/session").mock(
        return_value=Response(200, json={"id": SESSION_ID})
    )
    message_mock = respx.post(f"{BASE_URL}/session/{SESSION_ID}/message").mock(
        return_value=Response(200, json={
            "info": {"id": MESSAGE_ID},
            "parts": [{"type": "text", "text": "Yes, sir."}],
        })
    )
    with respx.mock:
        message_mock
        session_mock = respx.post(f"{BASE_URL}/session").mock(
            return_value=Response(200, json={"id": SESSION_ID})
        )
        message_mock = respx.post(f"{BASE_URL}/session/{SESSION_ID}/message").mock(
            return_value=Response(200, json={
                "info": {"id": MESSAGE_ID},
                "parts": [{"type": "text", "text": "Yes, sir."}],
            })
        )
    # Temporary file-based approach: write persona, test brain reads it
    import tempfile
    from pathlib import Path

    persona_file = Path(tempfile.mkstemp(suffix=".md")[1])
    persona_file.write_text(persona_content)

    try:
        respx.post(f"{BASE_URL}/session").mock(
            return_value=Response(200, json={"id": SESSION_ID})
        )
        persona_brain_message = respx.post(
            f"{BASE_URL}/session/{SESSION_ID}/message"
        ).mock(
            return_value=Response(200, json={
                "info": {"id": MESSAGE_ID},
                "parts": [{"type": "text", "text": "Yes, sir."}],
            })
        )
        persona_brain = Brain(
            base_url=BASE_URL,
            password=PASSWORD,
            persona_path=str(persona_file),
        )
        await persona_brain.send_turn("Hello")
        request_body = persona_brain_message.calls[0].request.read().decode()
        assert "system" in request_body
        assert persona_content in request_body
    finally:
        persona_file.unlink()


# — false-positive guard: no persona = no system field —
@pytest.mark.asyncio
@respx.mock
async def test_given_no_persona_then_no_system_field(brain):
    respx.post(f"{BASE_URL}/session").mock(
        return_value=Response(200, json={"id": SESSION_ID})
    )
    message_mock = respx.post(f"{BASE_URL}/session/{SESSION_ID}/message").mock(
        return_value=Response(200, json={
            "info": {"id": MESSAGE_ID},
            "parts": [{"type": "text", "text": "Hello."}],
        })
    )
    await brain.send_turn("test")
    request_body = message_mock.calls[0].request.read().decode()
    assert '"system"' not in request_body


# — boundary: abort sends correct request —
@pytest.mark.asyncio
@respx.mock
async def test_given_abort_then_posts_correct_endpoint(brain):
    respx.post(f"{BASE_URL}/session").mock(
        return_value=Response(200, json={"id": SESSION_ID})
    )
    respx.post(f"{BASE_URL}/session/{SESSION_ID}/message").mock(
        return_value=Response(200, json={
            "info": {"id": MESSAGE_ID},
            "parts": [{"type": "text", "text": "ok"}],
        })
    )
    abort_mock = respx.post(f"{BASE_URL}/session/{SESSION_ID}/abort").mock(
        return_value=Response(200, json=True)
    )
    await brain.send_turn("Test")
    await brain.abort()
    assert abort_mock.call_count == 1


# — tautology trap: abort without session is noop —
@pytest.mark.asyncio
@respx.mock
async def test_given_abort_before_session_then_no_request():
    brain = Brain(base_url=BASE_URL, password=PASSWORD)
    await brain.abort()
    # No session ID, abort silently — no HTTP call made.
    # If a call was made, httpx would have errored on the unknown route.
    # This test passes by not raising.


# — boundary: API errors propagate —
@pytest.mark.asyncio
@respx.mock
async def test_given_server_error_then_raises(brain):
    respx.post(f"{BASE_URL}/session").mock(
        return_value=Response(200, json={"id": SESSION_ID})
    )
    respx.post(f"{BASE_URL}/session/{SESSION_ID}/message").mock(
        return_value=Response(500, json={"error": "internal"})
    )
    with pytest.raises(Exception):
        await brain.send_turn("Hello")


# — false-positive guard: PartsWithoutText does NOT produce non-empty text —
@pytest.mark.asyncio
@respx.mock
async def test_given_no_text_parts_then_text_is_empty(brain):
    respx.post(f"{BASE_URL}/session").mock(
        return_value=Response(200, json={"id": SESSION_ID})
    )
    respx.post(f"{BASE_URL}/session/{SESSION_ID}/message").mock(
        return_value=Response(200, json={
            "info": {"id": MESSAGE_ID},
            "parts": [{"type": "tool_call", "name": "get_time"}],
        })
    )
    result = await brain.send_turn("What time?")
    assert result.text == ""


# — boundary: close disposes the client —
@pytest.mark.asyncio
@respx.mock
async def test_given_close_then_client_is_closed(brain):
    respx.post(f"{BASE_URL}/session").mock(
        return_value=Response(200, json={"id": SESSION_ID})
    )
    respx.post(f"{BASE_URL}/session/{SESSION_ID}/message").mock(
        return_value=Response(200, json={
            "info": {"id": MESSAGE_ID},
            "parts": [{"type": "text", "text": "ok"}],
        })
    )
    await brain.send_turn("Test")
    await brain.close()
    assert brain._client.is_closed


# — boundary: TurnResult has all fields —
@pytest.mark.asyncio
@respx.mock
async def test_given_response_then_turnresult_fields_populated(brain):
    respx.post(f"{BASE_URL}/session").mock(
        return_value=Response(200, json={"id": SESSION_ID})
    )
    respx.post(f"{BASE_URL}/session/{SESSION_ID}/message").mock(
        return_value=Response(200, json={
            "info": {"id": MESSAGE_ID},
            "parts": [{"type": "text", "text": "Done."}],
        })
    )
    result = await brain.send_turn("Test")
    assert result.session_id == SESSION_ID
    assert result.message_id == MESSAGE_ID
    assert result.text == "Done."
    assert isinstance(result.parts, list)
    assert len(result.parts) == 1
