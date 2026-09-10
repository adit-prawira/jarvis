"""Unit tests for OpenWakeWordEar.transcribe_utterance — given/then format.

`transcribe_utterance` is the recording seam: it feeds chunks to the silence
detector and returns `None` if the leading-silence timeout elapses before speech
begins, otherwise it transcribes the recorded (non-leading) audio. The
`sounddevice` stream is stubbed so the callback is driven synchronously with a
scripted sequence of chunks, skipping real audio I/O.
"""

import sys
from types import ModuleType

import numpy as np
import pytest

from domain.senses.silence_detector import SilenceDetector
from infrastructure.sense.openwakeword_ear import CHUNK_SAMPLES, SAMPLE_RATE, OpenWakeWordEar


class _CallbackStopError(Exception):
    pass


class StubTranscriber:
    """Records the audio it was given and returns a fixed transcript."""

    def __init__(self, text: str = "hello sir") -> None:
        self._text = text
        self.received_audio: np.ndarray | None = None

    def transcribe(self, audio_chunk: np.ndarray) -> str:
        self.received_audio = audio_chunk
        return self._text


def install_sounddevice_stub(monkeypatch: pytest.MonkeyPatch, chunks: list[np.ndarray]) -> None:
    """Inject a fake `sounddevice` whose `sleep` feeds the next scripted chunk."""
    module = ModuleType("sounddevice")
    streams: list = []

    class InputStream:
        def __init__(self, **kwargs: object) -> None:
            self.callback = kwargs["callback"]
            self.fed = 0
            streams.append(self)

        def __enter__(self) -> "InputStream":
            return self

        def __exit__(self, *args: object) -> bool:
            return False

    def sleep(_milliseconds: int) -> None:
        stream = streams[-1]
        if stream.fed < len(chunks):
            chunk = chunks[stream.fed]
            stream.fed += 1
            try:
                stream.callback(chunk)
            except _CallbackStopError:
                pass

    module.InputStream = InputStream
    module.sleep = sleep
    module.CallbackStop = _CallbackStopError
    monkeypatch.setitem(sys.modules, "sounddevice", module)


def build_ear(transcriber: StubTranscriber, silence_detector: SilenceDetector) -> OpenWakeWordEar:
    return OpenWakeWordEar(
        detector=object(),
        transcriber=transcriber,
        silence_detector=silence_detector,
    )


def silent_chunk() -> np.ndarray:
    return np.zeros((CHUNK_SAMPLES, 1), dtype=np.int16)


def loud_chunk() -> np.ndarray:
    return np.full((CHUNK_SAMPLES, 1), 10000, dtype=np.int16)


# — timeout: nothing but silence until the timeout elapses returns None —
def test_given_only_silence_until_timeout_then_returns_none(monkeypatch):
    silence_detector = SilenceDetector(
        sample_rate=SAMPLE_RATE, silence_threshold=100.0, silence_duration=1.0
    )
    transcriber = StubTranscriber()
    ear = build_ear(transcriber, silence_detector)
    install_sounddevice_stub(monkeypatch, [silent_chunk(), silent_chunk()])

    result = ear.transcribe_utterance(timeout=0.16)  # 2 chunks = 2560 samples

    assert result is None
    assert transcriber.received_audio is None


# — happy path: speech before the timeout transcribes normally —
def test_given_speech_before_timeout_then_returns_transcription(monkeypatch):
    silence_detector = SilenceDetector(
        sample_rate=SAMPLE_RATE, silence_threshold=100.0, silence_duration=0.08
    )
    transcriber = StubTranscriber("open safari")
    ear = build_ear(transcriber, silence_detector)
    install_sounddevice_stub(monkeypatch, [loud_chunk(), silent_chunk()])

    result = ear.transcribe_utterance(timeout=30.0)

    assert result == "open safari"


# — boundary: leading silence is discarded, not transcribed —
def test_given_leading_silence_then_discarded_from_transcription(monkeypatch):
    silence_detector = SilenceDetector(
        sample_rate=SAMPLE_RATE, silence_threshold=100.0, silence_duration=0.08
    )
    transcriber = StubTranscriber()
    ear = build_ear(transcriber, silence_detector)
    install_sounddevice_stub(monkeypatch, [silent_chunk(), loud_chunk(), silent_chunk()])

    ear.transcribe_utterance(timeout=30.0)

    assert transcriber.received_audio is not None
    assert transcriber.received_audio.size == 2 * CHUNK_SAMPLES


# — acceptance: ~1.5-2s trailing silence ends the turn —
def test_given_speech_then_trailing_silence_ends_turn_after_duration(monkeypatch):
    silence_detector = SilenceDetector(
        sample_rate=SAMPLE_RATE, silence_threshold=100.0, silence_duration=1.5
    )
    transcriber = StubTranscriber("open safari")
    ear = build_ear(transcriber, silence_detector)
    chunks = [loud_chunk()] + [silent_chunk()] * 19
    install_sounddevice_stub(monkeypatch, chunks)

    result = ear.transcribe_utterance(timeout=30.0)

    assert result == "open safari"
    assert transcriber.received_audio is not None
    # 1 loud + 19 silent chunks recorded (the 19th silent triggered end-of-turn)
    assert transcriber.received_audio.size == 20 * CHUNK_SAMPLES


# — acceptance: brief pause within utterance does NOT end the turn —
def test_given_brief_pause_within_utterance_then_turn_continues(monkeypatch):
    silence_detector = SilenceDetector(
        sample_rate=SAMPLE_RATE, silence_threshold=100.0, silence_duration=1.5
    )
    transcriber = StubTranscriber("open safari")
    ear = build_ear(transcriber, silence_detector)
    chunks = [loud_chunk(), silent_chunk(), loud_chunk()] + [silent_chunk()] * 19
    install_sounddevice_stub(monkeypatch, chunks)

    result = ear.transcribe_utterance(timeout=30.0)

    assert result == "open safari"
    assert transcriber.received_audio is not None
    # Both loud chunks recorded (brief 80ms pause did NOT end the turn)
    assert transcriber.received_audio.size == 22 * CHUNK_SAMPLES


# — backstop: 10s MAX_UTTERANCE_SECONDS cap ends runaway recordings —
def test_given_utterance_exceeding_max_seconds_then_turn_ends_at_cap(monkeypatch):
    silence_detector = SilenceDetector(
        sample_rate=SAMPLE_RATE, silence_threshold=100.0, silence_duration=1.5
    )
    transcriber = StubTranscriber()
    ear = build_ear(transcriber, silence_detector)
    chunks = [loud_chunk()] * 130
    install_sounddevice_stub(monkeypatch, chunks)

    result = ear.transcribe_utterance(timeout=30.0)

    assert result == "hello sir"
    assert transcriber.received_audio is not None
    # Capped at 10s (160_000 samples = 125 chunks); assert bounded near cap
    assert transcriber.received_audio.size <= 160_000
