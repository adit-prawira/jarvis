import numpy as np


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

    def feed(self, chunk: np.ndarray) -> bool:
        samples = chunk.astype(np.float64)
        squares = np.square(samples)
        mean_square = float(squares.mean())
        rms = float(np.sqrt(mean_square))

        if rms < self._silence_threshold:
            self._silent_samples += chunk.size
        else:
            self._silent_samples = 0
        return self._silent_samples >= self._required_silent_samples

    def reset(self) -> None:
        self._silent_samples = 0
