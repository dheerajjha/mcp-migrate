import ast

from .base import Finding, Fires, Project, Rule, Silent

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

_DICT_CALL_NAMES = {"dict", "defaultdict", "OrderedDict"}


def _is_dict_shape(node: ast.AST | None) -> bool:
    """Return True if the node represents a dict-like store.

    Recognises dict literals, dict comprehensions, and constructor calls
    to dict / defaultdict / OrderedDict (including the collections.xxx form).
    """
    if node is None:
        return False
    if isinstance(node, (ast.Dict, ast.DictComp)):
        return True
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id in _DICT_CALL_NAMES:
            return True
        if (
            isinstance(func, ast.Attribute)
            and func.attr in _DICT_CALL_NAMES
            and isinstance(func.value, ast.Name)
            and func.value.id == "collections"
        ):
            return True
    return False


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
    _DECLARED_BOUNDARIES = (
        Fires(
            snippet="sessions = {}",
            reason="A module-level dict with a connection-state name is shared process state.",
        ),
        Fires(
            snippet='session_store: dict[str, object] = {}',
            reason="An annotated module-level dict is still shared process state.",
        ),
        Fires(
            snippet="_sessions = {}",
            reason="The private sessions spelling is still a suspect shared store.",
        ),
        Fires(
            snippet="session_state = {}",
            reason="The session-state spelling is still a suspect shared store.",
        ),
        Fires(
            snippet="SESSIONS = {}",
            reason="The upper-case sessions spelling is still a suspect shared store.",
        ),
        Fires(
            snippet="client_state = {}",
            reason="The client-state spelling is still a suspect shared store.",
        ),
        Fires(
            snippet="per_session = {}",
            reason="The per-session spelling is still a suspect shared store.",
        ),
        Fires(
            snippet="sessions_by_tenant = {}",
            reason="A longer name containing the suspect sessions marker is still shared state.",
        ),
        Fires(
            snippet=(
                "class ServerState:\n"
                "    connections = {key: value for key, value in seed_items}\n"
            ),
            reason="A dict comprehension stored on a class is shared across connections.",
        ),
        Silent(
            snippet=(
                "def handle_request():\n"
                "    sessions = {}\n"
                "    return sessions\n"
            ),
            reason="A function-local dict is discarded with the request, not shared process state.",
        ),
        Silent(
            snippet=(
                "async def handle_request():\n"
                "    connections = {}\n"
                "    return connections\n"
            ),
            reason="An async-function-local dict is request-local rather than shared process state.",
        ),
        Silent(
            snippet=(
                "def build_handler():\n"
                "    class Handler:\n"
                "        connections = {}\n"
                "    return Handler()\n"
            ),
            reason="A class created inside a function stays behind the function-scope boundary.",
        ),
        Silent(
            snippet="sessions = SessionStore()",
            reason="R002 recognizes dict-shaped stores; an application-specific store object is outside those shapes.",
        ),
        Silent(
            snippet="session_store: SessionStore = SessionStore()\n",
            reason="An annotated store object, not a dict-shaped store, is outside R002's detected shapes.",
        ),
        Fires(
            snippet="const sessions = new Map<string, unknown>();",
            reason="A module-level Map under the canonical session name is shared process state.",
            language="typescript",
        ),
        Fires(
            snippet="let sessionStore: Set<string> = new Set();",
            reason="The camelCase suspect name and Set initializer are both covered.",
            language="typescript",
        ),
        Fires(
            snippet="const session_store = new Map();",
            reason="The snake_case session-store spelling is covered.",
            language="typescript",
        ),
        Fires(
            snippet="const _sessions = new Map();",
            reason="The private sessions spelling is covered.",
            language="typescript",
        ),
        Fires(
            snippet="const connections = new Map();",
            reason="The connections spelling is covered.",
            language="typescript",
        ),
        Fires(
            snippet="const sessionState = new Map();",
            reason="The camelCase session-state spelling is covered.",
            language="typescript",
        ),
        Fires(
            snippet="const session_state = new Map();",
            reason="The snake_case session-state spelling is covered.",
            language="typescript",
        ),
        Fires(
            snippet="const SESSIONS = new Map();",
            reason="The upper-case sessions spelling is covered.",
            language="typescript",
        ),
        Fires(
            snippet="const clientState = new Map();",
            reason="The camelCase client-state spelling is covered.",
            language="typescript",
        ),
        Fires(
            snippet="var client_state = new Object();",
            reason="The snake_case suspect name and Object initializer are both covered.",
            language="typescript",
        ),
        Fires(
            snippet="const perSession: Record<string, unknown> = {};",
            reason="A typed object literal under the camelCase per-session name is shared state.",
            language="typescript",
        ),
        Fires(
            snippet="const per_session = new Map();",
            reason="The snake_case per-session spelling is covered.",
            language="typescript",
        ),
        Silent(
            snippet="// const sessions = new Map();",
            reason="A commented-out store declaration is prose, not active state.",
            language="typescript",
        ),
        Silent(
            snippet='const example = "const sessions = new Map();";',
            reason="A string containing a store example is documentation, not active state.",
            language="typescript",
        ),
        Silent(
            snippet="const sessionsByTenant = new Map();",
            reason="A longer identifier is outside the exact suspect-name boundary.",
            language="typescript",
        ),
        Silent(
            snippet="const sessions = SessionStore.connect();",
            reason="An external store initializer is not one of the in-memory container shapes.",
            language="typescript",
        ),
        Silent(
            snippet="sessions = new Map();",
            reason="An assignment without a declaration does not establish module-owned storage.",
            language="typescript",
        ),
    )

    MESSAGE = "Looks like per-connection state held in process memory."

    boundaries = _DECLARED_BOUNDARIES + (
        Fires(
            snippet="sessions = dict()",
            reason="dict() constructor at module scope is a dict-shaped store.",
        ),
        Fires(
            snippet="from collections import defaultdict\nsessions = defaultdict(dict)",
            reason="defaultdict() constructor at module scope is a dict-shaped store.",
        ),
        Fires(
            snippet="from collections import OrderedDict\nsessions = OrderedDict()",
            reason="OrderedDict() constructor at module scope is a dict-shaped store.",
        ),
        Fires(
            snippet="import collections\nsessions = collections.defaultdict(dict)",
            reason="collections.defaultdict() at module scope is a dict-shaped store.",
        ),
        Silent(
            snippet="def handler():\n    sessions = defaultdict(dict)",
            reason="A dict-shaped store built inside a function is request-local, not process-wide state.",
        ),
        Silent(
            snippet="sessions = []",
            reason="A list is not a dict-shaped store.",
        ),
    )

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
                    if not _is_dict_shape(node.value):
                        continue
                    targets = [node.target]
                else:
                    if not _is_dict_shape(node.value):
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
