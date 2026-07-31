import re

from .base import Finding, Project, Rule

# Evidence the project registers real MCP request handlers -- the
# low-level SDK's own decorator names (list_tools, call_tool, ...) are
# distinctive enough on their own to use directly.
LOWLEVEL_HANDLER_RX = re.compile(
    r"@[\w.]*\.(?:list_tools|call_tool|list_resources|read_resource|"
    r"list_prompts|get_prompt)\s*\("
)
# Evidence that FastMCP is in play at all. A bare `FastMCP(` misses the two
# shapes real servers actually use, both verified against source:
#   * subclassing -- `class QdrantMCPServer(FastMCP)` in mcp-server-qdrant,
#     `class S3TablesMCPServer(FastMCP)` in awslabs/mcp. The name is never
#     followed by `(` in that position, so the old pattern never matched.
#   * instantiating a subclass whose name merely *ends* in FastMCP --
#     `ErrorPreservingFastMCP(...)` in mcp-atlassian. `\bFastMCP` cannot match
#     mid-identifier, so that missed too.
FASTMCP_EVIDENCE_RX = re.compile(
    r"\b\w*FastMCP\s*\(|"                    # FastMCP(...) / ErrorPreservingFastMCP(...)
    r"\bclass\s+\w+\s*\([^)]*\bFastMCP\b"    # class X(FastMCP) / class X(FastMCP[T])
)

# FastMCP's own registration names (`.tool(`, `.resource(`, `.prompt(`) are far
# more generic-looking than the low-level ones, so they only count as "has
# handlers" together with FASTMCP_EVIDENCE_RX in the same project -- a project
# that imports some unrelated, coincidentally-named `mcp` package and happens
# to have a `.tool(`-decorated function elsewhere would not trip this alone.
#
# Registration is not always a decorator. Both idioms are real:
#   @mcp.tool()                                    -- decorator
#   mcp.tool(name='get_active_alarms')(self.get_active_alarms)  -- cloudwatch
#   self.tool(find_foo, name="qdrant-find")        -- mcp-server-qdrant
# Matching only the decorator form handed an unearned A to every server that
# registers functionally, which is a grading fairness bug, not a detection
# nicety: those servers were never checked at all.
FASTMCP_DECORATOR_RX = re.compile(r"@[\w.]*\.(?:tool|resource|prompt)\s*\(")
FASTMCP_FUNCTIONAL_RX = re.compile(
    r"\b[\w.]+\.(?:tool|resource|prompt|add_tool|add_resource|add_prompt)\s*\("
)

# Evidence the project implements server/discover. The method name is a
# JSON-RPC string (can't be a bare identifier -- see the notifications/
# initialized note in r009), so it needs a raw scan; a `discover`-named
# handler function/decorator is code, so search_code covers that half.
#
# The function-name half must be anchored to the *whole* name. The previous
# `\bdef\s+\w*discover\w*\b` matched any identifier merely containing the
# substring, so Jira's `_try_discover_fields_from_existing_epic` and
# `_discover_application_types` (both in mcp-atlassian) read as "implements
# server/discover" and silently suppressed this rule for the entire project.
# That is the worst failure mode available here: not a false finding a
# maintainer can argue with, but a missing one nobody ever sees.
DISCOVER_CODE_RX = re.compile(
    r"@[\w.]*\.discover\s*\(|\bdef\s+(?:handle_|server_|on_)*discover\b"
)


def _has_request_handlers(project: Project) -> bool:
    if any(project.search_code(LOWLEVEL_HANDLER_RX.pattern)):
        return True
    if any(project.search_code(FASTMCP_EVIDENCE_RX.pattern)) and (
        any(project.search_code(FASTMCP_DECORATOR_RX.pattern))
        or any(project.search_code(FASTMCP_FUNCTIONAL_RX.pattern))
    ):
        return True
    return False


def _has_discover(project: Project) -> bool:
    if any(project.search_code(DISCOVER_CODE_RX.pattern)):
        return True
    if any(project.search(r"server/discover")):
        return True
    return False


# Downgraded from "breaking" after auditing 14 real, actively-maintained
# servers against this rule: server/discover is a brand-new requirement
# introduced by the very spec revision this project checks against, so
# *every single project written before 2026-07-28* is guaranteed to be
# missing it -- there is no such thing as a real server that predates the
# spec and still passes. 11 of the 14 real servers scanned tripped this
# absence check, and the other 3 only escaped it because of unrelated gaps
# in handler-registration detection, not because they actually implement
# server/discover. A rule that fires identically on nearly every existing
# codebase doesn't distinguish a well-maintained project from a neglected
# one -- it just measures "was this written before the spec existed",
# which stacked with R015/R016 (same shape of absence check) would have
# put every reference server at F on launch day. Keep the finding (it's a
# real, accurate gap worth surfacing) but at the severity that matches how
# little it discriminates between projects.
class ServerDiscoverMissing(Rule):
    id = "R010"
    title = "Registers MCP request handlers but never implements server/discover"
    severity = "advisory"
    spec_ref = "SEP-2575 https://modelcontextprotocol.io/specification/2026-07-28/changelog"
    fix = (
        "Servers MUST implement server/discover so clients can learn supported protocol "
        "versions, capabilities and server identity before doing anything else. Add a "
        "handler for it alongside your other request handlers."
    )

    def check(self, project: Project) -> list[Finding]:
        # Gate hard on the project actually registering *some* MCP request
        # handler first -- a project with no handlers at all isn't an MCP
        # server (or is a client, or a library), and flagging it for
        # missing server/discover would just be noise unrelated to this
        # check's purpose.
        if not _has_request_handlers(project):
            return []
        if _has_discover(project):
            return []
        return [self.finding(
            "This project registers MCP request handlers (tools/resources/prompts) "
            "but has no server/discover implementation anywhere in the project."
        )]
