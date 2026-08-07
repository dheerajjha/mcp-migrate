"""The `mcp-migrate-precommit` entry point.

pre-commit treats **any** non-zero exit as a failed hook. `check` exits 2
for "could not check it" -- no readable source in a supported language --
which is the correct answer for the CLI and completely wrong for a hook:
it would block every commit in any repository the tool cannot read, which
includes every repository right up until the moment someone adds their
first Python or TypeScript file. A hook that blocks commits for a reason
the user cannot act on gets uninstalled within the hour, and then it
catches nothing ever again.

So this wrapper is exactly one decision: **2 becomes 0.**

Nothing else changes. 1 still means a breaking finding and still blocks
the commit, which is the entire point of installing this. The message is
still printed, so "we could not read this" stays visible -- it just stops
being fatal.

A wrapper rather than a `--exit-zero-on-unscannable` flag on `check`: the
flag would be one more thing to get wrong on the command line, and the
distinction only exists because of how pre-commit interprets exit codes.
That is the hook's problem, so it lives in the hook.
"""
from __future__ import annotations

import sys

from .cli import EXIT_OK, EXIT_UNSCANNABLE, main as cli_main


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # `check` is implied. The hook only ever runs that one command, and
    # anything a user puts in `args:` is a path or a flag for it -- not a
    # subcommand. Testing for a leading dash is not enough: a bare path
    # would then be parsed as a subcommand name and argparse would exit 2,
    # which is the very code this wrapper exists to stop being fatal.
    if not argv or argv[0] != "check":
        argv = ["check", *argv]

    code = cli_main(argv)
    return EXIT_OK if code == EXIT_UNSCANNABLE else code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
