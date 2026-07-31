# Protocol sessions removed: `Mcp-Session-Id` and per-connection state

- **Rule:** [R001](../src/mcp_migrate/rules/r001_session_id.py) (breaking, any
  read/write of `Mcp-Session-Id`), [R002](../src/mcp_migrate/rules/r002_connection_state.py)
  (breaking, module-level dict keyed by connection)
- **Fixer:** [R001](../src/mcp_migrate/fixers/r001_session_id.py) is `review`
  confidence -- it comments out the header read and leaves a `TODO`, it does
  not (and can't) invent your new handle argument. R002 has no fixer: moving
  state into a real store is an architectural decision, not a text edit.
- **Severity:** breaking
- **Spec:** SEP-2567 -- https://github.com/modelcontextprotocol/modelcontextprotocol/pull/2567

## What broke

Before 2026-07-28, the Streamable HTTP transport minted a session at
`initialize` time and handed the client an `Mcp-Session-Id` header to send
back on every subsequent request. Servers used that header as a key into an
in-process dict to keep state between calls -- notes, a cursor position, an
open database transaction, whatever the tool needed to remember.

2026-07-28 removes protocol-level sessions entirely. There is no more
`Mcp-Session-Id` header, and servers are required to be stateless: any
instance behind a load balancer must be able to answer any request. Code
that reads `request.headers.get("Mcp-Session-Id")` gets `None` on every
request from a 2026-07-28 client (the header doesn't exist), and a
module-level `sessions: dict[str, State] = {}` becomes a memory leak that
also silently breaks the moment you run more than one server process --
each replica gets its own dict, so a client's second request can land on a
different replica than its first and find no state at all.

## Before

```python
from mcp.server import Server

sessions: dict[str, "SessionState"] = {}


class SessionState:
    def __init__(self, client_id: str) -> None:
        self.client_id = client_id
        self.notes: list[str] = []


server = Server("notes-server")


def _session_for(request) -> SessionState:
    mcp_session_id = request.headers.get("Mcp-Session-Id")
    if mcp_session_id is None:
        raise ValueError("missing Mcp-Session-Id header")
    if mcp_session_id not in sessions:
        sessions[mcp_session_id] = SessionState(mcp_session_id)
    return sessions[mcp_session_id]


@server.call_tool()
async def call_tool(name: str, arguments: dict, request=None):
    state = _session_for(request)
    if name == "add_note":
        state.notes.append(arguments["text"])
        return {"ok": True}
    if name == "get_notes":
        return {"notes": state.notes}
```

## After

```python
from mcp.server import Server

from .store import NoteStore

store = NoteStore()  # a real durable store -- a DB table, a keyed file, redis, ...
server = Server("notes-server")


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    # The client now passes its own handle as an ordinary tool argument --
    # there's no protocol-level session to derive it from. What the handle
    # *is* (a UUID the client mints and remembers, an account ID, a
    # notebook ID) is a decision for your API, not the protocol.
    handle = arguments["handle"]
    if name == "add_note":
        store.append(handle, arguments["text"])
        return {"resultType": "complete", "ok": True}
    if name == "get_notes":
        return {"resultType": "complete", "notes": store.read(handle)}
```

(`resultType` is a separate, unrelated required field -- see
[recipe 05](05-result-type-and-cache-metadata.md) -- included above only so
this snippet doesn't look like it's using two different response shapes.)

## Gotchas

- **The handle is not a session.** A session was minted by the server and
  scoped to one connection's lifetime. A handle is just an ordinary
  argument the client supplies and the server resolves against durable
  storage -- it has no connection lifecycle at all. Don't recreate a
  session by giving the handle a server-side expiry tied to "the client
  disconnected."
- **`mcp-migrate fix` only neutralizes the header read.** It comments out
  the `.headers.get("Mcp-Session-Id")` line and leaves a `TODO` immediately
  above it so the file doesn't silently look done -- it will not run
  because whatever used the old return value (`state = sessions[...]`) is
  still there and now references a variable that's commented out. You have
  to design the store and thread the handle through every tool signature
  by hand.
- **Look for the state dict under other names too.** R002's heuristic
  matches identifiers containing `sessions`, `session_store`,
  `connections`, `client_state`, `per_session`, etc. -- but a rename like
  `_clients` or `active_conns` won't trip it. Grep your own codebase for any
  module-level mutable container keyed by something connection-shaped.
- **Multi-process deployments surface this immediately; single-process
  deployments don't**, which is exactly why it's easy to miss in local
  testing. If your CI only ever runs one replica, this bug ships clean and
  breaks in production the first time you scale out.

## Spec link

https://github.com/modelcontextprotocol/modelcontextprotocol/pull/2567
