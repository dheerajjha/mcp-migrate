import re

from .base import Finding, Project, Rule

CAPS_RX = re.compile(r"ServerCapabilities|server_capabilities|capabilities\s*=")
EXTENSIONS_RX = re.compile(r"\bextensions\b")


class NoExtensionsDeclared(Rule):
    id = "R005"
    title = "Server capabilities declare no extensions map"
    severity = "advisory"
    spec_ref = "extensions field on ServerCapabilities"
    fix = (
        "Optional features now negotiate through `extensions` on ServerCapabilities. "
        "Declare an empty map if you support none -- it tells clients you speak 2026-07-28."
    )

    def check(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        seen_files = set()
        # search_code: a comment/docstring that merely mentions
        # ServerCapabilities isn't a real capabilities declaration.
        for f, line, text in project.search_code(CAPS_RX.pattern):
            if f.path in seen_files:
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
            out.append(self.finding("Capabilities are declared but `extensions` is absent.", f, line, text))
        return out
