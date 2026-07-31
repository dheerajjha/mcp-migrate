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

# Presence check, deliberately raw text (same permissive direction as
# r005_extensions.py / r015_result_type_required.py): a mention anywhere in
# the file is enough to count the metadata as handled, because a wrong
# "still missing" (breaking) claim costs far more than a generous read of
# "present" does.
CACHE_META_MENTION_RX = re.compile(r"ttlMs|cacheScope")


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
        "cacheScope. Add both so clients know how long they may cache the response."
    )

    def check(self, project: Project) -> list[Finding]:
        out: list[Finding] = []
        seen_files = set()
        for f, line, text in project.search_code(CACHEABLE_HANDLER_RX.pattern):
            if f.path in seen_files:
                continue
            if CACHE_META_MENTION_RX.search(f.text):
                continue
            seen_files.add(f.path)
            out.append(self.finding(
                "This file implements a list/read handler but neither `ttlMs` nor "
                "`cacheScope` appears in it.",
                f, line, text,
            ))
        return out
