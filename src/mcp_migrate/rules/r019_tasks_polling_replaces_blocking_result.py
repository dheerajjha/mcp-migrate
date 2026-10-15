import re

from .base import Finding, Fires, Project, Rule, Silent, wire_method

TASKS_CODE_RX = re.compile(
    r"\bListTasksRequest(?:Params|Schema)?\b|\bListTasksResult(?:Schema)?\b|"
    r"\bGetTaskPayloadRequest(?:Params|Schema)?\b|\bGetTaskPayloadResult(?:Schema)?\b"
)

# The TypeScript SDK exports Zod schemas for request handling, and that's
# the name a server actually references -- `server.setRequestHandler(
# ListTasksRequestSchema, ...)`. Bounded to the exact SDK export names
# (optionally suffixed `Params`/`Schema`) rather than an unbounded `\w*`
# suffix, which would also match unrelated identifiers like
# `ListTasksRequester` -- see #87.
TS_TASKS_CODE_RX = re.compile(
    r"\b(?:ListTasks|GetTaskPayload)Request(?:Params|Schema)?\b"
)

WIRE_RX = wire_method("tasks/list", "tasks/result")
MESSAGE_CODE = (
    "References the removed ListTasksRequest (tasks/list) or the removed "
    "blocking GetTaskPayloadRequest (tasks/result)."
)
MESSAGE_WIRE = (
    "References the removed tasks/list or blocking tasks/result JSON-RPC method."
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
    languages = ("python", "typescript", "javascript")
    boundaries = (
        Fires(
            snippet=(
                "from mcp.types import ListTasksRequestSchema\n"
                "request = ListTasksRequestSchema()\n"
            ),
            reason="The removed Python SDK task-list request type is a direct dependency.",
        ),
        Fires(
            snippet='METHODS = {"tasks/result": handle_blocking_result}\n',
            reason="The removed blocking tasks/result wire method must migrate to polling.",
        ),
        Silent(
            snippet=(
                'METHODS = {"tasks/get": get_task, "tasks/update": update_task}\n'
            ),
            reason="The replacement polling methods are current and must stay silent.",
        ),
        Silent(
            snippet=(
                '# tasks/list and tasks/result were replaced by polling tasks/get.\n'
                'PROTOCOL_VERSION = "2026-07-28"\n'
            ),
            reason="A migration comment is not an implementation of the removed methods.",
        ),
        Fires(
            snippet=(
                'import { ListTasksRequestSchema } from "@modelcontextprotocol/sdk/types.js";\n'
                "server.setRequestHandler(ListTasksRequestSchema, listTasks);\n"
            ),
            reason="The removed TypeScript SDK task-list schema is a direct dependency.",
            language="typescript",
        ),
        Fires(
            snippet='const method = "tasks/result";\n',
            reason="The removed blocking tasks/result wire method must migrate to polling.",
            language="typescript",
        ),
        Silent(
            snippet=(
                'const methods = ["tasks/get", "tasks/update"];\n'
            ),
            reason="The replacement polling methods are current and must stay silent.",
            language="typescript",
        ),
        Silent(
            snippet=(
                '// tasks/list and tasks/result were replaced by polling tasks/get.\n'
                'export const protocolVersion = "2026-07-28";\n'
            ),
            reason="A migration comment is not an implementation of the removed methods.",
            language="typescript",
        ),
        Fires(
            snippet=(
                'const { GetTaskPayloadRequestSchema } = require("@modelcontextprotocol/sdk/types.js");\n'
                "server.setRequestHandler(GetTaskPayloadRequestSchema, getTaskResult);\n"
            ),
            reason="The removed JavaScript SDK blocking-result schema is a direct dependency.",
            language="javascript",
        ),
        Fires(
            snippet='const method = "tasks/list";\n',
            reason="The removed tasks/list wire method is no longer part of core tasks.",
            language="javascript",
        ),
        Silent(
            snippet='const method = "tasks/get";\n',
            reason="The replacement polling method is current and must stay silent.",
            language="javascript",
        ),
        Silent(
            snippet=(
                '// tasks/list and tasks/result were replaced by polling tasks/get.\n'
                'export const protocolVersion = "2026-07-28";\n'
            ),
            reason="A migration comment is not an implementation of the removed methods.",
            language="javascript",
        ),
    )

    def check(self, project: Project) -> list[Finding]:
        if project.language in ("typescript", "javascript"):
            return self._check_ts(project)
        return self._check_python(project)

    def _check_python(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        for f, line, text in project.search_code(TASKS_CODE_RX.pattern):
            out.append(self.finding(MESSAGE_CODE, f, line, text))
        # tasks/list and tasks/result are JSON-RPC method strings, not
        # valid bare identifiers -- they can only appear inside a STRING
        # token, so search_code would never find them (see the
        # notifications/initialized note in r009). Raw scan instead.
        for f, line, text in project.search_wire(WIRE_RX):
            out.append(self.finding(MESSAGE_WIRE, f, line, text))
        return out

    def _check_ts(self, project: Project) -> list[Finding]:
        # TypeScript and JavaScript share the same two signals here: the SDK
        # schema name is code, and the wire method name only ever exists
        # inside a string literal, which search_code discards wholesale.
        seen: set[tuple[str, int]] = set()
        out: list[Finding] = []
        for pattern, message, search in (
            (TS_TASKS_CODE_RX.pattern, MESSAGE_CODE, project.search_code),
            (WIRE_RX, MESSAGE_WIRE, project.search_wire),
        ):
            for f, line, text in search(pattern):
                # A dispatcher line can carry both signals at once --
                # `case "tasks/list": return this.handleListTasks(ListTasksRequestSchema);`
                # is one removed-method usage, not two.
                if (str(f.path), line) in seen:
                    continue
                seen.add((str(f.path), line))
                out.append(self.finding(message, f, line, text))
        return sorted(out, key=lambda x: (str(x.path or ""), x.line or 0))
