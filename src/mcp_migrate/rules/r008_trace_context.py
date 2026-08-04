from .base import Finding, Project, Rule

# --- TypeScript -----------------------------------------------------------
#
# The Python gate is `project.imports()`, which walks the AST -- and the
# AST is Python-only (`SourceFile.tree` stays None for every other
# language), so the TypeScript side needs a textual equivalent.
#
# A quoted `@opentelemetry/...` specifier is that equivalent. The scope is
# narrow on purpose: the string only appears in an `import`/`require`, so
# matching it needs no anchor to the import keyword, and it cannot be
# confused with ordinary prose about tracing. `search_wire` keeps string
# literals (where the specifier lives) while dropping comments, so a
# `// TODO: add @opentelemetry/api` does not read as "OpenTelemetry is in
# use" -- which matters more here than in most rules, because this gate
# opening is what lets the rule fire at all.
TS_OTEL_SPECIFIER_RX = r"[\"'`]@opentelemetry/[^\"'`]*[\"'`]"

# Evidence the header is actually read. Both spellings are real and both
# have to count:
#
#   const tp = request.params._meta?.["traceparent"];   // string key
#   const tp = meta.traceparent;                        // property access
#
# `search_wire` is the mode that sees both -- `search_code` discards string
# tokens and would miss the first, while comments stay excluded either way,
# so "we should read traceparent" still does not count as reading it.
TS_TRACEPARENT_RX = r"\btraceparent\b"

# The other correct way to do this, and the reason the TypeScript port is
# quieter than the Python one: the idiomatic OTel API consumes the header
# through the propagator rather than by name.
#
#   propagation.extract(context.active(), request.params._meta ?? {})
#
# A server written that way propagates trace context correctly and may
# never spell `traceparent` anywhere. Flagging it would be a false positive
# on code that already does the right thing, so the extract call counts as
# evidence. `search_code` here: this one is a real call expression, not a
# string.
TS_PROPAGATION_EXTRACT_RX = r"\bpropagation\s*\.\s*extract\s*\("

MESSAGE = "OpenTelemetry is in use but `traceparent` is never read from `_meta`."


class NoTraceContextPropagation(Rule):
    id = "R008"
    title = "Does not propagate OpenTelemetry trace context from _meta"
    severity = "advisory"
    spec_ref = "SEP-414 https://github.com/modelcontextprotocol/modelcontextprotocol/pull/414"
    fix = (
        "Read `traceparent`, `tracestate` and `baggage` off `_meta` and hand them to your "
        "tracer. Without it, agent traces break at your server."
    )
    languages = ("python", "typescript")

    def check(self, project: Project) -> list[Finding]:
        if project.language == "typescript":
            return self._check_ts(project)
        return self._check_python(project)

    def _check_python(self, project: Project) -> list[Finding]:
        uses_otel = any("opentelemetry" in i for i in project.imports())
        if not uses_otel:
            return []
        # search_code: a comment saying "we should read traceparent" isn't
        # actually reading it.
        if any(project.search_code(r"traceparent")):
            return []
        return [self.finding(MESSAGE)]

    def _check_ts(self, project: Project) -> list[Finding]:
        # Same shape as Python: gate on OpenTelemetry actually being in
        # play, then look for evidence the header is consumed. A project
        # that does no tracing at all is not failing to propagate trace
        # context -- it has nothing to propagate.
        if not any(project.search_wire(TS_OTEL_SPECIFIER_RX)):
            return []
        if any(project.search_wire(TS_TRACEPARENT_RX)):
            return []
        if any(project.search_code(TS_PROPAGATION_EXTRACT_RX)):
            return []
        return [self.finding(MESSAGE)]
