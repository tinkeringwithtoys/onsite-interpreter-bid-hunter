#!/usr/bin/env bash
# =============================================================================
# deploy.sh - one-shot deployment of onsite-interpreter-bid-hunter
# =============================================================================
# Run this ON YOUR OWN MACHINE, from inside the unzipped folder, with .env
# present and filled in.
#
#     chmod +x deploy.sh
#     ./deploy.sh tinkeringwithtoys/onsite-interpreter-bid-hunter
#
# It is idempotent: safe to re-run. It will not overwrite an existing repo's
# history, and re-setting a secret just overwrites that secret.
# =============================================================================
set -euo pipefail

# Built from parts on purpose so no full literal URL sits in this file.
GH_HOST="github.com"
GH_BASE="https://${GH_HOST}"

REPO="${1:-}"
if [ -z "$REPO" ]; then
  echo "usage: ./deploy.sh <owner>/<repo>"
  echo "e.g.:  ./deploy.sh tinkeringwithtoys/onsite-interpreter-bid-hunter"
  exit 1
fi

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
ok()   { printf '   \033[32mok\033[0m  %s\n' "$*"; }
bad()  { printf '   \033[31mXX\033[0m  %s\n' "$*"; }

# -----------------------------------------------------------------------------
say "0. preflight"

for bin in git gh python3; do
  command -v "$bin" >/dev/null 2>&1 || { bad "$bin not installed"; exit 1; }
  ok "$bin present"
done

if ! gh auth status >/dev/null 2>&1; then
  bad "gh is not authenticated. Run:  gh auth login"
  exit 1
fi
ok "gh authenticated as $(gh api user --jq .login)"

[ -f .env ] || { bad ".env not found in $(pwd)"; exit 1; }
ok ".env present"

# Refuse to deploy a config that is lying about what it covers.
python3 validate_sources.py --check-eligibility || {
  bad "config integrity gate FAILED - fix config.yaml before deploying"
  exit 1
}

python3 envfile.py --check .env >/dev/null || {
  bad ".env is not usable - run: python3 envfile.py --check .env"
  exit 1
}
ok ".env validated"

# -----------------------------------------------------------------------------
say "1. repository"

if gh repo view "$REPO" >/dev/null 2>&1; then
  ok "repo already exists: $REPO"
else
  gh repo create "$REPO" --private --description "Scheduled RFQ/tender hunter for AR<->FR / AR<->EN interpreting"
  ok "created private repo: $REPO"
fi

# -----------------------------------------------------------------------------
say "2. git"

if [ ! -d .git ]; then
  git init -q
  ok "git initialised"
fi

# Scheduled workflows ONLY run on the default branch. Get this wrong and the
# cron silently never fires. This is the single most common deployment bug.
DEFAULT_BRANCH="$(gh repo view "$REPO" --json defaultBranchRef --jq .defaultBranchRef.name 2>/dev/null || echo main)"
DEFAULT_BRANCH="${DEFAULT_BRANCH:-main}"
git checkout -q -B "$DEFAULT_BRANCH"
ok "on branch $DEFAULT_BRANCH (schedules only fire here)"

# Hard stop if .env would be committed.
if ! git check-ignore -q .env; then
  bad ".env is NOT gitignored - refusing to push. Check .gitignore."
  exit 1
fi
ok ".env is gitignored"

git remote remove origin 2>/dev/null || true
git remote add origin "${GH_BASE}/${REPO}.git"

git add -A
if git diff --cached --quiet; then
  ok "nothing new to commit"
else
  git -c user.name="bid-hunter[bot]" \
      -c user.email="bid-hunter@users.noreply.github.com" \
      commit -q -m "deploy: bid-hunter v4.1"
  ok "committed"
fi

# The repo already contains bootstrap commits pushed from the Notion chat
# (.gitignore, requirements.txt, validate.yml). Rebase onto them instead of
# trying to push a divergent history, which GitHub would reject.
git fetch origin "$DEFAULT_BRANCH" >/dev/null 2>&1 || true
if git rev-parse --verify "origin/$DEFAULT_BRANCH" >/dev/null 2>&1; then
  if ! git pull --rebase --autostash origin "$DEFAULT_BRANCH"; then
    bad "rebase onto origin/$DEFAULT_BRANCH failed - resolve by hand, then re-run"
    exit 1
  fi
  ok "rebased onto existing remote history"
fi

git push -u origin "$DEFAULT_BRANCH"
ok "pushed to $REPO"

# Verify .env really is not up there.
if git ls-tree -r "$DEFAULT_BRANCH" --name-only | grep -qx '.env'; then
  bad "CRITICAL: .env got committed. Rotate every secret NOW."
  exit 1
fi
ok "confirmed: .env is not in the pushed tree"

# -----------------------------------------------------------------------------
say "3. secrets"

# Read .env, skip comments/blanks, skip anything the project does not need.
SET_COUNT=0
while IFS= read -r line; do
  case "$line" in \#*|"") continue ;; esac
  key="${line%%=*}"
  val="${line#*=}"
  case "$key" in
    GITHUB_TOKEN|GH_TOKEN|GITHUB_PAT)
      bad "skipping $key - Actions provides GITHUB_TOKEN automatically"
      continue ;;
  esac
  [ -z "$val" ] && continue
  printf '%s' "$val" | gh secret set "$key" --repo "$REPO" --body-file - >/dev/null
  ok "set $key"
  SET_COUNT=$((SET_COUNT+1))
done < .env
echo "   -> $SET_COUNT secrets set"

# -----------------------------------------------------------------------------
say "4. smoke test"

gh workflow enable validate.yml --repo "$REPO" 2>/dev/null || true
gh workflow run validate.yml --repo "$REPO" 2>/dev/null && ok "triggered validate.yml" \
  || bad "could not trigger validate.yml - run it by hand from the Actions tab"

cat <<EOF

=============================================================================
DEPLOYED
=============================================================================
Repo:     ${GH_BASE}/${REPO}
Actions:  ${GH_BASE}/${REPO}/actions
Secrets:  ${GH_BASE}/${REPO}/settings/secrets/actions

WATCH THE VALIDATOR RUN. Then download its artifact and compare it to your
local run:

    python3 validate_sources.py --json local_report.json

Anything that is OK locally but BLOCKED on the runner is IP-filtered --
GitHub Actions uses Azure datacenter IPs and several tender portals block
them. That diff is the whole reason the validator exists.

TWO THINGS THAT WILL BITE YOU LATER:
  1. Scheduled workflows only run on the DEFAULT branch (${DEFAULT_BRANCH}).
  2. GitHub disables schedules after 60 days of repo inactivity. The heavy
     lane writes .keepalive/last_run to push a commit and reset that clock.
=============================================================================
EOF
