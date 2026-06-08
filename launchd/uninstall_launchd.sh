#!/bin/bash
# Remove all IDP Command Center launchd agents

LAUNCH_DIR="$HOME/Library/LaunchAgents"
AGENTS=(
  "com.idp.hgi-audit-agent"
  "com.idp.xero-cash-agent"
  "com.idp.gardant-agent"
  "com.idp.portfolio-agent"
  "com.idp.leasing-agent"
)

echo "Uninstalling IDP Command Center launch agents..."
for label in "${AGENTS[@]}"; do
  plist="$LAUNCH_DIR/$label.plist"
  launchctl unload "$plist" 2>/dev/null && echo "  ✓ Unloaded: $label" || echo "  - Not loaded: $label"
  rm -f "$plist"
done
echo "Done."
