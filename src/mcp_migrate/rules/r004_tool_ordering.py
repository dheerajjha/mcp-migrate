import re

from .base import Finding, Project, Rule, _in_content_span

# This intentionally matches raw text, not just code (see base.py's
# `search`/`search_code` split): `tools/list` here is the literal
# JSON-RPC method name we want to find regardless of whether it shows up
# as a string in a manual dispatcher or as a decorator/def, so this rule
# does its own line scan below rather than using `search_code`.
HANDLER_RX = re.compile(r"def\s+list_tools\b|tools/list|@[\w.]*\blist_tools\b")

QUOTES = ("\"", "'", "`")
# A dict/object value that opens a function body right there on the same line.
INLINE_FUNCTION_VALUE_RX = re.compile(
    r"^\s*(?:async\s+)?(?:function\b|lambda\b|\(|[\w$]+\s*=>)"
)
# `{"jsonrpc": "2.0", "id": 2, "method": "tools/list"}` -- the literal is the
# method field of a request being *sent*. Only requests carry `method`, so
# this is always the client side of the wire, never a handler returning tools.
METHOD_FIELD_VALUE_RX = re.compile(r"""(?:["']method["']|\bmethod)\s*:\s*$""")

# `return { tools: alphabetize(registry) }` -- the sort may live one function
# away, extracted into a helper. Chasing that is a call graph, not a line
# scan, and this is a regex-based tool by design (#91). Rather than resolve
# the call -- or worse, keep scanning past it and stumble onto some sibling
# statement's `.sort(` -- treat any call assigned to `tools` as unprovable
# either way and stay silent. A wrong "no sort" against a helper that does
# sort costs more than a missed one against a helper that doesn't.
TOOLS_CALL_RESULT_RX = re.compile(r"""(?:["']tools["']|\btools\b)\s*:\s*[A-Za-z_$][\w.$]*\s*\(""")


def _is_config_or_request_use(line: str, start: int, end: int) -> bool:
    """True when the matched wire method name is naming a method rather than
    handling one -- a map key, a lookup into that map, or the `method` field
    of a request being sent.

    A wire method name lands on a line for reasons that have nothing to do
    with listing tools. All three of these are on dealfluence/adeu (#218),
    and account for 4 of the 5 R004 findings we reported against it:

        CACHE_POLICY = {"tools/list": {"ttl_ms": 3_600_000}}   # a key
        CACHE_POLICY["tools/list"]                             # reading it
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})  # a client

    None of them returns anything tool-shaped, so "tools are returned without
    an explicit sort" is just false at those lines -- and worse, the sort
    look-ahead below then scans whatever happens to follow, which for a dict
    entry is its sibling entries. A method name used as a key, or as the
    method field of an outbound request, is not a call site.

    Only quoted string literals are considered here. `def list_tools`,
    `@server.list_tools()` and `ListToolsRequestSchema` are unaffected, and
    so is every shape where the literal is compared or passed rather than
    keyed on -- `if method == "tools/list":`, `case "tools/list":`,
    `setRequestHandler("tools/list", handler)`.

    The one key shape kept alive is a value that opens a function body on
    the same line::

        const HANDLERS = {"tools/list": async () => ({tools: TOOLS})};

    There the handler body really is inside the window about to be scanned,
    so the check still means something. When the value is a bare identifier
    (``{"tools/list": handle_list_tools}``) this skips and accepts the miss:
    that body lives in another function, so the look-ahead was never going
    to find its sort either way. R004 is advisory -- three wrong points on
    a stranger's grade cost more than three missed ones.
    """
    before, after = line[:start], line[end:]
    if not (before.endswith(QUOTES) and after[:1] in QUOTES):
        return False
    before, after = before[:-1], after[1:]

    if before.rstrip().endswith("[") and after.lstrip().startswith("]"):
        return True
    if METHOD_FIELD_VALUE_RX.search(before):
        return True

    rest = after.lstrip()
    if not rest.startswith(":"):
        return False
    lead = before.rstrip()
    if lead and not lead.endswith(("{", ",")):
        return False
    return not INLINE_FUNCTION_VALUE_RX.match(rest[1:])


def _body_bounds(lines: list[str], line_no: int) -> tuple[int, int]:
    """Return (body_start, body_end) 0-based bounds for the block that
    starts at 1-based `line_no`.

    `line_no` may point at a decorator, at the `def` it decorates, or at an
    arbitrary line inside a manual dispatch branch -- in every case we skip
    forward past any remaining lines at the *same* indentation (stacked
    decorators, the `def` line itself) before we start looking for the
    dedent that ends the block. Without that skip, a decorator and the
    `def` line right below it -- both at indent 0 -- look like two
    separate, already-closed blocks instead of one function.
    """
    indent = len(lines[line_no - 1]) - len(lines[line_no - 1].lstrip())
    j = line_no  # 0-based index of the line right after the match
    while j < len(lines):
        text = lines[j]
        if not text.strip():
            j += 1
            continue
        if len(text) - len(text.lstrip()) > indent:
            break  # entered the indented body
        if len(text) - len(text.lstrip()) < indent:
            break  # nothing but a header on its own, no body found
        j += 1  # still header-level (another decorator, or the `def` line)
    body_start = j
    end = len(lines)
    for k in range(body_start, len(lines)):
        text = lines[k]
        if not text.strip():
            continue
        if len(text) - len(text.lstrip()) <= indent:
            end = k
            break
    return body_start, end


TS_HANDLER_RX = re.compile(r"ListToolsRequestSchema|listTools|tools/list")
TS_SORT_RX = re.compile(r"\.(?:sort|toSorted)\s*\(|\bsorted\s*\(|\bsortBy\b|\borderBy\b", re.IGNORECASE)


def _ts_body_bounds(
    lines: list[str], line_no: int, spans: list[tuple[tuple[int, int], tuple[int, int]]] | None
) -> tuple[int, int]:
    """Return (body_start, body_end) 0-based bounds for the TypeScript handler
    block starting at 1-based `line_no` using brace-depth scanning.

    Scans forward from `line_no` to find the opening '{' of the handler body,
    then tracks '{' and '}' braces (skipping any inside comments or strings via
    `spans`) until depth returns to 0. If no matching closing brace is found,
    falls back to min(len(lines), line_no + 40).
    """
    depth = 0
    found_first_brace = False
    body_start = line_no

    for cur_line_no in range(line_no, len(lines) + 1):
        line = lines[cur_line_no - 1]
        for col, char in enumerate(line):
            if spans is not None and _in_content_span(cur_line_no, col, spans):
                continue
            if char == "{":
                if not found_first_brace:
                    found_first_brace = True
                    body_start = cur_line_no
                depth += 1
            elif char == "}" and found_first_brace:
                depth -= 1
                if depth == 0:
                    return body_start, cur_line_no

    if not found_first_brace:
        return line_no, min(len(lines), line_no + 40)
    return body_start, len(lines)


class NondeterministicToolOrder(Rule):
    id = "R004"
    title = "tools/list order is not deterministic"
    severity = "advisory"
    spec_ref = "Deterministic tool ordering (SHOULD)"
    fix = (
        "Sort the tools you return. Stable ordering lets clients cache and it lifts "
        "LLM prompt-cache hit rates for everyone downstream."
    )
    languages = ("python", "typescript")

    def check(self, project: Project) -> list[Finding]:
        if project.language == "typescript":
            return self._check_ts(project)
        return self._check_python(project)

    def _check_python(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        for f in project.files:
            # A decorator (`@server.list_tools()`) and the `def` line right
            # below it both match the handler pattern for the *same*
            # function -- track already-covered spans so one handler can't
            # produce two findings.
            covered: list[tuple[int, int]] = []
            # Prose spans, for the same reason `search_wire` exists: the
            # `tools/list` half of HANDLER_RX is a raw literal match, so a
            # module docstring describing the HTTP surface ("POST
            # /mcp/tools/call - POST /mcp/tools/list") otherwise reads as a
            # tool handler with no sort. Seen on a real server.
            prose = project._prose_spans_for(f)
            for line_no, line in enumerate(f.lines, start=1):
                m = HANDLER_RX.search(line)
                if not m:
                    continue
                if prose is not None and _in_content_span(line_no, m.start(), prose):
                    continue
                if _is_config_or_request_use(line, m.start(), m.end()):
                    continue
                if any(start <= line_no <= end for start, end in covered):
                    continue

                # Scope the look-ahead to the enclosing block by indentation
                # instead of a fixed number of lines: a fixed window either
                # cuts a long handler short (false positive) or bleeds into
                # the next function and picks up an unrelated `.sort()`
                # (false negative).
                body_start, end_line = _body_bounds(f.lines, line_no)
                covered.append((line_no, end_line))

                window = "\n".join(f.lines[line_no - 1:end_line])
                if "sorted(" in window or ".sort(" in window:
                    continue
                if TOOLS_CALL_RESULT_RX.search(window):
                    continue
                out.append(self.finding(
                    "Tools are returned without an explicit sort.", f, line_no, line.strip(),
                ))
        return out

    def _check_ts(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        for f in project.files:
            covered: list[tuple[int, int]] = []
            prose = project._prose_spans_for(f)
            content_spans = project._spans_for(f)
            for line_no, line in enumerate(f.lines, start=1):
                if line.strip().startswith("import "):
                    continue
                m = TS_HANDLER_RX.search(line)
                if not m:
                    continue
                if prose is not None and _in_content_span(line_no, m.start(), prose):
                    continue
                if _is_config_or_request_use(line, m.start(), m.end()):
                    continue
                if any(start <= line_no <= end for start, end in covered):
                    continue

                body_start, end_line = _ts_body_bounds(f.lines, line_no, content_spans)
                covered.append((line_no, end_line))

                window = "\n".join(f.lines[line_no - 1:end_line])
                if TS_SORT_RX.search(window):
                    continue
                if TOOLS_CALL_RESULT_RX.search(window):
                    continue
                out.append(self.finding(
                    "Tools are returned without an explicit sort.", f, line_no, line.strip(),
                ))
        return out

