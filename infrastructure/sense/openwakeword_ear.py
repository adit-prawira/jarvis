import numpy as np

from domain.senses.ear import Ear, Transcriber, WakeWordDetector
from domain.senses.interrupt_detector import InterruptDetector
from domain.senses.silence_detector import SilenceDetector
from domain.text.interrupt_phrases import InterruptPhrases
from domain.wake_word import WakeWordScore

WAKE_MODEL_NAME = "hey_jarvis"
DEFAULT_THRESHOLD = 0.5
SAMPLE_RATE = 16_000
CHUNK_SAMPLES = 1280  # 80ms at 16kHz
MAX_UTTERANCE_SECONDS = 10.0

INTERRUPT_CAPTURE_SECONDS = 0.3
INTERRUPT_POLL_SECONDS = 0.08
DEFAULT_INTERRUPT_THRESHOLD = 1500.0
DEFAULT_MIN_INTERRUPT_SECONDS = 0.3


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
        return WakeWordScore(model_name=self._model_name, confidence=confidence)


class OpenWakeWordEar(Ear):
    """A microphone-backed ear: sounddevice stream feeding a detector"""

    def __init__(
        self,
        detector: WakeWordDetector,
        transcriber: Transcriber,
        silence_detector: SilenceDetector,
        interrupt_detector: InterruptDetector,
        interrupt_phrases: InterruptPhrases,
        threshold: float = DEFAULT_THRESHOLD,
        max_utterance_seconds: float = MAX_UTTERANCE_SECONDS,
    ) -> None:
        super().__init__()
        self._detector = detector
        self._threshold = threshold
        self._transcriber = transcriber
        self._silence_detector = silence_detector
        self._interrupt_detector = interrupt_detector
        self._interrupt_phrases = interrupt_phrases
        self._max_utterance_samples = int(max_utterance_seconds * SAMPLE_RATE)

    def listen_for_wake_command(self) -> None:
        import sounddevice as sd

        wake_detected = False

        def handle_audio(indata, *rest) -> None:
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

    def detect_interruption(self) -> str | None:
        import sounddevice as sd

        frames: list[np.ndarray] = []
        self._interrupt_detector.reset()

        def handle_audio(indata, *rest) -> None:
            chunk = indata[:, 0].copy()
            if self._interrupt_detector.feed(chunk):
                frames.append(chunk)
                raise sd.CallbackStop

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=CHUNK_SAMPLES,
            callback=handle_audio,
        ):
            sd.sleep(int(INTERRUPT_CAPTURE_SECONDS * 1000))

        if not frames:
            return None

        audio = np.concatenate(frames)
        transcript = self._transcriber.transcribe(audio)
        if self._interrupt_phrases.is_an_interrupt(transcript):
            return transcript
        return None

    def transcribe_utterance(self, timeout: float) -> str | None:
        import sounddevice as sd

        frames: list[np.ndarray] = []
        total_samples = 0
        turn_ended = False
        is_timeout = False
        silence_samples = int(timeout * SAMPLE_RATE)
        leading_silent_samples = 0

        def handle_audio(indata, *rest) -> None:
            nonlocal total_samples, turn_ended, is_timeout, silence_samples, leading_silent_samples
            chunk = indata[:, 0].copy()
            trailing_silence = self._silence_detector.feed(chunk)
            if not self._silence_detector.speech_started:
                leading_silent_samples += chunk.size
                if leading_silent_samples >= silence_samples:
                    is_timeout = True
                    turn_ended = True
                    raise sd.CallbackStop
                return

            frames.append(chunk)
            total_samples += chunk.size

            is_silence_detected = trailing_silence or total_samples >= self._max_utterance_samples
            if is_silence_detected:
                turn_ended = True
                raise sd.CallbackStop

        self._silence_detector.reset()
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=CHUNK_SAMPLES,
            callback=handle_audio,
        ):
            while not turn_ended:
                sd.sleep(100)

        if is_timeout:
            return None

        audio = np.concatenate(frames) if frames else np.zeros(0, dtype=np.int16)
        return self._transcriber.transcribe(audio)
