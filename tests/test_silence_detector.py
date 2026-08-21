"""Unit tests for SilenceDetector — given/then format.

`feed` is the end-of-turn seam: a chunk whose RMS falls below the silence
threshold accumulates silent samples; when enough consecutive silent samples
are seen, `feed` returns True. A loud chunk resets the counter.
"""

import numpy as np

from domain.senses.silence_detector import SilenceDetector

SAMPLE_RATE = 10
SILENCE_THRESHOLD = 100.0
SILENCE_DURATION = 1.0  # => 10 required silent samples

SILENT = np.zeros(5, dtype=np.int16)  # RMS 0
LOUD = np.full(5, 10000, dtype=np.int16)  # RMS 10000


def build_detector(
    sample_rate: int = SAMPLE_RATE,
    threshold: float = SILENCE_THRESHOLD,
    duration: float = SILENCE_DURATION,
) -> SilenceDetector:
    return SilenceDetector(sample_rate, threshold, duration)


# — boundary: partial silence does not end the turn —
def test_given_partial_silence_then_returns_false():
    detector = build_detector()
    assert detector.feed(SILENT) is False


# — boundary: silence reaching the required duration ends the turn —
def test_given_silence_reaching_duration_then_returns_true():
    detector = build_detector()
    detector.feed(SILENT)  # 5 samples
    assert detector.feed(SILENT) is True  # 10 samples


# — false-positive guard: a loud chunk does not end the turn —
def test_given_loud_chunk_then_returns_false():
    detector = build_detector()
    assert detector.feed(LOUD) is False


# — tautology trap: a loud chunk resets accumulated silence —
def test_given_loud_chunk_then_counter_resets():
    detector = build_detector()
    detector.feed(SILENT)  # 5 silent
    detector.feed(LOUD)  # reset to 0
    assert detector.feed(SILENT) is False  # only 5 silent again


# — boundary: silence must be consecutive —
def test_given_loud_between_silence_then_requires_full_duration_again():
    detector = build_detector()
    detector.feed(SILENT)  # 5
    detector.feed(LOUD)  # reset
    detector.feed(SILENT)  # 5
    assert detector.feed(SILENT) is True  # 10 consecutive


# — boundary: rms exactly at the threshold is not silent —
def test_given_chunk_at_threshold_then_not_silent():
    detector = build_detector()
    at_threshold = np.full(5, 100, dtype=np.int16)  # RMS == 100.0
    assert detector.feed(at_threshold) is False


# — boundary: duration truncates to whole samples —
def test_given_fractional_duration_then_required_samples_truncates():
    detector = build_detector(duration=0.5)  # 10 * 0.5 = 5 samples
    assert detector.feed(SILENT) is True


# — tautology trap: reset clears prior accumulation —
def test_given_reset_after_silence_then_next_feed_is_false():
    detector = build_detector()
    detector.feed(SILENT)  # 5
    detector.reset()
    assert detector.feed(SILENT) is False


# — speech onset: a fresh detector has not heard speech —
def test_given_new_detector_then_speech_not_started():
    assert build_detector().speech_started is False


# — speech onset: silent chunks do not mark speech —
def test_given_silent_chunk_then_speech_not_started():
    detector = build_detector()
    detector.feed(SILENT)
    assert detector.speech_started is False


# — speech onset: a loud chunk marks speech —
def test_given_loud_chunk_then_speech_started():
    detector = build_detector()
    detector.feed(LOUD)
    assert detector.speech_started is True


# — speech onset: once started, later silence does not unset it —
def test_given_silence_after_speech_then_speech_still_started():
    detector = build_detector()
    detector.feed(LOUD)
    detector.feed(SILENT)
    assert detector.speech_started is True


# — speech onset: reset clears the flag —
def test_given_reset_after_speech_then_speech_not_started():
    detector = build_detector()
    detector.feed(LOUD)
    detector.reset()
    assert detector.speech_started is False
