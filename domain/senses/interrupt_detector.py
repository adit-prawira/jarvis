import numpy as np

from utilities.math import MathUtil


class InterruptDetector:
    def __init__(
        self, sample_rate: int, speech_threshold: float, min_speech_duration: float
    ) -> None:
        self._speech_threshold = speech_threshold
        self._required_speech_samples = int(min_speech_duration * sample_rate)
        self._speech_samples = 0

    def feed(self, chunk: np.ndarray) -> bool:
        rms = MathUtil.calculate_rms(chunk)
        is_speech_detected = rms >= self._speech_threshold
        if is_speech_detected:
            self._speech_samples += chunk.size
        else:
            self._speech_samples = 0
        return self._speech_samples >= self._required_speech_samples

    def reset(self) -> None:
        self._speech_samples = 0
