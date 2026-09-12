import re

from .base import Finding, Project, Rule

# --- Python ---------------------------------------------------------------
#
# Identifiers are safe to match anywhere search_code allows -- a real
# variable/constant named mcp_session_id or MCP_SESSION_ID is a use of the
# session id, wherever it appears in code.
PY_IDENT_RX = r"mcp_session_id|MCP_SESSION_ID"

# Mcp-Session-Id is not a valid Python identifier, so the header name can
# only ever appear inside a string literal. search_code discards every
# STRING token -- including that one -- so this alternative could never
# match anything there; it needs search_wire instead, and it needs to be
# anchored to an actual header access rather than a bare mention, for the
# same reason TS_HEADER_RX is anchored below (see comment_only_mentions
# fixture: a docstring/comment/log string naming the header is not a read
# or write of it, and search_wire does not filter those out on its own --
# only comments and triple-quoted strings are excluded).
PY_HEADER_RX = (
    r"headers?\s*(?:\[|\.get\s*\(|\.setdefault\s*\(|\.pop\s*\()\s*"
    r"b?[\"']mcp-session-id[\"']"
    r"|b?[\"']mcp-session-id[\"']\s*:\s"  # dict literal: {"mcp-session-id": ...}
)

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
        seen: set[tuple[str, int]] = set()
        out: list[Finding] = []

        # search_code, not search: a docstring, --help string, or log
        # message that merely *mentions* mcp_session_id isn't code that
        # uses it (see motherduck's click.option help text, mcp-atlassian's
        # logger.debug call -- both false positives under plain search).
        for f, line, text in project.search_code(PY_IDENT_RX):
            seen.add((str(f.path), line))
            out.append(self.finding(self.MESSAGE, f, line, text))

        # The header-literal form ("Mcp-Session-Id") only ever appears
        # inside a string, so it needs search_wire, not search_code --
        # anchored to an access so a bare mention still doesn't fire.
        for f, line, text in project.search_wire(PY_HEADER_RX, flags=re.IGNORECASE):
            # mcp_session_id = request.headers.get("Mcp-Session-Id") hits
            # both patterns on one line -- that's one problem, not two.
            if (str(f.path), line) in seen:
                continue
            seen.add((str(f.path), line))
            out.append(self.finding(self.MESSAGE, f, line, text))

        return sorted(out, key=lambda x: (str(x.path or ""), x.line or 0))

    def _check_ts(self, project: Project) -> list[Finding]:
        seen: set[tuple[str, int]] = set()
        out: list[Finding] = []

        # Identifiers (mcpSessionId, MCP_SESSION_ID) use search_code:
        # a log/comment/error-message string that merely mentions the
        # identifier isn't a real reference to it.
        for f, line, text in project.search_code(TS_IDENT_RX, flags=re.IGNORECASE):
            seen.add((str(f.path), line))
            out.append(self.finding(self.MESSAGE, f, line, text))

        # Header-string literals ("mcp-session-id") use search_wire:
        # the header name lives in a string literal, which search_code
        # discards wholesale -- it would find nothing at all. search_wire
        # keeps string literals and drops comments.
        for f, line, text in project.search_wire(TS_HEADER_RX, flags=re.IGNORECASE):
            # The two patterns can both hit the same line
            # (`const mcpSessionId = req.headers["mcp-session-id"]`);
            # that is one problem, not two.
            if (str(f.path), line) in seen:
                continue
            seen.add((str(f.path), line))
            out.append(self.finding(self.MESSAGE, f, line, text))
        return sorted(out, key=lambda x: (str(x.path or ""), x.line or 0))
