r"""Unit tests for SentenceSplitter — given/then format.

The splitter uses the regex `(?<=[.!?])\s+` — it only flushes when
punctuation is followed by whitespace (a next sentence or trailing space).
Standalone "Hello, sir." without trailing whitespace stays in the buffer
until flush() is called or the next delta arrives starting with whitespace.
"""

from domain.text.sentence_splitter import SentenceSplitter


# — boundary: sentence followed by whitespace yields via flush —
def test_given_sentence_with_trailing_space_then_yields_on_next_feed():
    splitter = SentenceSplitter()
    result = list(splitter.feed("Hello, sir. "))
    assert result == ["Hello, sir."]


# — tautology trap: sentence without trailing space stays in buffer —
def test_given_sentence_no_trailing_space_then_buffers_not_yields():
    splitter = SentenceSplitter()
    result = list(splitter.feed("Hello, sir."))
    assert result == []
    assert len(splitter._buffer) > 0


# — boundary: flush releases buffered sentence —
def test_given_buffered_sentence_then_flush_returns_it():
    splitter = SentenceSplitter()
    list(splitter.feed("Hello, sir."))
    assert splitter.flush() == "Hello, sir."


# — boundary: question mark with trailing space yields —
def test_given_question_with_trailing_space_then_yields():
    splitter = SentenceSplitter()
    result = list(splitter.feed("Are you there, sir? "))
    assert result == ["Are you there, sir?"]


# — boundary: exclamation followed by space yields —
def test_given_exclamation_with_trailing_space_then_yields():
    splitter = SentenceSplitter()
    result = list(splitter.feed("Excellent! Indeed."))
    assert result == ["Excellent!"]


# — boundary: multiple sentences in one delta with spaces between them —
def test_given_multi_sentence_delta_with_spaces_then_yields_all():
    splitter = SentenceSplitter()
    result = list(splitter.feed("Hello, sir. How are you? Good."))
    assert result == ["Hello, sir.", "How are you?"]


# — false-positive guard: partial sentence must NOT flush —
def test_given_partial_sentence_then_yields_nothing():
    splitter = SentenceSplitter()
    result = list(splitter.feed("Hello,"))
    assert result == []


# — tautology trap: buffer state tracks remainder after sentence + space —
def test_given_sentence_then_space_then_buffer_holds_remainder():
    splitter = SentenceSplitter()
    result = list(splitter.feed("Hello, sir. How"))
    assert result == ["Hello, sir."]
    assert splitter._buffer == "How"


# — false-positive guard: fragment without boundary does not yield —
def test_given_fragment_only_then_does_not_yield():
    splitter = SentenceSplitter()
    result = list(splitter.feed("Without endpoint"))
    assert result == []


# — boundary: sentence spans two deltas, second starts with space —
def test_given_sentence_across_two_deltas_with_space_then_yields_complete():
    splitter = SentenceSplitter()
    list(splitter.feed("Hello,"))
    list(splitter.feed(" sir. "))
    assert splitter.flush() is None  # trailing space triggered the yield + flush


# — false-positive guard: second delta without space does not trigger flush —
def test_given_two_fragments_no_space_then_no_yield():
    splitter = SentenceSplitter()
    list(splitter.feed("Hello,"))
    result = list(splitter.feed("sir."))
    assert result == []


# — overflow: buffer exceeds 200 chars with no boundary —
def test_given_long_text_no_boundary_then_flushes_on_word_break():
    splitter = SentenceSplitter()
    long_text = "x " * 201
    result = list(splitter.feed(long_text))
    assert len(result) >= 1
    for chunk in result:
        assert len(chunk) > 0


# — tautology trap: overflow actually reduces buffer —
def test_given_buffer_over_200_chars_then_buffer_length_reduces():
    splitter = SentenceSplitter()
    splitter.feed("word " * 80)
    assert len(splitter._buffer) < 80 * len("word ")


# — boundary: flush returns None when buffer is empty —
def test_given_complete_sentence_with_space_flushed_then_flush_returns_none():
    splitter = SentenceSplitter()
    splitter.feed("Complete. ")
    assert splitter.flush() is None


# — false-positive guard: flush actually clears the buffer —
def test_given_flush_called_then_buffer_clears():
    splitter = SentenceSplitter()
    splitter.feed("Trailing text")
    splitter.flush()
    assert splitter._buffer == ""


# — boundary: empty delta is noop —
def test_given_empty_delta_then_yields_nothing():
    splitter = SentenceSplitter()
    result = list(splitter.feed(""))
    assert result == []
    assert len(splitter._buffer) == 0


# — boundary: leading space then sentence still works —
def test_given_leading_space_then_yields_if_boundary():
    splitter = SentenceSplitter()
    result = list(splitter.feed(" Hello, sir. "))
    assert result == ["Hello, sir."]


# — false-positive guard: consecutive deltas accumulate, not produce false breaks —
def test_given_consecutive_deltas_with_space_then_yields_on_boundary():
    splitter = SentenceSplitter()
    list(splitter.feed("This is"))
    list(splitter.feed(" a test. "))
    assert splitter.flush() is None


# — boundary: strip removes surrounding whitespace —
def test_given_padded_sentence_then_yields_stripped():
    splitter = SentenceSplitter()
    result = list(splitter.feed("  Hello, sir.  Good. "))
    assert result == ["Hello, sir.", "Good."]


# — tautology trap: flush after complete feed returns None —
def test_given_all_sentences_flushed_then_flush_is_none():
    splitter = SentenceSplitter()
    splitter.feed("One. Two. Three. ")
    assert splitter.flush() is None
