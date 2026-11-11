"""One home for the reasons a new enrollment is held Pending, with the text each one shows.

Two texts per reason: the one the tenant's admins and platform staff read in the notice
(``reason_text``) and the refusal an older agent build, which cannot take a 202 pending answer, gets
as a 403 (``refusal_text``). Keep the codes in step with components/PendingAgentsPanel.tsx REASONS.
"""
from typing import Any, Dict, Optional

REASON_SEAT_LIMIT = "seat_limit"
REASON_DUPLICATE_HARDWARE = "duplicate_hardware_id"
REASON_EXPIRED = "license_expired"
REASON_TRIAL_ENDED = "trial_ended"
REASON_NOT_ALLOWLISTED = "not_allowlisted"
REASON_KEY_EXHAUSTED = "key_exhausted"
REASON_NEW_NETWORK = "new_network"
REASON_CROSS_TENANT = "cross_tenant_duplicate"

REFUSAL_TEXT = {
    REASON_SEAT_LIMIT: "Agent limit reached ({limit}). This computer is waiting for approval by your provider; "
                       "it will connect once approved.",
    REASON_DUPLICATE_HARDWARE: "duplicate_hardware_id: this machine is already enrolled as another agent that was "
                               "seen in the last 24 hours. It is waiting for approval.",
    REASON_TRIAL_ENDED: "trial_ended: the free trial of this organization has ended. This computer is waiting for "
                        "approval by your provider.",
    REASON_NEW_NETWORK: "new_network: this computer enrolled from a network this organization has not used before. "
                        "It is waiting for platform approval.",
    REASON_CROSS_TENANT: "cross_tenant_duplicate: this computer is enrolled in another organization. It is waiting "
                         "for platform approval.",
}

REASON_TEXT = {
    REASON_SEAT_LIMIT: "the tenant has no free agent seat",
    REASON_DUPLICATE_HARDWARE: "this machine is already enrolled as another agent that is still active",
    REASON_NOT_ALLOWLISTED: "the machine is not on the tenant's hardware allowlist",
    REASON_KEY_EXHAUSTED: "its install key is used up, expired or revoked",
    REASON_EXPIRED: "the tenant's agent license has expired",
    REASON_TRIAL_ENDED: "the organization's free trial has ended",
    REASON_NEW_NETWORK: "it enrolled from a new network {ip}, waiting for platform approval",
    # D-36: the only text a tenant sees; it names no other organization
    REASON_CROSS_TENANT: "this computer is enrolled in another organization; waiting for platform approval",
}


def reason_text(reason: Optional[str], agent: Optional[Dict[str, Any]] = None) -> str:
    """What a notice says about a hold; a new-network hold names the address the server observed."""
    if reason and reason.startswith("sublimit:"):
        return f"the {reason[len('sublimit:'):]} sub-limit is full"
    text = REASON_TEXT.get(reason or "", reason or "unknown")
    if reason == REASON_NEW_NETWORK:
        return text.format(ip=(agent or {}).get("sourceIp") or "unknown address")
    return text


def refusal_text(reason: Optional[str], limit: Any) -> str:
    """The 403 detail an older agent build receives for a held enrollment."""
    return REFUSAL_TEXT.get(reason or "", reason or "").format(limit=limit)
