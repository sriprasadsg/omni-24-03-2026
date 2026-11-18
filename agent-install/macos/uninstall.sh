#!/bin/bash
# Removes the Omni-Agent. With uninstall protection on, it needs this agent's single-use uninstall
# code (Agents > agent > Uninstall code), as the first argument or in OMNI_UNINSTALL_CODE.
#   sudo "/Library/Application Support/OmniAgent/uninstall.sh" <code>
set -u
[ "$(id -u)" = 0 ] || { echo "Run it with sudo." >&2; exit 1; }
D="/Library/Application Support/OmniAgent"
CODE="${1:-${OMNI_UNINSTALL_CODE:-}}"

if [ -x "$D/omni-agent" ]; then
    # Exit 0: valid code, 1: wrong code, 3: no code issued yet (removal allowed).
    "$D/omni-agent" --verify-uninstall-code "$CODE"
    rc=$?
    case $rc in
        0|3) ;;
        1) echo "That uninstall code is not valid for this agent." >&2; exit 1 ;;
        *) echo "The uninstall code could not be checked (omni-agent returned $rc)." >&2; exit 1 ;;
    esac
    "$D/omni-agent" --report-uninstall "$CODE" --method macos-uninstaller || true
fi

launchctl bootout system/com.omniagent.agent 2>/dev/null || true
rm -f /Library/LaunchDaemons/com.omniagent.agent.plist
rm -rf "$D"
pkgutil --forget com.omniagent.agent >/dev/null 2>&1 || true
echo "Omni-Agent removed."
