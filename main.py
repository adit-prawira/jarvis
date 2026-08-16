from application.assistant import Assistant
from domain.senses.silence_detector import SilenceDetector
from infrastructure.sense.mlx_whisper_transcriber import MlxWhisperTranscriber
from infrastructure.sense.openwakeword_ear import (
    SAMPLE_RATE,
    OpenWakeWordDetector,
    OpenWakeWordEar,
)


def main() -> None:
    ear = OpenWakeWordEar(
        detector=OpenWakeWordDetector(),
        transcriber=MlxWhisperTranscriber(),
        silence_detector=SilenceDetector(
            sample_rate=SAMPLE_RATE,
            silence_threshold=300.0,
            silence_duration=1.5,
        ),
    )
    Assistant(ear=ear).run()


if __name__ == "__main__":
    main()
