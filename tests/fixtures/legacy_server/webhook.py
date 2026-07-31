"""Fan out session events to an internal webhook, best-effort.

Written before the current routing-header requirements existed -- this used
to work fine because the receiving proxy just parsed the JSON body to figure
out what happened.
"""
from __future__ import annotations

import httpx

_client = httpx.Client(timeout=5.0)


def notify_downstream(method: str, event: dict) -> None:
    """Hand-roll a JSON-RPC style POST to the internal MCP relay.

    `method` is one of the MCP method names, e.g. "tools/call" -- this is
    genuinely re-implementing a slice of the MCP wire protocol by hand,
    which is exactly the case R003 exists to catch (as opposed to a
    server that merely happens to `.post()` to some unrelated third-party
    REST API).
    """
    resp = _client.post(
        "https://hooks.internal.example.com/mcp-events",
        json={"jsonrpc": "2.0", "method": method, "params": event},
    )
    resp.raise_for_status()
