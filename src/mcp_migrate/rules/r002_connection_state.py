import ast

from .base import Finding, Project, Rule

SUSPECT = (
    "sessions",
    "session_store",
    "_sessions",
    "connections",
    "session_state",
    "SESSIONS",
    "client_state",
    "per_session",
)

TS_SUSPECT_NAMES = (
    r"sessions|sessionStore|session_store|_sessions|connections|sessionState|session_state|"
    r"SESSIONS|clientState|client_state|perSession|per_session"
)

# TypeScript pattern: declarations of suspect connection state stores
# (e.g. `const sessions = new Map()`, `const sessionStore = {}`, `let connections: Map<string, State> = new Map()`)
TS_RX = (
    rf"\b(?:const|let|var)\s+(?:{TS_SUSPECT_NAMES})\b"
    r"\s*(?::\s*[^=]+)?\s*=\s*(?:new\s+(?:Map|Set|Object)|\{)"
)

# Assignments inside these scopes are request-local, not shared process
# state, so they shouldn't count as "per-connection state" even if a
# variable happens to share a suspect name.
SCOPE_BOUNDARY = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _module_and_class_level_assigns(node: ast.AST):
    """Yield Assign/AnnAssign nodes declared at module or class scope.

    Walks the tree like ast.walk, but stops descending once it enters a
    function/lambda body -- a dict built and thrown away inside a request
    handler is not "process-wide state held between connections", it just
    happens to be named `sessions`.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.Assign, ast.AnnAssign)):
            yield child
        if isinstance(child, SCOPE_BOUNDARY):
            continue
        yield from _module_and_class_level_assigns(child)


class PerConnectionState(Rule):
    id = "R002"
    title = "Keeps per-connection state in a module-level dict"
    severity = "breaking"
    spec_ref = "SEP-2567 https://github.com/modelcontextprotocol/modelcontextprotocol/pull/2567"
    fix = (
        "A stateless server can sit behind a round-robin load balancer. Move this "
        "into a store keyed by an explicit handle you return to the client."
    )
    languages = ("python", "typescript")

    MESSAGE = "Looks like per-connection state held in process memory."

    def check(self, project: Project) -> list[Finding]:
        if project.language == "typescript":
            return [
                self.finding(self.MESSAGE, f, line, text)
                for f, line, text in project.search_code(TS_RX)
            ]

        out: list[Finding] = []
        for f in project.files:
            if f.tree is None:
                continue
            for node in _module_and_class_level_assigns(f.tree):
                # `sessions: dict[str, State] = {}` (AnnAssign) has a single
                # `target`, not a `targets` list like plain Assign.
                if isinstance(node, ast.AnnAssign):
                    if node.value is None or not isinstance(node.value, (ast.Dict, ast.DictComp)):
                        continue
                    targets = [node.target]
                else:
                    if not isinstance(node.value, (ast.Dict, ast.DictComp)):
                        continue
                    targets = node.targets
                for target in targets:
                    if isinstance(target, ast.Name) and any(s in target.id for s in SUSPECT):
                        out.append(
                            self.finding(
                                f"`{target.id}` looks like per-connection state held in process memory.",
                                f,
                                node.lineno,
                                f.lines[node.lineno - 1].strip()
                                if node.lineno <= len(f.lines)
                                else None,
                            )
                        )
        return out
