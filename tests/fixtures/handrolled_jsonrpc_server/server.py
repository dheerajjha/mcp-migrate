"""An MCP server that builds its own JSON-RPC envelopes, without the SDK.

R015's fixture. It cannot be legacy_server, because legacy_server imports
the official SDK -- and the SDK's runner stamps the required result-type
field on every result it serializes (mcp 2.0.0, Runner._serialize), so an
SDK-based server has nowhere to put it and nothing to fix. Telling those
authors to add it is a false positive on every SDK server there is.

A project like this one is the case where the finding is real: it owns the
response envelope end to end, so the missing field is genuinely on the wire
and genuinely the author's to fix.

Do not write the field name itself anywhere in this file. R015 treats a
mention anywhere in the text -- docstring or comment included -- as evidence
the field is handled, which is deliberate (a wrong "still missing" claim
costs more than a generous read), and it would silence this fixture.
"""
from __future__ import annotations

import json


def handle(request: dict) -> str:
    method = request.get("method")

    if method == "tools/list":
        return json.dumps({
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": {"tools": [{"name": "echo", "description": "Echo input"}]},
        })

    if method == "tools/call":
        return json.dumps({
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": {"content": [{"type": "text", "text": "ok"}]},
        })

    return json.dumps({
        "jsonrpc": "2.0",
        "id": request.get("id"),
        "error": {"code": -32601, "message": "Method not found"},
    })
