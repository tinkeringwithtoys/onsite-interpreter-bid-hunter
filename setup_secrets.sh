#!/usr/bin/env bash
# =============================================================================
# Push your .env into GitHub Actions Secrets.
#
# Actions cannot read your local .env - it never leaves your machine. Secrets
# are how the runner gets them, encrypted at rest and masked in logs.
#
#   1. gh auth login                    (once)
#   2. python3 envfile.py --check .env  (must say USABLE)
#   3. ./setup_secrets.sh <owner>/<repo>
# =============================================================================
set -euo pipefail

REPO="${1:-}"
ENV_FILE="${2:-.env}"

if [ -z "$REPO" ]; then
  echo "usage: ./setup_secrets.sh <owner>/<repo> [env-file]"
  echo "example: ./setup_secrets.sh samhaj/onsite-interpreter-bid-hunter"
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI not found. Install it: https://cli.github.com/"
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "$ENV_FILE not found. Copy .env.example to .env and fill it in."
  exit 1
fi

# Refuse to upload a file we know is malformed. Uploading a broken SMTP_FROM
# would produce a pipeline that authenticates, reports success, and emails
# nobody - the worst possible failure because it looks like it works.
echo "Validating $ENV_FILE ..."
if ! python3 envfile.py --check "$ENV_FILE"; then
  echo
  echo "Refusing to upload a malformed env file. Fix the errors above first."
  exit 1
fi

REQUIRED=(SMTP_HOST SMTP_PORT SMTP_USER SMTP_PASSWORD SMTP_FROM ALERT_EMAIL AGNES_API_KEY)
OPTIONAL=(AGNES_ENDPOINT AGNES_MODEL TUNEPS_USER TUNEPS_PASSWORD)

get_value() {
  # Exact match on the key at line start. Never a substring match.
  grep -E "^$1=" "$ENV_FILE" | head -n1 | cut -d= -f2- | sed 's/^["'\'']//; s/["'\'']$//'
}

echo
echo "Uploading secrets to $REPO ..."

for key in "${REQUIRED[@]}"; do
  value="$(get_value "$key")"
  if [ -z "$value" ]; then
    echo "  x $key is empty - aborting"
    exit 1
  fi
  printf '%s' "$value" | gh secret set "$key" --repo "$REPO" --body-file -
  echo "  ok $key"
done

for key in "${OPTIONAL[@]}"; do
  value="$(get_value "$key")"
  if [ -n "$value" ]; then
    printf '%s' "$value" | gh secret set "$key" --repo "$REPO" --body-file -
    echo "  ok $key (optional)"
  fi
done

echo
echo "Done. Verify with:  gh secret list --repo $REPO"
echo "Then trigger a run: gh workflow run 'fast (JSON APIs, hourly)' --repo $REPO"
