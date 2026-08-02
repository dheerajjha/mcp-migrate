import re

from .base import Finding, Project, Rule

# `SubscribeRequest`/`UnsubscribeRequest` are the MCP SDK's own model names
# -- distinctive, no false-positive risk.
SUBSCRIBE_CODE_RX = re.compile(r"\bSubscribeRequest\b|\bUnsubscribeRequest\b")
TS_SUBSCRIBE_CODE_RX = re.compile(r"\bSubscribeRequest\w*|\bUnsubscribeRequest\w*")


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

    CODE_MESSAGE = "References the removed SubscribeRequest/UnsubscribeRequest handler."
    WIRE_MESSAGE = (
        "References the removed resources/subscribe or resources/unsubscribe JSON-RPC method."
    )

    def check(self, project: Project) -> list[Finding]:
        if project.language == "typescript":
            out: list[Finding] = []
            for f, line, text in project.search_code(TS_SUBSCRIBE_CODE_RX.pattern):
                out.append(self.finding(self.CODE_MESSAGE, f, line, text))
            for f, line, text in project.search_wire(
                r"resources/subscribe|resources/unsubscribe"
            ):
                out.append(self.finding(self.WIRE_MESSAGE, f, line, text))
            return out

        out: list[Finding] = []
        for f, line, text in project.search_code(SUBSCRIBE_CODE_RX.pattern):
            out.append(self.finding(self.CODE_MESSAGE, f, line, text))
        # resources/subscribe and resources/unsubscribe are JSON-RPC method
        # strings, not valid bare identifiers -- they can only appear
        # inside a STRING token, so search_code would never find them (see
        # the notifications/initialized note in r009). Scan raw text.
        for f, line, text in project.search_wire(r"resources/subscribe|resources/unsubscribe"):
            out.append(self.finding(self.WIRE_MESSAGE, f, line, text))
        return out
