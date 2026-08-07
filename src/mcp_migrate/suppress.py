"""Inline suppression: `# mcp-migrate: ignore[R001] -- reason`.

This tool ships with open false-positive classes and says so in its own
README -- *"Treat a finding as a prompt to look, not as a verdict."* That
is honest, and until now it was also unworkable in CI, where a breaking
finding exits 1 and a user with one wrong finding had two options: switch
the rule off for the whole project, or stop running the tool.

There is also the legitimate case, which no amount of rule tuning fixes:
code that genuinely reads the way a rule matches, on purpose, and is not
going to change.

Four things this deliberately does *not* allow, each because the sloppy
version rots:

**No blanket ignores.** The rule id is required. `# mcp-migrate: ignore`
with no id silences whatever happens to be on that line today, including
findings from rules written next year, and nobody ever revisits it.

**No silent suppressions.** Every run reports how many findings were
suppressed, and `--show-suppressions` lists each one with its reason.
Suppression that cannot be audited is just a deleted finding with extra
steps, and this tool's whole posture is that a claim nobody can check is
worse than no claim.

**A reason is required.** Same argument one level down: `ignore[R001]`
with no explanation is unreviewable six months later, when the person who
wrote it has left and nobody dares remove it.

**Unused suppressions are reported.** A suppression that no longer
matches anything is either a fixed bug or a moved line, and both are
worth knowing -- otherwise they accumulate forever and the next reader
cannot tell which are load-bearing.

On the design question the issue raised -- *does a suppressed finding
still count against the grade?* -- see `apply()`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# `# mcp-migrate: ignore[R001] -- proxy shim, not MCP session state`
# `// mcp-migrate: ignore[R001, R006] -- deliberate`
#
# Both comment syntaxes, since the same rules read Python and TypeScript.
# The separator before the reason is `--` or `:` so it reads naturally in
# either language without fighting the `//` prefix.
DIRECTIVE_RX = re.compile(
    r"(?:#|//)\s*mcp-migrate:\s*ignore\s*"
    r"\[(?P<rules>[^\]]*)\]"
    r"(?:\s*(?:--|:)\s*(?P<reason>.*?))?\s*$",
    re.IGNORECASE,
)

# The same thing written without the rule list. Matched only so it can be
# reported as an error -- silently ignoring a directive someone believed
# was working is the worst outcome available here, because they will think
# the finding is suppressed and it will not be.
BARE_RX = re.compile(r"(?:#|//)\s*mcp-migrate:\s*ignore\s*(?![\[\w])", re.IGNORECASE)

RULE_ID_RX = re.compile(r"^R\d{3}$", re.IGNORECASE)


@dataclass
class Suppression:
    path: Path
    line: int
    rule_ids: tuple[str, ...]
    reason: str
    used: bool = False

    def location(self) -> str:
        return f"{self.path}:{self.line}"


@dataclass
class Problem:
    """A malformed directive. Reported, never silently dropped."""

    path: Path
    line: int
    message: str

    def location(self) -> str:
        return f"{self.path}:{self.line}"


def parse_file(path: Path, text: str) -> tuple[list[Suppression], list[Problem]]:
    suppressions: list[Suppression] = []
    problems: list[Problem] = []

    for i, line in enumerate(text.splitlines(), start=1):
        m = DIRECTIVE_RX.search(line)
        if not m:
            if BARE_RX.search(line):
                problems.append(Problem(
                    path, i,
                    "`mcp-migrate: ignore` needs a rule id, e.g. `ignore[R001]`. "
                    "A blanket ignore would also silence rules that do not exist yet.",
                ))
            continue

        raw_ids = [r.strip() for r in m.group("rules").replace(",", " ").split()]
        rule_ids = tuple(r.upper() for r in raw_ids if RULE_ID_RX.match(r))
        bad = [r for r in raw_ids if not RULE_ID_RX.match(r)]

        if bad:
            problems.append(Problem(
                path, i, f"not a rule id: {', '.join(repr(b) for b in bad)}",
            ))
        if not rule_ids:
            problems.append(Problem(path, i, "no valid rule id in the ignore directive"))
            continue

        reason = (m.group("reason") or "").strip()
        if not reason:
            problems.append(Problem(
                path, i,
                f"`ignore[{', '.join(rule_ids)}]` has no reason. Add one after `--`; "
                "an unexplained suppression is unreviewable later.",
            ))

        suppressions.append(Suppression(path, i, rule_ids, reason))

    return suppressions, problems


def collect(project) -> tuple[list[Suppression], list[Problem]]:
    """Every directive in the project, plus every malformed one."""
    suppressions: list[Suppression] = []
    problems: list[Problem] = []
    for f in project.files:
        s, p = parse_file(f.path, f.text)
        suppressions.extend(s)
        problems.extend(p)
    return suppressions, problems


def _index(suppressions: list[Suppression]) -> dict:
    index: dict = {}
    for s in suppressions:
        index.setdefault((str(s.path), s.line), []).append(s)
    return index


def apply(findings, suppressions: list[Suppression]):
    """Split findings into (kept, suppressed), marking suppressions used.

    **The grade question.** A suppressed finding does not reach the
    scorer, because a suppression that still costs you the grade is not a
    suppression -- the user's only remaining move would be to stop running
    the tool, which is the outcome this feature exists to prevent.

    The cost is real and worth naming: the grade becomes partly
    self-reported. Three things keep that honest rather than hiding it,
    all of them at the caller:

      * the count is always printed, never conditional on a flag
      * `--show-suppressions` lists every one with its file, rule and
        reason, so a reviewer can audit the lot in one command
      * a suppression must name its rule and carry a reason, so the audit
        is actually readable

    Which is the same standard the badge work (#101) applied to a stale
    grade: the claim can be wrong, but it cannot be quietly wrong.

    Project-level findings (no line) are never suppressed. There is no
    line to attach a comment to, and letting them be silenced from an
    arbitrary line elsewhere would be a blanket ignore wearing a
    disguise.
    """
    index = _index(suppressions)
    kept, suppressed = [], []

    for f in findings:
        if f.path is None or f.line is None:
            kept.append(f)
            continue
        matches = [
            s for s in index.get((str(f.path), f.line), [])
            if f.rule_id.upper() in s.rule_ids
        ]
        if matches:
            for s in matches:
                s.used = True
            suppressed.append(f)
        else:
            kept.append(f)

    return kept, suppressed


def unused(suppressions: list[Suppression]) -> list[Suppression]:
    """Suppressions that matched nothing.

    Either the finding was fixed or the code moved. Both are worth
    knowing: unused suppressions accumulate silently, and once there are
    enough of them nobody can tell which are still load-bearing.
    """
    return [s for s in suppressions if not s.used]
