import re
from collections.abc import Iterator

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_MAX_BUFFER = 200


class SentenceSplitter:
    def __init__(self) -> None:
        self._buffer = ""

    def feed(self, delta: str) -> Iterator[str]:
        self._buffer += delta
        while True:
            match = _SENTENCE_BOUNDARY.search(self._buffer)
            if match:
                end = match.end()
                sentence = self._buffer[:end].strip()
                self._buffer = self._buffer[end:]
                if sentence:
                    yield sentence
            else:
                break

        if len(self._buffer) >= _MAX_BUFFER:
            cutoff = self._buffer.rfind(" ", 0, _MAX_BUFFER)
            if cutoff == -1:
                cutoff = _MAX_BUFFER

            chunk = self._buffer[:cutoff].strip()
            self._buffer = self._buffer[cutoff:]
            if chunk:
                yield chunk

    def flush(self) -> str | None:
        remaining = self._buffer.strip()
        self._buffer = ""
        return remaining or None
