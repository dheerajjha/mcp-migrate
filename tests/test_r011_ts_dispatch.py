import pytest

from mcp_migrate.rules.r011_ping_removed import PingRemoved
from mcp_migrate.scan import load_project


@pytest.mark.parametrize(
    ("dispatch", "fires"),
    [
        ('if (method === "ping") runHealthCheck();', False),
        ('switch (method) { case "ping": break; }', False),
        ('switch (method) { case "initialize": break; case "ping": break; }', True),
        ('if (request.method === "tools/list") list(); else if (request.method === "ping") ping();', True),
        ('const handlers = { "tools/call": call, "ping": ping };', True),
        ('if (a.method === "tools/list") list(); else if (b.method === "ping") ping();', False),
        ('if (a?.method === "tools/list") list(); else if (a.method === "ping") ping();', False),
        ('switch (method) { case "ping": switch (other) { case "initialize": break; } }', False),
        ('const a = { "tools/call": call }; const b = { "ping": ping };', False),
        ('if (method === "ping") ping(); if (method === "tools/list") list();', True),
        ('if (a.method === "ping") ping(); if (b.method === "tools/list") list();', False),
        ('if (method === "ping") ping(); unrelated(); if (method === "tools/list") list();', False),
        ('if (status === "tools/list") list(); else if (status === "ping") ping();', False),
        ('const message = \'case "ping": case "initialize":\';', False),
    ],
)
def test_ts_dispatch_requires_sibling_mcp_method(tmp_path, dispatch, fires):
    (tmp_path / "server.ts").write_text(
        'import { Client } from "@modelcontextprotocol/sdk/client/index.js";\n'
        + dispatch + "\n",
        encoding="utf-8",
    )
    findings = PingRemoved().check(load_project(tmp_path).for_language("typescript"))
    assert bool(findings) is fires


def test_ts_consecutive_if_else_chains_report_each_ping_once(tmp_path):
    (tmp_path / "server.ts").write_text(
        'if (method === "other") other(); else if (method === "ping") ping();\n'
        'if (method === "initialize") init(); else if (method === "ping") ping();\n',
        encoding="utf-8",
    )
    findings = PingRemoved().check(load_project(tmp_path).for_language("typescript"))
    assert [finding.line for finding in findings] == [1, 2]


@pytest.mark.parametrize(
    ("dispatch", "fires"),
    [
        ('switch (method) { case "initialize": break; case "ping": break; }', True),
        ('switch (method) { case `initialize`: break; case `ping`: break; }', True),
        ('if (method === `tools/list`) list(); else if (`ping` === method) ping();', True),
        ('const handlers = { initialize: init, ping: pong };', True),
        ('const handlers = { ["tools/call"]: call, ["ping"]: pong };', True),
        ('const handlers = { [`initialize`]: init, [`ping`]: pong };', True),
        ('switch (method) { case `initialize`: break; case `${name}ping`: break; }', False),
        ('if (method === `tools/${name}`) list(); else if (method === `ping`) ping();', False),
        ('const handlers = { initialize: init, [`${name}ping`]: pong };', False),
        ('const handlers = { ping: pong };', False),
        ('const handlers = { [name]: init, ping: pong };', False),
        ('const alias = "initialize"; switch (method) { case alias: break; case "ping": break; }', False),
        ('switch (method) { case "initialize": break; case "ping":', False),
    ],
)
def test_ts_dispatch_resolves_static_methods_without_file_gate(tmp_path, dispatch, fires):
    (tmp_path / "server.ts").write_text(dispatch, encoding="utf-8")
    findings = PingRemoved().check(load_project(tmp_path).for_language("typescript"))
    assert bool(findings) is fires
