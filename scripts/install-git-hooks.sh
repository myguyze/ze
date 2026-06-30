#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOKS_SRC="$ROOT/scripts/git-hooks"
GIT_HOOKS="$ROOT/.git/hooks"

if [[ ! -d "$GIT_HOOKS" ]]; then
  echo "error: $GIT_HOOKS not found — are you in a git checkout?" >&2
  exit 1
fi

for hook in pre-commit pre-push; do
  src="$HOOKS_SRC/$hook"
  dest="$GIT_HOOKS/$hook"
  if [[ ! -f "$src" ]]; then
    echo "error: missing hook script $src" >&2
    exit 1
  fi
  chmod +x "$src"
  ln -sf "../../scripts/git-hooks/$hook" "$dest"
  echo "installed $hook -> scripts/git-hooks/$hook"
done

echo ""
echo "Git hooks installed. Use SKIP=1 git commit|push to bypass."
echo "Run 'make check' manually for the same checks as pre-push."
