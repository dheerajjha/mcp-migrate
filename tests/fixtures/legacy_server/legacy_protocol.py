"""Hand-rolled JSON-RPC dispatch for a custom transport shim.

Predates several pieces of core protocol surface that the 2026-07-28 spec
revision removes or replaces outright (SEP-2575, SEP-2663): ping,
logging/setLevel, resources/subscribe + resources/unsubscribe, and the
blocking tasks/list + tasks/result pair. Kept only as a migration example;
see server.py for the SDK-based handlers this server also exposes.
"""
from __future__ import annotations

from mcp.types import (
    GetTaskPayloadRequest,
    ListTasksRequest,
    PingRequest,
    SetLevelRequest,
    SubscribeRequest,
    UnsubscribeRequest,
)

RESOURCE_NOT_FOUND = -32002  # legacy resource-not-found code; now sent as -32602


async def dispatch(method: str, params: dict) -> dict:
    """Route a raw JSON-RPC method name to its legacy handler."""
    if method == "ping":
        return {}
    if method == "logging/setLevel":
        return {}
    if method == "resources/subscribe":
        return {"ok": True}
    if method == "resources/unsubscribe":
        return {"ok": True}
    if method == "tasks/list":
        return {"tasks": []}
    if method == "tasks/result":
        return {"result": None}
    raise LookupError(f"no resource matches {method}", RESOURCE_NOT_FOUND)


async def handle_ping(request: PingRequest) -> dict:
    return {}


async def handle_set_level(request: SetLevelRequest) -> dict:
    return {}


async def handle_subscribe(request: SubscribeRequest) -> dict:
    return {"ok": True}


async def handle_unsubscribe(request: UnsubscribeRequest) -> dict:
    return {"ok": True}


async def handle_tasks_list(request: ListTasksRequest) -> dict:
    return {"tasks": []}


async def handle_tasks_result(request: GetTaskPayloadRequest) -> dict:
    return {"result": None}
