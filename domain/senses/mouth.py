from typing import Protocol


class Mouth(Protocol):
    """Voice-output port. Speaks complete sentence aloud"""

    async def speak(self, text: str) -> None: ...
    async def stop(self) -> None: ...
