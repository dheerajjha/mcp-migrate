import re

from .base import Finding, Project, Rule

# `SubscribeRequest`/`UnsubscribeRequest` are the MCP SDK's own model names
# -- distinctive, no false-positive risk.
SUBSCRIBE_CODE_RX = re.compile(r"\bSubscribeRequest\b|\bUnsubscribeRequest\b")

# The TypeScript SDK exports Zod schemas for request handling, and that's
# the name a server actually references -- `server.setRequestHandler(
# SubscribeRequestSchema, ...)`. Bounded to the exact SDK export names
# (optionally suffixed `Params`/`Schema`) rather than an unbounded `\w*`
# suffix, which would also match unrelated identifiers like
# `SubscribeRequester` -- see #87.
TS_SUBSCRIBE_CODE_RX = re.compile(
    r"\b(?:Subscribe|Unsubscribe)Request(?:Params|Schema)?\b"
)

WIRE_RX = r"resources/subscribe|resources/unsubscribe"
MESSAGE_CODE = "References the removed SubscribeRequest/UnsubscribeRequest handler."
MESSAGE_WIRE = (
    "References the removed resources/subscribe or resources/unsubscribe "
    "JSON-RPC method."
)


class ResourceSubscriptionsReplaced(Rule):
    id = "R013"
    title = "Uses resources/subscribe or resources/unsubscribe, replaced by subscriptions/listen"
    severity = "breaking"
    spec_ref = "SEP-2575 https://modelcontextprotocol.io/specification/2026-07-28/changelog"
    fix = (
        "resources/subscribe and resources/unsubscribe are gone. Move subscription "
        "management to the new subscriptions/listen call."
    )
    languages = ("python", "typescript")

    def check(self, project: Project) -> list[Finding]:
        if project.language == "typescript":
            return self._check_ts(project)
        return self._check_python(project)

    def _check_python(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        for f, line, text in project.search_code(SUBSCRIBE_CODE_RX.pattern):
            out.append(self.finding(MESSAGE_CODE, f, line, text))
        # resources/subscribe and resources/unsubscribe are JSON-RPC method
        # strings, not valid bare identifiers -- they can only appear
        # inside a STRING token, so search_code would never find them (see
        # the notifications/initialized note in r009). Scan raw text.
        for f, line, text in project.search_wire(WIRE_RX):
            out.append(self.finding(MESSAGE_WIRE, f, line, text))
        return out

    def _check_ts(self, project: Project) -> list[Finding]:
        seen: set[tuple[str, int]] = set()
        out: list[Finding] = []
        for pattern, message, search in (
            (TS_SUBSCRIBE_CODE_RX.pattern, MESSAGE_CODE, project.search_code),
            (WIRE_RX, MESSAGE_WIRE, project.search_wire),
        ):
            for f, line, text in search(pattern):
                # A dispatcher line can carry both signals at once, e.g.
                # `case "resources/subscribe": return this.subscribe(SubscribeRequestSchema);`
                # -- that's one removed-method usage, not two.
                if (str(f.path), line) in seen:
                    continue
                seen.add((str(f.path), line))
                out.append(self.finding(message, f, line, text))
        return sorted(out, key=lambda x: (str(x.path or ""), x.line or 0))
