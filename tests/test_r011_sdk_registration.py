"""R011 SDK registration shape left open by #310 after #313 shipped R013."""
from mcp_migrate.rules.r011_ping_removed import PingRemoved
from mcp_migrate.scan import load_project


def test_r011_fires_on_sdk_constructor_keyword(tmp_path):
    (tmp_path / "server.py").write_text(
        "from mcp.server import Server\n"
        "\n"
        "async def ping(context):\n"
        "    return {}\n"
        "\n"
        "server = Server('demo', on_ping=ping)\n"
    )
    findings = PingRemoved().check(load_project(tmp_path))
    assert any("on_ping=" in (f.snippet or "") for f in findings)
    assert all(f.rule_id == "R011" for f in findings)
    assert all("SDK" in f.message for f in findings)


def test_r011_fires_on_black_formatted_constructor(tmp_path):
    (tmp_path / "server.py").write_text(
        "from mcp.server import Server\n"
        "\n"
        "async def ping(context):\n"
        "    return {}\n"
        "\n"
        "server = Server(\n"
        '    "demo",\n'
        "    on_ping=ping,\n"
        ")\n"
    )
    findings = PingRemoved().check(load_project(tmp_path))
    assert any("on_ping=" in (f.snippet or "") for f in findings)
    assert all(f.rule_id == "R011" for f in findings)


def test_r011_fires_on_mcpserver_constructor_keyword(tmp_path):
    (tmp_path / "server.py").write_text(
        "server = MCPServer('demo', on_ping=ping)\n"
    )
    findings = PingRemoved().check(load_project(tmp_path))
    assert any("on_ping=" in (f.snippet or "") for f in findings)


def test_r011_ignores_on_ping_outside_server_call(tmp_path):
    (tmp_path / "server.py").write_text(
        "options = dict(on_ping=ping)\n"
        "register(on_ping=ping)\n"
    )
    findings = PingRemoved().check(load_project(tmp_path))
    assert findings == []


def test_r011_ignores_on_ping_in_docstring_and_comment(tmp_path):
    (tmp_path / "server.py").write_text(
        '"""2.x registers ping with Server(..., on_ping=ping)."""\n'
        "# on_ping= is mentioned only here\n"
        "def health():\n"
        "    return 'ok'\n"
    )
    findings = PingRemoved().check(load_project(tmp_path))
    assert findings == []
