# Security policy

## Reporting a vulnerability

Please report it privately through GitHub: open this repository's **Security** tab and choose **Report a vulnerability**. Please don't open a public issue for it.

You'll hear back within a few days. The fix ships in a new release, and the advisory credits you unless you'd rather it didn't.

## Supported versions

Security fixes go into the latest release only.

## Scope

mcp-migrate reads your source files and never runs them. `fix --write` is the only command that writes, and only inside the project you point it at. The failures worth reporting are a crafted file that makes `check` or `fix` run code, touch a path outside the project, or hang on a pathological regular expression.
