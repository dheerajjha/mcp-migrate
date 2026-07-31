#!/usr/bin/env bash
# Bulk-file every issue in .github/GOOD_FIRST_ISSUES.md via `gh issue create`.
#
# Usage:
#   .github/scripts/file_issues.sh                    # repo gh is already pointed at
#   .github/scripts/file_issues.sh owner/mcp-migrate   # explicit target repo
#   .github/scripts/file_issues.sh owner/mcp-migrate --dry-run   # print, don't file
#
# Parses ISSUES_FILE's "### ISSUE_START" / "### ISSUE_END" blocks, each
# containing a "TITLE:" line, a "LABELS:" line (comma-separated), a
# "DIFFICULTY:" line, and a "BODY_START" / "BODY_END" body. Do not reformat
# GOOD_FIRST_ISSUES.md's markers or metadata lines without updating this
# script to match.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ISSUES_FILE="${ISSUES_FILE:-"$SCRIPT_DIR/../GOOD_FIRST_ISSUES.md"}"

REPO=""
DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    *) REPO="$arg" ;;
  esac
done

if [[ ! -f "$ISSUES_FILE" ]]; then
  echo "issues file not found: $ISSUES_FILE" >&2
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI not found -- install it or run with --dry-run to just preview" >&2
  [[ "$DRY_RUN" -eq 1 ]] || exit 1
fi

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

# GOOD_FIRST_ISSUES.md links to files with repo-relative paths (../cookbook/x,
# ../../src/y) so the document reads correctly in the repository. GitHub does
# not resolve relative links inside an *issue body*, though -- it resolves them
# against the issue URL, so every one would 404 on precisely the file the
# contributor needs to open. Rewrite them to absolute blob URLs at filing time,
# which keeps the in-repo document and the filed issue both correct.
link_repo="$REPO"
if [[ -z "$link_repo" ]] && command -v gh >/dev/null 2>&1; then
  link_repo="$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null || true)"
fi
link_branch="main"
if [[ -n "$link_repo" ]] && command -v gh >/dev/null 2>&1; then
  link_branch="$(gh repo view "$link_repo" --json defaultBranchRef \
    --jq .defaultBranchRef.name 2>/dev/null || echo main)"
  [[ -n "$link_branch" ]] || link_branch="main"
fi

absolutize_links() {
  if [[ -z "$link_repo" ]]; then
    cat  # no repo to resolve against; leave the body untouched
    return
  fi
  # ](../x) and ](../../x) both mean repo-root/x here, so strip every leading
  # ../ segment and anchor the remainder at the blob URL.
  sed -E "s#\]\((\.\./)+#](https://github.com/${link_repo}/blob/${link_branch}/#g"
}

# Split into one file per issue block. Lines between ISSUE_START/ISSUE_END
# (exclusive of the markers themselves) go into workdir/issue_N.txt.
awk -v dir="$workdir" '
  /^### ISSUE_START/ { n++; out = dir "/issue_" n ".txt"; next }
  /^### ISSUE_END/   { out = ""; next }
  out != "" { print > out }
' "$ISSUES_FILE"

shopt -s nullglob
files=("$workdir"/issue_*.txt)
if [[ ${#files[@]} -eq 0 ]]; then
  echo "no ISSUE_START/ISSUE_END blocks found in $ISSUES_FILE" >&2
  exit 1
fi

# Sort numerically (issue_2 before issue_10), not lexically. Built with a
# read loop rather than `mapfile`, which is bash 4+ only -- macOS still ships
# bash 3.2, so mapfile would fail for a large share of contributors.
sorted=()
while IFS= read -r line; do
  sorted+=("$line")
done < <(printf '%s\n' "${files[@]}" | sort -t_ -k2 -n)

filed=0
failed=0
for f in "${sorted[@]}"; do
  title="$(sed -n 's/^TITLE: //p' "$f" | head -n1)"
  labels_line="$(sed -n 's/^LABELS: //p' "$f" | head -n1)"
  body="$(sed -n '/^BODY_START$/,/^BODY_END$/p' "$f" | sed '1d;$d' | absolutize_links)"

  if [[ -z "$title" ]]; then
    echo "skipping $f: no TITLE: line found" >&2
    ((failed++)) || true
    continue
  fi

  label_args=()
  if [[ -n "$labels_line" ]]; then
    IFS=',' read -ra labels <<< "$labels_line"
    for l in "${labels[@]}"; do
      label_args+=(--label "$l")
    done
  fi

  repo_args=()
  [[ -n "$REPO" ]] && repo_args=(--repo "$REPO")

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "--- would file ---"
    echo "title:  $title"
    echo "labels: $labels_line"
    echo "repo:   ${REPO:-<current gh default>}"
    echo "body:"
    echo "$body" | sed 's/^/  /'
    echo
  else
    if gh issue create --title "$title" "${label_args[@]}" "${repo_args[@]}" --body "$body"; then
      ((filed++)) || true
    else
      echo "failed to file: $title" >&2
      ((failed++)) || true
    fi
  fi
done

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "dry run: ${#sorted[@]} issue(s) parsed, nothing filed"
else
  echo "filed $filed issue(s), $failed failure(s)"
fi
[[ "$failed" -eq 0 ]]
