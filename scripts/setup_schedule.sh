#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PYTHON="$PROJECT_ROOT/flask_app/.venv/bin/python"
VENV_BIN="$PROJECT_ROOT/flask_app/.venv/bin"
SCRIPT_PATH="$PROJECT_ROOT/scripts/morning_brief.py"
PLIST_TEMPLATE="$PROJECT_ROOT/launchd/com.dashboard.morningbrief.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.dashboard.morningbrief.plist"
LABEL="com.dashboard.morningbrief"

# Verify venv Python exists
if [ ! -f "$VENV_PYTHON" ]; then
  echo "ERROR: Python venv not found at $VENV_PYTHON"
  echo "  Run: python3 -m venv flask_app/.venv && flask_app/.venv/bin/pip install -r flask_app/requirements.txt"
  exit 1
fi

# Unload existing job if already registered
if launchctl list 2>/dev/null | grep -q "$LABEL"; then
  echo "Unloading existing job..."
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
fi

# Substitute template placeholders with real paths
mkdir -p "$HOME/Library/LaunchAgents"
sed \
  -e "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" \
  -e "s|__VENV_PYTHON__|$VENV_PYTHON|g" \
  -e "s|__SCRIPT_PATH__|$SCRIPT_PATH|g" \
  -e "s|__HOME__|$HOME|g" \
  -e "s|__VENV_PYTHON_DIR__|$VENV_BIN|g" \
  "$PLIST_TEMPLATE" > "$PLIST_DST"

chmod 644 "$PLIST_DST"

# Load using modern launchctl bootstrap
launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"

# Verify registration
if launchctl list 2>/dev/null | grep -q "$LABEL"; then
  echo "✓ Morning Brief scheduled for 7:00 AM Mon–Fri"
  echo "  Logs: ~/Library/Logs/morning_brief.log"
  echo "  To unload: launchctl bootout gui/\$(id -u)/$LABEL"
else
  echo "WARNING: job does not appear in launchctl list — check for errors above."
  exit 1
fi
