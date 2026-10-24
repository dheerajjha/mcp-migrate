"""R001 must not interpret a CORS array element as a header subscript."""
import json
from pathlib import Path

import pytest

from mcp_migrate.cli import main
from mcp_migrate.rules.base import Project, SourceFile
from mcp_migrate.rules.r001_session_id_removed import SessionIdRemoved


@pytest.mark.parametrize("source,line", [
    ('const sid = `${request.headers?.["mcp-session-id"]}`;\n', 1),
    ('const sid = `${getHeaders()["mcp-session-id"]}`;\n', 1),
    ('const sid = `session: ${\n  getHeaders()["mcp-session-id"]\n}`;\n', 2),
    ('const sid = `${({value: getHeaders()["mcp-session-id"]}).value}`;\n', 1),
    ('const sid = `${`nested ${getHeaders()["mcp-session-id"]}`}`;\n', 1),
])
def test_template_interpolation_header_reads_still_fire(source, line):
    findings = _findings(source)
    assert [(f.rule_id, f.line) for f in findings] == [("R001", line)]


@pytest.mark.parametrize("source", [
    'const help = `getHeaders()["mcp-session-id"]`;\n',
    'const help = `\\${getHeaders()["mcp-session-id"]}`;\n',
    'const help = `${"getHeaders()[\\\"mcp-session-id\\\"]"}`;\n',
    'const help = `${/* getHeaders()["mcp-session-id"] */ value}`;\n',
    'const help = `${value} getHeaders()["mcp-session-id"]`;\n',
])
def test_template_literal_text_and_interpolation_prose_remain_silent(source):
    assert _findings(source) == []


def _findings(source, language="typescript"):
    suffix = {"python": "py", "typescript": "ts", "javascript": "js"}[language]
    project = Project(
        root=Path("."),
        files=[SourceFile(Path(f"server.{suffix}"), source, language=language)],
    )
    return SessionIdRemoved().check(project)


@pytest.mark.parametrize("quote", ['"', "'", "`"])
@pytest.mark.parametrize("headers", [
    ["Mcp-Session-Id"],
    ["Mcp-Session-Id", "X-Request-Id"],
    ["X-Request-Id", "Mcp-Session-Id"],
    ["X-Request-Id", "Mcp-Session-Id", "X-Trace-Id"],
])
def test_typescript_cors_exposed_headers_are_silent_in_every_order(quote, headers):
    values = ", ".join(f"{quote}{header}{quote}" for header in headers)
    source = f"app.use(cors({{ exposedHeaders: [{values}] }}));\n"
    assert _findings(source) == []


@pytest.mark.parametrize("headers", [
    '["Mcp-Session-Id"]',
    '["Mcp-Session-Id", "X-Request-Id"]',
    '["X-Request-Id", "Mcp-Session-Id"]',
])
@pytest.mark.parametrize("language", ["python", "javascript"])
def test_existing_python_and_javascript_cors_silence_is_preserved(language, headers):
    source = (
        f"CORSMiddleware(app, expose_headers={headers})\n"
        if language == "python"
        else f"app.use(cors({{ exposedHeaders: {headers} }}));\n"
    )
    assert _findings(source, language) == []


@pytest.mark.parametrize("expression", [
    'request.headers["mcp-session-id"]',
    "request.headers['Mcp-Session-Id']",
    "request.headers[`Mcp-Session-Id`]",
    'request.headers [ "Mcp-Session-Id" ]',
    'metadata["mcp-session-id"]',
    'metadata [ "mcp-session-id" ]',
    'getHeaders()["mcp-session-id"]',
    'getHeaders() [ "mcp-session-id" ]',
    'allHeaders[0]["mcp-session-id"]',
    'getHeaders()?.["mcp-session-id"]',
    'request.headers!["mcp-session-id"]',
    'getHeaders()!["mcp-session-id"]',
    'allHeaders[0]!["mcp-session-id"]',
    '$["mcp-session-id"]',
    '{"mcp-session-id": "value"}["mcp-session-id"]',
])
def test_real_typescript_subscripts_still_fire(expression):
    source = f"const sid = {expression};\n"
    findings = _findings(source)
    assert [(f.rule_id, f.line, f.snippet) for f in findings] == [
        ("R001", 1, source.strip())
    ]


@pytest.mark.parametrize("source", [
    'const sid = request.headers.get("mcp-session-id");\n',
    'request.headers.set("Mcp-Session-Id", sid);\n',
    'request.headers.delete("Mcp-Session-Id");\n',
    'response.setHeader("Mcp-Session-Id", sid);\n',
])
def test_existing_typescript_header_methods_still_fire(source):
    assert len(_findings(source)) == 1


@pytest.mark.parametrize("source,line", [
    ('const sid = request.headers /* normalized */ ["mcp-session-id"];\n', 1),
    ('const sid = request.headers\n  ["mcp-session-id"];\n', 2),
    ('const sid = getHeaders() /* normalized */ ["mcp-session-id"];\n', 1),
    ('const sid = request.headers // normalized\n  ["mcp-session-id"];\n', 2),
    ('const sid = getHeaders()!\n  ["mcp-session-id"];\n', 2),
    ('const sid = request.headers[\n  "mcp-session-id"\n];\n', 2),
    ('const help = "a\\\nb";\nconst sid = request.headers /* x */ ["mcp-session-id"];\n', 3),
])
def test_subscripts_preserve_comment_and_newline_separators(source, line):
    findings = _findings(source)
    assert [(f.rule_id, f.line, f.snippet) for f in findings] == [
        ("R001", line, source.splitlines()[line - 1].strip())
    ]


@pytest.mark.parametrize("source", [
    'app.use(cors({ exposedHeaders: /* public */ ["Mcp-Session-Id"] }));\n',
    'app.use(cors({ exposedHeaders:\n  ["Mcp-Session-Id"] }));\n',
    'const help = `request.headers\n  ["mcp-session-id"]`;\n',
    'const value = getHeaders() /* first */;\n'
    'app.use(cors({ exposedHeaders: /* second */ ["Mcp-Session-Id"] }));\n',
])
def test_multiline_matching_keeps_cors_and_prose_silent(source):
    assert _findings(source) == []


def test_identifier_and_subscript_are_still_deduplicated():
    assert len(_findings('const mcpSessionId = request.headers["mcp-session-id"];\n')) == 1


@pytest.mark.parametrize("headers", [
    '["Mcp-Session-Id"]',
    '["Mcp-Session-Id", "X-Request-Id"]',
    '["X-Request-Id", "Mcp-Session-Id"]',
])
def test_actual_cli_does_not_fail_a_cors_exposure_list(tmp_path, capsys, headers):
    (tmp_path / "server.ts").write_text(
        f"app.use(cors({{ exposedHeaders: {headers} }}));\n", encoding="utf-8",
    )

    assert main(["check", str(tmp_path), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["findings"] == []
    assert report["counts"]["breaking"] == 0
    # TypeScript grading remains withheld pending #172.
    assert report["grade"] is None and report["score"] is None


def test_actual_cli_still_fails_a_real_header_read(tmp_path, capsys):
    (tmp_path / "server.ts").write_text(
        'const sid = request.headers["mcp-session-id"];\n', encoding="utf-8",
    )

    assert main(["check", str(tmp_path), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert [(f["rule"], f["line"]) for f in report["findings"]] == [("R001", 1)]
    assert report["counts"]["breaking"] == 1
