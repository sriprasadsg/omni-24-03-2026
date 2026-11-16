"""Every compliance check the shipping Rust agent sends reaches the controls it proves.

Value: protects=agent evidence landing on its controls (BitLocker on HIPAA 164.312(a)(2)(iv), PCI-3.4 and A.8.24);
fails_when=the agent sends a check name that COMPLIANCE_CHECK_MAPPINGS does not know (the processor matches names
exactly and drops the rest silently), or a renamed check maps to other controls than its older name;
no_claim=whether each agent check measures its setting correctly.
"""
import asyncio
import os
import re
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compliance_evidence_processor import COMPLIANCE_CHECK_MAPPINGS, process_automated_evidence  # noqa: E402

AGENT_SOURCE = os.path.join(os.path.dirname(__file__), "..", "..", "agent-install", "omni-agent-rs", "src",
                            "capabilities", "compliance.rs")

# Names the 2.1.x agent sends, and the older name of the same check whose controls they must share.
RENAMED = {
    "User Account Control (UAC)": "User Access Control",
    "BitLocker Drive Encryption": "BitLocker Encryption",
    "Windows Automatic Updates": "Automatic Updates",
    "RDP Network Level Authentication": "RDP NLA Required",
    "TLS 1.0 Disabled": "TLS Security Configuration",
}


def _agent_check_names():
    with open(AGENT_SOURCE, encoding="utf-8") as fh:
        return re.findall(r'"check":\s*"([^"]+)"', fh.read())


def test_the_agent_source_is_read():
    names = _agent_check_names()
    assert len(names) >= 14, names
    assert "BitLocker Drive Encryption" in names


def test_every_check_name_the_agent_sends_maps_to_controls():
    missing = [name for name in _agent_check_names() if not COMPLIANCE_CHECK_MAPPINGS.get(name)]
    assert not missing, f"agent checks the processor would drop: {missing}"


def test_a_renamed_check_keeps_the_controls_of_its_older_name():
    for new, old in RENAMED.items():
        assert COMPLIANCE_CHECK_MAPPINGS.get(new) == COMPLIANCE_CHECK_MAPPINGS[old], new


def test_a_passing_bitlocker_check_reaches_the_encryption_controls():
    db = MagicMock()
    db.asset_compliance.update_one = AsyncMock()
    db.assets.find_one = AsyncMock(return_value=None)
    db.agents.find_one = AsyncMock(return_value=None)
    data = {"compliance_checks": [
        {"check": "BitLocker Drive Encryption", "status": "Pass", "details": "System drive is BitLocker protected"}]}
    with patch("compliance_evidence_processor.set_tenant_id"), \
            patch("compliance_evidence_processor.get_tenant_id", return_value=None):
        asyncio.run(process_automated_evidence("host-1", data, db, agent_type="rust", fallback_tenant_id="t1"))
    written = {args[0]["controlId"]: args[1]["$set"]["status"]
               for args, _ in db.asset_compliance.update_one.call_args_list if "$set" in args[1]}
    for control in ("164.312(a)(2)(iv)", "PCI-3.4", "A.8.24", "SC-28"):
        assert written.get(control) == "Compliant", (control, written)
