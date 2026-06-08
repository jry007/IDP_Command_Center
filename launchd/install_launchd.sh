#!/bin/bash
# Install all IDP Command Center launchd agents
# Run once: bash launchd/install_launchd.sh

set -e

PLIST_DIR="$(cd "$(dirname "$0")" && pwd)"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$LAUNCH_DIR"

AGENTS=(
  "com.idp.hgi-audit-agent.plist"
  "com.idp.xero-cash-agent.plist"
  "com.idp.gardant-agent.plist"
  "com.idp.portfolio-agent.plist"
  "com.idp.leasing-agent.plist"
)

echo "Installing IDP Command Center launch agents..."
echo ""

for agent in "${AGENTS[@]}"; do
  src="$PLIST_DIR/$agent"
  dst="$LAUNCH_DIR/$agent"
  label="${agent%.plist}"

  # Unload if already loaded
  launchctl unload "$dst" 2>/dev/null || true

  # Copy plist
  cp "$src" "$dst"

  # Load
  launchctl load "$dst"
  echo "  ✓ Loaded: $label"
done

echo ""
echo "All agents installed. Schedule summary:"
echo "  7:45 AM daily     — HGI Night Audit parser"
echo "  8:00 AM daily     — Xero Cash Position"
echo "  8:30 AM Monday    — Leasing Follow-Up (AppFolio)"
echo "  9:00 AM daily     — Gardant AL Reports"
echo "  6:00 PM Friday    — Kim's Portfolio Report"
echo "  8:00 AM Monday    — Kim's Portfolio Report (catch-up)"
echo ""
echo "Logs: ~/IDP_Command_Center/logs/"
echo ""
echo "To uninstall all agents:"
echo "  bash launchd/uninstall_launchd.sh"
