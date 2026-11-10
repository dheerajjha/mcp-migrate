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
        ('if (method === "ping") ping(); if (method === "tools/list") list();', False),
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
