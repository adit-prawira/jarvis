import logging
from collections.abc import AsyncIterator

import httpx

from domain.brain import Brain, TurnResult
from infrastructure.opencode.event_stream import Event, EventStream

logger = logging.getLogger(__name__)


class OpenCodeBrain(Brain):
    def __init__(
        self,
        base_url: str,
        password: str,
        agent: str = "jarvis",
        model: str | None = None,
        location: str | None = None,
    ) -> None:
        self._agent = agent
        self._model = model
        self._location = location
        self._session_id: str | None = None
        self._client = httpx.AsyncClient(
            base_url=base_url,
            auth=httpx.BasicAuth("opencode", password),
            timeout=httpx.Timeout(60.0),
        )

    async def send_turn(self, message: str) -> TurnResult:
        session_id = await self._resolve_session()
        chunks: list[str] = []
        assistant_message_id: str | None = None

        async for event in self._turn_events(session_id, message):
            if event.type == "session.step.started":
                assistant_message_id = event.data.get("data", {}).get("assistantMessageID")
            elif event.type == "session.text.delta":
                chunks.append(event.data.get("data", {}).get("delta", ""))

        return TurnResult(
            session_id=session_id,
            message_id=assistant_message_id,
            text="".join(chunks),
            parts=[],
        )

    async def stream_turn(self, message: str) -> AsyncIterator[str]:
        session_id = await self._resolve_session()
        async for event in self._turn_events(session_id, message):
            if event.type == "session.text.delta":
                yield event.data.get("data", {}).get("delta", "")

    async def abort(self) -> None:
        if self._session_id is None:
            return
        await self._client.post(f"/api/session/{self._session_id}/interrupt")

    async def close(self) -> None:
        await self._client.aclose()

    async def _resolve_session(self) -> str:
        if self._session_id is not None:
            return self._session_id

        payload: dict[str, object] = {"agent": self._agent}
        if self._model is not None:
            payload["model"] = self._model_ref(self._model)
        if self._location is not None:
            payload["location"] = {"directory": self._location}

        response = await self._client.post("/api/session", json=payload)
        response.raise_for_status()
        logger.info("session create raw response: %s", response.text)
        data = response.json()
        self._session_id = data["data"]["id"]
        assert self._session_id is not None, "session_id is expected to be defined"
        return self._session_id

    @staticmethod
    def _model_ref(model: str) -> dict[str, str]:
        provider_id, model_id = model.split("/", 1)
        return {"id": model_id, "providerID": provider_id}

    async def _turn_events(self, session_id: str, message: str) -> AsyncIterator[Event]:
        async with self._client.stream("GET", "/api/event") as event_stream:
            event_stream.raise_for_status()

            prompt_response = await self._client.post(
                f"/api/session/{session_id}/prompt",
                json={"text": message},
            )
            prompt_response.raise_for_status()
            logger.info("prompt raw response: %s", prompt_response.text)

            async for event in EventStream.parse_event(event_stream):
                if event.data.get("data", {}).get("sessionID") != session_id:
                    continue
                if event.type in ("session.step.started", "session.text.delta"):
                    yield event
                elif event.type in (
                    "session.execution.succeeded",
                    "session.execution.failed",
                ):
                    return
