"""JavaScript coverage for R001 (removed Mcp-Session-Id)."""
from pathlib import Path

import pytest

from mcp_migrate.rules.base import Project, SourceFile
from mcp_migrate.rules.r001_session_id_removed import SessionIdRemoved


def _project(text: str, *, language: str = "javascript") -> Project:
    suffix = "js" if language == "javascript" else "ts"
    return Project(
        root=Path("."),
        files=[SourceFile(path=Path(f"server.{suffix}"), text=text, language=language)],
    )


def _findings(text: str):
    return SessionIdRemoved().check(_project(text))


@pytest.mark.parametrize(
    "code",
    [
        "const mcpSessionId = session.id;\n",
        "const MCP_SESSION_ID = session.id;\n",
        "module.exports = { mcpSessionId };\n",
    ],
)
def test_r001_finds_javascript_identifier_forms(code):
    findings = _findings(code)
    assert len(findings) == 1
    assert findings[0].line == 1


@pytest.mark.parametrize(
    "code",
    [
        'const id = req.headers["Mcp-Session-Id"];\n',
        "const id = req.header['mcp-session-id'];\n",
        "const id = req.headers?.[`mcp-session-id`];\n",
        'const id = req.headers.get("mcp-session-id");\n',
        'const id = req.headers?.get("mcp-session-id");\n',
        'req.headers.set("Mcp-Session-Id", id);\n',
        'req.headers?.delete("Mcp-Session-Id");\n',
        'res.setHeader("Mcp-Session-Id", id);\n',
    ],
)
def test_r001_finds_javascript_header_accesses(code):
    findings = _findings(code)
    assert len(findings) == 1
    assert findings[0].line == 1


def test_r001_deduplicates_identifier_and_header_on_the_same_line():
    findings = _findings('const mcpSessionId = req.headers["Mcp-Session-Id"];\n')
    assert len(findings) == 1


@pytest.mark.parametrize(
    "code",
    [
        '// mcpSessionId used to hold the old session header\nconst active = true;\n',
        '/* res.setHeader("Mcp-Session-Id", id); */\nconst active = true;\n',
        'const help = "Mcp-Session-Id is no longer required";\n',
        'const help = "mcpSessionId is legacy";\n',
    ],
)
def test_r001_ignores_comments_and_help_strings(code):
    assert _findings(code) == []


@pytest.mark.parametrize(
    "code",
    [
        'const id = metadata["mcp-session-id"];\n',
        'const id = req.sessionHeaders["mcp-session-id"];\n',
        'const id = req.headersByName["mcp-session-id"];\n',
        'response.resetHeader("mcp-session-id", id);\n',
        'response.unsetHeader("mcp-session-id");\n',
    ],
)
def test_r001_does_not_expand_header_like_names(code):
    assert _findings(code) == []


def test_r001_finds_commonjs_server_usage():
    code = """\
const http = require("node:http");

function handle(req, res) {
  const mcpSessionId = req.headers["mcp-session-id"];
  res.end("ok");
}

module.exports = { handle };
"""
    findings = _findings(code)
    assert len(findings) == 1
    assert findings[0].line == 4


def test_r001_keeps_existing_typescript_behavior():
    project = _project(
        'const mcpSessionId = req.headers["mcp-session-id"];\n',
        language="typescript",
    )
    findings = SessionIdRemoved().check(project)
    assert len(findings) == 1
    assert findings[0].line == 1
