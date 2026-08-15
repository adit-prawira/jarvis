"""Unit tests for WakeWordScore — given/then format.

`exceeds` implements the wake-word threshold contract: a score "exceeds"
its threshold when confidence is greater than or equal to the threshold
(used by `OpenWakeWordEar` to decide whether the wake word was heard).
"""

from domain.wake_word import WakeWordScore


def test_given_confidence_above_threshold_then_exceeds_is_true():
    score = WakeWordScore(model_name="hey_jarvis", confidence=0.7)
    assert score.exceeds(0.5) is True


def test_given_confidence_equal_to_threshold_then_exceeds_is_true():
    score = WakeWordScore(model_name="hey_jarvis", confidence=0.5)
    assert score.exceeds(0.5) is True


def test_given_confidence_below_threshold_then_exceeds_is_false():
    score = WakeWordScore(model_name="hey_jarvis", confidence=0.4)
    assert score.exceeds(0.5) is False


def test_given_zero_confidence_and_zero_threshold_then_exceeds_is_true():
    score = WakeWordScore(model_name="hey_jarvis", confidence=0.0)
    assert score.exceeds(0.0) is True


def test_given_negative_confidence_below_negative_threshold_then_exceeds_is_false():
    score = WakeWordScore(model_name="hey_jarvis", confidence=-0.2)
    assert score.exceeds(-0.1) is False
