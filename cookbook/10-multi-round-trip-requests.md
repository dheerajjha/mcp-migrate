# Multi Round-Trip Requests replace server-initiated roots/sampling/elicitation

- **Rule:** [R018](../src/mcp_migrate/rules/r018_multi_round_trip_replaces_server_initiated.py)
  (breaking -- overlaps on purpose with [R007](../src/mcp_migrate/rules/r007_deprecated_features.py),
  which reports the same code `deprecated` rather than `breaking`; see that
  rule's source for why both fire)
- **Fixer:** none
- **Severity:** breaking
- **Spec:** SEP-2322 -- https://modelcontextprotocol.io/specification/2026-07-28/changelog

## What broke

Server-initiated `roots/list`, `sampling/createMessage` and
`elicitation/create` -- along with `notifications/elicitation/complete` and
`elicitationId` -- are gone. Previously, a server that needed more
information mid-call (ask the client to pick a root, ask the user's LLM to
sample something, elicit a missing argument from the user) sent its own
request back to the client and waited for a response inline. 2026-07-28
replaces all of that with Multi Round-Trip Requests: the server returns an
`InputRequiredResult` (`resultType: "input_required"`, see
[recipe 05](05-result-type-and-cache-metadata.md)) and the *client* re-issues
the original call with `inputResponses` once it has what the server asked
for. The server never initiates a request of its own.

## Before

```python
async def handle_tool_call(name: str, args: dict) -> dict:
    if name == "summarize":
        sample = await ctx.create_message(
            messages=[{"role": "user", "content": args["text"]}],
        )
        return {"summary": sample.content}
```

## After

```python
async def handle_tool_call(name: str, args: dict, input_responses: dict | None = None) -> dict:
    if name == "summarize":
        if input_responses is None:
            return {
                "resultType": "input_required",
                "requests": [{"kind": "sampling/createMessage", "id": "summarize-sample"}],
            }
        sample = input_responses["summarize-sample"]
        return {"summary": sample["content"]}
```

## Gotchas

- **This is the biggest control-flow change in the whole spec revision.** A
  synchronous "ask and block" call becomes two separate request/response
  pairs correlated by the client's retry. Whatever local state the handler
  needed between "asked" and "got the answer" can't sit on the stack of a
  blocked coroutine anymore -- it has to survive across the boundary
  somehow (a cache keyed on a request/call id, as above, or persisted state
  if the retry can arrive after a process restart).
- **R018 and R007 both fire on the same code, and that's intentional.**
  R007 reports the same `create_message`/`list_roots` usage as `deprecated`
  (it existed before this change and was already headed for removal); R018
  reports it as `breaking` under the new SEP. Seeing both on one line isn't
  a bug in either rule.
- **Correlating a retry to the original call needs an explicit id.** The
  request/response pair before this change was implicit (same coroutine,
  same call stack); after, the client's retry has to carry something the
  server can use to find the right piece of pending state. Design that id
  before touching the handler code -- it's the part a mechanical fixer
  can't invent for you, which is also why there's no fixer for this rule.

## Spec link

https://modelcontextprotocol.io/specification/2026-07-28/changelog
