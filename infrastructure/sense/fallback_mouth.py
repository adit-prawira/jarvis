from domain.senses.mouth import Mouth


class FallbackMouth(Mouth):
    def __init__(self, primary: Mouth, fallback: Mouth) -> None:
        self._primary = primary
        self._fallback = fallback

    async def speak(self, text: str) -> None:
        try:
            await self._primary.speak(text)
        except Exception:
            await self._fallback.speak(text)

    async def stop(self) -> None:
        await self._primary.stop()
        await self._fallback.stop()
