import httpx
import json
from typing import AsyncIterator, Literal, get_args
from dataclasses import dataclass, field

EventType = Literal["message.updated", "session.idle", "session.error", "server.connected"]

ALLOWED_EVENTS = get_args(EventType)

@dataclass
class Event:
    type: EventType
    data: dict = field(default_factory=dict)

class EventStream:
    @staticmethod
    async def parse_event(response: httpx.Response) -> AsyncIterator[Event]:
        """Yield event objects from the gloabl SSE event stream."""
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
            is_known_event = event_type in ALLOWED_EVENTS
            if is_known_event:
                yield Event(type=event_type, data=raw_object)

