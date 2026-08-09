import re

from .base import Finding, Project, Rule, mcp_surface_paths

# Only the SDK's own names. A bare `capabilities = ...` used to be in
# here and it is simply too ordinary an identifier to carry any MCP
# meaning -- the registry scan turned up all three of these, none of which
# is a capabilities declaration under this spec or any other:
#
#   required_capabilities={Capability.EMBEDDINGS}        an OpenAI-compat shim
#   Registry.update_capabilities = _update_capabilities  a plugin registry
#   capabilities = {Capability.TEXT, Capability.VISION}  an LLM backend class
#
# Dropping it costs a hand-rolled server that assembles its own untyped
# capabilities dict, which is a false negative we accept: this rule is
# advisory, and a wrong "you're missing extensions" aimed at code that
# never spoke MCP is worse than a quiet miss.
CAPS_RX = re.compile(r"\bServerCapabilities\b|\bserver_capabilities\b")
EXTENSIONS_RX = re.compile(r"\bextensions\b")

# --- TypeScript -----------------------------------------------------------
#
# ServerCapabilities is the SDK's own type name in TypeScript, same as in
# Python. The other place capabilities are declared is the options object
# passed to `new Server({...}, {capabilities: {...}})`, where the type is
# inferred from the constructor and ServerCapabilities never appears as a
# name. A bare `capabilities` identifier is far too common to match on its
# own (91% false-positive rate on the Python side before it was tightened),
# so the constructor signal is gated on an @modelcontextprotocol/sdk import.
TS_CAPS_TYPE_RX = r"\bServerCapabilities\b"
TS_SDK_IMPORT_RX = re.compile(r"@modelcontextprotocol/sdk")
TS_CAPS_PROP_RX = r"\bcapabilities\s*:\s*\{"

MESSAGE = "Capabilities are declared but `extensions` is absent."


class NoExtensionsDeclared(Rule):
    id = "R005"
    title = "Server capabilities declare no extensions map"
    severity = "advisory"
    spec_ref = "extensions field on ServerCapabilities"
    fix = (
        "Optional features now negotiate through `extensions` on ServerCapabilities. "
        "Declare an empty map if you support none -- it tells clients you speak 2026-07-28."
    )
    languages = ("python", "typescript")

    def check(self, project: Project) -> list[Finding]:
        if project.language == "typescript":
            return self._check_ts(project)
        return self._check_python(project)

    def _check_python(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        seen_files = set()
        # The TS path below already gates its weaker signal on an SDK
        # import; this one had no gate at all, so a class of one's own
        # named `ServerCapabilities` in a file that never mentions MCP read
        # as an MCP capabilities declaration. Less overloaded than
        # `register_client`, but the asymmetry is the point: R005 reports
        # at most one finding per file, so a wrong hit silences the rule
        # for that whole file as well as costing points. See #234.
        surface = mcp_surface_paths(project)
        # search_code: a comment/docstring that merely mentions
        # ServerCapabilities isn't a real capabilities declaration.
        for f, line, text in project.search_code(CAPS_RX.pattern):
            if f.path in seen_files:
                continue
            if f.path not in surface:
                continue
            # Scoped to the file that declares capabilities, not the whole
            # project -- an unrelated module elsewhere that happens to
            # mention "extensions" (a docstring, a file-extension check)
            # shouldn't silence a real finding here, and vice versa a
            # completely unrelated capabilities declaration shouldn't be
            # excused by this file's own mention of extensions.
            if EXTENSIONS_RX.search(f.text):
                continue
            seen_files.add(f.path)
            out.append(self.finding(MESSAGE, f, line, text))
        return out

    def _check_ts(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        seen_files = set()

        # Signal 1: explicit ServerCapabilities type reference.
        # search_code skips comments and string literals, so a JSDoc block
        # or a string mentioning the type is not a declaration.
        for f, line, text in project.search_code(TS_CAPS_TYPE_RX):
            if f.path in seen_files:
                continue
            if EXTENSIONS_RX.search(f.text):
                continue
            seen_files.add(f.path)
            out.append(self.finding(MESSAGE, f, line, text))

        # Signal 2: capabilities property in a file that imports the MCP
        # SDK. In TypeScript the type is usually inferred from the Server
        # constructor, so ServerCapabilities never appears as a name. Gate
        # on an SDK import to keep the bare `capabilities` false-positive
        # rate down -- a file that doesn't import @modelcontextprotocol
        # is not an MCP server, no matter what properties its objects have.
        # search_wire keeps string literals (for "capabilities": {}) and
        # drops comments.
        for f, line, text in project.search_wire(TS_CAPS_PROP_RX):
            if f.path in seen_files:
                continue
            if not TS_SDK_IMPORT_RX.search(f.text):
                continue
            if EXTENSIONS_RX.search(f.text):
                continue
            seen_files.add(f.path)
            out.append(self.finding(MESSAGE, f, line, text))

        return out
