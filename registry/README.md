# The board

One YAML file per MCP server. That is the whole contribution.

```bash
uvx mcp-migrate entry --repo your-org/your-server > registry/servers/your-server.yaml
```

Edit the `notes:` line, open a PR. CI validates the schema and regenerates the
board in the root README. No maintainer taste is applied — if the schema passes
and the repo exists, it gets merged.

## Who submitted it matters

Entries carry `submitted_by`, either `project` or `owner`.

`project` means we scanned a public repo and wrote the entry ourselves.
`owner` means someone who maintains that server submitted it. **Every entry
here is currently `project`** — which makes the board a survey, and the
headline above the table says so.

That distinction is the only thing that makes the board worth anything. A list
we compiled says we can run our own tool. A list projects opted into says the
grade meant something to the people being graded. Blurring the two would be the
same overclaiming this tool refuses everywhere else.

**If you maintain a server already listed here**, open a PR setting
`submitted_by: owner` and correcting anything we got wrong — the notes, the
status, the grade if it has moved since. It becomes your entry, and we take
your word over our scan. If you would rather not be listed at all, say so in an
issue and we remove it, no argument.
