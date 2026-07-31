from __future__ import annotations

import argparse
import ast
import difflib
import itertools
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from . import __version__
from .fixers import all_fixers
from .grade import badge_url, letter, score
from .rules import all_rules
from .rules.base import Project, SourceFile
from .scan import load_project

SPEC = "2026-07-28"
SEV_STYLE = {"breaking": "bold red", "deprecated": "yellow", "advisory": "cyan"}
SEV_ORDER = {"breaking": 0, "deprecated": 1, "advisory": 2}
CONF_STYLE = {"safe": "bold green", "review": "yellow"}
MAX_SHOWN_PER_RULE = 5


def run_check(root: Path, *, include_tests: bool = False):
    project = load_project(root, include_tests=include_tests)
    rules = {r.id: r for r in all_rules()}
    findings = []
    for rule in rules.values():
        findings.extend(rule.check(project))
    findings.sort(key=lambda f: (SEV_ORDER.get(rules[f.rule_id].severity, 9), f.rule_id))
    value = score(findings, rules)
    return project, rules, findings, value, letter(value)


def cmd_check(args) -> int:
    console = Console()
    root = Path(args.path).resolve()
    project, rules, findings, value, grade = run_check(root, include_tests=args.include_tests)

    if args.json:
        print(json.dumps({
            "spec": SPEC,
            "path": str(root),
            "grade": grade,
            "score": value,
            "files_scanned": len(project.files),
            "findings": [{
                "rule": f.rule_id,
                "severity": rules[f.rule_id].severity,
                "message": f.message,
                "location": f.location(),
            } for f in findings],
        }, indent=2))
        return 1 if any(rules[f.rule_id].severity == "breaking" for f in findings) else 0

    console.print()
    console.print(f"[bold]mcp-migrate[/bold] [dim]v{__version__}[/dim]  ->  {root.name}")
    console.print(f"[dim]{len(project.files)} Python files, {len(rules)} rules, spec {SPEC}[/dim]")
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
    for rule in rules.values():
        findings.extend(rule.check(project))
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
    """Print a ready-to-commit registry entry for this project."""
    root = Path(args.path).resolve()
    _, _, findings, value, grade = run_check(root)
    repo = args.repo or root.name
    slug = repo.split("/")[-1].lower().replace("_", "-")
    body = f"""# registry/servers/{slug}.yaml
name: {slug}
repo: {repo}
language: python
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
