"""Bounded R003 syntax analysis, not a TypeScript type checker.

Only inline payloads and directly SDK-annotated parameters/locals qualify.
Named imports (including aliases) are resolved through lexical declarations;
this does not infer cross-file types, aliases of aliases, assignments, or
computed/spread options and headers. Unknown payloads or headers are left
alone. The declaration index handles shadowing conservatively; it is not
compiler binding/type semantics and does not track mutations or control flow.
"""
import json

from tree_sitter import Language, Parser
import tree_sitter_typescript


# Concrete members of ClientRequestSchema / ServerRequestSchema in the v1 SDK:
# https://github.com/modelcontextprotocol/typescript-sdk/blob/v1.x/src/types.ts
# Values say whether the transport requires Mcp-Name, not just Mcp-Method.
SDK_REQUESTS = dict.fromkeys((
    "PingRequest", "InitializeRequest", "CompleteRequest", "SetLevelRequest",
    "ListPromptsRequest", "ListResourcesRequest", "ListResourceTemplatesRequest",
    "SubscribeRequest", "UnsubscribeRequest", "ListToolsRequest",
    "GetTaskRequest", "GetTaskPayloadRequest", "ListTasksRequest",
    "CancelTaskRequest", "CreateMessageRequest", "ElicitRequest", "ListRootsRequest",
), False)
SDK_REQUESTS.update(CallToolRequest=True, ReadResourceRequest=True, GetPromptRequest=True)
NAMED_METHODS = {"tools/call", "resources/read", "prompts/get"}
LITERAL_METHODS = NAMED_METHODS | {"tools/list"}
FUNCTIONS = {
    "function_declaration", "function_expression", "arrow_function",
    "generator_function", "generator_function_declaration", "method_definition",
}
SCOPES = FUNCTIONS | {
    "program", "statement_block", "catch_clause", "for_statement",
    "for_in_statement", "class_declaration", "class",
}


def text(node):
    return node.text.decode("utf-8") if node is not None else ""


def literal(node):
    if node is not None and node.type == "string":
        # Escaped names are deliberately unknown rather than guessed.
        value = text(node)[1:-1]
        if "\\" not in value:
            return value
    return None


def children(node):
    return [c for c in node.named_children if c.type != "comment"] if node else []


def properties(node):
    if node is None or node.type != "object":
        return None
    out = {}
    for pair in children(node):
        if pair.type != "pair":
            return None
        key = pair.child_by_field_name("key")
        name = literal(key) if key.type == "string" else (
            text(key) if key.type == "property_identifier" else None
        )
        if name is None or name in out:
            return None
        out[name] = pair.child_by_field_name("value")
    return out


def member(node):
    if node is not None and node.type == "member_expression":
        return text(node.child_by_field_name("object")), text(node.child_by_field_name("property"))
    return None, None


class Syntax:
    def __init__(self, source, jsx):
        language = (tree_sitter_typescript.language_tsx if jsx
                    else tree_sitter_typescript.language_typescript)
        self.root = Parser(Language(language())).parse(source.encode("utf-8")).root_node
        self.scopes = {}
        self.parents = {}
        self.bindings = {}
        self.calls = []
        self._visit(self.root, None)

    def _bind(self, scope, pattern, declaration, sdk=None):
        if pattern is None:
            return
        if pattern.type in {"identifier", "type_identifier", "shorthand_property_identifier_pattern"}:
            self.bindings[scope].setdefault(text(pattern), []).append((declaration, sdk))
        else:
            for child in children(pattern):
                self._bind(scope, child, declaration)

    def _visit(self, node, scope):
        # Declaration names belong to the enclosing scope, not their own body.
        if node.type in {"function_declaration", "generator_function_declaration",
                         "class_declaration", "type_alias_declaration", "interface_declaration"}:
            self._bind(scope, node.child_by_field_name("name"), node)
        if node.type in SCOPES:
            parent, scope = scope, node.id
            self.parents[scope] = parent
            self.bindings[scope] = {}
            if node.type in {"function_expression", "generator_function", "class"}:
                self._bind(scope, node.child_by_field_name("name"), node)
            if node.type == "arrow_function":
                self._bind(scope, node.child_by_field_name("parameter"), node)
        self.scopes[node.id] = scope
        if node.type == "import_specifier":
            statement = node.parent.parent.parent
            source = literal(statement.child_by_field_name("source"))
            imported = text(node.child_by_field_name("name"))
            sdk = imported if source in {
                "@modelcontextprotocol/sdk/types", "@modelcontextprotocol/sdk/types.js",
            } and imported in SDK_REQUESTS else None
            self._bind(scope, node.child_by_field_name("alias") or node.child_by_field_name("name"), node, sdk)
        elif node.type in {"import_clause", "namespace_import"}:
            for child in children(node):
                if child.type == "identifier":
                    self._bind(scope, child, node)
        elif node.type in {"variable_declarator", "required_parameter", "optional_parameter",
                           "type_parameter", "catch_clause"}:
            pattern = node.child_by_field_name("name") or node.child_by_field_name("pattern") or node.child_by_field_name("parameter")
            target = scope
            if node.type == "variable_declarator" and node.parent.type == "variable_declaration":
                while self.parents[target] is not None and target != self.root.id:
                    # `var` is function-scoped, unlike let/const.
                    ancestor = node
                    while ancestor.id != target:
                        ancestor = ancestor.parent
                    if ancestor.type in FUNCTIONS:
                        break
                    target = self.parents[target]
            self._bind(target, pattern, node)
        if node.type == "call_expression":
            self.calls.append(node)
        for child in children(node):
            self._visit(child, scope)

    def binding(self, name, at):
        scope = self.scopes[at.id]
        while scope is not None:
            matches = self.bindings[scope].get(name, [])
            if matches:
                return matches[0] if len(matches) == 1 else (None, None)
            scope = self.parents[scope]
        return None, None

    def payload(self, node):
        """Return requires-name, or None when the payload is not proven MCP."""
        if node is None:
            return None
        if node.type == "call_expression":
            obj, prop = member(node.child_by_field_name("function"))
            args = children(node.child_by_field_name("arguments"))
            if ((obj, prop) != ("JSON", "stringify") or len(args) != 1
                    or args[0].type not in {"object", "identifier"}):
                return None
            # A locally replaced JSON object is not the built-in serializer.
            if self.binding("JSON", node)[0] is not None:
                return None
            return self.payload(args[0])
        if node.type == "object":
            props = properties(node)
            if props is None:
                return None
            method = literal(props.get("method"))
            if method in LITERAL_METHODS:
                return method in NAMED_METHODS
        if node.type == "string":
            value = literal(node)
            if value is not None:
                try:
                    data = json.loads(value)
                except json.JSONDecodeError:
                    return None
                if isinstance(data, dict):
                    method = data.get("method")
                    if isinstance(method, str) and method in LITERAL_METHODS:
                        return method in NAMED_METHODS
        if node.type == "identifier":
            declaration, _ = self.binding(text(node), node)
            if declaration is None or declaration.type not in {
                "variable_declarator", "required_parameter", "optional_parameter",
            }:
                return None
            pattern = declaration.child_by_field_name("name") or declaration.child_by_field_name("pattern")
            if pattern is None or pattern.type != "identifier":
                return None
            if declaration.type == "variable_declarator" and declaration.start_byte > node.start_byte:
                return None
            annotation = children(declaration.child_by_field_name("type"))
            if len(annotation) != 1 or annotation[0].type != "type_identifier":
                return None
            _, sdk = self.binding(text(annotation[0]), annotation[0])
            if sdk is not None:
                return SDK_REQUESTS[sdk]
        return None

    def deficient_calls(self):
        # Tree traversal is source-ordered, including multiple calls on one line.
        for call in self.calls:
            function = call.child_by_field_name("function")
            obj, prop = member(function)
            direct = text(function) if function.type == "identifier" else None
            if direct not in {"fetch", "axios", "got"} and prop not in {"post", "request"}:
                continue
            if call.has_error:
                continue
            args = children(call.child_by_field_name("arguments"))
            if not args:
                continue
            if prop == "post" and obj != "got":
                payload = args[1] if len(args) > 1 else None
                options = args[2] if len(args) > 2 else None
            else:
                options = args[0] if args[0].type == "object" else (args[1] if len(args) > 1 else None)
                props = properties(options) or {}
                payload = next((props[key] for key in ("body", "data", "json") if key in props), None)
            requires_name = self.payload(payload)
            if requires_name is None:
                continue
            props = properties(options) if options is not None else {}
            if props is None:
                continue
            headers = properties(props["headers"]) if "headers" in props else {}
            if headers is None:
                continue
            headers = {key.lower() for key in headers}
            missing_method = "mcp-method" not in headers
            missing_name = requires_name and "mcp-name" not in headers
            if missing_method or missing_name:
                yield call, missing_method, missing_name
