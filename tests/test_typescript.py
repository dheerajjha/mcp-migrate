"""The TypeScript language backend, and the two reference rule ports.

Most MCP servers are TypeScript, so this is the scaffold that lets the
remaining 19 rules be ported one at a time -- see the issues linked from
#30. R001 and R006 are the worked examples to copy.

The load-bearing idea: a rule declares `languages`, and the engine hands it
a Project view containing only files in that language. A Python rule
therefore never sees a `.ts` file, which matters because `search_code`
tokenizes as Python -- a TypeScript file fails to tokenize, falls back to
unfiltered raw matching, and every Python rule would quietly start
reporting matches out of TypeScript comments.
"""
from __future__ import annotations

import json

import pytest

from mcp_migrate.cli import main, run_check
from mcp_migrate.rules import all_rules
from mcp_migrate.rules.base import Project, SourceFile, _ts_spans
from mcp_migrate.rules.r001_session_id_removed import SessionIdRemoved
from mcp_migrate.rules.r003_routing_headers import MissingRoutingHeaders
from mcp_migrate.rules.r006_sse_transport_deprecated import DeprecatedSSETransport
from mcp_migrate.rules.r005_extensions import NoExtensionsDeclared
from mcp_migrate.scan import load_project

LEGACY_TS = """\
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { SSEServerTransport } from "@modelcontextprotocol/sdk/server/sse.js";

export async function handleStreamable(req, res, sessions) {
  const sessionId = req.headers["mcp-session-id"] as string | undefined;
  if (sessionId) {
    return sessions.get(sessionId);
  }
}

export function mountSse(app) {
  app.get("/sse", async (req, res) => {
    const transport = new SSEServerTransport("/messages", res);
    await server.connect(transport);
  });
}
"""

CLEAN_TS = """\
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";

// We dropped the Mcp-Session-Id header and the /sse route in the 2026-07-28
// migration; handles are ordinary tool arguments now.
export async function handle(req, res) {
  const transport = new StreamableHTTPServerTransport();
  await server.connect(transport);
}
"""


def _write(tmp_path, name, text):
    (tmp_path / name).write_text(text)
    return tmp_path


# --- the two ported rules -------------------------------------------------

def test_r001_finds_the_header_in_typescript(tmp_path):
    project = load_project(_write(tmp_path, "transport.ts", LEGACY_TS))
    findings = SessionIdRemoved().check(project.for_language("typescript"))
    assert len(findings) == 1
    assert findings[0].line == 5


def test_r006_finds_sse_in_typescript(tmp_path):
    project = load_project(_write(tmp_path, "transport.ts", LEGACY_TS))
    findings = DeprecatedSSETransport().check(project.for_language("typescript"))
    # The SDK import, the route literal, and the constructor.
    assert len(findings) >= 2


def test_neither_fires_on_a_migrated_typescript_server(tmp_path):
    # The comment names both removed things. A comment is not a use --
    # this is the whole reason the TS backend has comment-aware spans.
    project = load_project(_write(tmp_path, "transport.ts", CLEAN_TS)).for_language("typescript")
    assert SessionIdRemoved().check(project) == []
    assert DeprecatedSSETransport().check(project) == []


def test_r003_finds_missing_headers_in_typescript(tmp_path):
    code = """\
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";

export async function callTool(url: string, payload: any) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ method: "tools/call", params: payload })
  });
  return res.json();
}
"""
    project = load_project(_write(tmp_path, "client.ts", code))
    findings = MissingRoutingHeaders().check(project.for_language("typescript"))
    assert len(findings) == 1
    assert findings[0].line == 4
    assert "Mcp-Method" in findings[0].message


def test_r003_stays_silent_on_migrated_typescript_client(tmp_path):
    code = """\
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";

export async function callTool(url: string, payload: any) {
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Mcp-Method": "tools/call",
      "Mcp-Name": "my-tool"
    },
    body: JSON.stringify({ method: "tools/call", params: payload })
  });
  return res.json();
}
"""
    project = load_project(_write(tmp_path, "client.ts", code)).for_language("typescript")
    assert MissingRoutingHeaders().check(project) == []


def test_r003_ignores_http_calls_named_only_in_comment(tmp_path):
    code = """\
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";

// Legacy note: we used fetch(url) to send tools/call without Mcp-Method or Mcp-Name
export const info = "Migration complete";
"""
    project = load_project(_write(tmp_path, "client.ts", code)).for_language("typescript")
    assert MissingRoutingHeaders().check(project) == []


def test_r001_ignores_the_header_named_only_in_prose(tmp_path):
    project = load_project(_write(
        tmp_path, "docs.ts",
        '// Migration note: we used to read mcp-session-id here.\n'
        '/** The mcp-session-id header is gone in 2026-07-28. */\n'
        'export const NOTE = 1;\n',
    )).for_language("typescript")
    assert SessionIdRemoved().check(project) == []



# --- R005: extensions map on ServerCapabilities --------------------------

def test_r005_finds_missing_extensions_in_typescript(tmp_path):
    code = """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { ServerCapabilities } from "@modelcontextprotocol/sdk/types.js";

const capabilities: ServerCapabilities = {
  tools: { listChanged: true },
  resources: { listChanged: true },
};

const server = new Server({ name: "my-server", version: "1.0.0" }, { capabilities });
"""
    project = load_project(_write(tmp_path, "server.ts", code)).for_language("typescript")
    findings = NoExtensionsDeclared().check(project)
    assert len(findings) == 1
    assert "extensions" in findings[0].message


def test_r005_stays_silent_on_migrated_typescript_server(tmp_path):
    code = """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { ServerCapabilities } from "@modelcontextprotocol/sdk/types.js";

const capabilities: ServerCapabilities = {
  extensions: {},
  tools: { listChanged: true },
};

const server = new Server({ name: "my-server", version: "1.0.0" }, { capabilities });
"""
    project = load_project(_write(tmp_path, "server.ts", code)).for_language("typescript")
    assert NoExtensionsDeclared().check(project) == []


def test_r005_ignores_servercapabilities_named_only_in_comment(tmp_path):
    code = """\
// ServerCapabilities should include an extensions map in 2026-07-28.
// The capabilities object passed to new Server needs extensions too.
export const NOTE = 1;
"""
    project = load_project(_write(tmp_path, "docs.ts", code)).for_language("typescript")
    assert NoExtensionsDeclared().check(project) == []


def test_r005_finds_missing_extensions_in_constructor_pattern(tmp_path):
    # The common TS pattern: capabilities passed to new Server without
    # an explicit ServerCapabilities type reference. The type is inferred
    # from the constructor, so signal 2 (SDK import + capabilities prop)
    # is what catches this.
    code = """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";

const server = new Server(
  { name: "my-server", version: "1.0.0" },
  {
    capabilities: {
      tools: { listChanged: true },
    }
  }
);
"""
    project = load_project(_write(tmp_path, "server.ts", code)).for_language("typescript")
    findings = NoExtensionsDeclared().check(project)
    assert len(findings) == 1
    assert "extensions" in findings[0].message


def test_r005_stays_silent_on_non_mcp_typescript(tmp_path):
    # capabilities: {} is an ordinary property name. Without an SDK import
    # this is not an MCP server, so the rule stays quiet.
    code = """\
const config = {
  capabilities: {
    maxRetries: 3,
  }
};
"""
    project = load_project(_write(tmp_path, "config.ts", code)).for_language("typescript")
    assert NoExtensionsDeclared().check(project) == []

# --- the language split itself --------------------------------------------

def test_python_rules_never_see_typescript_files(tmp_path):
    # A .ts file whose *comment* contains Python-rule bait. If a Python
    # rule ever received this file, search_code would fail to tokenize it,
    # fall back to raw matching, and report the comment.
    (tmp_path / "bait.ts").write_text(
        "// InitializeRequest ServerCapabilities resources/subscribe ping\n"
        "export const x = 1;\n"
    )
    (tmp_path / "ok.py").write_text("import httpx\n")
    _project, _rules, findings, _value, _grade = run_check(tmp_path)
    ts_bait = [f for f in findings if f.path and str(f.path).endswith(".ts")]
    assert ts_bait == [], f"a Python rule read a TypeScript file: {ts_bait}"


def test_every_rule_declares_at_least_one_language():
    for rule in all_rules():
        assert rule.languages, f"{rule.id} declares no languages"
        assert "python" in rule.languages or "typescript" in rule.languages


def test_declaration_files_are_skipped(tmp_path):
    (tmp_path / "types.d.ts").write_text('export declare const x: "mcp-session-id";\n')
    project = load_project(tmp_path)
    assert project.files == [], "generated .d.ts is build output, not an implementation"


# --- a TypeScript tree is scanned but not graded --------------------------

def test_typescript_only_tree_reports_findings_without_a_grade(tmp_path, capsys):
    exit_code = main(["check", str(_write(tmp_path, "transport.ts", LEGACY_TS)), "--json"])
    data = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert data["scannable"] is False
    assert data["grade"] is None
    assert data["score"] is None
    assert data["findings"], "the ported rules did run -- their findings are real"
    assert any(f["rule"] == "R001" for f in data["findings"])
    assert "partial" in data["reason"]


def test_partial_coverage_is_stated_with_a_denominator(tmp_path, capsys):
    main(["check", str(_write(tmp_path, "transport.ts", LEGACY_TS))])
    # Collapse whitespace: rich wraps at terminal width and will happily
    # split the fraction across two lines.
    out = " ".join(capsys.readouterr().out.split())
    assert "4 of 21" in out, (
        "someone deciding whether to trust this needs the coverage fraction, "
        "and it should move as rules get ported"
    )


# --- the comment/string scanner -------------------------------------------

@pytest.mark.parametrize("text,expect_covered", [
    ('const a = "x"; // note\n', True),
    ("/* block */\nconst b = 1;\n", True),
    ("const c = `template`;\n", True),
])
def test_ts_spans_cover_comments_and_strings(text, expect_covered):
    assert bool(_ts_spans(text, prose_only=False)) is expect_covered


def test_ts_prose_spans_exclude_string_literals():
    text = 'const m = "resources/subscribe"; // resources/subscribe\n'
    prose = _ts_spans(text, prose_only=True)
    content = _ts_spans(text, prose_only=False)
    assert len(prose) == 1, "only the comment is prose"
    assert len(content) == 2, "the string counts as content too"


def test_ts_scanner_handles_escapes_and_unterminated_strings():
    # A backslash-escaped quote must not end the string, and a stray quote
    # must not swallow the rest of the file.
    text = 'const a = "he said \\"hi\\"";\nconst b = 1;\n'
    spans = _ts_spans(text, prose_only=False)
    assert all(s[0][0] == 1 for s in spans), f"string leaked past line 1: {spans}"
