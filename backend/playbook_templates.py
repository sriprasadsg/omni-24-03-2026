"""
SOAR Playbook Template Library aggregator.

Templates are split across two modules:
  playbook_templates_incident.py — phishing, malware, ransomware, brute force
  playbook_templates_network.py  — DDoS, data breach, insider threat, credential compromise
"""

from typing import List, Dict, Any

from playbook_templates_incident import (
    phishing_response as _phishing,
    malware_containment as _malware,
    ransomware_recovery as _ransomware,
    brute_force_response as _brute_force,
)
from playbook_templates_network import (
    ddos_mitigation as _ddos,
    data_breach_response as _data_breach,
    insider_threat_investigation as _insider_threat,
    credential_compromise as _credential,
)


class PlaybookTemplateLibrary:
    """Library of pre-built SOAR playbook templates."""

    @staticmethod
    def phishing_response() -> Dict[str, Any]:
        return _phishing()

    @staticmethod
    def malware_containment() -> Dict[str, Any]:
        return _malware()

    @staticmethod
    def ddos_mitigation() -> Dict[str, Any]:
        return _ddos()

    @staticmethod
    def data_breach_response() -> Dict[str, Any]:
        return _data_breach()

    @staticmethod
    def insider_threat_investigation() -> Dict[str, Any]:
        return _insider_threat()

    @staticmethod
    def ransomware_recovery() -> Dict[str, Any]:
        return _ransomware()

    @staticmethod
    def brute_force_response() -> Dict[str, Any]:
        return _brute_force()

    @staticmethod
    def credential_compromise() -> Dict[str, Any]:
        return _credential()

    @staticmethod
    def get_all_templates() -> List[Dict[str, Any]]:
        return [
            _phishing(), _malware(), _ddos(), _data_breach(),
            _insider_threat(), _ransomware(), _brute_force(), _credential(),
        ]


async def initialize_playbook_templates(db):
    """Seed the database with all built-in playbook templates."""
    for template in PlaybookTemplateLibrary.get_all_templates():
        existing = await db.playbooks.find_one({"name": template["name"], "is_template": True})
        if not existing:
            await db.playbooks.insert_one(template)
