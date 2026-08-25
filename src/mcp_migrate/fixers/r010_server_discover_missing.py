"""Scaffold a reviewable Python server/discover handler for R010.

The protocol versions, capabilities, identity, and SDK registration shape are
server-specific, so this fixer deliberately inserts placeholders and remains
review-only. It only acts when one unambiguous low-level server decorator is
present; FastMCP and functional registrations need a human to choose the
correct API.
"""
from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path

from ._textedit import string_lines
from .base import Fixer, FixResult

HANDLER_DECORATOR_RX = re.compile(
    r"^\s*@(?P<receiver>[A-Za-z_]\w*)\.(?:list_tools|call_tool|"
    r"list_resources|read_resource|list_prompts|get_prompt)\s*\("
)
DISCOVER_MARKER = "TODO(mcp-migrate): fill in your real server/discover values"


def _scaffold(receiver: str) -> str:
    return (
        "\n"
        f"# {DISCOVER_MARKER} and register this handler with the SDK's supported API.\n"
        f"@{receiver}.discover()\n"
        "async def handle_discover(request=None) -> dict:\n"
        "    return {\n"
        '        "protocolVersions": ["TODO: add supported protocol versions"],\n'
        '        "capabilities": {"TODO": "describe supported capabilities"},\n'
        '        "server": {"name": "TODO: replace with the real server name"},\n'
        "    }\n"
    )


def _has_discover_implementation(source: str, path: Path) -> bool:
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
        for index, token in enumerate(tokens):
            if token.type != tokenize.NAME:
                continue
            if token.string in {"discover", "handle_discover", "server_discover", "on_discover"}:
                previous = tokens[index - 1].string if index else ""
                if previous == "def":
                    return True
            if token.string == "discover":
                previous = tokens[index - 1].string if index else ""
                if previous == ".":
                    return True
        for token in tokens:
            if token.type == tokenize.STRING and "server/discover" in token.string:
                stripped = token.string.lstrip("rRbBuUfF")
                if not (stripped.startswith('"""') or stripped.startswith("'''")):
                    return True
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        return False
    return False


class ServerDiscoverFixer(Fixer):
    rule_id = "R010"
    title = "Add a review-only server/discover scaffold"
    confidence = "review"

    def fix(self, source: str, path: Path) -> FixResult:
        if path.suffix.lower() != ".py":
            return self.unchanged(source)
        if DISCOVER_MARKER in source or _has_discover_implementation(source, path):
            return self.unchanged(source)

        source_string_lines = string_lines(source, path)
        receivers: set[str] = set()
        for line_number, line in enumerate(source.splitlines(), start=1):
            if line_number in source_string_lines:
                continue
            match = HANDLER_DECORATOR_RX.match(line)
            if match:
                receivers.add(match.group("receiver"))

        if len(receivers) != 1:
            return self.unchanged(source)

        receiver = next(iter(receivers))
        separator = "" if not source or source.endswith("\n") else "\n"
        text = source + separator + _scaffold(receiver)
        return self.result(text, [
            "added a review-only server/discover scaffold with placeholder values",
        ])
