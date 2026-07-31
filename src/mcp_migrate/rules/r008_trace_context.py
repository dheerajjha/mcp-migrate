from .base import Finding, Project, Rule


class NoTraceContextPropagation(Rule):
    id = "R008"
    title = "Does not propagate OpenTelemetry trace context from _meta"
    severity = "advisory"
    spec_ref = "SEP-414 https://github.com/modelcontextprotocol/modelcontextprotocol/pull/414"
    fix = (
        "Read `traceparent`, `tracestate` and `baggage` off `_meta` and hand them to your "
        "tracer. Without it, agent traces break at your server."
    )

    def check(self, project: Project) -> list[Finding]:
        uses_otel = any("opentelemetry" in i for i in project.imports())
        if not uses_otel:
            return []
        # search_code: a comment saying "we should read traceparent" isn't
        # actually reading it.
        if any(project.search_code(r"traceparent")):
            return []
        return [self.finding(
            "OpenTelemetry is in use but `traceparent` is never read from `_meta`."
        )]
