import re

from .base import Finding, Project, Rule

# `SubscribeRequest`/`UnsubscribeRequest` are the MCP SDK's own model names
# -- distinctive, no false-positive risk.
SUBSCRIBE_CODE_RX = re.compile(r"\bSubscribeRequest\b|\bUnsubscribeRequest\b")


class ResourceSubscriptionsReplaced(Rule):
    id = "R013"
    title = "Uses resources/subscribe or resources/unsubscribe, replaced by subscriptions/listen"
    severity = "breaking"
    spec_ref = "SEP-2575 https://modelcontextprotocol.io/specification/2026-07-28/changelog"
    fix = (
        "resources/subscribe and resources/unsubscribe are gone. Move subscription "
        "management to the new subscriptions/listen call."
    )

    def check(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        for f, line, text in project.search_code(SUBSCRIBE_CODE_RX.pattern):
            out.append(self.finding(
                "References the removed SubscribeRequest/UnsubscribeRequest handler.",
                f, line, text,
            ))
        # resources/subscribe and resources/unsubscribe are JSON-RPC method
        # strings, not valid bare identifiers -- they can only appear
        # inside a STRING token, so search_code would never find them (see
        # the notifications/initialized note in r009). Scan raw text.
        for f, line, text in project.search(r"resources/subscribe|resources/unsubscribe"):
            out.append(self.finding(
                "References the removed resources/subscribe or resources/unsubscribe "
                "JSON-RPC method.", f, line, text,
            ))
        return out
