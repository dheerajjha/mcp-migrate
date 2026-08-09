import re

from .base import Finding, Project, Rule

# Only the five *list-shaped* results are cacheable per SEP-2549 --
# call_tool/get_prompt are not in that list, so a file that only
# implements tool calls (no listing/reading handler) shouldn't be flagged
# for lacking cache metadata it was never supposed to carry.
CACHEABLE_HANDLER_RX = re.compile(
    r"@[\w.]*\.(?:list_tools|list_prompts|list_resources|read_resource|"
    r"list_resource_templates)\s*\("
)

# Presence check: a mention anywhere in code or string literals in the file is
# enough to count the metadata as handled, because a wrong "still missing"
# (breaking) claim costs far more than a generous read of "present" does.
# Searched via search_wire to ignore comments and docstrings.
#
# Known limitation (#91): this looks for the literal token, so a computed
# property key built from string concatenation --
#   const TTL = "ttl" + "Ms";
#   ({ tools: [], [TTL]: 1000 })
# -- never spells "ttlMs" anywhere in the file and reads as absent even
# though it's on the wire. Accepted as a won't-fix: this is an exotic way
# to write the field name, and catching it would mean evaluating string
# expressions rather than scanning text.
CACHE_META_MENTION_RX = re.compile(r"ttlMs|cacheScope")

# The other, and more likely, way these fields get onto the wire.
#
# Unlike `resultType` (which the SDK always stamps), the SDK fills ttlMs and
# cacheScope *only when the server was configured with cache hints* --
# `Runner._serialize` guards on `self.server.cache_hints.get(method)`, and
# mcp/server/caching.py documents the API as a constructor argument:
#
#     Server(cache_hints={method: CacheHint(...)})
#
# So the author expresses this once at construction, not by writing the wire
# field names inside each handler's file. Scanning a handler file for the
# literal strings looks in the wrong place and reports "still missing"
# against a server that has already handled it properly.
#
# Configuring hints anywhere in the project therefore satisfies this rule,
# and a project with neither hints nor literal fields still gets the finding
# -- which stays true and actionable, because without hints the SDK emits no
# cache metadata at all.
CACHE_HINT_CONFIG_RX = re.compile(r"\bcache_hints\s*=|\bCacheHint\s*\(")

# --- TypeScript -----------------------------------------------------------
#
# Low-level servers register list/read handlers with request schemas or wire
# method names. search_code for the schema identifiers; search_wire for the
# method string literals in setRequestHandler calls.
TS_CACHEABLE_HANDLER_RX = (
    r"setRequestHandler\s*\(\s*(?:ListTools|ListPrompts|ListResources|"
    r"ReadResource|ListResourceTemplates)RequestSchema\b"
)
TS_CACHEABLE_METHOD_RX = (
    r"setRequestHandler\s*\(\s*"
    r"[\"'](?:tools/list|prompts/list|resources/list|resources/read|"
    r"resources/templates/list)[\"']"
)

# Server-level hints are configured once on construction:
#   new McpServer({ ... }, { cacheHints: { 'tools/list': { ttlMs, cacheScope }}})
# Per-resource hints use cacheHint: on registerResource. Either satisfies
# the rule project-wide -- scanning handler files for literal ttlMs/cacheScope
# would miss a server that configured hints correctly in a different file.
TS_CACHE_HINT_CONFIG_RX = re.compile(r"\bcacheHints\b|\bcacheHint\s*:")

MESSAGE = (
    "This file implements a list/read handler but neither `ttlMs` nor "
    "`cacheScope` appears in it."
)


# Downgraded from "breaking" after auditing real servers: ttlMs/cacheScope
# are brand-new required fields introduced by this same spec revision, so
# this is an absence check every pre-2026-07-28 list/read handler fails by
# construction. Of the 14 real servers scanned, all 5 whose handlers this
# rule could detect tripped it, 5 for 5 -- it isn't distinguishing better-
# from worse-maintained projects, it's just confirming they predate the
# spec. Stacked at `breaking` alongside R010/R015 (same shape of absence
# check, same 5 projects) this alone would have put every reference
# server at F on launch day, which isn't informative for a public board.
# Keep the finding, drop the severity to match how little it discriminates.
class CacheableResultMetadataMissing(Rule):
    id = "R016"
    title = "List/read results are returned without ttlMs / cacheScope"
    severity = "advisory"
    spec_ref = "SEP-2549 https://modelcontextprotocol.io/specification/2026-07-28/changelog"
    fix = (
        "tools/list, prompts/list, resources/list, resources/read and "
        "resources/templates/list results now require CacheableResult's ttlMs and "
        "cacheScope. With the official SDK you configure this once rather than "
        "per handler: Server(cache_hints={method: CacheHint(...)}). Without hints "
        "the SDK emits no cache metadata at all."
    )
    languages = ("python", "typescript")

    def check(self, project: Project) -> list[Finding]:
        if project.language == "typescript":
            return self._check_ts(project)
        return self._check_python(project)

    def _check_python(self, project: Project) -> list[Finding]:
        # Cache hints are registered once on the server, so this is a
        # project-wide question, not a per-file one.
        if any(project.search_code(CACHE_HINT_CONFIG_RX.pattern)):
            return []
        files_with_mention = {
            f.path for f, _, _ in project.search_wire(CACHE_META_MENTION_RX.pattern)
        }
        out: list[Finding] = []
        seen_files = set()
        for f, line, text in project.search_code(CACHEABLE_HANDLER_RX.pattern):
            if f.path in seen_files:
                continue
            if f.path in files_with_mention:
                continue
            seen_files.add(f.path)
            out.append(self.finding(MESSAGE, f, line, text))
        return out

    def _check_ts(self, project: Project) -> list[Finding]:
        if any(project.search_code(TS_CACHE_HINT_CONFIG_RX.pattern)):
            return []
        files_with_mention = {
            f.path for f, _, _ in project.search_wire(CACHE_META_MENTION_RX.pattern)
        }
        handler_hits: dict[object, tuple[int, str]] = {}
        for f, line, text in project.search_code(TS_CACHEABLE_HANDLER_RX):
            handler_hits.setdefault(f.path, (line, text))
        for f, line, text in project.search_wire(TS_CACHEABLE_METHOD_RX):
            handler_hits.setdefault(f.path, (line, text))
        out: list[Finding] = []
        for path, (line, text) in sorted(
            handler_hits.items(), key=lambda item: (str(item[0]), item[1][0])
        ):
            if path in files_with_mention:
                continue
            f = next(ff for ff in project.files if ff.path == path)
            out.append(self.finding(MESSAGE, f, line, text))
        return out
