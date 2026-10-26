#!/usr/bin/env bash
# Publish the site: generated pages → gh-pages branch (one orphan commit, no history),
# then trigger the Pages workflow, which overlays gh-pages onto main's code.
#
# Generated dirs are gitignored in main; this is the only way they reach GitHub.
# Restore one locally from the live site:  git restore -s origin/gh-pages -W -- <path>
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
cd "$REPO"

# Keep in sync with .gitignore and .github/workflows/deploy.yml
GEN=(en ru ar hi zh buildings app sales rents)

for d in "${GEN[@]}"; do
  [ -d "$d" ] || { echo "deploy: $d/ missing — run scripts/refresh_all.sh first" >&2; exit 1; }
done

[ "$(git symbolic-ref --short HEAD)" = main ] || { echo "deploy: not on main" >&2; exit 1; }

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "deploy: uncommitted changes in tracked files — commit them first:" >&2
  git status --short --untracked-files=no >&2
  exit 1
fi

git fetch -q origin
behind="$(git rev-list --count HEAD..origin/main)"
ahead="$(git rev-list --count origin/main..HEAD)"
[ "$behind" = 0 ] || { echo "deploy: main is $behind commit(s) behind origin/main — pull first" >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export GIT_INDEX_FILE="$TMP/index"
git add -f -A -- "${GEN[@]}" \
  ':(exclude,glob)**/.DS_Store' ':(exclude)rents/data' ':(exclude)sales/data'
tree="$(git write-tree)"
unset GIT_INDEX_FILE

prev="$(git rev-parse -q --verify 'origin/gh-pages^{tree}' || true)"
pages_changed=1
if [ "$tree" = "$prev" ]; then
  pages_changed=0
  echo "deploy: pages unchanged"
else
  n="$(git ls-tree -r --name-only "$tree" | wc -l | tr -d ' ')"
  commit="$(git commit-tree "$tree" -m "Pages for main@$(git rev-parse --short HEAD) ($n files)")"
  echo "deploy: pushing $n files to gh-pages"
  git push -q -f origin "$commit:refs/heads/gh-pages"
fi

if [ "$ahead" -gt 0 ]; then
  echo "deploy: pushing $ahead commit(s) to main (triggers the Pages workflow)"
  git push -q origin main
elif [ "$pages_changed" = 1 ]; then
  gh workflow run deploy.yml --ref main
else
  echo "deploy: nothing to deploy"
  exit 0
fi

git gc --auto -q
echo "deploy: started — follow with: gh run watch"
