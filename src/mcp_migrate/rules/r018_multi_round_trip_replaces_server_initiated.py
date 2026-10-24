import ast
import re
from bisect import bisect_right

from .base import Finding, Fires, Project, Rule, Silent, _in_content_span, wire_method

# Start a quoted-key match in code before its opening quote, so search_code
# can reject quoted field names embedded in prose strings. Matching quote
# delimiters keep longer keys such as "elicitationId's" outside the boundary.
TS_GAP = r"(?:\s|/\*(?:[^*]|\*(?!/))*\*/|//[^\n]*(?:\n|$))*"
TS_ELICITATION_ID_RX = (
    rf"(?:[\[{{,:=]|\.{TS_GAP}(?:get|set|has|delete){TS_GAP}\(){TS_GAP}"
    rf"""(?P<quote>["'`])elicitationId(?P=quote)(?={TS_GAP}(?:[\]}}:,);]|$))"""
)

# Code-shaped identifiers -- SDK model/class names or plain Python names,
# matched with search_code so a docstring/comment mention doesn't count.
# `list_roots`/`create_message` are not "a little more generic-sounding",
# which is what this comment used to say -- they are the names anyone gives
# the function that builds a message or lists roots, in any protocol. A bare
# `create_message` matched an LSP wire-framing helper in oraios/serena and
# contributed to a `breaking` grade published about a project whose MCP code
# was clean (#289). r007 already solved this by requiring the `session.`
# receiver, so this now carries the same anchor rather than the bare name,
# The SDK schema names beside it are distinctive and stay unanchored --
# gating those would only add a way to miss a real finding. They are
# otherwise the same signals r007 ships
# with for these two features, just now also reported as `breaking` under
# SEP-2322's replacement of the whole server-initiated-request pattern (as
# opposed to r007's "still deprecated, not yet gone" framing). The two
# rules firing on the same line is expected, not a bug -- both claims are
# true -- but showing the reader two contradicting severities for one
# symbol isn't, so `overlap.py` collapses the pair back into a single
# finding at report time (see #221).
FEATURES_CODE = {
    r"\bsession\.list_roots\b|\bListRootsRequest(?:Params|Schema)?\b|\bListRootsResult(?:Schema)?\b": "Server-initiated roots/list",
    r"\bsession\.create_message\b|\bCreateMessageRequest(?:Params|Schema)?\b|\bCreateMessageResult(?:Schema)?\b": "Server-initiated sampling/createMessage",
    r"\bElicitRequest(?:Params|Schema)?\b|\bElicitResult(?:Schema)?\b": "Server-initiated elicitation/create",
    r"\bElicitCompleteNotificationParams(?:Schema)?\b": "notifications/elicitation/complete",
    r"\belicitationId\b": "elicitationId",
}

# JSON-RPC method-name strings. Namespaced with a slash, so unlike a bare
# word these aren't things unrelated code reuses by accident -- but for
# that same reason (a slash isn't valid in a Python identifier) they can
# only ever appear inside a STRING token, so search_code would never find
# them (see the notifications/initialized note in r009). Use search_wire.
FEATURES_LITERAL = {
    wire_method("roots/list"): "Server-initiated roots/list",
    wire_method("sampling/createMessage"): "Server-initiated sampling/createMessage",
    wire_method("elicitation/create"): "Server-initiated elicitation/create",
    wire_method("notifications/elicitation/complete"): (
        "notifications/elicitation/complete"
    ),
}

# The TypeScript SDK exports Zod schemas for request handling. These names
# are specific to the removed MCP server-initiated requests, unlike generic
# callback names such as `createMessage` or `listRoots`.
#
# `elicitationId` is the odd one out here: it isn't a request/schema class,
# it's a field name a handler reads off an incoming payload
# (`params.elicitationId`), the same shape in both languages -- see
# `elicitationId` in FEATURES_CODE above. It has no `Schema` counterpart;
# quoted keys use a code-anchored pattern here and exact AST strings in Python.
TS_FEATURES_CODE = {
    r"\bListRootsRequestSchema\b": "Server-initiated roots/list",
    r"\bCreateMessageRequestSchema\b": "Server-initiated sampling/createMessage",
    r"\bElicitRequestSchema\b": "Server-initiated elicitation/create",
    r"\belicitationId\b": "elicitationId",
}


class MultiRoundTripReplacesServerInitiated(Rule):
    id = "R018"
    title = "Uses a server-initiated request replaced by Multi Round-Trip Requests"
    severity = "breaking"
    spec_ref = "SEP-2322 https://modelcontextprotocol.io/specification/2026-07-28/changelog"
    fix = (
        "Server-initiated roots/list, sampling/createMessage and elicitation/create are "
        "gone, along with notifications/elicitation/complete and elicitationId. Return "
        "an InputRequiredResult instead and let the client retry the call with "
        "inputResponses."
    )
    languages = ("python", "typescript")
    boundaries = (
        Fires(
            snippet=(
                "async def handler(ctx):\n"
                "    return await ctx.session.create_message(messages=[])"
            ),
            reason="Sampling through the MCP session is a removed server-initiated request.",
        ),
        Fires(
            snippet=(
                "async def gather(ctx):\n"
                "    return await ctx.session.list_roots()\n"
            ),
            reason="Listing roots through the MCP session is a removed server-initiated request.",
        ),
        Fires(
            snippet="from mcp.types import ListRootsResult",
            reason="The SDK result type belongs to the removed server-initiated roots flow.",
        ),
        Fires(
            snippet='METHOD = "elicitation/create"',
            reason="The exact removed elicitation wire method is still present.",
        ),
        Fires(
            snippet="def on_complete(params):\n    return params.elicitationId\n",
            reason="The removed elicitation correlation field is active Python code.",
        ),
        Fires(
            snippet='def on_complete(payload):\n    return payload["elicitationId"]\n',
            reason="Reading the removed correlation field by dictionary key is active Python code.",
        ),
        Silent(
            snippet='HELP = "Use elicitationId to correlate responses."',
            reason="A sentence mentioning the field is prose, not its exact quoted name.",
        ),
        Silent(
            snippet=(
                "def create_message(payload):\n"
                "    return payload"
            ),
            reason="A generic message-building helper without the session receiver is not MCP sampling.",
        ),
        Silent(
            snippet=(
                "import os\n\n"
                "def list_roots(base):\n"
                "    return sorted(os.listdir(base))\n"
            ),
            reason="A directory-listing helper without the session receiver is not MCP roots.",
        ),
        Silent(
            snippet=(
                'def handler():\n'
                '    """Sent CreateMessageRequest before Multi Round-Trip Requests replaced it."""\n'
            ),
            reason="A docstring that names the old request type is documentation, not surface.",
        ),
        Silent(
            snippet="# CreateMessageRequest and sampling/createMessage were replaced by MRTR",
            reason="A migration comment is prose, not an active server-initiated request.",
        ),
        Silent(
            snippet='METRIC = "roots/listeners"',
            reason="A longer wire name is outside the exact roots/list method boundary.",
        ),
        Silent(
            snippet="result = InputRequiredResult(inputResponses=[])",
            reason="The replacement Multi Round-Trip result shape is already migrated.",
        ),
        Fires(
            snippet=(
                'import { CreateMessageRequestSchema } from "@modelcontextprotocol/sdk/types.js";\n'
                "client.setRequestHandler(CreateMessageRequestSchema, handler);"
            ),
            reason="The removed sampling request schema is active TypeScript MCP code.",
            language="typescript",
        ),
        Fires(
            snippet='const legacyMethod = "sampling/createMessage";',
            reason="The exact removed sampling wire method is still present in TypeScript.",
            language="typescript",
        ),
        Fires(
            snippet="function onReply(params: { elicitationId: string }) { return params.elicitationId; }",
            reason="The removed elicitation correlation field is active TypeScript code.",
            language="typescript",
        ),
        Fires(
            snippet='const eid = params["elicitationId"];',
            reason="Reading the removed correlation field by quoted key is active TypeScript code.",
            language="typescript",
        ),
        Silent(
            snippet='const help = "Use elicitationId to correlate responses.";',
            reason="A sentence mentioning the field is prose, not its exact quoted name.",
            language="typescript",
        ),
        Silent(
            snippet="// CreateMessageRequestSchema and sampling/createMessage were replaced by MRTR.",
            reason="A TypeScript migration comment is prose, not active MCP surface.",
            language="typescript",
        ),
        Silent(
            snippet='const method = "sampling/createMessageLatency";',
            reason="A longer TypeScript wire name is outside the exact method boundary.",
            language="typescript",
        ),
        Silent(
            snippet="const result = { inputResponses: [] };",
            reason="The replacement Multi Round-Trip result shape is already migrated.",
            language="typescript",
        ),
        Silent(
            snippet=(
                'const createMessage = (text: string) => ({ role: "user", text });\n'
                'const listRoots = () => fs.readdirSync("/");\n'
            ),
            reason="Generic createMessage/listRoots callbacks are not the SDK's request schemas.",
            language="typescript",
        ),
    )

    def check(self, project: Project) -> list[Finding]:
        if project.language == "typescript":
            out: list[Finding] = []
            for pattern, name in TS_FEATURES_CODE.items():
                for f, line, text in project.search_code(pattern):
                    out.append(self.finding(
                        f"{name} was replaced by Multi Round-Trip Requests (InputRequiredResult "
                        "+ inputResponses).",
                        f,
                        line,
                        text,
                        feature=name,
                    ))
            for pattern, name in FEATURES_LITERAL.items():
                for f, line, text in project.search_wire(pattern):
                    out.append(self.finding(
                        f"{name} was replaced by Multi Round-Trip Requests (InputRequiredResult "
                        "+ inputResponses).",
                        f,
                        line,
                        text,
                        feature=name,
                    ))
            return self._with_typescript_keys(project, out)

        out: list[Finding] = []
        for pattern, name in FEATURES_CODE.items():
            # search_code: a comment/docstring mentioning "sampling" or
            # "roots/list" isn't a real dependency on it (see
            # r007_deprecated_features.py, same reasoning).
            for f, line, text in project.search_code(pattern):
                out.append(self.finding(
                    f"{name} was replaced by Multi Round-Trip Requests (InputRequiredResult "
                    "+ inputResponses).",
                    f, line, text,
                    feature=name,
                ))
        for pattern, name in FEATURES_LITERAL.items():
            # Already bounded at the definition, so both this path and the
            # TypeScript one above get the end boundary from the same place.
            # Wrapping again here would escape the pattern's own metacharacters
            # and match nothing.
            for f, line, text in project.search_wire(pattern):
                out.append(self.finding(
                    f"{name} was replaced by Multi Round-Trip Requests (InputRequiredResult "
                    "+ inputResponses).",
                    f, line, text,
                    feature=name,
                ))
        return self._with_python_keys(project, out)

    def _with_python_keys(self, project: Project, out: list[Finding]) -> list[Finding]:
        seen = {(f.path, f.line) for f in out if f.feature == "elicitationId"}
        for f in project.files:
            tree = f.tree
            if tree is None:
                try:
                    tree = ast.parse(f.text)
                except (SyntaxError, ValueError):
                    continue  # Without syntax, a quoted mention could be prose.
            prose_nodes = set()
            for owner in ast.walk(tree):
                if isinstance(owner, ast.BinOp):
                    # A fragment of a computed string is not the complete key.
                    prose_nodes.update(id(value) for value in (owner.left, owner.right))
                if isinstance(owner, (ast.Attribute, ast.Subscript)):
                    # Transforming/indexing the literal itself is not a read of
                    # that key; payload["elicitationId"].upper() still is one.
                    prose_nodes.add(id(owner.value))
                if isinstance(owner, ast.JoinedStr):
                    # F-string text fragments are not complete wire literals.
                    # Keep nested expressions available for real payload keys.
                    prose_nodes.update(
                        id(value) for value in owner.values if isinstance(value, ast.Constant)
                    )
                if not isinstance(owner, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if owner.body and isinstance(owner.body[0], ast.Expr):
                    value = owner.body[0].value
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        prose_nodes.add(id(value))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or node.value != "elicitationId":
                    continue
                if id(node) in prose_nodes:
                    continue
                literal = ast.get_source_segment(f.text, node) or ""
                if literal.lstrip("rRuUbBfF").startswith(('"""', "'''")):
                    continue  # Keep triple-quoted prose outside the boundary.
                key = (f.path, node.lineno)
                if key in seen:
                    continue
                seen.add(key)
                out.append(self.finding(
                    "elicitationId was replaced by Multi Round-Trip Requests (InputRequiredResult "
                    "+ inputResponses).",
                    f, node.lineno, f.lines[node.lineno - 1].strip(),
                    feature="elicitationId",
                ))
        return out

    def _with_typescript_keys(self, project: Project, out: list[Finding]) -> list[Finding]:
        # Inspect the whole source so a concatenation on the following line
        # cannot turn a string fragment into an exact wire literal. Bare
        # grouping/assertion expressions are conservatively left unclassified;
        # key-method arguments still count when the call's result is combined.
        seen = {(f.path, f.line) for f in out if f.feature == "elicitationId"}
        for f in project.files:
            offsets = [0] + [m.end() for m in re.finditer("\n", f.text)]
            spans = project._spans_for(f) or []
            for match in re.finditer(TS_ELICITATION_ID_RX, f.text):
                row = bisect_right(offsets, match.start()) - 1
                if _in_content_span(row + 1, match.start() - offsets[row], spans):
                    continue
                row = bisect_right(offsets, match.start("quote")) - 1
                key = (f.path, row + 1)
                if key in seen:
                    continue
                seen.add(key)
                out.append(self.finding(
                    "elicitationId was replaced by Multi Round-Trip Requests (InputRequiredResult "
                    "+ inputResponses).",
                    f, row + 1, f.lines[row].strip(),
                    feature="elicitationId",
                ))
        return out
