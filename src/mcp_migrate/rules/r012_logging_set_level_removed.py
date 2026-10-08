import re

from .base import Finding, Fires, Project, Rule, Silent, wire_method

# `SetLevelRequest`/`SetLevelRequestParams` are the MCP SDK's own model
# names for this request -- distinctive, no false-positive risk.
SET_LEVEL_CODE_RX = re.compile(r"\bSetLevelRequest(?:Params|Schema|Result|ResultSchema)?\b")
TS_SET_LEVEL_CODE_RX = re.compile(r"\bSetLevelRequest(?:Params|Schema|Result|ResultSchema)?\b")
SET_LEVEL_WIRE_RX = wire_method("logging/setLevel")


class LoggingSetLevelRemoved(Rule):
    id = "R012"
    title = "Implements the removed logging/setLevel request"
    severity = "breaking"
    spec_ref = "SEP-2575 https://modelcontextprotocol.io/specification/2026-07-28/changelog"
    fix = (
        "logging/setLevel is gone. Log level is now per-request: read it off "
        "`_meta[\"io.modelcontextprotocol/logLevel\"]` on each incoming request instead "
        "of tracking one process-wide level."
    )
    languages = ("python", "typescript", "javascript")
    boundaries = (
        Fires(
            snippet="request: SetLevelRequest",
            reason="The removed SDK request type is active Python code.",
        ),
        Fires(
            snippet='METHODS = {"logging/setLevel": handle_set_level}',
            reason="A dispatch table still exposes the removed wire method.",
        ),
        Silent(
            snippet="# SetLevelRequest used to handle logging/setLevel",
            reason="A comment that only describes the old request is not an implementation.",
        ),
        Silent(
            snippet='METRIC = "logging/setLevelLatency"',
            reason="A longer metric name is not the removed JSON-RPC method.",
        ),
        Silent(
            snippet="factory = SetLevelRequesterFactory()",
            reason="An unrelated identifier with a longer suffix is not an SDK request type.",
        ),
        Fires(
            snippet="const params: SetLevelRequestParams = {};",
            reason="The removed SDK params type is active TypeScript code.",
            language="typescript",
        ),
        Fires(
            snippet='server.setRequestHandler("logging/setLevel", handler);',
            reason="A TypeScript handler still registers the removed wire method.",
            language="typescript",
        ),
        Silent(
            snippet="// SetLevelRequest used to handle logging/setLevel",
            reason="A TypeScript comment is prose, not active MCP surface.",
            language="typescript",
        ),
        Silent(
            snippet='const method = "logging/setLevelExtra";',
            reason="A longer TypeScript wire name is outside the method boundary.",
            language="typescript",
        ),
        Silent(
            snippet="const factory = new SetLevelRequestBuilder();",
            reason="A longer TypeScript identifier is not an SDK request type.",
            language="typescript",
        ),
        Fires(
            snippet='const req = new SetLevelRequest({ level: "debug" });',
            reason="JavaScript constructs the removed SDK request type.",
            language="javascript",
        ),
        Fires(
            snippet='server.setRequestHandler("logging/setLevel", handler);',
            reason="A JavaScript handler still registers the removed wire method.",
            language="javascript",
        ),
        Silent(
            snippet="// SetLevelRequest used to handle logging/setLevel",
            reason="A JavaScript comment is prose, not active MCP surface.",
            language="javascript",
        ),
        Silent(
            snippet='const method = "logging/setLevelExtra";',
            reason="A longer JavaScript wire name is outside the method boundary.",
            language="javascript",
        ),
        Silent(
            snippet="const factory = new SetLevelRequestBuilder();",
            reason="A longer JavaScript identifier is not an SDK request type.",
            language="javascript",
        ),
    )

    CODE_MESSAGE = "References the removed SetLevelRequest / logging/setLevel handler."
    WIRE_MESSAGE = "References the removed logging/setLevel JSON-RPC method."

    def check(self, project: Project) -> list[Finding]:
        if project.language == "javascript":
            return self._check_js(project)
        if project.language == "typescript":
            out: list[Finding] = []
            for f, line, text in project.search_code(TS_SET_LEVEL_CODE_RX.pattern):
                out.append(self.finding(self.CODE_MESSAGE, f, line, text))
            for f, line, text in project.search_wire(SET_LEVEL_WIRE_RX):
                out.append(self.finding(self.WIRE_MESSAGE, f, line, text))
            return out

        out: list[Finding] = []
        for f, line, text in project.search_code(SET_LEVEL_CODE_RX.pattern):
            out.append(self.finding(self.CODE_MESSAGE, f, line, text))
        # `logging/setLevel` is a JSON-RPC method string, not a valid bare
        # identifier -- like notifications/initialized in r009, it can only
        # ever appear inside a STRING token, so search_code would never
        # find it. Scan the raw text for the literal instead.
        for f, line, text in project.search_wire(SET_LEVEL_WIRE_RX):
            out.append(self.finding(self.WIRE_MESSAGE, f, line, text))
        return out

    def _check_js(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        seen: set[tuple[str, int]] = set()
        for message, matches in (
            (self.CODE_MESSAGE, project.search_code(TS_SET_LEVEL_CODE_RX.pattern)),
            (self.WIRE_MESSAGE, project.search_wire(SET_LEVEL_WIRE_RX)),
        ):
            for f, line, text in matches:
                key = (f.path, line)
                if key in seen:
                    continue
                seen.add(key)
                out.append(self.finding(message, f, line, text))
        return out
