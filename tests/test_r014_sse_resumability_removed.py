"""Python R014 header reads must not depend on the receiving variable (#334)."""
import json

import pytest

from mcp_migrate.cli import main
from mcp_migrate.rules.r014_sse_resumability_removed import SSEResumabilityRemoved
from mcp_migrate.scan import load_project


MCP_CONTEXT = 'from mcp.server import Server\nserver = Server("demo")\n'


@pytest.mark.parametrize("header", ["Last-Event-ID", "last-event-id"])
@pytest.mark.parametrize("quote", ['"', "'"])
@pytest.mark.parametrize("read", [
    "cursor = request.headers.get({key})",
    "last_id = request.headers[{key}]",
])
def test_python_header_read_fires(tmp_path, header, quote, read):
    source = read.format(key=f"{quote}{header}{quote}") + "\n"
    path = tmp_path / "server.py"
    path.write_text(MCP_CONTEXT + source)

    findings = SSEResumabilityRemoved().check(load_project(tmp_path))

    assert [(f.path.name, f.line) for f in findings] == [("server.py", 3)]
    assert findings[0].snippet == source.strip()


def test_python_deduplicates_per_file_and_line(tmp_path):
    source = (
        'cursor = request.headers.get("Last-Event-ID")\n'
        'last_event_id = request.headers.get("Last-Event-ID")\n'
        'LAST_EVENT_ID = last_event_id\n'
    )
    for name in ("one.py", "two.py"):
        (tmp_path / name).write_text(MCP_CONTEXT + source)

    findings = SSEResumabilityRemoved().check(load_project(tmp_path))

    assert [(f.path.name, f.line) for f in findings] == [
        (name, line) for name in ("one.py", "two.py") for line in (3, 4, 5)
    ]


@pytest.mark.parametrize("source", [
    '# cursor = request.headers.get("Last-Event-ID")\n',
    '\'\'\'Read "Last-Event-ID" or last_event_id in older servers.\'\'\'\n',
    '"""Legacy transport.\nrequest.headers["Last-Event-ID"]\nlast_event_id\n"""\n',
    'NOTICE = "Last-Event-ID resumability was removed"\n',
    'NOTICE = "last_event_id is an old variable name"\n',
    'cursor = request.headers.get("X-Last-Event-ID")\n',
    'cursor = request.headers.get("Last-Event-ID-Suffix")\n',
])
def test_python_prose_and_unrelated_headers_stay_silent(tmp_path, source):
    (tmp_path / "server.py").write_text(MCP_CONTEXT + source)
    assert SSEResumabilityRemoved().check(load_project(tmp_path)) == []


def test_python_browser_chat_sse_stays_silent_in_an_mcp_project(tmp_path):
    # An MCP server elsewhere in the project must not turn an ordinary
    # browser EventSource stream into an MCP transport finding.
    (tmp_path / "server.py").write_text(MCP_CONTEXT)
    (tmp_path / "routes.py").write_text(
        "from starlette.requests import Request\n"
        "from starlette.responses import StreamingResponse\n"
        "from starlette.routing import Route\n"
        "\n"
        "async def events(request: Request):\n"
        '    marker = request.headers.get("last-event-id") or ""\n'
        '    return StreamingResponse(chat_events_after(marker), media_type="text/event-stream")\n'
        "\n"
        'routes = [Route("/chat/events", events)]\n'
    )
    assert SSEResumabilityRemoved().check(load_project(tmp_path)) == []


@pytest.mark.parametrize("identifier", ["last_event_id", "LAST_EVENT_ID"])
def test_python_identifier_still_fires_without_mcp_context(tmp_path, identifier):
    (tmp_path / "server.py").write_text(f"{identifier} = cursor\n")
    findings = SSEResumabilityRemoved().check(load_project(tmp_path))
    assert [(f.path.name, f.line) for f in findings] == [("server.py", 1)]


@pytest.mark.parametrize("context", [
    "import mcp.server as sdk\n",
    "from mcp.server import Server as MCPServer\n",
    'message = {"method": "tools/call"}\n',
])
def test_python_header_with_independent_mcp_surface_fires(tmp_path, context):
    (tmp_path / "server.py").write_text(
        context + 'cursor = headers.get("last-event-id")\n'
    )
    findings = SSEResumabilityRemoved().check(load_project(tmp_path))
    assert [(f.path.name, f.line) for f in findings] == [("server.py", 2)]


def test_python_header_check_and_fix_agree(tmp_path, capsys):
    path = tmp_path / "server.py"
    source = 'cursor = request.headers.get("Last-Event-ID")\n'
    path.write_text(MCP_CONTEXT + source)

    assert main(["check", str(tmp_path), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert (report["grade"], report["score"]) == ("C", 75)
    assert [(f["rule"], f["line"]) for f in report["findings"]] == [("R014", 3)]

    main(["fix", str(tmp_path), "--rule", "R014", "--write"])
    capsys.readouterr()
    assert path.read_text() != MCP_CONTEXT + source
    assert "# TODO(mcp-migrate):" in path.read_text()
    assert main(["check", str(tmp_path), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert (report["grade"], report["score"]) == ("A", 100)
    assert report["findings"] == []
