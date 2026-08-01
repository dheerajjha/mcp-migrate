import ast
import re

from .base import Finding, Project, Rule

HTTP_LIBS = ("requests", "httpx", "aiohttp")
# Any `.post(`/`.request(` call, on whatever object -- real code almost never
# calls the module function directly (`requests.post(...)`); it goes through
# a client/session instance (`self._client.post(...)`, `session.post(...)`).
# Anchoring on the literal module name missed that entirely.
HAND_ROLLED_CALL = re.compile(r"\.(?:post|request)\(")

# Literal JSON-RPC method names / the "jsonrpc" envelope key. Their presence
# in a file is (weak but real) evidence that the file is speaking MCP's own
# wire protocol, as opposed to just being a REST client for some unrelated
# third-party API (Confluence, Jira, S3, whatever the server wraps).
MCP_METHOD_RX = re.compile(
    r"tools/call|tools/list|resources/read|prompts/get|jsonrpc", re.IGNORECASE
)

# Mcp-Name is only required on the three request methods whose routing
# actually depends on *which* tool/resource/prompt is named -- confirmed
# against the spec (Streamable HTTP transport, 2026-07-28): tools/list,
# initialize, ping, etc. carry no "name" concept at all, so a proxy has
# nothing to route on for them. Flagging a POST for one of those as
# "missing Mcp-Name" was the bug: it isn't missing, it was never required.
NAME_REQUIRED_RX = re.compile(r"tools/call|resources/read|prompts/get")

TS_HTTP_CALL = r"\b(?:fetch|axios|got)\s*\(|\.(?:post|request)\s*\("
TS_MCP_SURFACE_RX = re.compile(
    r"@modelcontextprotocol|tools/call|tools/list|resources/read|prompts/get|jsonrpc",
    re.IGNORECASE,
)

# Submodules that are still "the SDK owns the transport entirely", the same
# way `mcp.server.fastmcp` is -- importing them is configuration of the
# SDK's own high-level transport, not evidence the file crafts JSON-RPC
# messages or sends them by hand. `transport_security` in particular is a
# settings dataclass (allowed hosts/origins, DNS-rebinding protection) with
# no method dispatch or message-sending of its own.
SDK_OWNED_TRANSPORT_PREFIXES = ("mcp.server.fastmcp", "mcp.server.transport_security")


def _is_mcp_transport_module(name: str) -> bool:
    """True for an import of `mcp` or a submodule that implies the file
    touches MCP's own transport/wire layer.

    Deliberately excludes `mcp.server.fastmcp` and `mcp.server.transport_security`:
    both are high-level SDK surface where the SDK owns the transport entirely, so a
    file that only imports one of them is not "hand-rolling MCP transport" no matter
    what else it POSTs to. Confirmed against real false positives:
    aws-documentation-mcp-server and duckduckgo-mcp-server both import
    only SDK-owned transport helpers (`mcp.server.fastmcp`, and in
    duckduckgo-mcp-server's case also `mcp.server.transport_security` for a
    `TransportSecuritySettings(...)` config object) and separately
    `.post()` to their own backend search APIs in the same file -- neither
    references MCP's wire protocol at all.
    """
    if name == "mcp":
        return True
    if not name.startswith("mcp."):
        return False
    return not name.startswith(SDK_OWNED_TRANSPORT_PREFIXES)


def _imports_mcp(f) -> bool:
    if f.tree is None:
        return False
    for node in ast.walk(f.tree):
        if isinstance(node, ast.Import):
            if any(_is_mcp_transport_module(a.name) for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom) and node.module:
            if _is_mcp_transport_module(node.module):
                return True
    return False


class MissingRoutingHeaders(Rule):
    id = "R003"
    title = "Custom HTTP client does not send Mcp-Method (or Mcp-Name where required)"
    # Downgraded from "breaking": even gated on the file referencing MCP's
    # own protocol surface (below), a single file can legitimately both
    # implement/import the MCP SDK *and* wrap an unrelated backend REST API
    # (Confluence, Jira, S3, ...) in the same module. That combination was
    # exactly how this rule produced its worst false positive (19 hits /
    # 475 penalty points on mcp-atlassian, all plain Confluence/Jira REST
    # calls). A wrong `breaking` costs a project its badge; a missed
    # `advisory` costs nothing but a little visibility, so advisory is the
    # safer place for a heuristic this fuzzy to live.
    severity = "advisory"
    spec_ref = (
        "https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http"
    )
    fix = (
        "POST requests now carry Mcp-Method on every request so proxies can route and "
        "rate-limit without parsing the body. Add it, and add Mcp-Name too if this call "
        "is tools/call, resources/read, or prompts/get -- those are the only methods "
        "that carry a name to route on. Or move to an SDK that sets both for you."
    )
    languages = ("python", "typescript")

    def check(self, project: Project) -> list[Finding]:
        if project.language == "typescript":
            return self._check_ts(project)
        return self._check_python(project)

    def _check_python(self, project: Project) -> list[Finding]:
        # Gate on the project actually importing a raw HTTP client -- without
        # that, ".post(" is almost certainly unrelated (an ORM, a queue, a
        # dataclass method) and flagging it would just be noise.
        imported_libs = {name.split(".")[0] for name in project.imports()}
        if not imported_libs & set(HTTP_LIBS):
            return []

        out: list[Finding] = []
        for f in project.files:
            if not any(lib in f.text for lib in HTTP_LIBS):
                continue
            # Most MCP servers wrap some other REST API (Jira, Confluence,
            # S3, ...) -- a bare ".post(" in a file that has nothing to do
            # with MCP's own transport is just that server doing its job,
            # not "hand-rolling MCP transport". Only fire when this file
            # plausibly *is* MCP transport code: it imports the `mcp`
            # package, or it references MCP's own JSON-RPC method names.
            if not (_imports_mcp(f) or MCP_METHOD_RX.search(f.text)):
                continue
            hand_rolled = [(i, line) for i, line in enumerate(f.lines, start=1)
                           if HAND_ROLLED_CALL.search(line)]
            if not hand_rolled:
                continue
            # Scoped to *this* file, not the whole project -- a header set
            # in some unrelated module doesn't mean this call site sends it.
            missing_method = "Mcp-Method" not in f.text
            # Mcp-Name is only required when the file is plausibly sending
            # one of the three methods that carry a name to route on. A
            # file that only ever mentions e.g. tools/list has nothing
            # that requires Mcp-Name, so its absence isn't a finding --
            # this is the R003 bug fix: Mcp-Name is not required on every
            # POST, only on tools/call / resources/read / prompts/get.
            requires_name = bool(NAME_REQUIRED_RX.search(f.text))
            missing_name = requires_name and "Mcp-Name" not in f.text
            if not missing_method and not missing_name:
                continue
            i, line = hand_rolled[0]
            if missing_method and missing_name:
                message = (
                    "This project posts MCP traffic by hand but never sets Mcp-Method, "
                    "and this call site sends tools/call, resources/read, or prompts/get "
                    "without Mcp-Name either."
                )
            elif missing_method:
                message = "This project posts MCP traffic by hand but never sets Mcp-Method."
            else:
                message = (
                    "This call site sends tools/call, resources/read, or prompts/get "
                    "by hand but never sets Mcp-Name."
                )
            out.append(self.finding(message, f, i, line.strip()))
        return out

    def _check_ts(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        for f in project.files:
            if not TS_MCP_SURFACE_RX.search(f.text):
                continue

            missing_method = "mcp-method" not in f.text.lower()
            requires_name = bool(NAME_REQUIRED_RX.search(f.text))
            missing_name = requires_name and "mcp-name" not in f.text.lower()
            if not missing_method and not missing_name:
                continue

            calls = [
                (line, text)
                for file_obj, line, text in project.search_wire(TS_HTTP_CALL)
                if file_obj.path == f.path
            ]
            if not calls:
                continue

            line, text = calls[0]
            if missing_method and missing_name:
                message = (
                    "This project posts MCP traffic by hand but never sets Mcp-Method, "
                    "and this call site sends tools/call, resources/read, or prompts/get "
                    "without Mcp-Name either."
                )
            elif missing_method:
                message = "This project posts MCP traffic by hand but never sets Mcp-Method."
            else:
                message = (
                    "This call site sends tools/call, resources/read, or prompts/get "
                    "by hand but never sets Mcp-Name."
                )
            out.append(self.finding(message, f, line, text))
        return out
