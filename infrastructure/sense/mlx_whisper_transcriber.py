from typing import Any

import numpy as np

from domain.senses.ear import Transcriber

DEFAULT_MODEL = "mlx-community/whisper-tiny"


class MlxWhisperTranscriber(Transcriber):
    """Speech-to-text adapter over mlx-whisper (Apple Silicon Native)."""

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self._model = model

    def transcribe(self, audio_chunk: np.ndarray) -> str:
        import mlx_whisper

        normalised = audio_chunk.astype(np.float32) / 32768.0
        results: dict[str, Any] = mlx_whisper.transcribe(
            normalised,
            path_or_hf_repo=self._model,
            temperature=0.0,
            language="en"
        )
        return results["text"].strip()
