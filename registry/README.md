# The board

One YAML file per MCP server. That is the whole contribution.

```bash
uvx mcp-migrate entry --repo your-org/your-server > registry/servers/your-server.yaml
```

Edit the `notes:` line, open a PR. CI validates the schema and regenerates the
board in the root README. No maintainer taste is applied — if the schema passes
and the repo exists, it gets merged.
