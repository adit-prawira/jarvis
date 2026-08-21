"""Unit tests for Assistant orchestration — given/then format.

The Assistant waits for the wake word, transcribes a command with a 30s
no-command timeout, prompts ("are you there, sir?") when nothing was said, then
streams the response through the brain into sentence-level speech. A FakeEar
returns scripted transcriptions, a FakeBrain streams scripted deltas, and a
FakeMouth records spoken sentences — so the orchestration is tested without
audio, HTTP, or a real brain.
"""

from collections.abc import AsyncIterator

from application.assistant import (
    ARE_YOU_THERE_MESSAGE,
    NO_COMMAND_TIMEOUT_SECONDS,
    POST_PROMPT_GRACE_SECONDS,
    WELCOME_MESSAGE,
    Assistant,
)


class FakeEar:
    """Returns scripted transcriptions in order and records the timeouts asked for."""

    def __init__(self, *transcriptions: str | None) -> None:
        self._transcriptions = list(transcriptions)
        self.timeouts: list[float] = []
        self.wake_calls = 0

    def listen_for_wake_command(self) -> None:
        self.wake_calls += 1

    def transcribe_utterance(self, timeout: float) -> str | None:
        self.timeouts.append(timeout)
        return self._transcriptions.pop(0)


class FakeBrain:
    """Streams scripted deltas for each turn and records the messages it received."""

    def __init__(self, *deltas: str) -> None:
        self._deltas = list(deltas)
        self.messages: list[str] = []

    async def stream_turn(self, message: str) -> AsyncIterator[str]:
        self.messages.append(message)
        for delta in self._deltas:
            yield delta


class FakeMouth:
    """Records each sentence spoken so ordering can be asserted."""

    def __init__(self) -> None:
        self.spoken: list[str] = []

    async def speak(self, text: str) -> None:
        self.spoken.append(text)


def build_assistant(
    *transcriptions: str | None, deltas: tuple[str, ...] = ()
) -> tuple[Assistant, FakeEar, FakeMouth, FakeBrain]:
    ear = FakeEar(*transcriptions)
    brain = FakeBrain(*deltas)
    mouth = FakeMouth()
    assistant = Assistant(ear=ear, brain=brain, mouth=mouth)
    return assistant, ear, mouth, brain


# — happy path: a command within the timeout is transcribed, no prompt —
async def test_given_command_within_timeout_then_transcribes_without_prompt(capsys):
    assistant, ear, _, _ = build_assistant("open Safari")
    await assistant._listen_for_a_command()
    output = capsys.readouterr().out
    assert "Transcribe: open Safari" in output
    assert ARE_YOU_THERE_MESSAGE not in output
    assert ear.timeouts == [NO_COMMAND_TIMEOUT_SECONDS]


# — timeout: no command in 30s prompts, then 5s more of silence returns to wake —
async def test_given_no_command_then_prompts_and_returns_on_further_silence(capsys):
    assistant, ear, _, _ = build_assistant(None, None)
    await assistant._listen_for_a_command()
    output = capsys.readouterr().out
    assert ARE_YOU_THERE_MESSAGE in output
    assert "Transcribe:" not in output
    assert ear.timeouts == [NO_COMMAND_TIMEOUT_SECONDS, POST_PROMPT_GRACE_SECONDS]


# — grace period: speech during the 5s post-prompt wait is transcribed —
async def test_given_speech_during_grace_then_transcribes(capsys):
    assistant, ear, _, _ = build_assistant(None, "what time is it")
    await assistant._listen_for_a_command()
    output = capsys.readouterr().out
    assert ARE_YOU_THERE_MESSAGE in output
    assert "Transcribe: what time is it" in output
    assert ear.timeouts == [NO_COMMAND_TIMEOUT_SECONDS, POST_PROMPT_GRACE_SECONDS]


# — greeting: welcome is spoken once across multiple wake cycles —
async def test_given_two_wake_cycles_then_welcome_printed_once(capsys):
    assistant, ear, _, _ = build_assistant("first", "second")
    await assistant._listen_for_a_command()
    await assistant._listen_for_a_command()
    output = capsys.readouterr().out
    assert output.count(WELCOME_MESSAGE) == 1
    assert ear.wake_calls == 2


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
