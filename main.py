import asyncio
import logging
import os
import pathlib

from dotenv import load_dotenv

from application.assistant import Assistant
from domain.senses.silence_detector import SilenceDetector
from infrastructure.opencode.brain_client import OpenCodeBrain
from infrastructure.sense.edge_tts_mouth import EdgeTtsMouth
from infrastructure.sense.fallback_mouth import FallbackMouth
from infrastructure.sense.mlx_whisper_transcriber import MlxWhisperTranscriber
from infrastructure.sense.openwakeword_ear import (
    SAMPLE_RATE,
    OpenWakeWordDetector,
    OpenWakeWordEar,
)
from infrastructure.sense.say_mouth import SayMouth

PROJECT_ROOT = pathlib.Path(__file__).parent.resolve()


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

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
        base_url="http://127.0.0.1:4096",
        password=os.environ["OPENCODE_SERVER_PASSWORD"],
        model="opencode-go/minimax-m3.1-flash-free",
        location=str(PROJECT_ROOT),
    )
    edge_tts_mouth = EdgeTtsMouth()
    say_mouth = SayMouth()
    mouth = FallbackMouth(primary=edge_tts_mouth, fallback=say_mouth)

    asyncio.run(Assistant(ear=ear, brain=brain, mouth=mouth).run())


if __name__ == "__main__":
    main()
