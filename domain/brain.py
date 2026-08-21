from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class TurnResult:
    """The outcome of one conversation turn."""

    session_id: str
    message_id: str | None
    text: str
    parts: list[dict[str, Any]]


class Brain(Protocol):
    """Conversation-engine port. Implemented by OpenCodeBrain over opencode serve."""

    async def send_turn(self, message: str) -> TurnResult: ...

    def stream_turn(self, message: str) -> AsyncIterator[str]: ...

    async def abort(self) -> None: ...

    async def close(self) -> None: ...
