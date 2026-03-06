#!/bin/bash
#
# End-to-End Test: Verify before_prompt_build hook injection
#
# Prerequisites:
#   - OpenClaw gateway is running
#   - Plugin is installed and enabled
#
# Usage:
#   ./scripts/test_hook.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$HOME/.openclaw/logs/anti-repeat-errors"
LOG_FILE="$LOG_DIR/injections.jsonl"

echo "=== Anti-Repeat-Errors Hook Test ==="
echo ""
echo "Skill directory: $SKILL_DIR"
echo "Log directory: $LOG_DIR"
echo ""

# 1. Check OpenClaw CLI
echo "1. Checking OpenClaw CLI..."
if ! command -v openclaw &> /dev/null; then
    echo "✗ openclaw CLI not found in PATH"
    echo "  Please install OpenClaw or add it to PATH"
    exit 1
fi
echo "✓ openclaw CLI found: $(which openclaw)"

# 2. Check gateway status
echo ""
echo "2. Checking gateway status..."
GATEWAY_STATUS=$(openclaw gateway status 2>/dev/null || echo "unknown")
if echo "$GATEWAY_STATUS" | grep -qi "running\|active\|up"; then
    echo "✓ Gateway appears to be running"
else
    echo "! Gateway status: $GATEWAY_STATUS"
    echo "  If gateway is not running, start it with: openclaw gateway start"
fi

# 3. Check plugin installation
echo ""
echo "3. Checking plugin installation..."
if [ -f "$SKILL_DIR/openclaw.plugin.json" ]; then
    echo "✓ Plugin manifest found"
    PLUGIN_ID=$(python3 -c "import json; print(json.load(open('$SKILL_DIR/openclaw.plugin.json')).get('id', 'unknown'))" 2>/dev/null || echo "unknown")
    echo "  Plugin ID: $PLUGIN_ID"
else
    echo "✗ Plugin manifest not found at $SKILL_DIR/openclaw.plugin.json"
fi

# Check if plugin is registered (if openclaw plugins list is available)
PLUGINS=$(openclaw plugins list 2>/dev/null || echo "")
if [ -n "$PLUGINS" ]; then
    if echo "$PLUGINS" | grep -q "anti-repeat-errors"; then
        echo "✓ anti-repeat-errors plugin registered"
    else
        echo "! anti-repeat-errors plugin not found in registry"
        echo "  Install with: openclaw plugins install $SKILL_DIR"
    fi
fi

# 4. Check hook registration
echo ""
echo "4. Checking hook registration..."
HOOKS=$(openclaw hooks list 2>/dev/null || echo "")
if [ -n "$HOOKS" ]; then
    if echo "$HOOKS" | grep -q "anti-repeat-errors\|before_prompt_build"; then
        echo "✓ Hook registered"
    else
        echo "! Hook not visible in list (may be plugin-managed)"
    fi
else
    echo "! Cannot list hooks (openclaw hooks list unavailable)"
fi

# 5. Ensure log directory exists
echo ""
echo "5. Setting up log directory..."
mkdir -p "$LOG_DIR"
if [ -d "$LOG_DIR" ]; then
    echo "✓ Log directory ready: $LOG_DIR"
else
    echo "✗ Failed to create log directory"
    exit 1
fi

# 6. Count existing logs
echo ""
echo "6. Checking existing logs..."
if [ -f "$LOG_FILE" ]; then
    LOG_COUNT_BEFORE=$(wc -l < "$LOG_FILE" 2>/dev/null || echo "0")
    echo "✓ Found existing log file with $LOG_COUNT_BEFORE entries"
else
    LOG_COUNT_BEFORE=0
    echo "! No existing log file"
fi

# 7. Run verification script
echo ""
echo "7. Running verification script..."
if [ -f "$SCRIPT_DIR/verify_injection.py" ]; then
    cd "$SKILL_DIR"
    if python3 scripts/verify_injection.py --verbose; then
        echo "✓ Verification passed"
    else
        echo "! Verification failed (see output above)"
    fi
else
    echo "✗ Verification script not found: $SCRIPT_DIR/verify_injection.py"
fi

# 8. Summary
echo ""
echo "=== Test Summary ==="
echo ""

if [ -f "$LOG_FILE" ]; then
    LOG_COUNT_AFTER=$(wc -l < "$LOG_FILE" 2>/dev/null || echo "0")
    echo "Log entries: $LOG_COUNT_AFTER total"
    
    if [ "$LOG_COUNT_AFTER" -gt 0 ]; then
        echo ""
        echo "Recent log entries:"
        tail -n 3 "$LOG_FILE" 2>/dev/null | while read -r line; do
            # Try to pretty-print JSON
            echo "$line" | python3 -m json.tool 2>/dev/null || echo "$line"
        done
    fi
    
    # Check for injection events
    SUCCESS_COUNT=$(grep -c '"event":"injection_success"' "$LOG_FILE" 2>/dev/null || echo "0")
    SKIP_COUNT=$(grep -c '"event":"injection_skipped"' "$LOG_FILE" 2>/dev/null || echo "0")
    TRIGGER_COUNT=$(grep -c '"event":"hook_triggered"' "$LOG_FILE" 2>/dev/null || echo "0")
    
    echo ""
    echo "Event counts:"
    echo "  Hook triggered: $TRIGGER_COUNT"
    echo "  Injections: $SUCCESS_COUNT"
    echo "  Skips: $SKIP_COUNT"
else
    echo "No log file found at: $LOG_FILE"
    echo ""
    echo "To generate logs:"
    echo "  1. Ensure the plugin is installed and enabled"
    echo "  2. Send a message through OpenClaw"
    echo "  3. Run this script again"
fi

echo ""
echo "=== Test Complete ==="