"""Autonomous Ops reporting (Phase 86, D-05..D-21): statistics, time saved, the daily digest, the
activity export and the go-live checklist.

This package is read-only over ``autonomy_actions``. The only collections it owns are
``autonomy_digests`` (what was already sent), ``autonomy_golive_checks`` (the recorded go-live
checks) and ``autonomy_golive_test_org`` (the single go-live test organization mark). Every query goes through ``autonomous_ops.scope.raw`` with an explicit tenantId; nothing
here uses the ambient tenant context and nothing here imports an LLM client.

Constants only (stdlib): later plans import these names and never redefine them.
"""
from types import MappingProxyType

# D-06: the statistics period the screen offers.
WINDOWS = (7, 30, 90)
DEFAULT_WINDOW = 30

# D-07: control rows (stop, resume, breaker) and platform health rows are never decisions.
EXCLUDED_KINDS = ("control", "platform_health")

# D-07 column map (ledger states).
DONE_STATES = ("executed", "verified")
UNDONE_STATES = ("undone", "rolled_back")
REFUSED_STATES = ("refused", "expired", "cancelled_by_stop")
SHADOW_STATE = "shadow"

# D-08 / D-19: fixed minutes saved per kind of action. Not editable at run time. Only an action that
# really ran (executed or verified) counts; simulations and undone actions add nothing.
MINUTES_PER_KIND = MappingProxyType({
    "isolate_host": 15, "quarantine_file": 15, "restore_file": 15,
    "rotate_key": 20, "rollback_ransomware": 30, "ticket_answer": 8,
    "block_ip": 10, "restart_service": 10, "kill_process": 10, "reboot_host": 10,
    "upgrade_software": 10, "disable_service": 10, "install_patches": 10,
    # Putting something back, a re-scan, and a hand-off to a person save no time of their own.
    "unblock_ip": 0, "enable_service": 0, "unquarantine_file": 0, "restore_host": 0,
    "rotate_key_rollback": 0, "rollback_patches": 0, "ticket_withdraw": 0,
    "scan_file": 0, "scan_ip": 0, "scan_url": 0, "scan_hash": 0,
    "ticket_handoff": 0,
})

# D-10 / D-11: one export is at most this many rows.
EXPORT_ROW_CAP = 5000

# D-01 / D-02 / D-03: the daily digest.
DIGEST_HOUR_UTC = 7
DIGEST_SECTION_CAP = 10
DIGEST_TARGET_CAP = 80

# Collections this package owns.
DIGESTS = "autonomy_digests"
GOLIVE_CHECKS = "autonomy_golive_checks"
GOLIVE_TEST_ORG = "autonomy_golive_test_org"      # D-23: one document, the designated go-live test organization
TEST_ORG_DOC_ID = "current"

# D-14 / D-15: the go-live checklist and the shadow period before it can be lifted.
GOLIVE_CHECK_IDS = ("firewall_round_trip", "reboot_gate", "watchdog_stop_start", "alert_delivery", "live_stop_drill")
SHADOW_DAYS_REQUIRED = 7
NOTE_MIN = 10
NOTE_MAX = 500
