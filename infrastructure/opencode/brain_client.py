from collections.abc import AsyncIterator
from typing import Any

import httpx

from domain.brain import Brain, TurnResult
from infrastructure.opencode.event_stream import EventStream


class OpenCodeBrain(Brain):
    """Concrete Brain adapter over opencode serve's synchronous HTTP API."""

    def __init__(
        self,
        base_url: str,
        password: str,
        agent: str = "jarvis",
    ) -> None:
        self._agent = agent
        self._session_id: str | None = None
        self._client = httpx.AsyncClient(
            base_url=base_url,
            auth=httpx.BasicAuth("opencode", password),
            timeout=httpx.Timeout(60.0),
        )

    async def send_turn(self, message: str) -> TurnResult:
        session_id = await self._resolve_session()
        payload: dict[str, Any] = {
            "parts": [{"type": "text", "text": message}],
            "agent": self._agent,
        }

        response = await self._client.post(f"/session/{session_id}/message", json=payload)
        response.raise_for_status()
        data = response.json()
        parts = data.get("parts", [])
        text = "".join(part.get("text", "") for part in parts if part.get("type") == "text")

        return TurnResult(
            session_id=session_id,
            message_id=data.get("info", {}).get("id"),
            text=text,
            parts=parts,
        )

    async def stream_turn(self, message: str) -> AsyncIterator[str]:
        session_id = await self._resolve_session()
        async with self._client.stream("GET", "/event") as event_stream:
            event_stream.raise_for_status()
            payload: dict[str, Any] = {
                "parts": [{"type": "text", "text": message}],
                "agent": self._agent,
            }
            prompt_response = await self._client.post(
                f"/session/{session_id}/prompt_async", json=payload
            )
            prompt_response.raise_for_status()
            reasoning_part_ids: set[str] = set()

            async for event in EventStream.parse_event(event_stream):
                should_process_event = (
                    event.type == "message.part.updated"
                    or event.type == "message.part.delta"
                    or event.type == "session.idle"
                )
                if not should_process_event:
                    continue

                if event.type == "message.part.updated":
                    properties = event.data.get("properties", {})
                    part = properties.get("part", {})
                    is_jarvis_session = part.get("sessionID") == session_id
                    is_reasoning = part.get("type") == "reasoning"
                    should_add_reasoning_ids = is_jarvis_session and is_reasoning
                    if not should_add_reasoning_ids:
                        continue
                    reasoning_part_ids.add(part.get("id"))
                elif event.type == "message.part.delta":
                    properties = event.data.get("properties", {})
                    is_jarvis_session = properties.get("sessionID") == session_id
                    is_reasoning = properties.get("partID") in reasoning_part_ids
                    should_process_response_text_chunk = is_jarvis_session and not is_reasoning
                    if not should_process_response_text_chunk:
                        continue

                    response_text_chunk = properties.get("delta")
                    if not response_text_chunk:
                        continue
                    yield response_text_chunk
                elif event.type == "session.idle":
                    properties = event.data.get("properties", {})
                    is_jarvis_session = properties.get("sessionID") == session_id
                    if is_jarvis_session:
                        return

    async def abort(self) -> None:
        if self._session_id is None:
            return
        await self._client.post(f"/session/{self._session_id}/abort")

    async def close(self) -> None:
        await self._client.aclose()

    async def _resolve_session(self) -> str:
        if self._session_id is not None:
            return self._session_id

        response = await self._client.post("/session")
        response.raise_for_status()
        data = response.json()
        self._session_id = data.get("id", "")
        assert self._session_id is not None, "session_id is expected to be defined"
        return self._session_id
