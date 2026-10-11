import numpy as np

from utilities.math import MathUtil


class SilenceDetector:
    """Detects silence over int16 PCM chunks and signals end-of-turn.

    When a chunk's RMS falls below the threshold it is treated as silent. When
    silent samples accumulate for the required duration, `feed` returns True —
    the user has finished speaking.
    """

    def __init__(
        self,
        sample_rate: int,
        silence_threshold: float,
        silence_duration: float,
    ) -> None:
        self._silence_threshold = silence_threshold
        self._required_silent_samples = int(silence_duration * sample_rate)
        self._silent_samples = 0
        self._speech_started = False

    @property
    def speech_started(self) -> bool:
        return self._speech_started

    def feed(self, chunk: np.ndarray) -> bool:
        rms = MathUtil.calculate_rms(chunk)
        is_silent = rms < self._silence_threshold
        if is_silent:
            self._silent_samples += chunk.size
        else:
            self._speech_started = True
            self._silent_samples = 0
        return self._silent_samples >= self._required_silent_samples

    def reset(self) -> None:
        self._silent_samples = 0
        self._speech_started = False
