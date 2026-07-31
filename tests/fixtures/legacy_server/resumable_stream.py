"""SSE stream resumability -- replaying missed events after a reconnect.

Predates SEP-2575, which removes stream resumability entirely: a dropped
connection is just a dropped connection now, the client re-issues its
request instead of resuming a stream with Last-Event-ID.
"""
from __future__ import annotations


class _EventLog:
    def __init__(self) -> None:
        self._events: list[tuple[str, dict]] = []

    def append(self, event_id: str, payload: dict) -> None:
        self._events.append((event_id, payload))

    def replay_after(self, last_event_id: str):
        """Replay every event the client missed since `Last-Event-ID`."""
        seen = False
        for event_id, payload in self._events:
            if seen:
                yield event_id, payload
            if event_id == last_event_id:
                seen = True


def handle_reconnect(request) -> list[tuple[str, dict]]:
    last_event_id = request.headers.get("Last-Event-ID")
    if last_event_id is None:
        return []
    return list(_EventLog().replay_after(last_event_id))
