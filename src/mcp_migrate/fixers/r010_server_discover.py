"""Fixer for R010 -- registers request handlers but never implements server/discover.

This is a scaffold-inserting fixer, not a value-inserting one. A
`server/discover` response describes *this* server's protocol versions,
capabilities and identity, and only the person who owns the server knows
what those are -- a wrong value is what cookbook/02 warns about. What the
fixer can safely add is the handler skeleton: registered on the same
instance the existing handlers already use, with obviously-placeholder
values and a loud TODO, matching the scaffold the GOOD_FIRST_ISSUES entry
for R010 describes. Confidence "review": every inserted stub still needs a
human pass to fill in the real capabilities and delete the stub if the SDK
auto-implements server/discover.

`fix()` only ever sees one file's text, so it cannot reproduce `check()`'s
project-wide search for an existing server/discover (r016 documents this
same limit). It does apply the rule's own evidence and presence checks to
the file in front of it, which covers the common shape -- handlers and the
missing discover in the same module that registers them. Across files it
stays generous, because there it has no choice: a stub on the wrong of two
server files costs a human a few seconds to delete, a missing one costs a
silent spec violation nobody sees.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..rules.base import wire_method
from .base import Fixer, FixResult, SLASH_COMMENT_SUFFIXES

SPEC_URL = "https://modelcontextprotocol.io/specification/2026-07-28/changelog"
COOKBOOK = "cookbook/02-initialize-to-server-discover.md"

# --- Evidence, copied from rules/r010_server_discover_missing.py so the
# fixer and the rule agree on what "this file registers MCP request
# handlers" and what "server/discover is already implemented" look like --
# the same arrangement r016 makes with its rule. For the handler half the
# instance name is captured too: the stub must be registered on the *same*
# object the real handlers use, or `fix --write` drops an undefined name
# into the file and reports success.

_LOWLEVEL_HANDLER_RX = re.compile(
    r"@([\w.]+)\.(?:list_tools|call_tool|list_resources|read_resource|"
    r"list_prompts|get_prompt)\s*\("
)
_FASTMCP_EVIDENCE_RX = re.compile(
    r"\b\w*FastMCP\s*\(|"
    r"\bclass\s+\w+\s*\([^)]*\bFastMCP\b"
)
# Functional registration (`mcp.tool(name="x")(fn)`) is a plain call, not a
# decorator, so the second alternative has no `@`. A `self.tool(...)` shape
# is skipped further down: it is valid inside a class method but the scaffold
# is appended at module scope, where `self` means nothing.
_FASTMCP_RECEIVER_RX = re.compile(
    r"@([\w.]+)\.(?:tool|resource|prompt)\s*\("
    r"|([\w.]+)\.(?:tool|resource|prompt|add_tool|add_resource|add_prompt)\s*\("
)
_TS_SET_HANDLER_RX = re.compile(r"(\w+)\.set(?:Request|Notification)Handler\s*\(")
_TS_SDK_IMPORT_RX = re.compile(r"@modelcontextprotocol/sdk")
# The McpServer names (.tool(/.prompt(/...) are generic-looking, so -- same
# as the rule -- they only count together with the SDK itself imported.
_TS_REGISTER_RX = re.compile(
    r"(\w+)\.(?:registerTool|registerResource|registerPrompt|tool|resource|prompt)\s*\("
)

# --- Already-implemented discover, bounded end-to-end via wire_method() so
# a longer method/metric name like `server/discoverFoo` doesn't read as an
# implementation of server/discover (matches the rule's own gate).
#
# The wire half is checked line by line with comment lines excluded, which
# mirrors what search_wire does with prose: a `# TODO ... server/discover`
# admitting the gap is exactly the file this fixer exists to stub. A full
# line/commented-out code shape still counts, on purpose -- it can never
# make `check` go clean on its own, so a fixer declining there is the safe
# direction, never a contradiction of a clean grade.

_DISCOVER_CODE_RX = re.compile(
    r"@[\w.]*\.discover\s*\(|\bdef\s+(?:handle_|server_|on_)*discover\b"
)
_TS_DISCOVER_CODE_RX = re.compile(
    r"\b(?:handle|on|server)?[Dd]iscover\s*(?:\(|=|:)"
    r"|\bfunction\s+(?:handle|on|server)?[Dd]iscover\b"
)
_DISCOVER_WIRE_RX = re.compile(wire_method("server/discover"))

# The scaffold. `@@NAME@@` becomes the handler-registration instance's name
# (prefixed with `@` for the Python decorator), `@@PREFIX@@` the file's
# comment prefix, `@@SPEC@@`/`@@COOKBOOK@@` the guidance pointers. The code
# braces are literal because the template is spliced with str.replace, not
# format().
_PY_SCAFFOLD = """\
\n@@PREFIX@@TODO(mcp-migrate): this module registers request handlers but never implements
@@PREFIX@@server/discover. Stub inserted by mcp-migrate -- replace the placeholder
@@PREFIX@@protocol versions, capabilities and identity with this server's real ones,
@@PREFIX@@or delete the stub if the SDK already auto-implements server/discover.
@@PREFIX@@See @@SPEC@@ and @@COOKBOOK@@.
@@NAME@@.discover()
async def handle_server_discover(request=None) -> dict:
    return {
        "protocolVersions": ["2026-07-28"],
        "capabilities": {},
        "server": {"name": "<your-server-name>", "version": "<your-version>"},
    }
"""

_TS_SCAFFOLD = """\
\n@@PREFIX@@TODO(mcp-migrate): this module registers request handlers but never implements
@@PREFIX@@server/discover. Stub inserted by mcp-migrate -- replace the placeholder
@@PREFIX@@protocol versions, capabilities and identity with this server's real ones,
@@PREFIX@@or delete the stub if the SDK already auto-implements server/discover.
@@PREFIX@@See @@SPEC@@ and @@COOKBOOK@@.
@@NAME@@.setRequestHandler("server/discover", async () => ({
  protocolVersions: ["2026-07-28"],
  capabilities: {},
  server: { name: "<your-server-name>", version: "<your-version>" },
}));
"""


def _first_usable(names) -> str | None:
    """The first receiver name safe to reference at module scope."""
    for n in names:
        if n and n != "self" and not n.startswith("self."):
            return n
    return None


def _handler_instance(source: str, path: Path) -> str | None:
    """The name of the object the existing handlers are registered on, or
    None when there is no handler evidence (or only unscaffoldable shapes
    like `self.`), in which case the fixer must leave the file alone."""
    if path.suffix.lower() not in SLASH_COMMENT_SUFFIXES:
        candidates: list[str] = [m.group(1) for m in _LOWLEVEL_HANDLER_RX.finditer(source)]
        if _FASTMCP_EVIDENCE_RX.search(source):
            candidates.extend(
                m.group(1) or m.group(2) for m in _FASTMCP_RECEIVER_RX.finditer(source)
            )
        return _first_usable(candidates) if candidates else None

    lowlevel = _first_usable(m.group(1) for m in _TS_SET_HANDLER_RX.finditer(source))
    if lowlevel is not None:
        return lowlevel
    if _TS_SDK_IMPORT_RX.search(source):
        return _first_usable(m.group(1) for m in _TS_REGISTER_RX.finditer(source))
    return None


def _already_implements_discover(source: str, path: Path) -> bool:
    is_ts = path.suffix.lower() in SLASH_COMMENT_SUFFIXES
    if _TS_DISCOVER_CODE_RX.search(source) if is_ts else _DISCOVER_CODE_RX.search(source):
        return True
    line_comment = ("//",) if is_ts else ("#",)
    for line in source.splitlines():
        stripped = line.lstrip(" \t")
        if not stripped or stripped.startswith(line_comment):
            continue
        if _DISCOVER_WIRE_RX.search(line):
            return True
    return False


class ServerDiscoverFixer(Fixer):
    rule_id = "R010"
    title = "Scaffold a stub server/discover handler with a fill-in TODO"
    confidence = "review"

    def fix(self, source: str, path: Path) -> FixResult:
        if _already_implements_discover(source, path):
            return self.unchanged(source)
        name = _handler_instance(source, path)
        if name is None:
            return self.unchanged(source)

        if path.suffix.lower() not in SLASH_COMMENT_SUFFIXES:
            template, prefix, labelled = _PY_SCAFFOLD, "# ", f"@{name}"
        else:
            template, prefix, labelled = _TS_SCAFFOLD, "// ", name

        scaffold = (
            template.replace("@@NAME@@", labelled)
            .replace("@@PREFIX@@", prefix)
            .replace("@@SPEC@@", SPEC_URL)
            .replace("@@COOKBOOK@@", COOKBOOK)
        )
        if source and not source.endswith("\n"):
            source += "\n"
        return self.result(
            source + scaffold,
            ["appended a stub server/discover handler with a fill-in TODO"],
        )