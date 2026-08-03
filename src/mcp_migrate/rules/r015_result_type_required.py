import re

from .base import Finding, Project, Rule

# Evidence a file implements a result-returning MCP handler at all -- if a
# file doesn't do this, it has nothing to add `resultType` to, and firing
# here would just be noise unrelated to what the rule checks.
RESULT_HANDLER_RX = re.compile(
    r"@[\w.]*\.(?:call_tool|list_tools|list_resources|read_resource|"
    r"list_prompts|get_prompt)\s*\("
)

# Presence check for the required field. Deliberately raw text, not
# search_code: this is the same permissive direction r005_extensions.py
# uses for its own "is `extensions` declared anywhere in this file" check
# -- a mention anywhere (even a comment noting the transport layer adds it)
# is enough to consider the field present, because the cost of a wrong
# "still missing" claim (breaking) is much higher than the cost of a
# generous read of "present".
RESULT_TYPE_MENTION_RX = re.compile(r"resultType")

# Whether the official Python SDK is serializing this server's responses.
#
# This decides whether the rule may fire at all, because the SDK sets the
# field itself. `Runner._serialize` in mcp/server/runner.py ends with:
#
#     if version in MODERN_PROTOCOL_VERSIONS and dumped.get("resultType") is None:
#         dumped["resultType"] = "complete"
#
# unconditionally, for every method including custom and extension ones, and
# mcp 2.0.0 on PyPI ships it. So a handler in an SDK-based server has nowhere
# to put `resultType` and nothing to fix: the field is already on the wire.
# Telling those authors to add it is a false positive on 100% of SDK servers,
# and "add a field you cannot add" is the kind of finding that costs a tool
# its credibility. The genuine risk is a server that hand-rolls its own
# JSON-RPC responses and therefore owns the envelope itself.
SDK_SERVER_MODULES = ("mcp.server", "mcp.types", "mcp.shared", "fastmcp")

# TypeScript. The official SDK stamps resultType on every result it
# serializes, same as the Python runner -- a file that imports
# @modelcontextprotocol/sdk has nothing to add and nothing to fix.
TS_SDK_IMPORT_RX = re.compile(r"@modelcontextprotocol/sdk")

# What a server that owns its own envelope looks like: it writes the JSON-RPC
# framing and the MCP method names itself, as string literals. Both halves are
# required -- "jsonrpc" alone is any JSON-RPC service on earth, and a method
# name alone shows up in tests and docs -- and the project must not import the
# SDK, which is checked first.
JSONRPC_ENVELOPE_RX = re.compile(r"[\"']jsonrpc[\"']")
# TypeScript object literals usually use an unquoted `jsonrpc:` key.
TS_JSONRPC_ENVELOPE_RX = re.compile(r"\bjsonrpc\s*:")
MCP_METHOD_NAME_RX = re.compile(
    r"[\"'](?:tools/list|tools/call|resources/list|resources/read|"
    r"resources/templates/list|prompts/list|prompts/get)[\"']"
)


def _sdk_owns_serialization(project) -> bool:
    for mod in project.imports():
        if mod == "mcp" or mod.startswith(SDK_SERVER_MODULES):
            return True
    return False


def _ts_sdk_owns_serialization(project: Project) -> bool:
    return any(TS_SDK_IMPORT_RX.search(f.text) for f in project.files)


# Downgraded from "breaking" after auditing real servers: resultType is a
# brand-new required field introduced by this same spec revision, so this
# is an absence check that every pre-2026-07-28 handler fails by
# construction -- of the 14 real servers scanned, all 5 whose handlers this
# rule could even detect (the low-level SDK decorator style) tripped it,
# 5 for 5. That's not this rule finding a bug some projects have and
# others don't; it's the rule detecting "was this file written before the
# field existed", which is true of virtually all real MCP code today.
# Stacked at `breaking` alongside R010/R016 (the same shape of absence
# check) this took every reference server straight to F on the day the
# spec shipped, which tells a reader nothing about which of those projects
# is actually further along. Keep surfacing it, just not at a severity
# that drowns out real signal.
class RequiredResultTypeMissing(Rule):
    id = "R015"
    title = "Results are returned without the required resultType field"
    severity = "advisory"
    spec_ref = "SEP-2322 https://modelcontextprotocol.io/specification/2026-07-28/changelog"
    fix = (
        "Every result now carries resultType: \"complete\" or \"input_required\". "
        "If you build JSON-RPC responses yourself, set it on each result you "
        "return. On the official SDK you do not need to do anything: the runner "
        "stamps resultType on every result it serializes."
    )
    languages = ("python", "typescript")

    MESSAGE = (
        "This file builds JSON-RPC responses for MCP methods without the "
        "official SDK, so it owns the result envelope, and `resultType` "
        "never appears in it."
    )

    def check(self, project: Project) -> list[Finding]:
        if project.language == "typescript":
            return self._check_ts(project)
        return self._check_python(project)

    def _check_python(self, project: Project) -> list[Finding]:
        # The SDK stamps `resultType` on every result it serializes, so an
        # SDK-based server has nothing to add and this rule has nothing to
        # say. Only a project that owns its own JSON-RPC envelope can be
        # missing the field in a way its author can act on.
        if _sdk_owns_serialization(project):
            return []
        out: list[Finding] = []
        seen_files = set()
        # Deliberately raw `search`, not `search_code`: a hand-rolled server
        # names the protocol in string literals ("jsonrpc", "tools/list"),
        # which is exactly what search_code is built to skip. Same reasoning
        # as r009's note about notifications/initialized.
        for f in project.files:
            if RESULT_TYPE_MENTION_RX.search(f.text):
                continue
            if f.path in seen_files:
                continue
            if not JSONRPC_ENVELOPE_RX.search(f.text):
                continue
            m = MCP_METHOD_NAME_RX.search(f.text)
            if not m:
                continue
            line = f.text[: m.start()].count("\n") + 1
            seen_files.add(f.path)
            out.append(self.finding(
                self.MESSAGE,
                f, line, f.lines[line - 1].strip() if line <= len(f.lines) else None,
            ))
        return out

    def _check_ts(self, project: Project) -> list[Finding]:
        if _ts_sdk_owns_serialization(project):
            return []
        jsonrpc_paths = {
            ff.path for ff, _, _ in project.search_wire(TS_JSONRPC_ENVELOPE_RX.pattern)
        }
        jsonrpc_paths |= {
            ff.path for ff, _, _ in project.search_wire(JSONRPC_ENVELOPE_RX.pattern)
        }
        method_hits: dict[object, tuple[int, str]] = {}
        for ff, line, text in project.search_wire(MCP_METHOD_NAME_RX.pattern):
            method_hits.setdefault(ff.path, (line, text))

        out: list[Finding] = []
        for f in project.files:
            if RESULT_TYPE_MENTION_RX.search(f.text):
                continue
            if f.path not in jsonrpc_paths:
                continue
            if f.path not in method_hits:
                continue
            line, text = method_hits[f.path]
            out.append(self.finding(self.MESSAGE, f, line, text))
        return out

