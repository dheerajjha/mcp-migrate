from .base import Finding, Project, Rule


class SessionIdRemoved(Rule):
    id = "R001"
    title = "Uses Mcp-Session-Id, which no longer exists"
    severity = "breaking"
    spec_ref = "SEP-2567 https://github.com/modelcontextprotocol/modelcontextprotocol/pull/2567"
    fix = (
        "Sessions are gone from the transport. Mint an explicit handle server-side "
        "and take it as an ordinary tool argument instead."
    )

    def check(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        # search_code, not search: a docstring, --help string, or log
        # message that merely *mentions* Mcp-Session-Id isn't code that
        # uses it (see motherduck's click.option help text, mcp-atlassian's
        # logger.debug call -- both false positives under plain search).
        for f, line, text in project.search_code(r"Mcp-Session-Id|mcp_session_id|MCP_SESSION_ID"):
            out.append(self.finding(
                "Mcp-Session-Id was removed from the Streamable HTTP transport.",
                f, line, text,
            ))
        return out
