from .base import Finding, Project, Rule

FEATURES = {
    r"\broots/list\b|list_roots|RootsCapability": ("Roots", "Use resource URIs instead."),
    r"sampling/createMessage|create_message|SamplingCapability": ("Sampling", "Sampling is deprecated; plan a migration."),
    r"notifications/message|LoggingCapability|set_logging_level": ("Logging", "Logging moves out of core; use an extension."),
}


class DeprecatedCoreFeatures(Rule):
    id = "R007"
    title = "Depends on a deprecated core feature (Roots / Sampling / Logging)"
    severity = "deprecated"
    spec_ref = "Roots, Sampling and Logging deprecated"
    fix = "These stay in the spec for at least 12 months, then leave. Start moving now."

    def check(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        for pattern, (name, advice) in FEATURES.items():
            # search_code: a comment/docstring mentioning "sampling" or
            # "roots/list" isn't a real dependency on the deprecated
            # feature.
            for f, line, text in project.search_code(pattern):
                out.append(self.finding(f"{name} is deprecated. {advice}", f, line, text))
        return out
