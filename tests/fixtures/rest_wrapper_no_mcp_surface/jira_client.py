"""A plain REST client for a third-party API (mirroring mcp-atlassian's
Confluence/Jira client modules) -- it hand-rolls `.post()` calls, but has
nothing to do with MCP's own wire protocol: no `mcp` import, no JSON-RPC
method-name literal anywhere in the file. Flagging this as "hand-rolling
MCP transport" was R003's worst false positive (19 hits / 475 penalty
points on mcp-atlassian, all ordinary Jira/Confluence REST calls), so this
file should produce zero R003 findings.
"""
from __future__ import annotations

import httpx


class JiraClient:
    def __init__(self, base_url: str, token: str) -> None:
        self._client = httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {token}"})

    def create_issue(self, payload: dict) -> dict:
        resp = self._client.post("/rest/api/3/issue", json=payload)
        resp.raise_for_status()
        return resp.json()

    def add_comment(self, issue_key: str, body: str) -> dict:
        resp = self._client.post(f"/rest/api/3/issue/{issue_key}/comment", json={"body": body})
        resp.raise_for_status()
        return resp.json()
