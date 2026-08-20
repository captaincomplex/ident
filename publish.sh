#!/usr/bin/env bash
# Publish this project to GitHub and enable GitHub Pages (serves /docs on the current branch).
# Safe to re-run: if the repo or Pages site already exists it just reports and moves on.
set -uo pipefail
REPO="flightwall"
cd "$(dirname "$0")"

# 1) clear any stale git lock left by a synced (Dropbox/iCloud) folder
rm -f .git/index.lock .git/HEAD.lock .git/*.lock 2>/dev/null || true

# 2) require gh + auth
command -v gh >/dev/null || { echo "ERROR: gh CLI not installed. Run: brew install gh"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "ERROR: not logged in. Run: gh auth login"; exit 1; }

# 3) init + commit if needed
if [ ! -d .git ]; then
  git init -q
  git branch -M main
fi
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
git add -A
git diff --cached --quiet || git commit -q -m "Publish $REPO site" || true

# 4) create the GitHub repo + push (skip create if it already exists)
if gh repo view "$REPO" >/dev/null 2>&1; then
  echo "Repo $REPO already exists on GitHub — pushing current $BRANCH."
  git remote get-url origin >/dev/null 2>&1 || gh repo view "$REPO" --json url -q .url | xargs -I{} git remote add origin {}.git
  git push -u origin "$BRANCH"
else
  gh repo create "$REPO" --public --source=. --remote=origin --push
fi

# 5) enable GitHub Pages on /docs @ $BRANCH (ignore error if already enabled)
OWNER="$(gh api user -q .login)"
gh api -X POST "repos/$OWNER/$REPO/pages" \
  -f "source[branch]=$BRANCH" -f "source[path]=/docs" >/dev/null 2>&1 \
  && echo "Pages enabled." \
  || echo "Pages already enabled (or enable manually: Settings -> Pages -> $BRANCH /docs)."

echo "Done. Site: https://$OWNER.github.io/$REPO/"
