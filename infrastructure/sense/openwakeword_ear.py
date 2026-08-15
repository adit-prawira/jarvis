import numpy as np

from domain.senses.ear import Ear, WakeWordDetector
from domain.wake_word import WakeWordScore

WAKE_MODEL_NAME = "hey_jarvis"
DEFAULT_THRESHOLD = 0.5
SAMPLE_RATE = 16_000
CHUNK_SAMPLES = 1280 # 80ms at 16kHz

class OpenWakeWordDetector(WakeWordDetector):
    """Wake-word scoring backed by openwakeword's pre-trained model.

    openwakeword will be imported lazily so importing this adapter never
    triggers the heavy model dependency.
    """

    def __init__(self, model_name: str = WAKE_MODEL_NAME) -> None:
        import openwakeword
        from openwakeword.model import Model
        super().__init__()
        self._model_name = model_name
        model_path = openwakeword.models[model_name]["model_path"]
        self._model = Model(wakeword_model_paths=[model_path])

    def score(self, audio_chunk: np.ndarray) -> WakeWordScore:
        results = self._model.predict(audio_chunk)
        scores = results[0] if isinstance(results, tuple) else results
        confidence = max(scores.values()) if scores else 0.0
        return WakeWordScore(
            model_name=self._model_name,
            confidence=confidence
        )

class OpenWakeWordEar(Ear):
    """A microphone-backed ear: sounddevice stream feeding a detector"""

    def __init__(self, detector: WakeWordDetector, threshold: float = DEFAULT_THRESHOLD) -> None:
        super().__init__()
        self._detector = detector
        self._threshold = threshold

    def listen_for_wake_command(self) -> None:
        import sounddevice as sd
        wake_detected = False

        def handle_audio(indata, frames, time_info, status) -> None:
            nonlocal wake_detected
            score = self._detector.score(indata[:, 0])
            if score.exceeds(self._threshold):
                wake_detected = True
                raise sd.CallbackStop

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=CHUNK_SAMPLES,
            callback=handle_audio,
        ):
            while not wake_detected:
                sd.sleep(100)
