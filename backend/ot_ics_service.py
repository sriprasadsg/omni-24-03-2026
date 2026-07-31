"""OT / ICS security assessment + reference — gap #4 from the capability review.

Scoped deliberately as GRC content, not live protocol scanning: reaching real
Modbus/DNP3 gear needs OT-network access this platform does not have, and
faking a scan would be dishonest. Instead this provides the assessment
substrate a compliance product needs:

  * IEC 62443 security levels (SL 0-4) and the zone/conduit model.
  * The Purdue Enterprise Reference Architecture levels (0-5, incl. the 3.5
    DMZ) used to classify ICS assets.
  * A risk reference for the common ICS protocols (Modbus, DNP3, OPC-UA,
    EtherNet/IP, PROFINET, BACnet) — default port, native auth/encryption
    posture, and key risks.
  * `assess_asset(...)` — turns an OT asset descriptor (protocols, Purdue
    level, internet exposure) into risk findings mapped to IEC 62443 and, via
    framework_mappings_service, to NIST CSF categories.

Pure data + pure functions; no OT network I/O.
"""
from typing import Optional

import framework_mappings_service as fm

# --- IEC 62443 security levels ---------------------------------------------
IEC_62443_SECURITY_LEVELS = [
    {"sl": 0, "name": "No specific protection", "protects_against": "No requirement"},
    {"sl": 1, "name": "Casual/coincidental violation", "protects_against": "Casual or accidental misuse"},
    {"sl": 2, "name": "Intentional — low resources", "protects_against": "Simple means, low motivation"},
    {"sl": 3, "name": "Intentional — moderate resources", "protects_against": "Sophisticated means, ICS-specific skills"},
    {"sl": 4, "name": "Intentional — extended resources", "protects_against": "Nation-state, extended resources"},
]

# --- Purdue model levels ---------------------------------------------------
PURDUE_LEVELS = [
    {"level": "0", "name": "Physical Process", "zone": "Cell/Area"},
    {"level": "1", "name": "Basic Control (PLC/RTU)", "zone": "Cell/Area"},
    {"level": "2", "name": "Area Supervisory (HMI/SCADA)", "zone": "Cell/Area"},
    {"level": "3", "name": "Site Operations (Historian/MES)", "zone": "Manufacturing"},
    {"level": "3.5", "name": "Industrial DMZ", "zone": "IDMZ"},
    {"level": "4", "name": "Site Business Planning", "zone": "Enterprise"},
    {"level": "5", "name": "Enterprise Network", "zone": "Enterprise"},
]
_PURDUE_VALID = {p["level"] for p in PURDUE_LEVELS}

# --- ICS protocol risk reference -------------------------------------------
ICS_PROTOCOLS = {
    "modbus": {"name": "Modbus TCP", "port": 502, "native_auth": False, "native_encryption": False,
               "risks": ["No authentication", "No encryption", "Unauthenticated write to coils/registers"]},
    "dnp3": {"name": "DNP3", "port": 20000, "native_auth": False, "native_encryption": False,
             "risks": ["Auth only via Secure Authentication extension (rarely enabled)", "Spoofable control commands"]},
    "opcua": {"name": "OPC-UA", "port": 4840, "native_auth": True, "native_encryption": True,
              "risks": ["Often deployed in 'None' security mode", "Certificate management gaps"]},
    "ethernetip": {"name": "EtherNet/IP (CIP)", "port": 44818, "native_auth": False, "native_encryption": False,
                   "risks": ["No authentication", "CIP object manipulation", "Stop-CPU commands"]},
    "profinet": {"name": "PROFINET", "port": 34962, "native_auth": False, "native_encryption": False,
                 "risks": ["No authentication", "Layer-2 exposure", "DCP device reconfiguration"]},
    "bacnet": {"name": "BACnet/IP", "port": 47808, "native_auth": False, "native_encryption": False,
               "risks": ["No authentication", "Write-property to building controllers", "Device spoofing"]},
}


def get_reference() -> dict:
    """All OT/ICS reference taxonomies in one payload."""
    return {
        "iec_62443_security_levels": IEC_62443_SECURITY_LEVELS,
        "purdue_levels": PURDUE_LEVELS,
        "ics_protocols": ICS_PROTOCOLS,
    }


def _severity(purdue_level: str, internet_exposed: bool) -> str:
    """Lower Purdue levels (closer to the physical process) and any internet
    exposure raise the severity of an unauthenticated-protocol finding."""
    if internet_exposed:
        return "critical"
    if purdue_level in ("0", "1", "2"):
        return "high"
    return "medium"


def assess_asset(
    protocols: Optional[list] = None,
    purdue_level: str = "2",
    internet_exposed: bool = False,
) -> dict:
    """Assess one OT asset descriptor into IEC 62443 / NIST CSF findings.

    `protocols` is a list of protocol keys (see ICS_PROTOCOLS). Unknown keys
    are reported as such rather than dropped. Returns findings plus a rolled-up
    max severity and the distinct NIST CSF categories the findings touch."""
    protocols = protocols or []
    level = purdue_level if purdue_level in _PURDUE_VALID else "2"
    findings = []
    csf_categories: set = set()
    rank = {"medium": 1, "high": 2, "critical": 3}
    max_sev = None

    for key in protocols:
        proto = ICS_PROTOCOLS.get(str(key).lower())
        if not proto:
            findings.append({"protocol": key, "severity": "info",
                             "issue": "Unknown/unsupported protocol — manual review", "csf": []})
            continue
        if not proto["native_auth"] or internet_exposed:
            sev = _severity(level, internet_exposed)
            # unauthenticated control protocol -> Protect/Detect concerns
            csf = ["PR.AA", "PR.IR", "DE.CM"] if internet_exposed else ["PR.AA", "DE.CM"]
            csf_categories.update(csf)
            findings.append({
                "protocol": proto["name"],
                "port": proto["port"],
                "severity": sev,
                "issue": "; ".join(proto["risks"]),
                "iec_62443_recommendation": "Place in a segmented zone with a conduit firewall; "
                                            "target SL 2+ via compensating controls (no native auth).",
                "csf": [{"id": c, "name": fm.csf_category_name(c) or c} for c in csf],
            })
            if max_sev is None or rank[sev] > rank[max_sev]:
                max_sev = sev

    return {
        "purdue_level": level,
        "internet_exposed": internet_exposed,
        "max_severity": max_sev or "none",
        "finding_count": len(findings),
        "csf_categories": sorted(csf_categories),
        "findings": findings,
    }
