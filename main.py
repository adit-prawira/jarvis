import asyncio
import os

from dotenv import load_dotenv

from application.assistant import Assistant
from domain.senses.interrupt_detector import InterruptDetector
from domain.senses.silence_detector import SilenceDetector
from domain.text.interrupt_phrases import InterruptPhrases
from infrastructure.opencode.brain_client import OpenCodeBrain
from infrastructure.sense.edge_tts_mouth import EdgeTtsMouth
from infrastructure.sense.mlx_whisper_transcriber import MlxWhisperTranscriber
from infrastructure.sense.openwakeword_ear import (
    SAMPLE_RATE,
    OpenWakeWordDetector,
    OpenWakeWordEar,
)


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
        interrupt_detector=InterruptDetector(
            sample_rate=SAMPLE_RATE, speech_threshold=1500.0, min_speech_duration=0.3
        ),
        interrupt_phrases=InterruptPhrases(),
    )
    brain = OpenCodeBrain(
        base_url="http://127.0.0.1:4096", password=os.environ["OPENCODE_SERVER_PASSWORD"]
    )
    mouth = EdgeTtsMouth()

    asyncio.run(Assistant(ear=ear, brain=brain, mouth=mouth).run())


if __name__ == "__main__":
    main()
