import httpx 
from dataclasses import dataclass 
from typing import Any
from pathlib import Path 

@dataclass
class TurnResult:
    session_id: str 
    message_id: str 
    text: str 
    parts: list[dict[str, Any]]

class Brain:
    _base_url: str 
    _session_id: str | None = None
    _client: httpx.AsyncClient
    _persona: str | None = None

    def __init__(self, base_url:str, password: str, persona_path: str | None = None) -> None: 
        self._base_url = base_url
        if persona_path:
            self._persona = Path(persona_path).read_text()
        self._client = httpx.AsyncClient(
            base_url=self._base_url, 
            auth=httpx.BasicAuth("opencode", password),
            timeout=httpx.Timeout(60.0)
        )

    async def send_turn(self, message: str) -> TurnResult:
        session_id = await self._resolve_session()
        payload: dict[str, Any] = {
            "parts": [{"type": "text", "text": message }]
        }
        if self._persona: 
            payload["system"] = self._persona

        response = await self._client.post(f"/session/{session_id}/message", json=payload)

        response.raise_for_status()
        data = response.json()
        parts = data.get("parts", [])

        text = "".join([part.get("text", "") for part in parts if part.get("type") == "text"])
        return TurnResult(
            session_id=session_id, 
            message_id=data.get("info", {}).get("id", None),
            text=text, 
            parts=parts
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

