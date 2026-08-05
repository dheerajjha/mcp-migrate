import re

from .base import Finding, Project, Rule, wire_method

TASKS_CODE_RX = re.compile(
    r"\bListTasksRequest(?:Params|Schema)?\b|\bListTasksResult(?:Schema)?\b|"
    r"\bGetTaskPayloadRequest(?:Params|Schema)?\b|\bGetTaskPayloadResult(?:Schema)?\b"
)


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

    def check(self, project: Project) -> list[Finding]:
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
        for f, line, text in project.search_wire(wire_method("tasks/list", "tasks/result")):
            out.append(self.finding(
                "References the removed tasks/list or blocking tasks/result JSON-RPC "
                "method.",
                f, line, text,
            ))
        return out
