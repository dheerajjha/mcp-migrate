#!/usr/bin/env python3
"""Re-scan pinned board entries and report grade drift.

The board promises that every published grade is reproducible from the
recorded `repo`, `sha`, optional `path`, and `checked_with`. This script
replays that claim locally: fetch each unique `repo@sha` once, scan every
entry rooted in that checkout, and fail loudly when today's grade/score no
longer matches the committed YAML.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SERVERS = ROOT / "registry" / "servers"

sys.path.insert(0, str(ROOT / "src"))

from mcp_migrate import __version__  # noqa: E402
from mcp_migrate.cli import run_check_detailed, unscannable_reason  # noqa: E402
from mcp_migrate.config import load_config  # noqa: E402
from mcp_migrate.languages import survey  # noqa: E402


@dataclass(frozen=True)
class BoardEntry:
    name: str
    repo: str
    sha: str
    path: str
    grade: str
    score: int
    checked_with: str
    file: Path

    @property
    def repo_sha(self) -> tuple[str, str]:
        return self.repo, self.sha


@dataclass(frozen=True)
class ScanResult:
    grade: str
    score: int
    checked_with: str


@dataclass(frozen=True)
class Drift:
    entry: BoardEntry
    actual: ScanResult


def _required_text(data: dict, key: str, *, source: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{source.name}: missing required string field `{key}`")
    return value.strip()


def _required_int(data: dict, key: str, *, source: Path) -> int:
    value = data.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{source.name}: missing required int field `{key}`")
    return value


def load_entries(paths: list[Path] | None = None) -> list[BoardEntry]:
    entries: list[BoardEntry] = []
    for path in sorted(paths or SERVERS.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{path.name}: top level must be a mapping")
        entries.append(
            BoardEntry(
                name=_required_text(data, "name", source=path),
                repo=_required_text(data, "repo", source=path),
                sha=_required_text(data, "sha", source=path),
                path=str(data.get("path") or "").strip(),
                grade=_required_text(data, "grade", source=path),
                score=_required_int(data, "score", source=path),
                checked_with=_required_text(data, "checked_with", source=path),
                file=path,
            )
        )
    return entries


def group_entries(entries: list[BoardEntry]) -> dict[tuple[str, str], list[BoardEntry]]:
    groups: dict[tuple[str, str], list[BoardEntry]] = {}
    for entry in entries:
        groups.setdefault(entry.repo_sha, []).append(entry)
    return groups


def display_file(path: Path) -> str:
    """Prefer a repo-relative path, but tolerate out-of-tree test fixtures."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _checkout_dir(workspace: Path, repo: str, sha: str) -> Path:
    owner, name = repo.split("/", 1)
    return workspace / f"{owner}--{name}-{sha[:12]}"


def _run(cmd: list[str], *, cwd: Path) -> None:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        stderr = proc.stderr.strip() or proc.stdout.strip() or "unknown error"
        raise RuntimeError(f"{' '.join(cmd)} failed: {stderr}")


def checkout_repo(repo: str, sha: str, *, workspace: Path) -> Path:
    dest = _checkout_dir(workspace, repo, sha)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    _run(["git", "init", "-q", "."], cwd=dest)
    _run(["git", "remote", "add", "origin", f"https://github.com/{repo}.git"], cwd=dest)
    _run(["git", "fetch", "-q", "--depth", "1", "origin", sha], cwd=dest)
    _run(["git", "-c", "advice.detachedHead=false", "checkout", "-q", "FETCH_HEAD"], cwd=dest)
    return dest


def scan_entry(entry: BoardEntry, checkout_root: Path) -> ScanResult:
    target = checkout_root / entry.path if entry.path else checkout_root
    if not target.exists():
        raise RuntimeError(f"{entry.name}: target path does not exist in checkout: {target}")

    config = load_config(target)
    result = run_check_detailed(target, config=config)
    counts = survey(target, extra_skip=config.skip)
    reason = unscannable_reason(
        target,
        result.project,
        counts,
        include_tests=config.include_tests,
        checked_languages=result.checked_languages,
    )
    if reason:
        raise RuntimeError(f"{entry.name}: regrade refused: {reason}")
    return ScanResult(
        grade=result.grade,
        score=result.value,
        checked_with=f"mcp-migrate {__version__}",
    )


def find_drifts(entries: list[BoardEntry], *, workspace: Path) -> tuple[list[Drift], list[str]]:
    drifts: list[Drift] = []
    problems: list[str] = []
    for (repo, sha), group in sorted(group_entries(entries).items()):
        try:
            checkout = checkout_repo(repo, sha, workspace=workspace)
        except Exception as exc:  # noqa: BLE001 - report per-group failure cleanly
            problems.append(f"{repo}@{sha[:12]}: {exc}")
            continue

        for entry in group:
            try:
                actual = scan_entry(entry, checkout)
            except Exception as exc:  # noqa: BLE001 - report per-entry failure cleanly
                problems.append(str(exc))
                continue
            if (actual.grade, actual.score) != (entry.grade, entry.score):
                drifts.append(Drift(entry=entry, actual=actual))
    return drifts, problems


def drift_patch(drift: Drift) -> str:
    return "\n".join(
        [
            display_file(drift.entry.file),
            f"  grade: {drift.actual.grade}",
            f"  score: {drift.actual.score}",
            f"  checked_with: {drift.actual.checked_with}",
        ]
    )


def as_json(entries: list[BoardEntry], drifts: list[Drift], problems: list[str]) -> str:
    payload = {
        "entries_checked": len(entries),
        "repo_sha_groups": len(group_entries(entries)),
        "drifts": [
            {
                "entry": {
                    "name": drift.entry.name,
                    "file": display_file(drift.entry.file),
                    "repo": drift.entry.repo,
                    "sha": drift.entry.sha,
                    "path": drift.entry.path,
                    "recorded_grade": drift.entry.grade,
                    "recorded_score": drift.entry.score,
                    "recorded_checked_with": drift.entry.checked_with,
                },
                "actual": asdict(drift.actual),
            }
            for drift in drifts
        ],
        "problems": problems,
    }
    return json.dumps(payload, indent=2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "names",
        nargs="*",
        help="optional entry names to regrade; defaults to every registry entry",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        help="directory for temporary checkouts; defaults to a temp directory",
    )
    parser.add_argument(
        "--keep-workspace",
        action="store_true",
        help="do not delete the temporary checkout directory",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable drift data",
    )
    args = parser.parse_args(argv)

    entries = load_entries()
    if args.names:
        wanted = set(args.names)
        entries = [entry for entry in entries if entry.name in wanted]
        missing = sorted(wanted - {entry.name for entry in entries})
        if missing:
            parser.error(f"unknown board entry name(s): {', '.join(missing)}")

    if not entries:
        parser.error("no board entries selected")

    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    workspace = args.workspace
    if workspace is None:
        temp_dir = tempfile.TemporaryDirectory(prefix="mcp-migrate-regrade-")
        workspace = Path(temp_dir.name)
    workspace.mkdir(parents=True, exist_ok=True)

    try:
        drifts, problems = find_drifts(entries, workspace=workspace)
        if args.json:
            print(as_json(entries, drifts, problems))
        else:
            print(
                f"Checked {len(entries)} board entr"
                f"{'y' if len(entries) == 1 else 'ies'} across "
                f"{len(group_entries(entries))} pinned repo@sha group"
                f"{'' if len(group_entries(entries)) == 1 else 's'}."
            )
            if drifts:
                for drift in drifts:
                    print(
                        f"DRIFT {drift.entry.name}: "
                        f"recorded {drift.entry.grade}/{drift.entry.score} -> "
                        f"current {drift.actual.grade}/{drift.actual.score}"
                    )
                    print(drift_patch(drift))
            if problems:
                for problem in problems:
                    print(f"ERROR {problem}")
            if not drifts and not problems:
                print("All pinned board entries reproduce their recorded grade and score.")
    finally:
        if temp_dir is not None and not args.keep_workspace:
            temp_dir.cleanup()

    return 1 if drifts or problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
