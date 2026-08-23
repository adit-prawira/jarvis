import asyncio

from domain.brain import Brain
from domain.senses.ear import Ear
from domain.senses.mouth import Mouth
from domain.text.markdown_stripper import MarkdownStripper
from domain.text.sentence_splitter import SentenceSplitter

NO_COMMAND_TIMEOUT_SECONDS = 30.0
POST_PROMPT_GRACE_SECONDS = 5.0
WELCOME_MESSAGE = "Welcome back, Sir"
ARE_YOU_THERE_MESSAGE = "Are you there, Sir?"


class Assistant:
    """Application service: orchestrate JARVIS senses and the brain"""

    def __init__(self, ear: Ear, brain: Brain, mouth: Mouth) -> None:
        self._brain = brain
        self._ear = ear
        self._mouth = mouth
        self._is_welcomed = False

    async def run(self) -> None:
        print("Listening for 'hey jarvis'...")
        while True:
            await self._listen_for_a_command()

    async def _listen_for_a_command(self) -> None:
        await asyncio.to_thread(self._ear.listen_for_wake_command)
        if not self._is_welcomed:
            await self._mouth.speak(WELCOME_MESSAGE)
            self._is_welcomed = True
        utterance = await asyncio.to_thread(
            self._ear.transcribe_utterance, NO_COMMAND_TIMEOUT_SECONDS
        )
        if utterance is None:
            await self._mouth.speak(ARE_YOU_THERE_MESSAGE)
            utterance = await asyncio.to_thread(
                self._ear.transcribe_utterance, POST_PROMPT_GRACE_SECONDS
            )
            if utterance is None:
                return
        print(f"\nTranscribe: {utterance}")
        await self._respond(utterance)

    async def _respond(self, utterance: str) -> None:
        splitter = SentenceSplitter()
        async for response_text_chunk in self._brain.stream_turn(utterance):
            for sentence in splitter.feed(response_text_chunk):
                sanitised_sentence = MarkdownStripper.strip(sentence)
                if not sanitised_sentence:
                    continue
                await self._mouth.speak(sanitised_sentence)

        remainder = splitter.flush()
        if not remainder:
            return None

        sanitised_remainder = MarkdownStripper.strip(remainder)
        if not sanitised_remainder:
            return None

        await self._mouth.speak(sanitised_remainder)
