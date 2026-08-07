from __future__ import annotations

import argparse
import ast
import difflib
import itertools
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.table import Table

from . import __version__
from . import suppress as suppress_mod
from .fixers import all_fixers
from .grade import badge_url, letter, score
from .languages import DISPLAY, PARTIAL, SUPPORTED, describe, primary, survey
from .rules import all_rules
from .rules.base import Project, SourceFile
from .scan import load_project
from .sdk import detect_sdk

SPEC = "2026-07-28"
SEV_STYLE = {"breaking": "bold red", "deprecated": "yellow", "advisory": "cyan"}
SEV_ORDER = {"breaking": 0, "deprecated": 1, "advisory": 2}
CONF_STYLE = {"safe": "bold green", "review": "yellow"}
MAX_SHOWN_PER_RULE = 5

# 0 = checked it, it's fine. 1 = checked it, it's broken. 2 = could not
# check it. Keeping "couldn't read this" distinct from "this is clean" is
# the whole point of the exit codes here: CI that treats a refusal as a
# pass is exactly how an ungraded repo ends up wearing an A badge.
EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_UNSCANNABLE = 2

LANG_ISSUE_URL = "https://github.com/dheerajjha/mcp-migrate/issues/30"
# #30 was the coverage gap; it closed once every rule read TypeScript.
# What's left is whether a `PARTIAL` language ever gets graded at all --
# a decision, not a count -- and that's #172.
GRADE_ISSUE_URL = "https://github.com/dheerajjha/mcp-migrate/issues/172"
# JavaScript loads but no rule declares it yet -- step 2 of #149.
JS_ISSUE_URL = "https://github.com/dheerajjha/mcp-migrate/issues/149"


@dataclass
class CheckResult:
    """Everything one `check` produced.

    `findings` excludes suppressed ones -- they are in `suppressed`, and
    the score is computed without them. See suppress.apply for why, and
    for what keeps that honest.
    """

    project: object
    rules: dict
    findings: list
    value: int
    grade: str
    suppressed: list
    suppressions: list
    suppression_problems: list


def run_check_detailed(root: Path, *, include_tests: bool = False) -> "CheckResult":
    project = load_project(root, include_tests=include_tests)
    rules = {r.id: r for r in all_rules()}
    findings = []
    # One pass per (rule, language it declares), against a project view
    # filtered to that language. Views are cached because building one
    # discards the span cache, and re-tokenizing every file per rule is the
    # difference between a fast scan and a slow one.
    views: dict[str, Project] = {}
    for rule in rules.values():
        for language in rule.languages:
            if language not in views:
                views[language] = project.for_language(language)
            view = views[language]
            if view.files:
                findings.extend(rule.check(view))
    findings.sort(key=lambda f: (SEV_ORDER.get(rules[f.rule_id].severity, 9), f.rule_id))

    suppressions, problems = suppress_mod.collect(project)
    findings, suppressed = suppress_mod.apply(findings, suppressions)

    value = score(findings, rules)
    return CheckResult(
        project=project, rules=rules, findings=findings, value=value,
        grade=letter(value), suppressed=suppressed,
        suppressions=suppressions, suppression_problems=problems,
    )


def run_check(root: Path, *, include_tests: bool = False):
    """The 5-tuple every existing caller unpacks.

    `run_check_detailed` is the full result; this stays because a lot of
    code -- tests included -- unpacks exactly five values, and widening a
    tuple is the kind of change that breaks callers silently.
    """
    r = run_check_detailed(root, include_tests=include_tests)
    return r.project, r.rules, r.findings, r.value, r.grade


def _partial_coverage() -> tuple[int, int]:
    """(rules that read a `PARTIAL` language, rules total).

    The fraction that decides whether "partial" still describes a coverage
    gap or has become the wrong word for what's actually being withheld
    (#172): once every rule reads the language, `covered == total` and
    there's no port left to finish -- only the grading decision itself.
    """
    rules_total = list(all_rules())
    covered = sum(1 for r in rules_total if set(r.languages) & PARTIAL)
    return covered, len(rules_total)


def unscannable_reason(root: Path, project, counts, *, include_tests: bool) -> str | None:
    """Why we must not report a grade for `root`, or None if we may.

    An empty finding set has two very different causes -- "we read this and
    it's clean" and "we read nothing" -- and the scoring code cannot tell
    them apart, because both arrive as `[]`. Anything that turns findings
    into a grade has to ask this first.
    """
    # "Did we read anything gradable", not "did we read anything". A
    # PARTIAL tree is scanned by the rules ported to it, and a grade
    # derived from a subset would be a confident claim about the rules that
    # never ran. (No counts here on purpose -- the last version of this
    # comment said "2 of 21 ... the 19 that never ran" long after the real
    # numbers were 21 and 0.)
    if any(f.language in SUPPORTED for f in project.files):
        return None
    if not counts:
        return f"no source files found under {root.name}/"

    partial = sum(counts.get(lang, 0) for lang in PARTIAL)
    if partial:
        covered, total = _partial_coverage()
        if covered >= total:
            # Every rule reads it -- "partial" can no longer mean "we
            # haven't ported enough of the rule set". Say what's actually
            # true: coverage is complete, and grading it is a call that
            # hasn't been made (#172), not a gap that's still closing.
            return (
                f"found {describe(counts)}. Every rule reads it now, but whether it "
                f"gets graded is still an open decision, not a coverage gap -- "
                f"see {GRADE_ISSUE_URL}"
            )
        return (
            f"found {describe(counts)}. TypeScript support is partial -- "
            f"{covered} of {total} rules read it so far, which is "
            "enough to report findings but not enough to stand behind a grade"
        )

    python_files = counts.get("python", 0)
    if python_files and not include_tests:
        return (
            f"found {python_files} Python file(s), but every one of them looks like "
            "test code, which is skipped by default -- re-run with --include-tests "
            "if you want them scanned"
        )
    if python_files:
        return f"found {python_files} Python file(s) but could not read any of them"
    # Reached only when nothing here is in SUPPORTED or PARTIAL. Naming the
    # languages we do read beats naming one of them: this said "only reads
    # Python today" for months after TypeScript was being read by every
    # rule, which is the same stale-claim bug as #171 and #172, printed at
    # the person instead of buried in a docstring.
    readable = ", ".join(DISPLAY.get(lang, lang) for lang in sorted(SUPPORTED | PARTIAL))
    return f"found {describe(counts)}, and mcp-migrate reads {readable}"


def _print_language_hint(console, counts) -> None:
    """Point someone at the issue that would fix their case, if one exists.

    Keyed off what is actually open. Pointing a JavaScript project at the
    TypeScript issue was wrong in both directions: TypeScript is read by
    every rule now, so it is not up for grabs, and the work JavaScript
    still needs is the rule port in #149, not #30.
    """
    if counts.get("javascript"):
        console.print(
            f"[dim]JavaScript files are read, but no rule reads into them yet -- "
            f"porting the rules is up for grabs: {JS_ISSUE_URL}[/dim]"
        )
    elif counts.get("typescript"):
        console.print(
            f"[dim]Every rule reads TypeScript; whether it gets a grade is the "
            f"open question: {GRADE_ISSUE_URL}[/dim]"
        )
    elif counts:
        console.print(
            f"[dim]Adding a language backend is a tractable contribution: "
            f"{LANG_ISSUE_URL}[/dim]"
        )


def _suppressed_dict(f, rules, result) -> dict:
    """A suppressed finding, with the reason that suppressed it.

    The reason is the point. A suppression list without reasons is a list
    of findings somebody made disappear.
    """
    d = _finding_dict(f, rules)
    reason = ""
    for s in result.suppressions:
        if str(s.path) == str(f.path) and s.line == f.line and f.rule_id.upper() in s.rule_ids:
            reason = s.reason
            break
    d["reason"] = reason
    return d


def _finding_dict(f, rules) -> dict:
    d = {
        "rule": f.rule_id,
        "severity": rules[f.rule_id].severity,
        "path": str(f.path) if f.path else None,
        "line": f.line,
        "message": f.message,
    }
    fix = rules[f.rule_id].fix
    if fix:
        d["fix"] = fix
    return d


def _severity_counts(findings, rules) -> dict:
    counts = {"breaking": 0, "deprecated": 0, "advisory": 0}
    for f in findings:
        counts[rules[f.rule_id].severity] += 1
    return counts


def _exit_for(findings, rules) -> int:
    """Exit code from findings alone: 1 if anything breaking, else 0."""
    return EXIT_FINDINGS if any(
        rules[f.rule_id].severity == "breaking" for f in findings
    ) else EXIT_OK


def _checked_something(project) -> bool:
    """Did we actually read source, or is this an empty/unreadable tree?

    The discriminator between "partial coverage" and "could not check".
    A TypeScript project is `PARTIAL` -- we withhold the *grade*, which is
    correct and deliberate, but we did open files and run rules against
    them, so the exit code has real information to carry. An empty
    directory or a tree in a language with no backend read nothing, and
    EXIT_UNSCANNABLE is the honest answer there.

    Deliberately not `bool(project.files)`: the scanner can load a file
    (JavaScript, today) into a language no rule has been ported to yet,
    which means it sits in `project.files` without a single rule ever
    having run against it. That is "could not check" wearing "checked
    it" as a disguise -- exactly the false confidence this function
    exists to refuse.
    """
    return any(f.language in SUPPORTED or f.language in PARTIAL for f in project.files)


def _report_suppressions(console, result, *, show: bool) -> None:
    """Say how many findings were suppressed -- always, not behind a flag.

    A suppressed finding is one the grade no longer pays for, so the count
    is part of reading the grade honestly. Hiding it behind a flag would
    make this a way to quietly improve a score, which is exactly the
    stale-claim problem #101 removed from the badge.
    """
    for problem in result.suppression_problems:
        console.print(
            f"[yellow]suppression ignored[/yellow]  {problem.location()}  {problem.message}"
        )

    stale = suppress_mod.unused(result.suppressions)
    for s in stale:
        console.print(
            f"[dim]unused suppression[/dim]    {s.location()}  "
            f"ignore[{', '.join(s.rule_ids)}] matched nothing -- fixed, or the code moved?"
        )

    if not result.suppressed:
        return

    console.print()
    console.print(
        f"[yellow]{len(result.suppressed)} finding(s) suppressed[/yellow] by inline "
        f"`mcp-migrate: ignore` comments, and not counted against the grade."
    )
    if show:
        for f in result.suppressed:
            reason = next(
                (s.reason for s in result.suppressions
                 if str(s.path) == str(f.path) and s.line == f.line
                 and f.rule_id.upper() in s.rule_ids),
                "",
            )
            console.print(f"  [dim]{f.rule_id}  {f.location()}[/dim]  {reason or '(no reason given)'}")
    else:
        console.print("[dim]Run with --show-suppressions to see each one and its reason.[/dim]")


def cmd_check(args) -> int:
    console = Console()
    root = Path(args.path).resolve()

    if not root.exists():
        # rglob over a path that isn't there yields nothing, which would
        # otherwise sail through as a clean A for a typo'd directory name.
        console.print(f"[bold red]No such path:[/bold red] {root}")
        return EXIT_UNSCANNABLE

    result = run_check_detailed(root, include_tests=args.include_tests)
    project, rules, findings = result.project, result.rules, result.findings
    value, grade = result.value, result.grade
    counts = survey(root)
    reason = unscannable_reason(root, project, counts, include_tests=args.include_tests)
    sdk_info = detect_sdk(root)

    if args.json:
        if sdk_info.is_sdk:
            print(json.dumps({
                "tool": "mcp-migrate",
                "version": __version__,
                "spec": SPEC,
                "path": str(root),
                "scannable": True,
                "is_sdk": True,
                "sdk_reason": sdk_info.reason,
                "languages": dict(counts),
                "grade": None,
                "score": None,
                "files_scanned": len(project.files),
                "counts": _severity_counts(findings, rules),
                "findings": [_finding_dict(f, rules) for f in findings],
                "suppressed": [_suppressed_dict(f, rules, result) for f in result.suppressed],
            }, indent=2))
            return EXIT_OK
        if reason:
            print(json.dumps({
                "tool": "mcp-migrate",
                "version": __version__,
                "spec": SPEC,
                "path": str(root),
                "scannable": False,
                "reason": reason,
                "languages": dict(counts),
                "grade": None,
                "score": None,
                "files_scanned": len(project.files),
                # Findings can be non-empty here: a partially-supported
                # language gets read by the rules that cover it. What it
                # doesn't get is a grade.
                "counts": _severity_counts(findings, rules),
                "findings": [_finding_dict(f, rules) for f in findings],
                "suppressed": [_suppressed_dict(f, rules, result) for f in result.suppressed],
            }, indent=2))
            return _exit_for(findings, rules) if _checked_something(project) \
                else EXIT_UNSCANNABLE
        print(json.dumps({
            "tool": "mcp-migrate",
            "version": __version__,
            "spec": SPEC,
            "path": str(root),
            "scannable": True,
            "languages": dict(counts),
            "grade": grade,
            "score": value,
            "files_scanned": len(project.files),
            "counts": _severity_counts(findings, rules),
            "findings": [_finding_dict(f, rules) for f in findings],
            "suppressed": [_suppressed_dict(f, rules, result) for f in result.suppressed],
        }, indent=2))
        return _exit_for(findings, rules)

    console.print()
    console.print(f"[bold]mcp-migrate[/bold] [dim]v{__version__}[/dim]  ->  {root.name}")

    if sdk_info.is_sdk:
        console.print()
        if sdk_info.package_name:
            console.print(
                f"[bold yellow]No grade:[/] this looks like a protocol SDK (package name \"{sdk_info.package_name}\"), not a server."
            )
        else:
            console.print(
                "[bold yellow]No grade:[/] project configured as a library/SDK."
            )
        if findings:
            console.print(
                f"An SDK implements the removed surface on purpose. {len(findings)} findings listed below as a migration checklist, not a verdict."
            )
            console.print()
            table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
            table.add_column("", width=10)
            table.add_column("rule", width=6)
            table.add_column("where", overflow="fold")
            table.add_column("what")
            for rule_id, group in itertools.groupby(findings, key=lambda f: f.rule_id):
                group = list(group)
                sev = rules[rule_id].severity
                for f in group[:MAX_SHOWN_PER_RULE]:
                    table.add_row(f"[{SEV_STYLE[sev]}]{sev}[/]", f.rule_id, f.location(), f.message)
                extra = len(group) - MAX_SHOWN_PER_RULE
                if extra > 0:
                    table.add_row("", "", "", f"[dim]+{extra} more {rule_id} finding(s) (see --json for all)[/dim]")
            console.print(table)
            console.print()
        else:
            console.print("No findings listed for this SDK.")
            console.print()
        console.print(
            "[dim]No grade and no badge: this tool has no opinion about code that implements the protocol itself.[/dim]"
        )
        console.print()
        return EXIT_OK

    if reason:
        console.print()
        # Not .capitalize() -- that lowercases the rest, turning "24
        # TypeScript" into "24 typescript".
        # "Nothing scannable" is only true when we opened nothing. A clean
        # TypeScript tree now exits 0, and pairing that with "nothing
        # scannable" would contradict it -- we did read those files and run
        # every rule that covers them; what we withheld is the grade.
        headline = (
            "Nothing scannable here." if not _checked_something(project)
            else "No grade for this one."
        )
        console.print(
            f"[bold yellow]{headline}[/bold yellow] {reason[0].upper()}{reason[1:]}."
        )
        # "The rules that didn't run" is only true while a port is still in
        # progress -- once coverage is complete there's nothing left that
        # didn't run, and the honest reason is that grading it is a decision
        # still pending (#172), not a gap in what got read.
        covered, total = _partial_coverage()
        full_coverage = covered >= total
        if findings:
            console.print()
            for f in findings:
                sev = rules[f.rule_id].severity
                console.print(
                    f"  [{SEV_STYLE[sev]}]{sev}[/]  {f.rule_id}  {f.location()}  {f.message}"
                )
            console.print()
            console.print(
                f"[dim]{len(findings)} finding(s) from the rules that do cover this "
                "language. Real, and worth fixing -- but a letter grade would be a "
                "claim about a decision that hasn't been made.[/dim]"
                if full_coverage else
                f"[dim]{len(findings)} finding(s) from the rules that do cover this "
                "language. Real, and worth fixing -- but a letter grade would be a "
                "claim about the rules that didn't run.[/dim]"
            )
        _print_language_hint(console, counts)
        # Two different silences, and saying the wrong one is worse than
        # saying nothing. When we read files and ran rules over them, "code
        # it could not read" contradicts the findings printed directly
        # above -- what we withheld is the grade, not the reading.
        if not _checked_something(project):
            console.print(
                "[dim]No grade and no badge: this tool has no opinion about code it "
                "could not read.[/dim]"
            )
        elif full_coverage:
            console.print(
                "[dim]No grade and no badge: whether to grade a language every rule "
                f"reads is still an open decision -- {GRADE_ISSUE_URL}[/dim]"
            )
        else:
            console.print(
                "[dim]No grade and no badge: a letter grade would be a claim about the "
                "rules that didn't run.[/dim]"
            )
        console.print()
        return _exit_for(findings, rules) if _checked_something(project) \
            else EXIT_UNSCANNABLE

    _report_suppressions(console, result, show=args.show_suppressions)

    n_python = sum(1 for f in project.files if f.language == "python")
    console.print(f"[dim]{n_python} Python files, {len(rules)} rules, spec {SPEC}[/dim]")

    partial = Counter({k: v for k, v in counts.items() if k in PARTIAL})
    if partial:
        covered, total = _partial_coverage()
        if covered >= total:
            console.print(
                f"[dim]Also found {describe(partial)}, read by every rule -- the grade "
                f"leans on the Python anyway, since grading it is still an open "
                f"decision ({GRADE_ISSUE_URL}), not a coverage gap.[/dim]"
            )
        else:
            console.print(
                f"[dim]Also found {describe(partial)}, read by {covered} of {total} "
                f"rules -- partial coverage, so those files inform the findings but the "
                f"grade leans on the Python.[/dim]"
            )
    unread = Counter({k: v for k, v in counts.items()
                      if k not in SUPPORTED and k not in PARTIAL})
    if unread:
        # A grade on the Python third of a mostly-JavaScript repo is true
        # about what it measured and misleading about the repo. Say so.
        console.print(
            f"[dim]Also found {describe(unread)} -- not read at all. This grade covers "
            f"the Python only.[/dim]"
        )
    console.print()

    if not findings:
        console.print("[bold green]Grade A.[/bold green] Nothing to fix. Add your badge:")
        console.print(f"[dim]![MCP {SPEC}]({badge_url(grade)})[/dim]")
        return 0

    counts = {"breaking": 0, "deprecated": 0, "advisory": 0}
    for f in findings:
        counts[rules[f.rule_id].severity] += 1

    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("", width=10)
    table.add_column("rule", width=6)
    table.add_column("where", overflow="fold")
    table.add_column("what")
    # `findings` is sorted by (severity-order-of-rule, rule_id), so every
    # rule's findings are contiguous -- group them to cap how many rows
    # any single rule can spam into the table. The JSON output above is
    # unaffected; this only trims what prints to the terminal.
    for rule_id, group in itertools.groupby(findings, key=lambda f: f.rule_id):
        group = list(group)
        sev = rules[rule_id].severity
        for f in group[:MAX_SHOWN_PER_RULE]:
            table.add_row(f"[{SEV_STYLE[sev]}]{sev}[/]", f.rule_id, f.location(), f.message)
        extra = len(group) - MAX_SHOWN_PER_RULE
        if extra > 0:
            table.add_row("", "", "", f"[dim]+{extra} more {rule_id} finding(s) (see --json for all)[/dim]")
    console.print(table)
    console.print()

    for rule_id in dict.fromkeys(f.rule_id for f in findings):
        rule = rules[rule_id]
        console.print(f"  [bold]{rule.id}[/bold]  {rule.title}")
        console.print(f"  [dim]{rule.spec_ref}[/dim]")
        console.print(f"  {rule.fix}")
        console.print()

    grade_style = "bold green" if grade in "AB" else "bold yellow" if grade == "C" else "bold red"
    console.print(
        f"[{grade_style}]Grade {grade}[/] ({value}/100)  "
        f"{counts['breaking']} breaking, {counts['deprecated']} deprecated, {counts['advisory']} advisory"
    )
    console.print()
    console.print("[dim]Add your server to the board:  mcp-migrate entry --repo owner/name[/dim]")
    return 1 if counts["breaking"] else 0


def cmd_rules(args) -> int:
    console = Console()
    table = Table(show_header=True, header_style="bold", box=None)
    table.add_column("id")
    table.add_column("severity")
    table.add_column("title")
    table.add_column("spec")
    for rule in all_rules():
        table.add_row(rule.id, f"[{SEV_STYLE[rule.severity]}]{rule.severity}[/]", rule.title, rule.spec_ref)
    console.print(table)
    return 0


def _select_fixers(*, safe_only: bool = False, rule: str | None = None):
    fixers = all_fixers()
    if rule:
        fixers = [fx for fx in fixers if fx.rule_id == rule]
    if safe_only:
        fixers = [fx for fx in fixers if fx.confidence == "safe"]
    return fixers


def _findings_for(root: Path, files: list[SourceFile]):
    """Run every rule against an in-memory set of files (some possibly
    edited, not yet written to disk) instead of re-reading from disk.

    Used to report an accurate "still needs a human" count for `fix
    --dry-run`, where nothing has actually been written yet.
    """
    project = Project(root=root, files=files)
    rules = {r.id: r for r in all_rules()}
    findings = []
    views: dict[str, Project] = {}
    for rule in rules.values():
        for language in rule.languages:
            if language not in views:
                views[language] = project.for_language(language)
            view = views[language]
            if view.files:
                findings.extend(rule.check(view))
    return findings


def run_fix(root: Path, *, include_tests: bool = False, safe_only: bool = False, rule: str | None = None):
    """Compute fixes for every file under `root`, without touching disk.

    Returns (project, list of (SourceFile, new_text, [change descriptions])
    for files that actually changed, sorted fixers actually available).
    """
    project = load_project(root, include_tests=include_tests)
    fixers = _select_fixers(safe_only=safe_only, rule=rule)
    results = []
    for f in project.files:
        text = f.text
        file_changes: list[tuple[str, str]] = []  # (rule_id/confidence, description)
        for fixer in fixers:
            outcome = fixer.fix(text, f.path)
            if outcome.changed:
                text = outcome.text
                for c in outcome.changes:
                    file_changes.append((fixer, c))
        if text != f.text:
            results.append((f, text, file_changes))
    return project, fixers, results


def cmd_fixers(args) -> int:
    console = Console()
    table = Table(show_header=True, header_style="bold", box=None)
    table.add_column("rule")
    table.add_column("confidence")
    table.add_column("title")
    for fixer in all_fixers():
        style = CONF_STYLE.get(fixer.confidence, "")
        table.add_row(fixer.rule_id, f"[{style}]{fixer.confidence}[/]" if style else fixer.confidence, fixer.title)
    console.print(table)
    return 0


def cmd_fix(args) -> int:
    console = Console()
    if args.write and args.dry_run:
        console.print("[bold red]--write and --dry-run are mutually exclusive.[/bold red]")
        return 2

    root = Path(args.path).resolve()
    fixers = _select_fixers(safe_only=args.safe_only, rule=args.rule)
    if not fixers:
        console.print("[yellow]No fixers match the given filters (--rule / --safe-only).[/yellow]")
        return 0

    project, _, results = run_fix(
        root, include_tests=args.include_tests, safe_only=args.safe_only, rule=args.rule,
    )

    if not results:
        console.print("[bold green]Nothing to fix.[/bold green] "
                       "(either the project is clean, or no fixer covers what's here -- see `mcp-migrate check`)")
        return 0

    changed_files = 0
    conf_counts = {"safe": 0, "review": 0}
    # Build the post-fix file set as we go, so we can report an accurate
    # "still needs a human" count without writing anything to disk first.
    fixed_by_path = {f.path: new_text for f, new_text, _ in results}

    for f, new_text, file_changes in results:
        diff = list(difflib.unified_diff(
            f.text.splitlines(keepends=True), new_text.splitlines(keepends=True),
            fromfile=f"a/{f.path}", tofile=f"b/{f.path}",
        ))
        if not diff:
            continue
        changed_files += 1
        console.print(f"[bold]{f.path}[/bold]")
        for line in diff:
            line = line.rstrip("\n")
            if line.startswith("+++") or line.startswith("---"):
                console.print(line, style="bold")
            elif line.startswith("@@"):
                console.print(line, style="cyan")
            elif line.startswith("+"):
                console.print(line, style="green")
            elif line.startswith("-"):
                console.print(line, style="red")
            else:
                console.print(line)
        for fixer, desc in file_changes:
            conf_counts[fixer.confidence] += 1
            console.print(f"  [dim][{fixer.rule_id}/{fixer.confidence}][/dim] {desc}")
        console.print()
        if args.write:
            (root / f.path).write_text(new_text, encoding="utf-8")

    if changed_files == 0:
        console.print("[bold green]Nothing to fix.[/bold green]")
        return 0

    total = conf_counts["safe"] + conf_counts["review"]
    console.print(
        f"[bold]{changed_files} file(s)[/bold], {total} change(s): "
        f"{conf_counts['safe']} safe, {conf_counts['review']} flagged for human review"
    )

    # What's left, computed against the fixed-but-maybe-not-written text so
    # a dry run's summary is honest about what --write would actually do.
    post_fix_files = []
    for f in project.files:
        text = fixed_by_path.get(f.path, f.text)
        try:
            tree = ast.parse(text, filename=str(f.path))
        except SyntaxError:
            tree = None
        post_fix_files.append(SourceFile(path=f.path, text=text, tree=tree))
    remaining = _findings_for(root, post_fix_files)
    if remaining:
        console.print(f"[yellow]{len(remaining)} finding(s) still need a human after this fix "
                       f"-- run `mcp-migrate check{' --include-tests' if args.include_tests else ''} "
                       f"{args.path}` for details.[/yellow]")
    else:
        console.print("[bold green]No findings remain.[/bold green]")

    if args.write:
        console.print("[bold green]Changes written.[/bold green]")
    else:
        console.print("[dim]Dry run -- nothing was written. Re-run with --write to apply.[/dim]")
    return 0


def cmd_entry(args) -> int:
    """Print a ready-to-commit registry entry for this project.

    Refuses far more readily than `check` does. `check` reports to the
    person who ran it, who can see their own repo; `entry` produces a claim
    about someone's code that goes on a public board and that CI is
    instructed to merge on sight. The cost of being wrong is asymmetric, so
    the bar is higher.
    """
    # Refusals go to stderr: stdout is YAML that people redirect straight
    # into registry/servers/<name>.yaml, and a refusal must never end up
    # inside the file it was refusing to write.
    err = Console(stderr=True)
    root = Path(args.path).resolve()

    if not root.exists():
        err.print(f"[bold red]No such path:[/bold red] {root}")
        return EXIT_UNSCANNABLE

    project, _, findings, value, grade = run_check(root)
    counts = survey(root)

    sdk_info = detect_sdk(root)
    if sdk_info.is_sdk:
        if sdk_info.package_name:
            err.print(
                f"[bold red]Refusing to generate an entry:[/bold red] {root.name} looks like a protocol SDK "
                f"(package name \"{sdk_info.package_name}\"), not a server. mcp-migrate does not publish "
                f"registry entries for protocol implementations."
            )
        else:
            err.print(
                f"[bold red]Refusing to generate an entry:[/bold red] {root.name} is configured as a library/SDK. "
                f"mcp-migrate does not publish registry entries for protocol implementations."
            )
        return EXIT_UNSCANNABLE

    reason = unscannable_reason(root, project, counts, include_tests=False)
    if reason:
        err.print(f"[bold red]Refusing to generate an entry:[/bold red] {reason}.")
        _print_language_hint(err, counts)
        err.print(
            "[dim]The board only carries grades that were actually derived from "
            "source. Nothing was written.[/dim]"
        )
        return EXIT_UNSCANNABLE

    language = primary(counts)
    if language not in SUPPORTED:
        # Scannable, but the Python is a minority of the tree -- a helper
        # script in a TypeScript server, say. The grade would be true of
        # what it read and false as a description of the repo, and it's the
        # repo that the board entry names.
        err.print(
            f"[bold red]Refusing to generate an entry:[/bold red] this tree is mostly "
            f"{describe(counts)}, so filing it as a Python entry graded on "
            f"{len(project.files)} Python file(s) would misdescribe the repo."
        )
        _print_language_hint(err, counts)
        return EXIT_UNSCANNABLE

    repo = args.repo or root.name
    slug = repo.split("/")[-1].lower().replace("_", "-")
    body = f"""# registry/servers/{slug}.yaml
name: {slug}
repo: {repo}
language: {language}
grade: {grade}
score: {value}
checked_with: mcp-migrate {__version__}
spec: "{SPEC}"
status: {"ready" if grade in "AB" else "migrating"}
notes: >-
  Replace this line with one sentence about what your server does.
"""
    print(body)
    print(f"# Save it, then: gh pr create --title 'registry: add {slug}'", file=sys.stderr)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="mcp-migrate",
        description="Will your MCP server survive the 2026-07-28 spec?",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")

    p_check = sub.add_parser("check", help="check a project")
    p_check.add_argument("path", nargs="?", default=".")
    p_check.add_argument("--json", action="store_true")
    p_check.add_argument(
        "--show-suppressions", action="store_true",
        help="list every inline `mcp-migrate: ignore` suppression and its reason",
    )
    p_check.add_argument(
        "--include-tests", action="store_true",
        help="also scan tests/, fixtures/, examples/, docs/, and test_*.py files "
             "(skipped by default -- see README)",
    )
    p_check.set_defaults(func=cmd_check)

    p_rules = sub.add_parser("rules", help="list every rule")
    p_rules.set_defaults(func=cmd_rules)

    p_fix = sub.add_parser("fix", help="apply automatic fixes")
    p_fix.add_argument("path", nargs="?", default=".")
    p_fix.add_argument(
        "--dry-run", action="store_true",
        help="show a unified diff and change nothing (this is the default)",
    )
    p_fix.add_argument("--write", action="store_true", help="apply the fixes to disk")
    p_fix.add_argument(
        "--safe-only", action="store_true",
        help="only apply \"safe\"-confidence fixers, skip anything needing review",
    )
    p_fix.add_argument("--rule", help="restrict to a single rule id, e.g. R001")
    p_fix.add_argument(
        "--include-tests", action="store_true",
        help="also fix tests/, fixtures/, examples/, docs/, and test_*.py files "
             "(skipped by default -- see README)",
    )
    p_fix.set_defaults(func=cmd_fix)

    p_fixers = sub.add_parser("fixers", help="list every fixer")
    p_fixers.set_defaults(func=cmd_fixers)

    p_entry = sub.add_parser("entry", help="generate your registry entry")
    p_entry.add_argument("path", nargs="?", default=".")
    p_entry.add_argument("--repo", help="owner/name on GitHub")
    p_entry.set_defaults(func=cmd_entry)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
