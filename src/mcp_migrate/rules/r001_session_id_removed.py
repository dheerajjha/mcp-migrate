import re

from .base import Finding, Project, Rule

# --- Python ---------------------------------------------------------------
PY_RX = r"Mcp-Session-Id|mcp_session_id|MCP_SESSION_ID"

# --- TypeScript -----------------------------------------------------------
#
# The identifier forms are safe to match anywhere, same as in Python.
TS_IDENT_RX = r"\bmcpSessionId\b|\bMCP_SESSION_ID\b"

# The header name itself, but only where it is being *used* as a header --
# indexed, read, or set. In TypeScript the header name is far more often a
# bare string literal than a variable (`req.headers["mcp-session-id"]`),
# so unlike the Python side this cannot be an identifier-only match. Anchor
# it to an access to keep prose and docs out: a README line or an error
# message naming the header is not a use of it.
TS_HEADER_RX = (
    r"headers?\s*(?:\[|\.get\s*\(|\.set\s*\(|\.delete\s*\()\s*"
    r"[\"'`]mcp-session-id[\"'`]"
    r"|[\"'`]mcp-session-id[\"'`]\s*\]"
    r"|setHeader\s*\(\s*[\"'`]mcp-session-id[\"'`]"
)


class SessionIdRemoved(Rule):
    id = "R001"
    title = "Uses Mcp-Session-Id, which no longer exists"
    severity = "breaking"
    spec_ref = "SEP-2567 https://github.com/modelcontextprotocol/modelcontextprotocol/pull/2567"
    fix = (
        "Sessions are gone from the transport. Mint an explicit handle server-side "
        "and take it as an ordinary tool argument instead."
    )
    languages = ("python", "typescript")

    MESSAGE = "Mcp-Session-Id was removed from the Streamable HTTP transport."

    def check(self, project: Project) -> list[Finding]:
        if project.language == "typescript":
            return self._check_ts(project)
        return self._check_python(project)

    def _check_python(self, project: Project) -> list[Finding]:
        # search_code, not search: a docstring, --help string, or log
        # message that merely *mentions* Mcp-Session-Id isn't code that
        # uses it (see motherduck's click.option help text, mcp-atlassian's
        # logger.debug call -- both false positives under plain search).
        return [
            self.finding(self.MESSAGE, f, line, text)
            for f, line, text in project.search_code(PY_RX)
        ]

    def _check_ts(self, project: Project) -> list[Finding]:
        # search_wire, not search_code: in TypeScript the header name lives
        # in a string literal, which search_code discards wholesale -- it
        # would find nothing at all. search_wire keeps string literals and
        # drops comments, which is exactly the split needed here.
        seen: set[tuple[str, int]] = set()
        out: list[Finding] = []
        for pattern in (TS_IDENT_RX, TS_HEADER_RX):
            for f, line, text in project.search_wire(pattern, flags=re.IGNORECASE):
                # The two patterns can both hit the same line
                # (`const mcpSessionId = req.headers["mcp-session-id"]`);
                # that is one problem, not two.
                if (str(f.path), line) in seen:
                    continue
                seen.add((str(f.path), line))
                out.append(self.finding(self.MESSAGE, f, line, text))
        return sorted(out, key=lambda x: (str(x.path or ""), x.line or 0))
