"""Unit tests for OpenWakeWordDetector.score — given/then format.

`score` is the wake-word detection seam: it turns a raw model prediction into a
`WakeWordScore` by taking the highest confidence across models. The detector
holds its model behind a private attribute, so tests inject a stub model and
skip the heavy `openwakeword` import in `__init__`.
"""

import numpy as np

from infrastructure.sense.openwakeword_ear import OpenWakeWordDetector

AUDIO_CHUNK = np.zeros(1280, dtype=np.float32)


class StubModel:
    """Returns a preset prediction, ignoring the audio chunk."""

    def __init__(self, prediction: object) -> None:
        self._prediction = prediction

    def predict(self, audio_chunk: np.ndarray) -> object:
        return self._prediction


def build_detector(prediction: object) -> OpenWakeWordDetector:
    """Construct a detector with a stubbed model, bypassing the openwakeword import."""
    detector = OpenWakeWordDetector.__new__(OpenWakeWordDetector)
    detector._model_name = "hey_jarvis"
    detector._model = StubModel(prediction)
    return detector


def test_given_tuple_prediction_then_uses_first_element_as_scores():
    detector = build_detector(({"hey_jarvis": 0.9, "alexa": 0.4}, {"meta": "extra"}))
    score = detector.score(AUDIO_CHUNK)
    assert score.confidence == 0.9


def test_given_dict_prediction_then_uses_dict_as_scores():
    detector = build_detector({"hey_jarvis": 0.3, "alexa": 0.7})
    score = detector.score(AUDIO_CHUNK)
    assert score.confidence == 0.7


def test_given_empty_scores_then_confidence_is_zero():
    detector = build_detector({})
    score = detector.score(AUDIO_CHUNK)
    assert score.confidence == 0.0


def test_given_prediction_then_model_name_is_preserved():
    detector = build_detector({"hey_jarvis": 0.6})
    score = detector.score(AUDIO_CHUNK)
    assert score.model_name == "hey_jarvis"


def test_given_multiple_scores_then_returns_highest_confidence():
    detector = build_detector({"hey_jarvis": 0.2, "alexa": 0.55, "computer": 0.8})
    score = detector.score(AUDIO_CHUNK)
    assert score.confidence == 0.8
