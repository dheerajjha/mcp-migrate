"""Manual initialize handshake handling.

The SDK negotiates this internally today, but this server intercepts the
raw messages itself to log them -- a pattern that predates SEP-2575, which
removes the initialize handshake outright in favour of a single discovery
call clients make up front.
"""
from __future__ import annotations

from mcp.types import InitializedNotification, InitializeRequest


async def dispatch_handshake(message):
    if isinstance(message, InitializeRequest):
        return {"protocolVersion": "2025-06-18"}
    if isinstance(message, InitializedNotification):
        return None
    return None
