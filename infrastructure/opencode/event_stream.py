import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx


@dataclass
class Event:
    type: str
    data: dict = field(default_factory=dict)


class EventStream:
    @staticmethod
    async def parse_event(response: httpx.Response) -> AsyncIterator[Event]:
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            payload = line.removeprefix("data: ")
            try:
                raw_object = json.loads(payload)
            except json.JSONDecodeError:
                continue

            event_type = raw_object.get("type", "")
            if event_type:
                yield Event(type=event_type, data=raw_object)
