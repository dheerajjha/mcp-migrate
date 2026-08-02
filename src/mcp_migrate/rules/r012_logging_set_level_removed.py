import re

from .base import Finding, Project, Rule

# `SetLevelRequest`/`SetLevelRequestParams` are the MCP SDK's own model
# names for this request -- distinctive, no false-positive risk.
SET_LEVEL_CODE_RX = re.compile(r"\bSetLevelRequest\b|\bSetLevelRequestParams\b")
TS_SET_LEVEL_CODE_RX = re.compile(r"\bSetLevelRequest\w*")


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
    languages = ("python", "typescript")

    CODE_MESSAGE = "References the removed SetLevelRequest / logging/setLevel handler."
    WIRE_MESSAGE = "References the removed logging/setLevel JSON-RPC method."

    def check(self, project: Project) -> list[Finding]:
        if project.language == "typescript":
            out: list[Finding] = []
            for f, line, text in project.search_code(TS_SET_LEVEL_CODE_RX.pattern):
                out.append(self.finding(self.CODE_MESSAGE, f, line, text))
            for f, line, text in project.search_wire(r"logging/setLevel"):
                out.append(self.finding(self.WIRE_MESSAGE, f, line, text))
            return out

        out: list[Finding] = []
        for f, line, text in project.search_code(SET_LEVEL_CODE_RX.pattern):
            out.append(self.finding(self.CODE_MESSAGE, f, line, text))
        # `logging/setLevel` is a JSON-RPC method string, not a valid bare
        # identifier -- like notifications/initialized in r009, it can only
        # ever appear inside a STRING token, so search_code would never
        # find it. Scan the raw text for the literal instead.
        for f, line, text in project.search_wire(r"logging/setLevel"):
            out.append(self.finding(self.WIRE_MESSAGE, f, line, text))
        return out
