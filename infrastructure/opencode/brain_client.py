from typing import Any

import httpx

from domain.brain import Brain, TurnResult


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

        response = await self._client.post(
            f"/session/{session_id}/message", json=payload
        )
        response.raise_for_status()
        data = response.json()
        parts = data.get("parts", [])
        text = "".join(
            part.get("text", "") for part in parts if part.get("type") == "text"
        )

        return TurnResult(
            session_id=session_id,
            message_id=data.get("info", {}).get("id"),
            text=text,
            parts=parts,
        )

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
