"""A stateless server that predates Mcp-Session-Id and never used it.

This docstring, the comment below, and the log message in `handle_request`
all *mention* Mcp-Session-Id in plain English -- exactly like mcp-atlassian's
only R001 hit, which was inside a `logger.debug(...)` call, and like
motherduck's, which was inside a `click.option(help=...)` string explaining
a CLI flag. None of these are code that actually reads or sets the header,
so R001 should not fire here.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def handle_request(payload: dict) -> dict:
    # NOTE: some older clients still send an Mcp-Session-Id header; this
    # server does not read it and never has.
    logger.debug("handling request; Mcp-Session-Id (if sent) is ignored")
    return {"ok": True, "echo": payload}
