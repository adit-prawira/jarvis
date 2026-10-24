"""Unit tests for Assistant orchestration — given/then format.

The Assistant waits for the wake word, transcribes a command with a 30s
no-command timeout, prompts ("are you there, sir?") when nothing was said, then
streams the response through the brain into sentence-level speech. A FakeEar
returns scripted transcriptions, a FakeBrain streams scripted deltas, and a
FakeMouth records spoken sentences — so the orchestration is tested without
audio, HTTP, or a real brain.
"""

import asyncio
from collections.abc import AsyncIterator
from threading import Event

from application.assistant import (
    ARE_YOU_THERE_MESSAGE,
    NO_COMMAND_TIMEOUT_SECONDS,
    POST_PROMPT_GRACE_SECONDS,
    SIGN_OFF_MESSAGE,
    WELCOME_MESSAGE,
    Assistant,
)


class FakeEar:
    """Returns scripted transcriptions in order and records the timeouts asked for."""

    def __init__(
        self,
        *transcriptions: str | None,
        interruptions: tuple[bool, ...] = (),
    ) -> None:
        self._transcriptions = list(transcriptions)
        self._interruptions = list(interruptions)
        self.timeouts: list[float] = []
        self.wake_calls = 0

    def listen_for_wake_command(self) -> None:
        self.wake_calls += 1

    def transcribe_utterance(self, timeout: float) -> str | None:
        self.timeouts.append(timeout)
        return self._transcriptions.pop(0)

    def listen_for_interruption(self, stop_event: Event, keywords: tuple[str, ...]) -> bool:
        if self._interruptions:
            return self._interruptions.pop(0)
        return False


class FakeBrain:
    """Streams scripted deltas for each turn and records the messages it received."""

    def __init__(self, *deltas: str) -> None:
        self._deltas = list(deltas)
        self.messages: list[str] = []
        self.abort_called = False

    async def stream_turn(self, message: str) -> AsyncIterator[str]:
        self.messages.append(message)
        for delta in self._deltas:
            yield delta

    async def abort(self) -> None:
        self.abort_called = True


class FakeMouth:
    """Records each sentence spoken so ordering can be asserted."""

    def __init__(self, speak_delay: float = 0.0) -> None:
        self.spoken: list[str] = []
        self.stop_called = False
        self._speak_delay = speak_delay

    async def speak(self, text: str) -> None:
        self.spoken.append(text)
        if self._speak_delay:
            await asyncio.sleep(self._speak_delay)

    async def stop(self) -> None:
        self.stop_called = True


def build_assistant(
    *transcriptions: str | None,
    deltas: tuple[str, ...] = (),
    interruptions: tuple[bool, ...] = (),
    mouth_delay: float = 0.0,
) -> tuple[Assistant, FakeEar, FakeMouth, FakeBrain]:
    ear = FakeEar(*transcriptions, interruptions=interruptions)
    brain = FakeBrain(*deltas)
    mouth = FakeMouth(speak_delay=mouth_delay)
    assistant = Assistant(ear=ear, brain=brain, mouth=mouth)
    return assistant, ear, mouth, brain


# — happy path: a command within the timeout is transcribed, no prompt —
async def test_given_command_within_timeout_then_transcribes_without_prompt(capsys):
    assistant, ear, _, _ = build_assistant("open Safari")
    utterance = await assistant._listen_for_next_utterance()
    assert utterance == "open Safari"
    assert ARE_YOU_THERE_MESSAGE not in capsys.readouterr().out
    assert ear.timeouts == [NO_COMMAND_TIMEOUT_SECONDS]


# — timeout: no command in 30s prompts, then 5s more of silence returns to wake —
async def test_given_no_command_then_prompts_and_returns_on_further_silence(capsys):
    assistant, ear, mouth, _ = build_assistant(None, None)
    utterance = await assistant._listen_for_next_utterance()
    assert utterance is None
    assert mouth.spoken.count(ARE_YOU_THERE_MESSAGE) == 1
    assert ear.timeouts == [NO_COMMAND_TIMEOUT_SECONDS, POST_PROMPT_GRACE_SECONDS]


# — grace period: speech during the 5s post-prompt wait is transcribed —
async def test_given_speech_during_grace_then_transcribes(capsys):
    assistant, ear, mouth, _ = build_assistant(None, "what time is it")
    utterance = await assistant._listen_for_next_utterance()
    assert utterance == "what time is it"
    assert mouth.spoken.count(ARE_YOU_THERE_MESSAGE) == 1
    assert ear.timeouts == [NO_COMMAND_TIMEOUT_SECONDS, POST_PROMPT_GRACE_SECONDS]


# — greeting: welcome is spoken once across multiple wake cycles —
async def test_given_two_wake_cycles_then_welcome_spoken_once():
    assistant, ear, mouth, _ = build_assistant("first", "second")
    await assistant._wait_for_wake_and_greet()
    await assistant._wait_for_wake_and_greet()
    assert mouth.spoken.count(WELCOME_MESSAGE) == 1
    assert ear.wake_calls == 2


# — _is_farewell: phrase matching —
def test_given_thanks_then_is_farewell():
    assert Assistant._is_farewell("thanks") is True


def test_given_thanks_with_punctuation_then_is_farewell():
    assert Assistant._is_farewell("thanks!") is True
    assert Assistant._is_farewell("goodbye.") is True


def test_given_uppercase_then_is_farewell():
    assert Assistant._is_farewell("Thanks") is True
    assert Assistant._is_farewell("GOODBYE") is True


def test_given_non_farewell_utterance_then_not_farewell():
    assert Assistant._is_farewell("open Safari") is False
    assert Assistant._is_farewell("") is False


# — _hold_conversation: multi-turn loop —
async def test_given_two_consecutive_utterances_then_both_turns_run_without_re_wake():
    assistant, ear, _, brain = build_assistant("what time", "thanks jarvis")
    await assistant._hold_conversation()
    assert brain.messages == ["what time"]
    assert ear.wake_calls == 0


async def test_given_farewell_then_signs_off_and_returns_to_wake():
    assistant, _, mouth, brain = build_assistant("thanks")
    await assistant._hold_conversation()
    assert mouth.spoken == [SIGN_OFF_MESSAGE]
    assert brain.messages == []


async def test_given_silence_during_conversation_then_returns_to_wake():
    assistant, _, _, brain = build_assistant("hi", None, None)
    await assistant._hold_conversation()
    assert brain.messages == ["hi"]


# — streaming: a response is split into sentences and spoken in order —
async def test_given_streamed_response_then_speaks_sentences_in_order():
    assistant, _, mouth, _ = build_assistant("hello", deltas=("Hello, sir. ", "How are you?"))
    await assistant._respond("hello")
    assert mouth.spoken == ["Hello, sir.", "How are you?"]


# — flush: a response without trailing punctuation is spoken at end of stream —
async def test_given_response_without_trailing_punctuation_then_flushes_remainder():
    assistant, _, mouth, _ = build_assistant("hello", deltas=("No punctuation here",))
    await assistant._respond("hello")
    assert mouth.spoken == ["No punctuation here"]


# — empty response: no deltas means nothing is spoken —
async def test_given_empty_response_then_speaks_nothing():
    assistant, _, mouth, _ = build_assistant("hello", deltas=())
    await assistant._respond("hello")
    assert mouth.spoken == []


# — brain handoff: the transcribed utterance is sent to the brain —
async def test_given_utterance_then_brain_receives_it():
    assistant, _, _, brain = build_assistant("hello", deltas=())
    await assistant._respond("hello")
    assert brain.messages == ["hello"]


# — sanitise: markdown in the brain response is stripped before speaking —
async def test_given_markdown_response_then_speaks_sanitised_sentences():
    assistant, _, mouth, _ = build_assistant(
        "hello", deltas=("**Hello**, sir. ", "[see docs](https://x).")
    )
    await assistant._respond("hello")
    assert mouth.spoken == ["Hello, sir.", "see docs."]


# — sanitise: a sentence that strips to empty is not spoken —
async def test_given_markdown_only_sentence_then_skipped():
    assistant, _, mouth, _ = build_assistant("hello", deltas=("Hello, sir. --- ",))
    await assistant._respond("hello")
    assert mouth.spoken == ["Hello, sir."]


# — interruption: no interruption means all sentences are spoken —
async def test_given_no_interruption_then_speaks_all_sentences():
    assistant, _, mouth, _ = build_assistant(
        "hello",
        deltas=("Hello, sir. ", "How are you?"),
        interruptions=(False, False),
        mouth_delay=0.01,
    )
    await assistant._respond("hello")
    assert mouth.spoken == ["Hello, sir.", "How are you?"]


# — interruption: detection during first sentence stops the response —
async def test_given_interruption_during_first_sentence_then_stops_responding():
    assistant, _, mouth, brain = build_assistant(
        "hello",
        deltas=("Hello, sir. ", "How are you?"),
        interruptions=(True,),
        mouth_delay=0.01,
    )
    await assistant._respond("hello")
    assert mouth.spoken == ["Hello, sir."]
    assert brain.messages == ["hello"]


# — interruption: detection is logged —
async def test_given_interruption_then_logs_detection(caplog):
    assistant, _, _, _ = build_assistant(
        "hello",
        deltas=("Hello, sir. ",),
        interruptions=(True,),
        mouth_delay=0.01,
    )
    with caplog.at_level("INFO"):
        await assistant._respond("hello")
    assert "INTERRUPTION IS DETECTED" in caplog.text


# — interruption: mouth is stopped —
async def test_given_interruption_then_mouth_is_stopped():
    assistant, _, mouth, _ = build_assistant(
        "hello",
        deltas=("Hello, sir. ", "How are you?"),
        interruptions=(True,),
        mouth_delay=0.01,
    )
    await assistant._respond("hello")
    assert mouth.stop_called is True


# — interruption: brain turn is aborted —
async def test_given_interruption_then_brain_is_aborted():
    assistant, _, _, brain = build_assistant(
        "hello",
        deltas=("Hello, sir. ", "How are you?"),
        interruptions=(True,),
        mouth_delay=0.01,
    )
    await assistant._respond("hello")
    assert brain.abort_called is True


# — no interruption: mouth is not stopped —
async def test_given_no_interruption_then_mouth_is_not_stopped():
    assistant, _, mouth, _ = build_assistant(
        "hello",
        deltas=("Hello, sir. ",),
        interruptions=(False,),
        mouth_delay=0.01,
    )
    await assistant._respond("hello")
    assert mouth.stop_called is False


# — no interruption: brain is not aborted —
async def test_given_no_interruption_then_brain_is_not_aborted():
    assistant, _, _, brain = build_assistant(
        "hello",
        deltas=("Hello, sir. ",),
        interruptions=(False,),
        mouth_delay=0.01,
    )
    await assistant._respond("hello")
    assert brain.abort_called is False
