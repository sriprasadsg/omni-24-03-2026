"""Cross-framework mapping data layer — gap #3 from the capability review.

`mitre_service.py` already ships an ATT&CK matrix + coverage heatmap. What was
missing (and is the genuinely useful asset from the Cybersecurity-Skills
catalog) is the *defensive* and *governance* side and the crosswalk between
them:

  * NIST CSF 2.0 — all 6 functions and their categories.
  * MITRE D3FEND — the 6 defensive tactics and representative techniques.
  * An ATT&CK -> D3FEND -> NIST-CSF crosswalk keyed on the technique IDs that
    `mitre_service.ATTACK_MATRIX` already carries, so an offensive technique
    resolves to the countermeasures that mitigate it and the CSF categories
    they satisfy.

Pure data + pure query helpers — no DB, no tenant state — so this is safe to
import anywhere and trivially testable. `map_technique()` is the join point the
threat and compliance surfaces call to turn an ATT&CK id into defensive +
governance context.
"""
from typing import Optional

# --- NIST CSF 2.0 (2024) — 6 functions, 22 categories ----------------------
NIST_CSF_2 = {
    "version": "2.0",
    "functions": [
        {"id": "GV", "name": "Govern", "categories": [
            {"id": "GV.OC", "name": "Organizational Context"},
            {"id": "GV.RM", "name": "Risk Management Strategy"},
            {"id": "GV.RR", "name": "Roles, Responsibilities, and Authorities"},
            {"id": "GV.PO", "name": "Policy"},
            {"id": "GV.OV", "name": "Oversight"},
            {"id": "GV.SC", "name": "Cybersecurity Supply Chain Risk Management"},
        ]},
        {"id": "ID", "name": "Identify", "categories": [
            {"id": "ID.AM", "name": "Asset Management"},
            {"id": "ID.RA", "name": "Risk Assessment"},
            {"id": "ID.IM", "name": "Improvement"},
        ]},
        {"id": "PR", "name": "Protect", "categories": [
            {"id": "PR.AA", "name": "Identity Management, Authentication, and Access Control"},
            {"id": "PR.AT", "name": "Awareness and Training"},
            {"id": "PR.DS", "name": "Data Security"},
            {"id": "PR.PS", "name": "Platform Security"},
            {"id": "PR.IR", "name": "Technology Infrastructure Resilience"},
        ]},
        {"id": "DE", "name": "Detect", "categories": [
            {"id": "DE.CM", "name": "Continuous Monitoring"},
            {"id": "DE.AE", "name": "Adverse Event Analysis"},
        ]},
        {"id": "RS", "name": "Respond", "categories": [
            {"id": "RS.MA", "name": "Incident Management"},
            {"id": "RS.AN", "name": "Incident Analysis"},
            {"id": "RS.CO", "name": "Incident Response Reporting and Communication"},
            {"id": "RS.MI", "name": "Incident Mitigation"},
        ]},
        {"id": "RC", "name": "Recover", "categories": [
            {"id": "RC.RP", "name": "Incident Recovery Plan Execution"},
            {"id": "RC.CO", "name": "Incident Recovery Communication"},
        ]},
    ],
}

_CSF_CATEGORY_NAMES = {
    cat["id"]: cat["name"]
    for fn in NIST_CSF_2["functions"] for cat in fn["categories"]
}

# --- MITRE D3FEND — 6 defensive tactics ------------------------------------
D3FEND_TACTICS = [
    {"id": "D3-M", "name": "Model", "techniques": [
        "Asset Inventory", "Network Mapping", "Data Inventory"]},
    {"id": "D3-H", "name": "Harden", "techniques": [
        "Multi-factor Authentication", "Application Configuration Hardening",
        "Local File Permissions", "Executable Denylisting", "Message Encryption"]},
    {"id": "D3-D", "name": "Detect", "techniques": [
        "Network Traffic Analysis", "Process Spawn Analysis", "Script Execution Analysis",
        "User Behavior Analysis", "File Analysis", "Message Analysis",
        "Authentication Event Thresholding"]},
    {"id": "D3-I", "name": "Isolate", "techniques": [
        "Network Isolation", "Execution Isolation", "Broadcast Domain Isolation"]},
    {"id": "D3-DC", "name": "Deceive", "techniques": [
        "Decoy File", "Decoy Network Resource", "Decoy Credential"]},
    {"id": "D3-E", "name": "Evict", "techniques": [
        "Account Locking", "Process Termination", "Authentication Cache Invalidation"]},
]

_D3FEND_TECHNIQUE_TACTIC = {
    tech: tactic["name"] for tactic in D3FEND_TACTICS for tech in tactic["techniques"]
}

# --- ATT&CK -> D3FEND countermeasures + NIST CSF categories ------------------
# Keyed on technique ids present in mitre_service.ATTACK_MATRIX. Each entry maps
# an offensive technique to the defensive techniques that counter it and the CSF
# categories those countermeasures satisfy.
ATTACK_CROSSWALK = {
    "T1566": {"d3fend": ["Message Analysis", "User Behavior Analysis"], "csf": ["PR.AT", "DE.CM"]},
    "T1078": {"d3fend": ["Multi-factor Authentication", "User Behavior Analysis"], "csf": ["PR.AA", "DE.AE"]},
    "T1110": {"d3fend": ["Multi-factor Authentication", "Authentication Event Thresholding", "Account Locking"], "csf": ["PR.AA", "DE.CM"]},
    "T1059": {"d3fend": ["Script Execution Analysis", "Executable Denylisting"], "csf": ["PR.PS", "DE.CM"]},
    "T1055": {"d3fend": ["Process Spawn Analysis", "Process Termination"], "csf": ["DE.AE", "RS.MI"]},
    "T1068": {"d3fend": ["Application Configuration Hardening", "Local File Permissions"], "csf": ["PR.PS"]},
    "T1547": {"d3fend": ["Process Spawn Analysis", "File Analysis"], "csf": ["DE.CM"]},
    "T1543": {"d3fend": ["Process Spawn Analysis", "Executable Denylisting"], "csf": ["PR.PS", "DE.CM"]},
    "T1003": {"d3fend": ["Local File Permissions", "User Behavior Analysis"], "csf": ["PR.AA", "DE.AE"]},
    "T1558": {"d3fend": ["Authentication Cache Invalidation", "User Behavior Analysis"], "csf": ["PR.AA", "DE.AE"]},
    "T1021": {"d3fend": ["Network Traffic Analysis", "Network Isolation"], "csf": ["PR.IR", "DE.CM"]},
    "T1071": {"d3fend": ["Network Traffic Analysis"], "csf": ["DE.CM"]},
    "T1046": {"d3fend": ["Network Traffic Analysis", "Network Mapping"], "csf": ["ID.AM", "DE.CM"]},
    "T1048": {"d3fend": ["Network Traffic Analysis", "Message Encryption"], "csf": ["PR.DS", "DE.CM"]},
    "T1041": {"d3fend": ["Network Traffic Analysis"], "csf": ["PR.DS", "DE.AE"]},
    "T1567": {"d3fend": ["Network Traffic Analysis"], "csf": ["PR.DS", "DE.CM"]},
    "T1486": {"d3fend": ["File Analysis", "Local File Permissions"], "csf": ["PR.DS", "RC.RP"]},
    "T1490": {"d3fend": ["File Analysis"], "csf": ["RC.RP"]},
    "T1489": {"d3fend": ["Process Termination"], "csf": ["RS.MI"]},
    "T1562": {"d3fend": ["Application Configuration Hardening"], "csf": ["PR.PS", "DE.CM"]},
    "T1070": {"d3fend": ["File Analysis", "User Behavior Analysis"], "csf": ["DE.AE"]},
    "T1550": {"d3fend": ["Multi-factor Authentication", "Authentication Cache Invalidation"], "csf": ["PR.AA"]},
    "T1195": {"d3fend": ["Asset Inventory", "Executable Denylisting"], "csf": ["GV.SC", "ID.AM"]},
    "T1190": {"d3fend": ["Application Configuration Hardening", "Network Traffic Analysis"], "csf": ["PR.PS", "DE.CM"]},
    "T1133": {"d3fend": ["Multi-factor Authentication", "Network Isolation"], "csf": ["PR.AA", "PR.IR"]},
    "T1204": {"d3fend": ["Message Analysis", "Executable Denylisting"], "csf": ["PR.AT", "DE.CM"]},
    "T1053": {"d3fend": ["Process Spawn Analysis"], "csf": ["DE.CM"]},
    "T1548": {"d3fend": ["Local File Permissions", "User Behavior Analysis"], "csf": ["PR.AA", "DE.AE"]},
    "T1105": {"d3fend": ["Network Traffic Analysis", "File Analysis"], "csf": ["DE.CM"]},
}


# --- Query helpers ---------------------------------------------------------
def get_nist_csf() -> dict:
    """Full NIST CSF 2.0 function/category tree."""
    return NIST_CSF_2


def get_d3fend() -> list:
    """MITRE D3FEND defensive tactics and techniques."""
    return D3FEND_TACTICS


def csf_category_name(category_id: str) -> Optional[str]:
    """Human name for a CSF category id, e.g. 'PR.AA' -> 'Identity Management…'."""
    return _CSF_CATEGORY_NAMES.get(category_id)


def d3fend_tactic_for(technique_name: str) -> Optional[str]:
    """The D3FEND tactic a defensive technique belongs to."""
    return _D3FEND_TECHNIQUE_TACTIC.get(technique_name)


def map_technique(attack_id: str) -> dict:
    """Resolve an ATT&CK technique id to its defensive + governance context.

    Returns {attack_id, d3fend: [{technique, tactic}], csf: [{id, name}],
    mapped: bool}. Unknown ids return `mapped=False` with empty lists rather
    than raising — an unmapped technique is a data gap, not an error."""
    entry = ATTACK_CROSSWALK.get((attack_id or "").upper())
    if not entry:
        return {"attack_id": attack_id, "d3fend": [], "csf": [], "mapped": False}
    d3fend = [
        {"technique": t, "tactic": _D3FEND_TECHNIQUE_TACTIC.get(t, "Unknown")}
        for t in entry["d3fend"]
    ]
    csf = [{"id": c, "name": _CSF_CATEGORY_NAMES.get(c, c)} for c in entry["csf"]]
    return {"attack_id": attack_id.upper(), "d3fend": d3fend, "csf": csf, "mapped": True}


def get_crosswalk() -> dict:
    """The full ATT&CK -> D3FEND/CSF crosswalk, resolved to names."""
    return {tid: map_technique(tid) for tid in ATTACK_CROSSWALK}
