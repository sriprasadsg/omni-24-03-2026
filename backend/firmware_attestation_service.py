"""Hardware/firmware attestation posture — gap #5 from the capability review.

`firmware_driver_service.py` tracks BIOS/UEFI *versions* (inventory). This adds
the *attestation posture* dimension that was missing — the CHIPSEC/UEFI/TPM
side of the Cybersecurity-Skills catalog — as an assessment over a per-asset
firmware/hardware descriptor:

  * Secure Boot, UEFI (vs legacy CSM), firmware password.
  * TPM presence and TPM 2.0, Measured Boot (PCR quote), Boot Guard.
  * DMA protection (IOMMU / VT-d / DMAr) against evil-maid DMA attacks.

Each failed check carries a severity and a NIST CSF category (mostly PR.PS
Platform Security) resolved via framework_mappings_service. Pure data + pure
functions — the descriptor comes from an agent's collected evidence upstream;
this module does not itself touch hardware.
"""
from typing import Optional

import framework_mappings_service as fm

# Each check: descriptor key -> requirement. `desired` is the secure value.
ATTESTATION_CHECKS = [
    {"key": "secure_boot", "name": "UEFI Secure Boot enabled", "desired": True,
     "severity": "high", "csf": "PR.PS",
     "remediation": "Enable Secure Boot in firmware; enroll only trusted keys."},
    {"key": "uefi_mode", "name": "Booting in UEFI mode (not legacy/CSM)", "desired": True,
     "severity": "medium", "csf": "PR.PS",
     "remediation": "Disable CSM/legacy boot; migrate to UEFI native boot."},
    {"key": "tpm_present", "name": "TPM present", "desired": True,
     "severity": "high", "csf": "PR.PS",
     "remediation": "Enable the discrete/firmware TPM in firmware settings."},
    {"key": "tpm_2_0", "name": "TPM 2.0 (not 1.2)", "desired": True,
     "severity": "medium", "csf": "PR.PS",
     "remediation": "Upgrade to a TPM 2.0 module or firmware TPM."},
    {"key": "measured_boot", "name": "Measured Boot / PCR quote available", "desired": True,
     "severity": "high", "csf": "DE.CM",
     "remediation": "Enable Measured Boot and collect PCR quotes for remote attestation."},
    {"key": "boot_guard", "name": "Intel Boot Guard / AMD equivalent active", "desired": True,
     "severity": "medium", "csf": "PR.PS",
     "remediation": "Provision hardware verified-boot fusing on supported platforms."},
    {"key": "dma_protection", "name": "DMA protection (IOMMU/VT-d) enabled", "desired": True,
     "severity": "high", "csf": "PR.PS",
     "remediation": "Enable IOMMU/VT-d and kernel DMA protection to block evil-maid DMA."},
    {"key": "firmware_password", "name": "Firmware/BIOS admin password set", "desired": True,
     "severity": "medium", "csf": "PR.AA",
     "remediation": "Set a firmware administrator password to prevent unauthorized changes."},
]

_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def get_checks() -> list:
    """The attestation check catalog (posture requirements)."""
    return ATTESTATION_CHECKS


def assess_posture(descriptor: Optional[dict] = None) -> dict:
    """Assess a firmware/hardware descriptor against the attestation checks.

    `descriptor` maps check keys to observed booleans; a MISSING key is treated
    as 'unknown' and reported separately (never silently assumed secure). A key
    whose value differs from `desired` is a failed check. Returns per-check
    results, the distinct NIST CSF categories touched by failures, a rolled-up
    max severity, and a simple 0-100 posture score."""
    descriptor = descriptor or {}
    failed, unknown, passed = [], [], []
    csf_categories: set = set()
    max_sev = None

    for check in ATTESTATION_CHECKS:
        key = check["key"]
        if key not in descriptor:
            unknown.append({"key": key, "name": check["name"]})
            continue
        observed = bool(descriptor[key])
        if observed == check["desired"]:
            passed.append(key)
            continue
        csf_categories.add(check["csf"])
        failed.append({
            "key": key,
            "name": check["name"],
            "severity": check["severity"],
            "remediation": check["remediation"],
            "csf": {"id": check["csf"], "name": fm.csf_category_name(check["csf"]) or check["csf"]},
        })
        if max_sev is None or _RANK[check["severity"]] > _RANK[max_sev]:
            max_sev = check["severity"]

    scored = len(passed) + len(failed)  # unknowns excluded from the score denominator
    score = round(100 * len(passed) / scored) if scored else 0

    return {
        "posture_score": score,
        "max_severity": max_sev or "none",
        "passed": passed,
        "failed": failed,
        "unknown": unknown,
        "csf_categories": sorted(csf_categories),
    }
