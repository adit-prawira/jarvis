import asyncio
import logging
from threading import Event

from domain.brain import Brain
from domain.senses.ear import Ear
from domain.senses.mouth import Mouth
from domain.text.markdown_stripper import MarkdownStripper
from domain.text.sentence_splitter import SentenceSplitter

NO_COMMAND_TIMEOUT_SECONDS = 30.0
POST_PROMPT_GRACE_SECONDS = 5.0
WELCOME_MESSAGE = "Welcome back, Sir"
ARE_YOU_THERE_MESSAGE = "Are you there, Sir?"
FAREWELL_PHRASE = ("thanks", "thanks jarvis", "goodbye", "that's all", "dismissed")
SIGN_OFF_MESSAGE = "Very good, Sir."
INTERRUPTION_KEYWORDS = ("stop", "shut up", "hold on", "enough", "quiet", "cancel")

logger = logging.getLogger(__name__)


class Assistant:
    """Application service: orchestrate JARVIS senses and the brain"""

    def __init__(self, ear: Ear, brain: Brain, mouth: Mouth) -> None:
        self._brain = brain
        self._ear = ear
        self._mouth = mouth
        self._is_welcomed = False

    async def run(self) -> None:
        while True:
            await self._wait_for_wake_and_greet()
            await self._hold_conversation()

    async def _wait_for_wake_and_greet(self) -> None:
        await asyncio.to_thread(self._ear.listen_for_wake_command)
        if not self._is_welcomed:
            await self._mouth.speak(WELCOME_MESSAGE)
            self._is_welcomed = True

    async def _hold_conversation(self) -> None:
        while True:
            utterance = await self._listen_for_next_utterance()
            if utterance is None:
                return

            if self._is_farewell(utterance):
                await self._mouth.speak(SIGN_OFF_MESSAGE)
                return
            logger.info(f"[UTTERANCE] -> {utterance}")
            await self._respond(utterance)

    async def _listen_for_next_utterance(self) -> str | None:
        utterance = await asyncio.to_thread(
            self._ear.transcribe_utterance, NO_COMMAND_TIMEOUT_SECONDS
        )
        if utterance is not None:
            return utterance

        await self._mouth.speak(ARE_YOU_THERE_MESSAGE)
        return await asyncio.to_thread(self._ear.transcribe_utterance, POST_PROMPT_GRACE_SECONDS)

    async def _respond(self, utterance: str) -> None:
        splitter = SentenceSplitter()
        async for response_text_chunk in self._brain.stream_turn(utterance):
            for sentence in splitter.feed(response_text_chunk):
                sanitised = MarkdownStripper.strip(sentence)
                if not sanitised:
                    continue

                if await self._speak_with_listening_for_interruption(sanitised):
                    return

        remainder = splitter.flush()
        if not remainder:
            return None
        sanitised = MarkdownStripper.strip(remainder)
        if sanitised:
            if await self._speak_with_listening_for_interruption(sanitised):
                return

    async def _speak_with_listening_for_interruption(self, text: str) -> bool:
        stop_event = Event()
        speak_task = asyncio.create_task(self._mouth.speak(text))
        interruption_listener_task = asyncio.create_task(
            asyncio.to_thread(
                self._ear.listen_for_interruption, stop_event, INTERRUPTION_KEYWORDS
            )
        )

        done, pending_tasks = await asyncio.wait(
            {speak_task, interruption_listener_task}, return_when=asyncio.FIRST_COMPLETED
        )

        is_interruption_detected = False
        if interruption_listener_task in done:
            is_interruption_detected = interruption_listener_task.result()

        if speak_task in done:
            await speak_task

        stop_event.set()

        for task in pending_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if is_interruption_detected:
            logger.info("INTERRUPTION IS DETECTED")
        return is_interruption_detected

    @staticmethod
    def _is_farewell(utterance: str) -> bool:
        normalised = utterance.strip().lower().rstrip(".!")
        return normalised in FAREWELL_PHRASE
