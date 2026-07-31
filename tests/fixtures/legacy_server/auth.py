"""OAuth client onboarding.

Predates Client ID Metadata Documents: registers new clients dynamically
per RFC 7591 (Dynamic Client Registration), which the 2026-07-28 spec
deprecates in CIMD's favour.
"""
from __future__ import annotations


async def register_client(client_metadata: dict) -> dict:
    """Dynamically register a new OAuth client (RFC 7591)."""
    return {"client_id": "generated-id", **client_metadata}
