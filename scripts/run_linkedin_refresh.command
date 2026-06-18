#!/bin/zsh
set -euo pipefail

PROJECT_DIR="/Users/youngkit/Documents/codex_project/projects/job-tracker"
LOG_DIR="$PROJECT_DIR/logs/launcher"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/linkedin-refresh-$(date +%Y%m%d-%H%M%S).log"

cd "$PROJECT_DIR"

if [ -f "$PROJECT_DIR/.env" ]; then
  source "$PROJECT_DIR/.env"
fi

exec > >(tee -a "$LOG_FILE") 2>&1

echo "== Job Tracker: LinkedIn Refresh =="
echo "Project: $PROJECT_DIR"
echo "Log: $LOG_FILE"
echo

source .venv/bin/activate

REMOTE_DEBUGGING_URL="${LINKEDIN_REMOTE_DEBUGGING_URL:-http://127.0.0.1:9222}"
REMOTE_DEBUGGING_PORT="${REMOTE_DEBUGGING_URL##*:}"
CHROME_APP_PATH="/Applications/Google Chrome.app"
CHROME_EXECUTABLE="${LINKEDIN_BROWSER_EXECUTABLE:-}"
CHROME_PROFILE_DIR="${LINKEDIN_BROWSER_USER_DATA_DIR:-$PROJECT_DIR/.browser-profile}"

if ! curl --noproxy '*' --silent --fail "${REMOTE_DEBUGGING_URL}/json/version" >/dev/null 2>&1; then
  echo "Chrome debug session not detected. Launching dedicated Chrome profile..."

  if [ -n "$CHROME_EXECUTABLE" ]; then
    open -na "$CHROME_APP_PATH" --args \
      --remote-debugging-port="$REMOTE_DEBUGGING_PORT" \
      --user-data-dir="$CHROME_PROFILE_DIR"
  else
    open -na "$CHROME_APP_PATH" --args \
      --remote-debugging-port="$REMOTE_DEBUGGING_PORT" \
      --user-data-dir="$CHROME_PROFILE_DIR"
  fi

  echo "Waiting for Chrome to start..."
  sleep 8
fi

echo "Refreshing LinkedIn sources..."

python linkedin_browser_refresh.py --refresh-bundle

echo
echo "LinkedIn refresh completed successfully."
echo "Press Enter to close this window."
read
