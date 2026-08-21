import asyncio
import os

from dotenv import load_dotenv

from application.assistant import Assistant
from domain.senses.mouth import Mouth
from domain.senses.silence_detector import SilenceDetector
from infrastructure.opencode.brain_client import OpenCodeBrain
from infrastructure.sense.mlx_whisper_transcriber import MlxWhisperTranscriber
from infrastructure.sense.openwakeword_ear import (
    SAMPLE_RATE,
    OpenWakeWordDetector,
    OpenWakeWordEar,
)


class ConsoleMouth(Mouth):
    async def speak(self, text: str) -> None:
        print(text)

    async def stop(self) -> None:
        pass


def main() -> None:
    load_dotenv()
    ear = OpenWakeWordEar(
        detector=OpenWakeWordDetector(),
        transcriber=MlxWhisperTranscriber(),
        silence_detector=SilenceDetector(
            sample_rate=SAMPLE_RATE,
            silence_threshold=300.0,
            silence_duration=1.5,
        ),
    )
    brain = OpenCodeBrain(
        base_url="http://127.0.0.1:4096", password=os.environ["OPENCODE_SERVER_PASSWORD"]
    )
    asyncio.run(Assistant(ear=ear, brain=brain, mouth=ConsoleMouth()).run())


if __name__ == "__main__":
    main()
