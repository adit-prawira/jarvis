"""Unit tests for Assistant._listen_for_a_command — given/then format.

`_listen_for_a_command` is the wake-cycle seam: wait for the wake word, then
transcribe a command with a 30s no-command timeout; if nothing was said, prompt
("are you there, sir?") and listen 5s more before returning to wake. The greeting
is spoken only once per session. A FakeEar returns scripted transcriptions and
records the timeouts it was asked for, so the orchestration is tested without
audio or a real brain.
"""

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


def build_assistant(*transcriptions: str | None) -> tuple[Assistant, FakeEar]:
    ear = FakeEar(*transcriptions)
    return Assistant(ear=ear), ear


# — happy path: a command within the timeout is transcribed, no prompt —
def test_given_command_within_timeout_then_transcribes_without_prompt(capsys):
    assistant, ear = build_assistant("open Safari")
    assistant._listen_for_a_command()
    output = capsys.readouterr().out
    assert "Transcribed: open Safari" in output
    assert ARE_YOU_THERE_MESSAGE not in output
    assert ear.timeouts == [NO_COMMAND_TIMEOUT_SECONDS]


# — timeout: no command in 30s prompts, then 5s more of silence returns to wake —
def test_given_no_command_then_prompts_and_returns_on_further_silence(capsys):
    assistant, ear = build_assistant(None, None)
    assistant._listen_for_a_command()
    output = capsys.readouterr().out
    assert ARE_YOU_THERE_MESSAGE in output
    assert "Transcribed:" not in output
    assert ear.timeouts == [NO_COMMAND_TIMEOUT_SECONDS, POST_PROMPT_GRACE_SECONDS]


# — grace period: speech during the 5s post-prompt wait is transcribed —
def test_given_speech_during_grace_then_transcribes(capsys):
    assistant, ear = build_assistant(None, "what time is it")
    assistant._listen_for_a_command()
    output = capsys.readouterr().out
    assert ARE_YOU_THERE_MESSAGE in output
    assert "Transcribed: what time is it" in output
    assert ear.timeouts == [NO_COMMAND_TIMEOUT_SECONDS, POST_PROMPT_GRACE_SECONDS]


# — greeting: welcome is spoken once across multiple wake cycles —
def test_given_two_wake_cycles_then_welcome_printed_once(capsys):
    assistant, ear = build_assistant("first", "second")
    assistant._listen_for_a_command()
    assistant._listen_for_a_command()
    output = capsys.readouterr().out
    assert output.count(WELCOME_MESSAGE) == 1
    assert ear.wake_calls == 2
