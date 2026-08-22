"""Unit tests for EdgeTtsMouth — given/then format.

`EdgeTtsMouth` lazily imports edge_tts, miniaudio, and sounddevice. Tests inject
stub modules into sys.modules so the lazy imports resolve without the real
dependencies. The testable seam is `synthesize(text) -> bytes` plus the two
public `speak`/`stop` methods.
"""

import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

from infrastructure.sense.edge_tts_mouth import EdgeTtsMouth

DEFAULT_VOICE = "en-GB-RyanNeural"
SAMPLE_RATE = 24_000


class _Stream:
    """Replays a fixed list of edge_tts messages when streamed."""

    def __init__(self, messages: list[dict[str, Any]]) -> None:
        self._messages = messages

    async def stream(self):
        for message in self._messages:
            yield message


class StubEdgeTts:
    """Records Communicate(text, voice) calls and replays fixed messages."""

    def __init__(self, messages: list[dict[str, Any]]) -> None:
        self.messages = messages
        self.calls: list[tuple[str, str]] = []

    def communicate(self, text: str, voice: str) -> _Stream:
        self.calls.append((text, voice))
        return _Stream(self.messages)


class StubMiniaudio:
    """Records decode() calls and returns fixed signed-16 samples."""

    def __init__(self, samples: list[int]) -> None:
        self._samples = samples
        self.decode_calls: list[tuple[bytes, str, int, int]] = []
        self.SampleFormat = SimpleNamespace(SIGNED16="signed16", SIGNED32="signed32")

    def decode(
        self,
        mp3_bytes: bytes,
        *,
        output_format: str,
        nchannels: int,
        sample_rate: int,
    ) -> SimpleNamespace:
        self.decode_calls.append((mp3_bytes, output_format, nchannels, sample_rate))
        return SimpleNamespace(samples=self._samples)


class StubSoundDevice:
    """Records play/wait/stop calls without producing audio."""

    def __init__(self) -> None:
        self.play_calls: list[tuple[np.ndarray, int]] = []
        self.wait_calls = 0
        self.stop_calls = 0

    def play(self, samples: np.ndarray, sample_rate: int) -> None:
        self.play_calls.append((samples, sample_rate))

    def wait(self) -> None:
        self.wait_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1


@pytest.fixture
def stub_edge_tts(monkeypatch: pytest.MonkeyPatch) -> StubEdgeTts:
    stub = StubEdgeTts(
        [
            {"type": "audio", "data": b"\x01\x02"},
            {"type": "WordBoundary", "data": b"\xffignore\xff"},
            {"type": "audio", "data": b"\x03\x04"},
        ]
    )
    module = ModuleType("edge_tts")
    module.Communicate = stub.communicate  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "edge_tts", module)
    return stub


@pytest.fixture
def stub_miniaudio(monkeypatch: pytest.MonkeyPatch) -> StubMiniaudio:
    stub = StubMiniaudio([1, -2, 3])
    module = ModuleType("miniaudio")
    module.decode = stub.decode  # type: ignore[attr-defined]
    module.SampleFormat = stub.SampleFormat  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "miniaudio", module)
    return stub


@pytest.fixture
def stub_sounddevice(monkeypatch: pytest.MonkeyPatch) -> StubSoundDevice:
    stub = StubSoundDevice()
    module = ModuleType("sounddevice")
    module.play = stub.play  # type: ignore[attr-defined]
    module.wait = stub.wait  # type: ignore[attr-defined]
    module.stop = stub.stop  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sounddevice", module)
    return stub


# — boundary: only audio messages are kept, joined in stream order —
async def test_given_mixed_messages_then_decodes_only_audio_chunks(
    stub_edge_tts: StubEdgeTts, stub_miniaudio: StubMiniaudio
) -> None:
    mouth = EdgeTtsMouth()
    await mouth.synthesize("hello sir")
    assert stub_miniaudio.decode_calls[0][0] == b"\x01\x02\x03\x04"


# — boundary: audio messages with empty data are skipped —
async def test_given_audio_message_with_empty_data_then_skips_it(
    stub_edge_tts: StubEdgeTts, stub_miniaudio: StubMiniaudio
) -> None:
    stub_edge_tts.messages = [
        {"type": "audio", "data": b"\x01"},
        {"type": "audio", "data": b""},
        {"type": "audio", "data": b"\x02"},
    ]
    mouth = EdgeTtsMouth()
    await mouth.synthesize("hello")
    assert stub_miniaudio.decode_calls[0][0] == b"\x01\x02"


# — boundary: the default voice is the spec'd en-GB-RyanNeural —
async def test_given_default_voice_then_forwards_en_gb_ryan_neural(
    stub_edge_tts: StubEdgeTts, stub_miniaudio: StubMiniaudio
) -> None:
    mouth = EdgeTtsMouth()
    await mouth.synthesize("hello")
    assert stub_edge_tts.calls[0] == ("hello", DEFAULT_VOICE)


# — boundary: a custom voice is forwarded to edge_tts —
async def test_given_custom_voice_then_forwards_custom_voice(
    stub_edge_tts: StubEdgeTts, stub_miniaudio: StubMiniaudio
) -> None:
    mouth = EdgeTtsMouth(voice="en-US-AriaNeural")
    await mouth.synthesize("hello")
    assert stub_edge_tts.calls[0][1] == "en-US-AriaNeural"


# — boundary: mp3 is decoded to signed-16 mono at 24 kHz —
async def test_given_mp3_bytes_then_decodes_signed16_mono_at_24khz(
    stub_edge_tts: StubEdgeTts, stub_miniaudio: StubMiniaudio
) -> None:
    mouth = EdgeTtsMouth()
    await mouth.synthesize("hello")
    _, output_format, nchannels, sample_rate = stub_miniaudio.decode_calls[0]
    assert output_format == "signed16"
    assert nchannels == 1
    assert sample_rate == SAMPLE_RATE


# — boundary: the decoded samples come back as int16 PCM bytes —
async def test_given_decoded_samples_then_returns_int16_pcm_bytes(
    stub_edge_tts: StubEdgeTts, stub_miniaudio: StubMiniaudio
) -> None:
    mouth = EdgeTtsMouth()
    result = await mouth.synthesize("hello")
    np.testing.assert_array_equal(np.frombuffer(result, dtype=np.int16), [1, -2, 3])


# — boundary: speak plays the synthesized samples —
async def test_given_text_then_speak_plays_decoded_samples(
    stub_edge_tts: StubEdgeTts,
    stub_miniaudio: StubMiniaudio,
    stub_sounddevice: StubSoundDevice,
) -> None:
    mouth = EdgeTtsMouth()
    await mouth.speak("hello")
    played_samples = stub_sounddevice.play_calls[0][0]
    np.testing.assert_array_equal(played_samples, [1, -2, 3])


# — boundary: speak plays back at the decoded sample rate —
async def test_given_text_then_speak_plays_at_24khz(
    stub_edge_tts: StubEdgeTts,
    stub_miniaudio: StubMiniaudio,
    stub_sounddevice: StubSoundDevice,
) -> None:
    mouth = EdgeTtsMouth()
    await mouth.speak("hello")
    assert stub_sounddevice.play_calls[0][1] == SAMPLE_RATE


# — boundary: speak blocks until playback finishes —
async def test_given_text_then_speak_waits_for_playback(
    stub_edge_tts: StubEdgeTts,
    stub_miniaudio: StubMiniaudio,
    stub_sounddevice: StubSoundDevice,
) -> None:
    mouth = EdgeTtsMouth()
    await mouth.speak("hello")
    assert stub_sounddevice.wait_calls == 1


# — boundary: stop halts any in-flight playback —
async def test_given_stop_then_stops_playback(stub_sounddevice: StubSoundDevice) -> None:
    mouth = EdgeTtsMouth()
    await mouth.stop()
    assert stub_sounddevice.stop_calls == 1
