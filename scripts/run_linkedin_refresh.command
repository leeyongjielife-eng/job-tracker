#!/bin/zsh
set -euo pipefail

PROJECT_DIR="/Users/youngkit/Documents/codex_project/projects/job-tracker"
LOG_DIR="$PROJECT_DIR/logs/launcher"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/linkedin-refresh-$(date +%Y%m%d-%H%M%S).log"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "== Job Tracker: LinkedIn Refresh =="
echo "Project: $PROJECT_DIR"
echo "Log: $LOG_FILE"
echo

cd "$PROJECT_DIR"
source .venv/bin/activate

python linkedin_browser_refresh.py --refresh-bundle

echo
echo "LinkedIn refresh completed successfully."
echo "Press Enter to close this window."
read
