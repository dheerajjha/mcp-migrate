import re

from .base import Finding, Project, Rule

# `ListTasksRequest`/`GetTaskPayloadRequest` are the MCP SDK's own model
# names for the two removed shapes (tasks/list, and the blocking
# tasks/result) -- distinctive, no false-positive risk.
TASKS_CODE_RX = re.compile(r"\bListTasksRequest\b|\bGetTaskPayloadRequest\b")


class TasksPollingReplacesBlockingResult(Rule):
    id = "R019"
    title = "Uses removed tasks/list or the removed blocking tasks/result"
    severity = "breaking"
    spec_ref = "SEP-2663 https://modelcontextprotocol.io/specification/2026-07-28/changelog"
    fix = (
        "tasks/list is gone, and blocking tasks/result is replaced by polling "
        "tasks/get + tasks/update. Tasks itself moved out of core into the "
        "io.modelcontextprotocol/tasks extension -- declare it there instead."
    )
    languages = ("python", "typescript")

    def check(self, project: Project) -> list[Finding]:
        if project.language == "typescript":
            # The removed task methods are JSON-RPC wire names, so they
            # appear as string literals. search_wire keeps those literals
            # while ignoring comments that merely describe the migration.
            return [
                self.finding(
                    "References the removed tasks/list or blocking tasks/result JSON-RPC "
                    "method.",
                    f,
                    line,
                    text,
                )
                for f, line, text in project.search_wire(r"tasks/list|tasks/result")
            ]

        out: list[Finding] = []
        for f, line, text in project.search_code(TASKS_CODE_RX.pattern):
            out.append(self.finding(
                "References the removed ListTasksRequest (tasks/list) or the removed "
                "blocking GetTaskPayloadRequest (tasks/result).",
                f, line, text,
            ))
        # tasks/list and tasks/result are JSON-RPC method strings, not
        # valid bare identifiers -- they can only appear inside a STRING
        # token, so search_code would never find them (see the
        # notifications/initialized note in r009). Raw scan instead.
        for f, line, text in project.search_wire(r"tasks/list|tasks/result"):
            out.append(self.finding(
                "References the removed tasks/list or blocking tasks/result JSON-RPC "
                "method.",
                f, line, text,
            ))
        return out
