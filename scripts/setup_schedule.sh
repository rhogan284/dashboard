#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PLIST_SRC="$PROJECT_ROOT/launchd/com.dashboard.morningbrief.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.dashboard.morningbrief.plist"

# Unload existing job if it's already loaded
if launchctl list | grep -q "com.dashboard.morningbrief"; then
  echo "Unloading existing job..."
  launchctl unload "$PLIST_DST" 2>/dev/null || true
fi

# Copy plist to LaunchAgents
mkdir -p "$HOME/Library/LaunchAgents"
cp "$PLIST_SRC" "$PLIST_DST"
chmod 644 "$PLIST_DST"

# Load the job
launchctl load "$PLIST_DST"

echo "✓ Morning Brief scheduled for 7:00 AM Mon–Fri"
echo "  Logs: ~/Library/Logs/morning_brief.log"
echo "  To unload: launchctl unload $PLIST_DST"
