# Tasks moved to an extension; polling replaces blocking `tasks/result`

- **Rule:** [R019](../src/mcp_migrate/rules/r019_tasks_polling_replaces_blocking_result.py)
- **Fixer:** none
- **Severity:** breaking
- **Spec:** SEP-2663 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

## What broke

`tasks/list` is removed outright, and the old blocking `tasks/result` (wait
until a long-running task finishes, then get the result in one call) is
replaced by polling: `tasks/get` to check status, `tasks/update` to act on
it. Tasks as a whole also moves out of core protocol capabilities into the
`io.modelcontextprotocol/tasks` extension, so a server needs to declare it
there (see [recipe 16](16-extensions-map.md) for the `extensions` map
mechanics) rather than assuming it's always available.

## Before

```python
async def handle_request(method: str, params: dict) -> dict:
    if method == "tasks/result":
        task_id = params["taskId"]
        while not _tasks[task_id].done:
            await asyncio.sleep(1)
        return {"result": _tasks[task_id].result}
    if method == "tasks/list":
        return {"tasks": [t.summary() for t in _tasks.values()]}
```

## After

```python
async def handle_request(method: str, params: dict) -> dict:
    if method == "tasks/get":
        task_id = params["taskId"]
        task = _tasks[task_id]
        return {"status": task.status, "result": task.result if task.done else None}
    if method == "tasks/update":
        task_id, action = params["taskId"], params["action"]
        return await _apply_task_update(task_id, action)
```

```python
def declare_extensions() -> dict:
    return {"io.modelcontextprotocol/tasks": {}}
```

## Gotchas

- **`tasks/list` has no replacement -- it's just gone.** If your client
  relied on enumerating tasks, that has to be tracked client-side (e.g. by
  remembering the task ids it created) rather than asked of the server.
- **A blocking `while ... await asyncio.sleep(1)` loop server-side stops
  being the pattern; the client polls instead.** Don't reimplement the old
  blocking wait behind the new method names -- `tasks/get` should return
  immediately with current status, not block until done, or you've just
  moved the same problem one layer down.
- **Overlaps conceptually with R018's Multi Round-Trip Requests, but
  they're different mechanisms for different problems.** R018 is about a
  server needing *more input* mid-call (roots, sampling, elicitation);
  tasks are about work that's *long-running* and doesn't need more input,
  just time. A handler can use both in the same server without either rule
  double-reporting the other, since they match on different identifiers
  entirely.
- **Declaring the extension isn't optional busywork.** A 2026-07-28 client
  checks `extensions` before assuming task support exists at all -- without
  the `io.modelcontextprotocol/tasks` entry, a compliant client won't call
  `tasks/get`/`tasks/update` on your server regardless of whether you
  implement them.

## Spec link

https://modelcontextprotocol.io/specification/2026-07-28/changelog
