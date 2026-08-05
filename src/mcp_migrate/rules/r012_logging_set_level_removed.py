import re

from .base import Finding, Project, Rule, wire_method

# `SetLevelRequest`/`SetLevelRequestParams` are the MCP SDK's own model
# names for this request -- distinctive, no false-positive risk.
SET_LEVEL_CODE_RX = re.compile(r"\bSetLevelRequest(?:Params|Schema|Result|ResultSchema)?\b")


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

    def check(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        for f, line, text in project.search_code(SET_LEVEL_CODE_RX.pattern):
            out.append(self.finding(
                "References the removed SetLevelRequest / logging/setLevel handler.",
                f, line, text,
            ))
        # `logging/setLevel` is a JSON-RPC method string, not a valid bare
        # identifier -- like notifications/initialized in r009, it can only
        # ever appear inside a STRING token, so search_code would never
        # find it. Scan the raw text for the literal instead.
        for f, line, text in project.search_wire(wire_method("logging/setLevel")):
            out.append(self.finding(
                "References the removed logging/setLevel JSON-RPC method.", f, line, text,
            ))
        return out
