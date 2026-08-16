"""Unit tests for MlxWhisperTranscriber.transcribe — given/then format.

`transcribe` lazily imports mlx_whisper, normalizes int16 PCM to float32 in
[-1, 1], and strips the returned text. Tests inject a stub mlx_whisper module
into sys.modules so the lazy import resolves without the heavy MLX dependency.
"""

import sys
from types import ModuleType
from typing import Any

import numpy as np
import pytest

from infrastructure.sense.mlx_whisper_transcriber import MlxWhisperTranscriber

DEFAULT_MODEL = "mlx-community/whisper-tiny"


class StubMlxWhisper:
    """Records transcribe calls and returns a fixed, padded result."""

    def __init__(self) -> None:
        self.calls: list[tuple[np.ndarray, str, dict[str, Any]]] = []

    def transcribe(
        self, audio: np.ndarray, *, path_or_hf_repo: str, **decode_options: Any
    ) -> dict:
        self.calls.append((audio, path_or_hf_repo, decode_options))
        return {"text": "  hello sir  "}


@pytest.fixture
def stub_mlx_whisper(monkeypatch: pytest.MonkeyPatch) -> StubMlxWhisper:
    stub = StubMlxWhisper()
    module = ModuleType("mlx_whisper")
    module.transcribe = stub.transcribe  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mlx_whisper", module)
    return stub


# — boundary: int16 PCM is normalized to float32 in [-1, 1] —
def test_given_int16_audio_then_normalizes_to_float32(stub_mlx_whisper):
    transcriber = MlxWhisperTranscriber()
    audio = np.array([0, 16384, -32768], dtype=np.int16)
    transcriber.transcribe(audio)
    called_audio = stub_mlx_whisper.calls[0][0]
    assert called_audio.dtype == np.float32
    np.testing.assert_allclose(called_audio, [0.0, 0.5, -1.0])


# — boundary: the returned text is stripped —
def test_given_padded_result_then_returns_stripped_text(stub_mlx_whisper):
    transcriber = MlxWhisperTranscriber()
    result = transcriber.transcribe(np.zeros(4, dtype=np.int16))
    assert result == "hello sir"


# — boundary: the default model is forwarded to mlx_whisper —
def test_given_default_model_then_forwards_model(stub_mlx_whisper):
    transcriber = MlxWhisperTranscriber()
    transcriber.transcribe(np.zeros(4, dtype=np.int16))
    assert stub_mlx_whisper.calls[0][1] == DEFAULT_MODEL


# — boundary: a custom model is forwarded —
def test_given_custom_model_then_forwards_custom_model(stub_mlx_whisper):
    transcriber = MlxWhisperTranscriber(model="mlx-community/whisper-large-v3")
    transcriber.transcribe(np.zeros(4, dtype=np.int16))
    assert stub_mlx_whisper.calls[0][1] == "mlx-community/whisper-large-v3"


# — false-positive guard: English must be explicitly pinned, not a stub default —
def test_given_transcribe_then_forces_english_language(stub_mlx_whisper):
    transcriber = MlxWhisperTranscriber()
    transcriber.transcribe(np.zeros(4, dtype=np.int16))
    assert stub_mlx_whisper.calls[0][2].get("language") == "en"


# — false-positive guard: greedy decoding must be explicitly pinned, not a stub default —
def test_given_transcribe_then_uses_greedy_decoding(stub_mlx_whisper):
    transcriber = MlxWhisperTranscriber()
    transcriber.transcribe(np.zeros(4, dtype=np.int16))
    assert stub_mlx_whisper.calls[0][2].get("temperature") == 0.0
