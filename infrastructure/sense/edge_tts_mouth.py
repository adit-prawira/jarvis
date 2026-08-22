import asyncio

import numpy as np

from domain.senses.mouth import Mouth

DEFAULT_VOICE = "en-GB-RyanNeural"
SAMPLE_RATE = 24_000
PCM_TYPE = np.int16


class EdgeTtsMouth(Mouth):
    """Voice-output adapter: Edge TTS text-to-speech played through sounddevice"""

    def __init__(self, voice: str = DEFAULT_VOICE) -> None:
        self._voice = voice

    async def speak(self, text: str) -> None:
        audio_bytes = await self.synthesize(text)
        await asyncio.to_thread(self._play, audio_bytes)

    async def synthesize(self, text: str) -> bytes:
        mp3_bytes = await self._stream_mp3(text)
        return self._decode_mp3_to_pcm(mp3_bytes).tobytes()

    async def stop(self) -> None:
        import sounddevice as sd

        await asyncio.to_thread(sd.stop)

    async def _stream_mp3(self, text: str) -> bytes:
        import edge_tts as et

        audio_chunks: list[bytes] = []
        communicate = et.Communicate(text, voice=self._voice)
        async for message in communicate.stream():
            is_audio_message = message["type"] == "audio"
            if not is_audio_message:
                continue
            data = message.get("data")
            if not data:
                continue
            audio_chunks.append(data)

        return b"".join(audio_chunks)

    def _decode_mp3_to_pcm(self, mp3_bytes: bytes) -> np.ndarray:
        import miniaudio

        decoded = miniaudio.decode(
            mp3_bytes,
            output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=1,
            sample_rate=SAMPLE_RATE,
        )
        return np.asarray(decoded.samples, dtype=PCM_TYPE)

    def _play(self, audio_bytes: bytes) -> None:
        import sounddevice as sd

        samples = np.frombuffer(audio_bytes, dtype=PCM_TYPE)
        sd.play(samples, SAMPLE_RATE)
        sd.wait()
