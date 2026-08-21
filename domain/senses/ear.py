from typing import Protocol

import numpy as np

from domain.wake_word import WakeWordScore


class WakeWordDetector(Protocol):
    """Scores a chunk of audio input for wake-work command presence"""

    def score(self, audio_chunk: np.ndarray) -> WakeWordScore: ...


class Transcriber(Protocol):
    """Speech-to-text port. Utilise MlxWhisperTranscriber over mlx-whisper"""

    def transcribe(self, audio_chunk: np.ndarray) -> str: ...


class Ear(Protocol):
    """The hearing sense of JARVIS, this will allow the personal assistant to process word"""

    def listen_for_wake_command(self) -> None: ...

    def transcribe_utterance(self, timeout: float) -> str | None: ...
