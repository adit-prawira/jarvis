import asyncio

from domain.senses.mouth import Mouth


class SayMouth(Mouth):
    def __init__(self, voice: str = "Daniel") -> None:
        self._voice = voice
        self._process: asyncio.subprocess.Process | None = None

    async def speak(self, text: str) -> None:
        self._process = await asyncio.create_subprocess_exec(
            "say",
            "-v",
            self._voice,
            text,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await self._process.wait()

    async def stop(self) -> None:
        if self._process is None or self._process.returncode is not None:
            return
        self._process.terminate()
        try:
            await asyncio.wait_for(self._process.wait(), timeout=1.0)
        except TimeoutError:
            self._process.kill()
