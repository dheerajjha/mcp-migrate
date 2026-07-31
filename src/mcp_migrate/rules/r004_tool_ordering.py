import re

from .base import Finding, Project, Rule

# This intentionally matches raw text, not just code (see base.py's
# `search`/`search_code` split): `tools/list` here is the literal
# JSON-RPC method name we want to find regardless of whether it shows up
# as a string in a manual dispatcher or as a decorator/def, so this rule
# does its own line scan below rather than using `search_code`.
HANDLER_RX = re.compile(r"def\s+list_tools\b|tools/list|@[\w.]*\blist_tools\b")


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


class NondeterministicToolOrder(Rule):
    id = "R004"
    title = "tools/list order is not deterministic"
    severity = "advisory"
    spec_ref = "Deterministic tool ordering (SHOULD)"
    fix = (
        "Sort the tools you return. Stable ordering lets clients cache and it lifts "
        "LLM prompt-cache hit rates for everyone downstream."
    )

    def check(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        for f in project.files:
            # A decorator (`@server.list_tools()`) and the `def` line right
            # below it both match the handler pattern for the *same*
            # function -- track already-covered spans so one handler can't
            # produce two findings.
            covered: list[tuple[int, int]] = []
            for line_no, line in enumerate(f.lines, start=1):
                if not HANDLER_RX.search(line):
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
                out.append(self.finding(
                    "Tools are returned without an explicit sort.", f, line_no, line.strip(),
                ))
        return out
