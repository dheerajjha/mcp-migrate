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
from mcp_migrate.rules.r004_tool_ordering import NondeterministicToolOrder
from mcp_migrate.rules.r005_extensions import NoExtensionsDeclared
from mcp_migrate.rules.r006_sse_transport_deprecated import DeprecatedSSETransport
from mcp_migrate.rules.r007_deprecated_features import DeprecatedCoreFeatures
from mcp_migrate.rules.r009_initialize_handshake_removed import (
    InitializeHandshakeStillImplemented,
)
from mcp_migrate.rules.r019_tasks_polling_replaces_blocking_result import (
    TasksPollingReplacesBlockingResult,
)
from mcp_migrate.rules.r011_ping_removed import PingRemoved
from mcp_migrate.rules.r012_logging_set_level_removed import LoggingSetLevelRemoved
from mcp_migrate.rules.r015_result_type_required import RequiredResultTypeMissing
from mcp_migrate.rules.r016_cacheable_result_required import (
    CacheableResultMetadataMissing,
)
from mcp_migrate.rules.r018_multi_round_trip_replaces_server_initiated import (
    MultiRoundTripReplacesServerInitiated,
)
from mcp_migrate.rules.r020_dynamic_client_registration_deprecated import (
    DynamicClientRegistrationDeprecated,
)
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


def test_r019_finds_removed_task_methods_in_typescript(tmp_path):
    code = """\
export function listTasks() {
  return { method: "tasks/list" };
}

export function waitForTask() {
  return { method: "tasks/result" };
}
"""
    project = load_project(_write(tmp_path, "tasks.ts", code)).for_language("typescript")
    findings = TasksPollingReplacesBlockingResult().check(project)
    assert len(findings) == 2
    assert [finding.line for finding in findings] == [2, 6]


def test_r019_stays_silent_on_migrated_typescript_server(tmp_path):
    code = """\
export function pollTask() {
  return { method: "tasks/get" };
}

export function updateTask() {
  return { method: "tasks/update" };
}
"""
    project = load_project(_write(tmp_path, "tasks.ts", code)).for_language("typescript")
    assert TasksPollingReplacesBlockingResult().check(project) == []


def test_r019_ignores_typescript_comment_only_mentions(tmp_path):
    code = """\
// tasks/list and tasks/result were replaced by polling tasks/get.
export const protocolVersion = "2026-07-28";
"""
    project = load_project(_write(tmp_path, "notes.ts", code)).for_language("typescript")
    assert TasksPollingReplacesBlockingResult().check(project) == []


def test_r018_finds_server_initiated_request_in_typescript(tmp_path):
    code = """\
import { CreateMessageRequestSchema } from "@modelcontextprotocol/sdk/types.js";

server.setRequestHandler(CreateMessageRequestSchema, async () => ({}));
export const legacyMethod = "sampling/createMessage";
"""
    project = load_project(_write(tmp_path, "requests.ts", code)).for_language(
        "typescript"
    )
    findings = MultiRoundTripReplacesServerInitiated().check(project)
    assert len(findings) == 3
    assert [finding.line for finding in findings] == [1, 3, 4]


def test_r018_stays_silent_on_migrated_typescript_server(tmp_path):
    code = """\
export const inputRequiredResult = { inputResponses: [] };
"""
    project = load_project(_write(tmp_path, "requests.ts", code)).for_language(
        "typescript"
    )
    assert MultiRoundTripReplacesServerInitiated().check(project) == []


def test_r018_ignores_typescript_comment_only_mentions(tmp_path):
    code = """\
// CreateMessageRequestSchema and sampling/createMessage were replaced by MRTR.
export const protocolVersion = "2026-07-28";
"""
    project = load_project(_write(tmp_path, "notes.ts", code)).for_language("typescript")
    assert MultiRoundTripReplacesServerInitiated().check(project) == []


def test_r015_finds_missing_result_type_in_typescript(tmp_path):
    code = """\
export function handle(request: { method: string; id: string | number }) {
  if (request.method === "tools/list") {
    return JSON.stringify({
      jsonrpc: "2.0",
      id: request.id,
      result: { tools: [{ name: "echo", description: "Echo input" }] },
    });
  }
  return JSON.stringify({
    jsonrpc: "2.0",
    id: request.id,
    error: { code: -32601, message: "Method not found" },
  });
}
"""
    project = load_project(_write(tmp_path, "server.ts", code)).for_language("typescript")
    findings = RequiredResultTypeMissing().check(project)
    assert len(findings) == 1
    assert findings[0].line == 2


def test_r015_stays_silent_on_migrated_typescript_server(tmp_path):
    code = """\
export function handle(request: { method: string; id: string | number }) {
  if (request.method === "tools/list") {
    return JSON.stringify({
      jsonrpc: "2.0",
      id: request.id,
      result: { tools: [], resultType: "complete" },
    });
  }
}
"""
    project = load_project(_write(tmp_path, "server.ts", code)).for_language("typescript")
    assert RequiredResultTypeMissing().check(project) == []


def test_r015_finds_missing_result_type_with_quoted_jsonrpc_key(tmp_path):
    code = """\
export function handle(request: { method: string; id: string | number }) {
  if (request.method === "tools/list") {
    return JSON.stringify({
      "jsonrpc": "2.0",
      id: request.id,
      result: { tools: [] },
    });
  }
}
"""
    project = load_project(_write(tmp_path, "server.ts", code)).for_language("typescript")
    findings = RequiredResultTypeMissing().check(project)
    assert len(findings) == 1


def test_r015_ignores_jsonrpc_named_only_in_comment(tmp_path):
    code = """\
// This file builds jsonrpc responses for tools/list without resultType.
export const NOTE = 1;
"""
    project = load_project(_write(tmp_path, "docs.ts", code)).for_language("typescript")
    assert RequiredResultTypeMissing().check(project) == []


def test_r015_stays_silent_when_sdk_owns_serialization(tmp_path):
    code = """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";

export function handle(request: { method: string; id: string | number }) {
  if (request.method === "tools/list") {
    return JSON.stringify({
      jsonrpc: "2.0",
      id: request.id,
      result: { tools: [] },
    });
  }
}

const server = new Server({ name: "my-server", version: "1.0.0" }, { capabilities: {} });
"""
    project = load_project(_write(tmp_path, "server.ts", code)).for_language("typescript")
    assert RequiredResultTypeMissing().check(project) == []


def test_r012_finds_removed_logging_set_level_in_typescript(tmp_path):
    code = """\
import type { SetLevelRequest, SetLevelRequestParams } from "@modelcontextprotocol/sdk/types.js";
import { SetLevelRequestSchema } from "@modelcontextprotocol/sdk/types.js";

const request: SetLevelRequest = { method: "logging/setLevel" } as SetLevelRequest;
const params: SetLevelRequestParams = {} as SetLevelRequestParams;
server.setRequestHandler(SetLevelRequestSchema, async () => ({}));
export const legacyMethod = "logging/setLevel";
"""
    project = load_project(_write(tmp_path, "logging.ts", code)).for_language("typescript")
    findings = LoggingSetLevelRemoved().check(project)
    assert len(findings) == 7
    assert [finding.line for finding in findings] == [1, 2, 4, 5, 6, 4, 7]


def test_r012_stays_silent_on_migrated_typescript_server(tmp_path):
    code = """\
export function logLevel(request) {
  return request._meta?.["io.modelcontextprotocol/logLevel"];
}
"""
    project = load_project(_write(tmp_path, "logging.ts", code)).for_language("typescript")
    assert LoggingSetLevelRemoved().check(project) == []


def test_r012_ignores_typescript_comment_only_mentions(tmp_path):
    code = """\
// SetLevelRequest, SetLevelRequestParams, SetLevelRequestSchema, and logging/setLevel were removed.
export const protocolVersion = "2026-07-28";
"""
    project = load_project(_write(tmp_path, "notes.ts", code)).for_language("typescript")
    assert LoggingSetLevelRemoved().check(project) == []


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


# --- R020: Dynamic Client Registration deprecated -----------------------

def test_r020_finds_register_client_in_typescript(tmp_path):
    code = """\
import type { OAuthClientMetadata } from "@modelcontextprotocol/sdk/types.js";

export async function registerClient(
  authorizationServerUrl: URL,
  metadata: OAuthClientMetadata,
) {
  const registrationUrl = new URL("/register", authorizationServerUrl);
  const res = await fetch(registrationUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(metadata),
  });
  return res.json();
}
"""
    project = load_project(_write(tmp_path, "auth.ts", code)).for_language("typescript")
    findings = DynamicClientRegistrationDeprecated().check(project)
    assert len(findings) == 1
    assert findings[0].line == 3


def test_r020_finds_register_client_request_type_in_typescript(tmp_path):
    code = """\
import type { RegisterClientRequest } from "@modelcontextprotocol/sdk/types.js";

export function buildRequest(): RegisterClientRequest {
  return { redirect_uris: ["https://app.example/callback"] };
}
"""
    project = load_project(_write(tmp_path, "auth.ts", code)).for_language("typescript")
    findings = DynamicClientRegistrationDeprecated().check(project)
    assert len(findings) >= 1
    assert any("RegisterClientRequest" in (f.snippet or "") for f in findings)


def test_r020_stays_silent_on_migrated_typescript_auth(tmp_path):
    # CIMD: client metadata is hosted at a well-known URL, no /register call.
    code = """\
import type { OAuthClientMetadata } from "@modelcontextprotocol/sdk/types.js";

export const CLIENT_METADATA: OAuthClientMetadata = {
  client_id: "https://app.example/.well-known/oauth-client",
  redirect_uris: ["https://app.example/callback"],
};
"""
    project = load_project(_write(tmp_path, "auth.ts", code)).for_language("typescript")
    assert DynamicClientRegistrationDeprecated().check(project) == []


def test_r020_ignores_dynamic_client_registration_named_only_in_comment(tmp_path):
    code = """\
// Legacy note: we used registerClient against the /register endpoint.
// RegisterClientRequest and DynamicClientRegistration are deprecated.
export const AUTH_MODE = "cimd";
"""
    project = load_project(_write(tmp_path, "docs.ts", code)).for_language("typescript")
    assert DynamicClientRegistrationDeprecated().check(project) == []


def test_r020_does_not_fire_on_unrelated_register_method(tmp_path):
    code = """\
class CRM {
  registerNewCustomer(info: Record<string, unknown>) {
    return { customer_id: 1, ...info };
  }
}
"""
    project = load_project(_write(tmp_path, "billing.ts", code)).for_language("typescript")
    assert DynamicClientRegistrationDeprecated().check(project) == []


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



# --- R011: removed ping request/response ---------------------------------

def test_r011_finds_ping_request_schema_in_typescript(tmp_path):
    code = """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { PingRequestSchema } from "@modelcontextprotocol/sdk/types.js";

server.setRequestHandler(PingRequestSchema, async () => {
  return {};
});
"""
    project = load_project(_write(tmp_path, "server.ts", code)).for_language("typescript")
    findings = PingRemoved().check(project)
    assert len(findings) == 2
    assert all("PingRequest" in f.message for f in findings)


def test_r011_finds_method_dispatch_in_typescript(tmp_path):
    code = """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";

export async function handle(method: string) {
  if (method === "ping") {
    return {};
  }
}
"""
    project = load_project(_write(tmp_path, "server.ts", code)).for_language("typescript")
    findings = PingRemoved().check(project)
    assert len(findings) == 1
    assert "ping" in findings[0].message


def test_r011_finds_case_dispatch_in_typescript(tmp_path):
    code = """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";

switch (method) {
  case "ping": return {};
  case "tools/call": return callTool();
}
"""
    project = load_project(_write(tmp_path, "server.ts", code)).for_language("typescript")
    findings = PingRemoved().check(project)
    assert len(findings) == 1
    assert "ping" in findings[0].message


def test_r011_stays_silent_on_migrated_typescript_server(tmp_path):
    code = """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";

const server = new Server({ name: "my-server", version: "1.0.0" });
"""
    project = load_project(_write(tmp_path, "server.ts", code)).for_language("typescript")
    assert PingRemoved().check(project) == []


def test_r011_ignores_ping_named_only_in_comment(tmp_path):
    code = """\
// We removed the ping handler in the 2026-07-28 migration.
// PingRequestSchema is gone, liveness rides on the transport now.
export const NOTE = 1;
"""
    project = load_project(_write(tmp_path, "docs.ts", code)).for_language("typescript")
    assert PingRemoved().check(project) == []


def test_r011_stays_silent_on_health_check_endpoint(tmp_path):
    # A /ping health-check route in a file that also imports the MCP SDK.
    # The dispatch patterns don't match "/ping" (it has a leading slash),
    # and there's no method === "ping" comparison, so this stays quiet
    # even with MCP context present.
    code = """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import express from "express";

const app = express();
app.get("/ping", (req, res) => res.json({ ok: true }));

const server = new Server({ name: "my-server", version: "1.0.0" });
"""
    project = load_project(_write(tmp_path, "server.ts", code)).for_language("typescript")
    assert PingRemoved().check(project) == []


def test_r011_stays_silent_on_ping_dispatch_without_mcp_context(tmp_path):
    # method === "ping" but no MCP SDK import and no MCP method names.
    # This is a game server or a network tool, not an MCP server.
    code = """\
export function handle(message: string) {
  if (message === "ping") {
    return "pong";
  }
  return null;
}
"""
    project = load_project(_write(tmp_path, "game.ts", code)).for_language("typescript")
    assert PingRemoved().check(project) == []
# --- R007: deprecated core features (Roots / Sampling / Logging) ---------

def test_r007_finds_the_sdk_names_in_typescript(tmp_path):
    code = """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import {
  ListRootsRequestSchema,
  CreateMessageRequestSchema,
  LoggingMessageNotificationSchema,
} from "@modelcontextprotocol/sdk/types.js";
"""
    project = load_project(_write(tmp_path, "server.ts", code)).for_language("typescript")
    findings = DeprecatedCoreFeatures().check(project)
    named = {f.line: f.message for f in findings}
    assert "Roots" in named[3]
    assert "Sampling" in named[4]
    assert "Logging" in named[5]
    assert len(findings) == 3


def test_r007_finds_the_wire_names_in_typescript(tmp_path):
    # JSON-RPC method names only ever exist inside string literals, so
    # this is the half search_code would never find.
    code = """\
export const DEPRECATED = [
  "roots/list",
  "sampling/createMessage",
  "notifications/message",
];
"""
    project = load_project(_write(tmp_path, "methods.ts", code)).for_language("typescript")
    findings = DeprecatedCoreFeatures().check(project)
    assert [f.line for f in findings] == [2, 3, 4]


def test_r007_finds_sampling_through_the_server_object(tmp_path):
    code = """\
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";

const mcpServer = new McpServer({ name: "demo", version: "1.0.0" });

export async function summarise(text: string) {
  return mcpServer.server.createMessage({
    messages: [{ role: "user", content: { type: "text", text } }],
    maxTokens: 100,
  });
}
"""
    project = load_project(_write(tmp_path, "sample.ts", code)).for_language("typescript")
    findings = DeprecatedCoreFeatures().check(project)
    assert len(findings) == 1
    assert findings[0].line == 6
    assert "Sampling" in findings[0].message


def test_r007_does_not_fire_on_a_chat_wrapper_without_mcp_context(tmp_path):
    # The Python rule's whole false-positive story: a `createMessage`
    # wrapper around a chat API has nothing to do with MCP Sampling. In a
    # file that never mentions MCP, this stays quiet.
    code = """\
import Anthropic from "@anthropic-ai/sdk";

export class ChatClient {
  constructor(private client: Anthropic) {}

  async createMessage(prompt: string) {
    return this.client.messages.create({
      model: "claude-sonnet-5",
      max_tokens: 1024,
      messages: [{ role: "user", content: prompt }],
    });
  }
}

const chatClient = new ChatClient(new Anthropic());
await chatClient.createMessage("hello");
"""
    project = load_project(_write(tmp_path, "chat.ts", code)).for_language("typescript")
    assert DeprecatedCoreFeatures().check(project) == []


def test_r007_charges_one_line_once_per_feature(tmp_path):
    # Two signals for Sampling on one line is one dependency on Sampling.
    code = """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";

const result: CreateMessageResult = await server.createMessage(params);
"""
    project = load_project(_write(tmp_path, "sample.ts", code)).for_language("typescript")
    findings = DeprecatedCoreFeatures().check(project)
    assert len(findings) == 1
    assert findings[0].line == 3


def test_r007_stays_silent_on_migrated_typescript_server(tmp_path):
    code = """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";

const server = new Server({ name: "demo", version: "1.0.0" });

server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: [] }));
"""
    project = load_project(_write(tmp_path, "server.ts", code)).for_language("typescript")
    assert DeprecatedCoreFeatures().check(project) == []


def test_r007_ignores_deprecated_features_named_only_in_comments(tmp_path):
    code = """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";

// Migration note: we dropped roots/list, sampling/createMessage and
// notifications/message. RootsCapability and SamplingCapability are gone.
/** server.createMessage() and server.listRoots() are no longer called. */
export const NOTE = 1;
"""
    project = load_project(_write(tmp_path, "docs.ts", code)).for_language("typescript")
    assert DeprecatedCoreFeatures().check(project) == []


# --- R009: the removed initialize handshake ------------------------------

def test_r009_finds_the_initialize_handshake_in_typescript(tmp_path):
    code = """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import {
  InitializeRequestSchema,
  InitializedNotificationSchema,
} from "@modelcontextprotocol/sdk/types.js";

const server = new Server({ name: "demo", version: "1.0.0" });

server.setRequestHandler(InitializeRequestSchema, async () => {
  return { protocolVersion: "2025-06-18", capabilities: {}, serverInfo: {} };
});

server.setNotificationHandler(InitializedNotificationSchema, async () => {
  ready = true;
});
"""
    project = load_project(_write(tmp_path, "server.ts", code)).for_language("typescript")
    findings = InitializeHandshakeStillImplemented().check(project)
    # The two imports and the two registrations -- four lines, four findings.
    assert [f.line for f in findings] == [3, 4, 9, 13]
    assert all("initialize handshake" in f.message for f in findings)


def test_r009_finds_the_wire_name_in_typescript(tmp_path):
    # The literal only ever exists inside a string, so this is the half
    # search_code would silently never find.
    code = """\
export async function handshake(send: (m: unknown) => void) {
  send({ jsonrpc: "2.0", method: "notifications/initialized" });
}
"""
    project = load_project(_write(tmp_path, "client.ts", code)).for_language("typescript")
    findings = InitializeHandshakeStillImplemented().check(project)
    assert len(findings) == 1
    assert findings[0].line == 2
    assert "notifications/initialized" in findings[0].message


def test_r009_charges_a_dual_signal_line_once(tmp_path):
    # Both signals land on line 2. That is one handshake implementation,
    # and one finding -- findings are grade penalties.
    code = """\
switch (method) {
  case "notifications/initialized": return onInitializedNotification();
}
"""
    project = load_project(_write(tmp_path, "dispatch.ts", code)).for_language("typescript")
    findings = InitializeHandshakeStillImplemented().check(project)
    assert len(findings) == 1
    assert findings[0].line == 2


def test_r009_stays_silent_on_migrated_typescript_server(tmp_path):
    code = """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";

const server = new Server({ name: "demo", version: "1.0.0" });

server.setRequestHandler("server/discover", async () => {
  return { protocolVersions: ["2026-07-28"], capabilities: {} };
});
"""
    project = load_project(_write(tmp_path, "server.ts", code)).for_language("typescript")
    assert InitializeHandshakeStillImplemented().check(project) == []


def test_r009_ignores_the_handshake_named_only_in_a_comment(tmp_path):
    code = """\
// Migration note: we deleted the InitializeRequestSchema handler and the
// notifications/initialized round trip in the 2026-07-28 migration.
/** InitializeResult and InitializedNotification are gone; see server/discover. */
export const NOTE = 1;
"""
    project = load_project(_write(tmp_path, "docs.ts", code)).for_language("typescript")
    assert InitializeHandshakeStillImplemented().check(project) == []


def test_r009_does_not_fire_on_an_unrelated_initialize(tmp_path):
    # `initialize` is one of the most overloaded words in software. Only
    # the SDK's own compound names count.
    code = """\
export class Pool {
  async initialize() {
    this.ready = true;
  }
}

const db = new Pool();
await db.initialize();
"""
    project = load_project(_write(tmp_path, "pool.ts", code)).for_language("typescript")
    assert InitializeHandshakeStillImplemented().check(project) == []


# --- R016: ttlMs/cacheScope on list/read results -------------------------

def test_r016_finds_missing_cache_metadata_in_typescript(tmp_path):
    code = """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";

const server = new Server({ name: "demo", version: "1.0.0" });

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return { tools: [] };
});
"""
    project = load_project(_write(tmp_path, "server.ts", code)).for_language("typescript")
    findings = CacheableResultMetadataMissing().check(project)
    assert len(findings) == 1
    assert findings[0].line == 6
    assert "ttlMs" in findings[0].message


def test_r016_stays_silent_on_migrated_typescript_server(tmp_path):
    code = """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";

const server = new Server({ name: "demo", version: "1.0.0" });

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return { tools: [], ttlMs: 300_000, cacheScope: "server" };
});
"""
    project = load_project(_write(tmp_path, "server.ts", code)).for_language("typescript")
    assert CacheableResultMetadataMissing().check(project) == []


def test_r016_flags_cache_metadata_named_only_in_comment(tmp_path):
    code = """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";

// The transport layer adds ttlMs and cacheScope when cacheHints are set.
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return { tools: [] };
});
"""
    project = load_project(_write(tmp_path, "server.ts", code)).for_language("typescript")
    # Comment mentions ttlMs/cacheScope but handler still lacks them in code --
    # prose mentions do not satisfy the rule.
    assert len(CacheableResultMetadataMissing().check(project)) == 1


def test_r016_is_satisfied_by_cache_hints_configured_on_the_server(tmp_path):
    code = """\
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";

const server = new McpServer(
  { name: "demo", version: "1.0.0" },
  {
    cacheHints: {
      "tools/list": { ttlMs: 60_000, cacheScope: "public" },
    },
  }
);

server.registerTool("noop", { description: "no-op" }, async () => ({
  content: [{ type: "text", text: "ok" }],
}));
"""
    project = load_project(_write(tmp_path, "server.ts", code)).for_language("typescript")
    assert CacheableResultMetadataMissing().check(project) == []


def test_r016_finds_wire_method_handler_without_cache_metadata(tmp_path):
    code = """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";

const server = new Server({ name: "demo", version: "1.0.0" });

server.setRequestHandler("tools/list", async () => {
  return { tools: [] };
});
"""
    project = load_project(_write(tmp_path, "server.ts", code)).for_language("typescript")
    findings = CacheableResultMetadataMissing().check(project)
    assert len(findings) == 1
    assert findings[0].line == 5


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


def test_r004_finds_unsorted_tools_in_typescript(tmp_path):
    code = """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";

const server = new Server({ name: "example", version: "1.0.0" });
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      { name: "b_tool", description: "B" },
      { name: "a_tool", description: "A" }
    ]
  };
});
"""
    project = load_project(_write(tmp_path, "server.ts", code)).for_language("typescript")
    findings = NondeterministicToolOrder().check(project)
    assert len(findings) == 1
    assert findings[0].line == 5
    assert "Tools are returned without an explicit sort." in findings[0].message


def test_r004_stays_silent_on_sorted_tools_in_typescript(tmp_path):
    code = """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";

const server = new Server({ name: "example", version: "1.0.0" });
server.setRequestHandler(ListToolsRequestSchema, async () => {
  const tools = [
    { name: "b_tool", description: "B" },
    { name: "a_tool", description: "A" }
  ];
  return { tools: tools.sort((a, b) => a.name.localeCompare(b.name)) };
});
"""
    project = load_project(_write(tmp_path, "server.ts", code)).for_language("typescript")
    assert NondeterministicToolOrder().check(project) == []


def test_r004_ignores_unrelated_sort_outside_handler_body(tmp_path):
    code = """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";

const server = new Server({ name: "example", version: "1.0.0" });
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      { name: "b_tool", description: "B" },
      { name: "a_tool", description: "A" }
    ]
  };
});

// Unrelated sort 10 lines later
const items = getItems();
items.sort((a, b) => a.id - b.id);
"""
    project = load_project(_write(tmp_path, "server.ts", code)).for_language("typescript")
    findings = NondeterministicToolOrder().check(project)
    assert len(findings) == 1
    assert findings[0].line == 5


def test_r004_scopes_long_handlers_correctly_past_40_lines(tmp_path):
    padding = "\n".join(f"  const step{i} = {i};" for i in range(45))
    code = f"""\
import {{ Server }} from "@modelcontextprotocol/sdk/server/index.js";
import {{ ListToolsRequestSchema }} from "@modelcontextprotocol/sdk/types.js";

const server = new Server({{ name: "example", version: "1.0.0" }});
server.setRequestHandler(ListToolsRequestSchema, async () => {{
{padding}
  const tools = [{{ name: "b" }}, {{ name: "a" }}];
  return {{ tools: tools.sort((a, b) => a.name.localeCompare(b.name)) }};
}});
"""
    project = load_project(_write(tmp_path, "server.ts", code)).for_language("typescript")
    assert NondeterministicToolOrder().check(project) == []


def test_r004_handles_closing_braces_inside_strings_and_template_literals(tmp_path):
    code = """\
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";

const server = new Server({ name: "example", version: "1.0.0" });
server.setRequestHandler(ListToolsRequestSchema, async () => {
  const msg = `Closing brace inside string: }`;
  const tools = [{ name: "b" }, { name: "a" }];
  return { tools: tools.sort((a, b) => a.name.localeCompare(b.name)) };
});
"""
    project = load_project(_write(tmp_path, "server.ts", code)).for_language("typescript")
    assert NondeterministicToolOrder().check(project) == []



def test_partial_coverage_is_stated_with_a_denominator(tmp_path, capsys):
    main(["check", str(_write(tmp_path, "transport.ts", LEGACY_TS))])
    # Collapse whitespace: rich wraps at terminal width and will happily
    # split the fraction across two lines.
    out = " ".join(capsys.readouterr().out.split())

    # Derived, not hardcoded. Every TypeScript port moves this number by
    # one, and a literal here makes the ports mutually exclusive: whoever
    # merges second is asserting a count that main has already passed, so
    # main goes red through no fault of theirs. Ports are meant to land in
    # parallel and independently -- the test has to tolerate that.
    ported = sum(1 for r in all_rules() if "typescript" in r.languages)
    total = len(list(all_rules()))
    assert f"{ported} of {total}" in out, (
        "someone deciding whether to trust this needs the coverage fraction, "
        "and it should move as rules get ported"
    )
    assert ported >= 4, "the reference ports (R001/R003/R005/R006) are still there"


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


# --- test-code exclusion is a cross-language concern ----------------------
#
# The exclusion list was written for Python and silently did nothing for
# TypeScript, so every TS project's test suite was scanned as if it were
# the server. Found by running the newly ported rules against
# modelcontextprotocol/servers: both findings for `src/filesystem` came
# out of `__tests__/`.

@pytest.mark.parametrize("rel", [
    "__tests__/server.test.ts",
    "__mocks__/transport.ts",
    "spec/server.ts",
    "e2e/flow.ts",
    "src/server.test.ts",
    "src/server.spec.ts",
    "src/server.test.tsx",
])
def test_typescript_test_code_is_skipped_by_default(tmp_path, rel):
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(LEGACY_TS)
    assert load_project(tmp_path).files == [], f"{rel} is test code, not the server"


def test_typescript_test_code_is_scanned_with_include_tests(tmp_path):
    path = tmp_path / "__tests__" / "server.test.ts"
    path.parent.mkdir(parents=True)
    path.write_text(LEGACY_TS)
    assert load_project(tmp_path, include_tests=True).files != []


def test_production_typescript_that_merely_contains_test_in_the_name_is_kept(tmp_path):
    # `testUtils.ts` ships in the server; `latest.ts` ends in "test" as a
    # substring. Neither is test code and a sloppier match would drop both.
    (tmp_path / "testUtils.ts").write_text(LEGACY_TS)
    (tmp_path / "latest.ts").write_text(LEGACY_TS)
    names = sorted(f.path.name for f in load_project(tmp_path).files)
    assert names == ["latest.ts", "testUtils.ts"]
