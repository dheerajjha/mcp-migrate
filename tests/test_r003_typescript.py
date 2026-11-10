"""R003 must prove MCP payload and routing headers at the same HTTP call."""
import pytest

from mcp_migrate.cli import main
from mcp_migrate.rules.r003_routing_headers import MissingRoutingHeaders
from mcp_migrate.scan import load_project


SDK = 'import type {\n CallToolRequest as Call,\n ListToolsRequest as List\n} from "@modelcontextprotocol/sdk/types.js";\n'
CALL = '{ method: "tools/call", params: { name: "x" } }'
LIST = '{ method: "tools/list" }'


def check(tmp_path, source, extension="ts"):
    (tmp_path / f"client.{extension}").write_text(source, encoding="utf-8")
    return MissingRoutingHeaders().check(load_project(tmp_path).for_language("typescript"))


@pytest.mark.parametrize("source", [
    'import { Server } from "@modelcontextprotocol/sdk/server"; fetch("/billing", {body: JSON.stringify({invoice: 1})});',
    SDK + 'function log(r: Call) { console.log(JSON.stringify(r)); } fetch("/billing", {body: "{}"});',
    SDK + 'function send(r: Call) { fetch("/billing", {body: log(JSON.stringify(r))}); }',
    SDK + 'function send(r: Call) { fetch("/billing", {body: (() => JSON.stringify(r))()}); }',
    SDK + 'function send(r: Call) { function bill(r: string) { fetch("/", {body: JSON.stringify(r)}); } }',
    SDK + 'function send(r: Call) { const bill = r => fetch("/", {body: JSON.stringify(r)}); }',
    SDK + 'function send(r: Call) { try {} catch (r) { fetch("/", {body: JSON.stringify(r)}); } }',
    SDK + 'function send(r: Call) { const bill = function r() { fetch("/", {body: JSON.stringify(r)}); }; }',
    SDK + 'function send(r: Call) { { const r = {invoice: 1}; fetch("/", {body: JSON.stringify(r)}); } }',
    SDK + 'function send(r: Call) { const {r} = billing; fetch("/", {body: JSON.stringify(r)}); }',
    SDK + 'function send({params: r}: Call) { fetch("/", {body: JSON.stringify(r)}); }',
    SDK + 'function send(r: Call) { { var r = billing; } fetch("/", {body: JSON.stringify(r)}); }',
    SDK + 'function send(r: Call, JSON: any) { fetch("/", {body: JSON.stringify(r)}); }',
    SDK + 'import JSON from "billing"; function send(r: Call) { fetch("/", {body: JSON.stringify(r)}); }',
    SDK + 'function send(r: Call) { fetch("/", {body: JSON.stringify(JSON.stringify(r))}); }',
    SDK + 'function send<Call>(r: Call) { fetch("/", {body: JSON.stringify(r)}); }',
    SDK + 'function send() { type Call = {invoice: number}; const r: Call = {invoice: 1}; fetch("/", {body: JSON.stringify(r)}); }',
    'import type { InvoiceRequest } from "@modelcontextprotocol/sdk/types.js"; function send(r: InvoiceRequest) { fetch("/", {body: JSON.stringify(r)}); }',
    'import type { CallToolRequest } from "./billing"; function send(r: CallToolRequest) { fetch("/", {body: JSON.stringify(r)}); }',
    'const note = "tools/call jsonrpc"; fetch("/", {body: "{}"});',
    'fetch("/", {body: JSON.stringify({invoice: "tools/call"})});',
    'fetch("/", {body: JSON.stringify({invoice: {method: "tools/call"}})});',
    'fetch("/", {body: JSON.stringify({method: "tools/call", ...billing})});',
    'fetch("/", {body: JSON.stringify({method: "tools/call"}), headers: configuredHeaders});',
    'fetch("/", {body: JSON.stringify({method: "tools/call"}), headers: {...configuredHeaders}});',
    'fetch("/", {body: JSON.stringify({method: "tools/call"}), headers: {[headerName]: value}});',
    'fetch("/", {body: JSON.stringify({method: "tools/list"}), headers: {"Mcp-Method": "tools/list"}});',
])
def test_unrelated_or_unknown_payload_is_not_mcp(tmp_path, source):
    assert check(tmp_path, source) == []


@pytest.mark.parametrize("source,missing_name", [
    (SDK + 'function send(r: Call) { fetch("/", {body: JSON.stringify(r)}); }', True),
    (SDK + 'function send(r: List) { fetch("/", {body: JSON.stringify(r)}); }', False),
    (SDK + 'function send() { const r: Call = build(); fetch("/", {body: JSON.stringify(r)}); }', True),
    (SDK + 'function send(r: Call) { fetch("/", {headers: {"Mcp-Method": "tools/call"}, body: JSON.stringify(r)}); }', True),
    ('fetch("/", {body: JSON.stringify(' + CALL + ')});', True),
    ('fetch("/", {body: JSON.stringify(' + LIST + ')});', False),
    ("""fetch("/", {body: '{"jsonrpc":"2.0","method":"tools/call"}'});""", True),
    ('fetch("/", {body: JSON.stringify({method: "resources/read"})});', True),
    ('fetch("/", {body: JSON.stringify({method: "prompts/get"})});', True),
])
def test_direct_typed_and_literal_payloads(tmp_path, source, missing_name):
    findings = check(tmp_path, source)
    assert len(findings) == 1
    assert ("Mcp-Name" in findings[0].message) == missing_name


@pytest.mark.parametrize("extension", ["ts", "tsx"])
@pytest.mark.parametrize("expression", [
    'fetch("/", {body: JSON.stringify(PAYLOAD)})',
    'axios("/", {data: PAYLOAD})',
    'axios({url: "/", data: PAYLOAD})',
    'got("/", {json: PAYLOAD})',
    'client.post("/", PAYLOAD)',
    'client.request("/", {body: JSON.stringify(PAYLOAD)})',
    'client.request({url: "/", data: PAYLOAD})',
    'axios.post("/", PAYLOAD, {headers: {"Content-Type": "application/json"}})',
    'got.post("/", {json: PAYLOAD})',
])
def test_supported_http_forms(tmp_path, extension, expression):
    assert len(check(tmp_path, expression.replace("PAYLOAD", CALL), extension)) == 1


@pytest.mark.parametrize("separator", ["\n", " "])
def test_first_deficient_actual_call_and_neighbor_headers(tmp_path, separator):
    migrated = 'fetch("/", {body: JSON.stringify(' + CALL + '), headers: {"Mcp-Method": "tools/call", "Mcp-Name": "x"}});'
    billing = 'fetch("/billing", {body: JSON.stringify({invoice: ")}]"}), headers: {"X-Note": "Mcp-Method Mcp-Name"}});'
    bad = 'fetch("/", { /* )}] Mcp-Method Mcp-Name */ body: JSON.stringify(' + CALL + ')});'
    source = separator.join([billing, migrated, bad, bad])
    findings = check(tmp_path, source)
    assert len(findings) == 1
    assert findings[0].line == (3 if separator == "\n" else 1)
    assert "Mcp-Method" in findings[0].message
    assert "Mcp-Name" in findings[0].message


@pytest.mark.parametrize("payload", [
    'JSON.stringify({jsonrpc: "2.0", method: "invoice/pay"})',
    """'{"jsonrpc":"2.0","method":"invoice/pay"}'""",
    'JSON.stringify({jsonrpc: "2.0", id: 1})',
])
def test_jsonrpc_billing_beside_migrated_mcp_is_not_flagged(tmp_path, payload):
    source = (
        'fetch("/billing", {body: ' + payload + '});\n'
        'fetch("/mcp", {body: JSON.stringify(' + CALL + '), '
        'headers: {"Mcp-Method": "tools/call", "Mcp-Name": "x"}});\n'
    )
    assert check(tmp_path, source) == []


def test_fix_cli_leaves_flagged_typescript_unchanged(tmp_path):
    source = (
        '// mcp-method mcp-name\n'
        'const httpx = client;\n'
        'httpx.post("/mcp", {method: "tools/call"});\n'
    )
    assert len(check(tmp_path, source)) == 1
    path = tmp_path / "client.ts"
    before = path.read_bytes()
    assert main(["fix", str(tmp_path), "--rule", "R003", "--write"]) == 0
    assert path.read_bytes() == before
    assert len(MissingRoutingHeaders().check(
        load_project(tmp_path).for_language("typescript")
    )) == 1


def test_r003_local_const_object_payload(tmp_path):
    # Fires: local const payload via JSON.stringify
    snippet = """
export async function listTools(url: string) {
  const payload = { jsonrpc: "2.0", id: 1, method: "tools/list" };
  return fetch(url, { method: "POST", body: JSON.stringify(payload) });
}
"""
    findings = check(tmp_path, snippet)
    assert len(findings) == 1
    assert "Mcp-Method" in findings[0].message
    assert "Mcp-Name" not in findings[0].message

    # Fires: local const payload via axios.post
    axios_snippet = """
export async function listTools(url: string) {
  const payload = { jsonrpc: "2.0", id: 1, method: "tools/list" };
  return axios.post(url, payload);
}
"""
    findings_axios = check(tmp_path, axios_snippet)
    assert len(findings_axios) == 1
    assert "Mcp-Method" in findings_axios[0].message

    # Silent: const payload whose method is not MCP
    non_mcp = """
export async function listInvoices(url: string) {
  const payload = { method: "invoices.list" };
  return fetch(url, { method: "POST", body: JSON.stringify(payload) });
}
"""
    assert check(tmp_path, non_mcp) == []

    # Silent: let (not const)
    let_snippet = """
export async function listTools(url: string) {
  let payload = { method: "tools/list" };
  return fetch(url, { method: "POST", body: JSON.stringify(payload) });
}
"""
    assert check(tmp_path, let_snippet) == []

    # Silent: const from an outer scope
    outer_const = """
const payload = { method: "tools/list" };
export async function listTools(url: string) {
  return fetch(url, { method: "POST", body: JSON.stringify(payload) });
}
"""
    assert check(tmp_path, outer_const) == []
