import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal, get_args

import httpx

EventType = Literal["message.updated", "session.idle", "session.error", "server.connected"]

ALLOWED_EVENTS = get_args(EventType)


@dataclass
class Event:
    type: EventType
    data: dict = field(default_factory=dict)


class EventStream:
    @staticmethod
    async def parse_event(response: httpx.Response) -> AsyncIterator[Event]:
        """Yield event objects from the global SSE event stream."""
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            payload = line.removeprefix("data: ")
            if payload == "[DONE]":
                return

            try:
                raw_object = json.loads(payload)
            except json.JSONDecodeError:
                continue

            event_type = raw_object.get("type", "")
            if event_type in ALLOWED_EVENTS:
                yield Event(type=event_type, data=raw_object)
