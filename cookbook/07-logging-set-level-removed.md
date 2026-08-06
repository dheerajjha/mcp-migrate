# `logging/setLevel` removed

- **Rule:** [R012](../src/mcp_migrate/rules/r012_logging_set_level_removed.py)
- **Fixer:** none yet on `main`, see [#22](https://github.com/dheerajjha/mcp-migrate/issues/22)
  (a `review`-confidence fixer is up in [#125](https://github.com/dheerajjha/mcp-migrate/pull/125))
- **Severity:** breaking
- **Spec:** SEP-2575 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

## What broke

`logging/setLevel` (and `SetLevelRequest`) is gone -- there's no more single,
process-wide log level a client can push to a server. Log level is now
per-request: read off `_meta["io.modelcontextprotocol/logLevel"]` on each
incoming request instead of tracking one mutable global. A server that still
implements `setLevel` never gets it called by a 2026-07-28 client, so any
logic gating verbosity on that stored level effectively freezes at whatever
level it was last set to (or its default) forever.

## Before

```python
_log_level = "info"

async def handle_request(method: str, params: dict) -> dict:
    global _log_level
    if method == "logging/setLevel":
        _log_level = params["level"]
        return {}
    if _log_level == "debug":
        logger.debug("handling %s", method)
    return await dispatch(method, params)
```

## After

```python
async def handle_request(method: str, params: dict, meta: dict) -> dict:
    level = meta.get("io.modelcontextprotocol/logLevel", "info")
    if level == "debug":
        logger.debug("handling %s", method)
    return await dispatch(method, params)
```

## Gotchas

- **Python's stdlib `logging` is process-global by default**, which is the
  opposite of what per-request level control needs. A module-level
  `logging.getLogger(__name__).setLevel(...)` call still races every
  concurrent request against the same logger. `contextvars.ContextVar` set
  at the top of the request handler and read from a custom `Filter` (or
  just an `if level == "debug":` guard like above, if you don't need it to
  flow through every stdlib log call) is the usual way to make it
  request-scoped instead.
- **`_meta` is optional and per-request, not sticky.** A client that sent
  `logging/setLevel` once and expected it to apply to every subsequent
  request now has to send the `_meta` key on every request where it wants
  that level -- there's no equivalent of "set it once."
- **The rule's `search_wire` pass for the wire-string half only looks for
  the literal `logging/setLevel`.** A server that dispatches on some
  normalized/lowercased form of the method name (unusual, but possible)
  won't be caught by that half -- the `SetLevelRequest` identifier check is
  the more reliable of the two signals if your SDK exposes it.

## Spec link

https://modelcontextprotocol.io/specification/2026-07-28/changelog
