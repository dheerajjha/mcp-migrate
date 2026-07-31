"""An MCP server with domain helpers whose names merely contain "discover".

Mirrors mcp-atlassian, where `_try_discover_fields_from_existing_epic` and
`_discover_application_types` (Jira field/application probing -- nothing to
do with MCP) matched R010's old `\\bdef\\s+\\w*discover\\w*\\b` pattern and
silently convinced the rule the project already implemented the discovery
RPC. The whole project then escaped the check.

This server registers low-level MCP handlers and implements no discovery
RPC, so R010 must fire on it despite the helper names.

Note for anyone editing this fixture: do not write the literal wire method
name in this file -- R010 matches it with a deliberately permissive raw
search that counts a mention in a comment or docstring as evidence.
"""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

app = Server("issue-tracker")


def _try_discover_fields_from_existing_epic(project_key: str) -> dict[str, str]:
    """Probe an existing epic to learn this Jira instance's custom field ids."""
    return {"epic_name": "customfield_10011", "project": project_key}


def _discover_application_types() -> list[str]:
    """Ask the remote instance which linked applications it exposes."""
    return ["bitbucket", "fecru"]


class FieldDiscoverer:
    def discover_fields(self) -> dict[str, str]:
        return _try_discover_fields_from_existing_epic("ENG")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="create_issue",
            description="Create an issue",
            inputSchema={"type": "object", "properties": {}},
        )
    ]
