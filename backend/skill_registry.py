"""Skill registry — defines all /slash commands available in the AI chat assistant."""
from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class SkillParam:
    name: str
    description: str
    required: bool = False


@dataclass
class Skill:
    name: str
    description: str
    usage: str
    params: List[SkillParam] = field(default_factory=list)
    category: str = "general"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "usage": self.usage,
            "category": self.category,
            "params": [{"name": p.name, "description": p.description, "required": p.required} for p in self.params],
        }


SKILLS: List[Skill] = [
    Skill("help", "List all available skills", "/help", category="general"),
    Skill(
        "agents",
        "Show agent fleet status (online / offline counts)",
        "/agents",
        category="agents",
    ),
    Skill(
        "alerts",
        "Show recent security alerts",
        "/alerts [critical|high|medium|low]",
        category="security",
    ),
    Skill(
        "vulnerabilities",
        "List top vulnerabilities by severity",
        "/vulnerabilities [critical|high|medium]",
        category="security",
    ),
    Skill(
        "compliance",
        "Show compliance posture summary",
        "/compliance [framework]",
        category="compliance",
    ),
    Skill(
        "scan",
        "Dispatch a security scan to all online agents",
        "/scan [target]",
        category="operations",
    ),
    Skill(
        "threat-hunt",
        "Translate a natural-language query into a threat hunt",
        "/threat-hunt <query>",
        params=[SkillParam("query", "e.g. failed SSH logins last 24 h", required=True)],
        category="security",
    ),
    Skill(
        "playbook",
        "Generate a security playbook for a scenario",
        "/playbook <scenario>",
        params=[SkillParam("scenario", "e.g. ransomware outbreak response", required=True)],
        category="security",
    ),
    Skill(
        "summarize",
        "Ask the AI to summarize the current page",
        "/summarize",
        category="analysis",
    ),
    Skill(
        "patch-status",
        "Show patch deployment status and overdue patches",
        "/patch-status [critical|high|overdue]",
        category="operations",
    ),
    Skill(
        "software-outdated",
        "List outdated software packages across assets",
        "/software-outdated [pip|npm|apt]",
        category="operations",
    ),
    Skill(
        "vendor-risk",
        "Show vendor risk scores and portfolio summary",
        "/vendor-risk [vendor-name]",
        category="security",
    ),
    Skill(
        "assets",
        "Show asset inventory counts and recent discoveries",
        "/assets [os] e.g. /assets Linux",
        category="inventory",
    ),
    Skill(
        "tickets",
        "Show recent incident tickets and ticketing config status",
        "/tickets [open|closed]",
        category="operations",
    ),
    Skill(
        "approvals",
        "List pending approval requests",
        "/approvals",
        category="operations",
    ),
    Skill(
        "dr-status",
        "Show disaster recovery and HA/DR health summary",
        "/dr-status",
        category="operations",
    ),
    Skill(
        "maintenance",
        "Show active and upcoming maintenance windows",
        "/maintenance",
        category="operations",
    ),
    Skill(
        "knowledge-search",
        "Search the knowledge base for articles and playbooks",
        "/knowledge-search <query>",
        params=[SkillParam("query", "e.g. ransomware containment", required=True)],
        category="analysis",
    ),
    Skill(
        "users",
        "Show active users, roles, and last login times",
        "/users [role]",
        category="general",
    ),
    Skill(
        "risk-register",
        "Show open risks by severity and owner",
        "/risk-register [open|accepted|mitigated]",
        category="security",
    ),
    Skill(
        "cost-snapshot",
        "Show cloud spend summary and top cost drivers",
        "/cost-snapshot",
        category="analysis",
    ),
]

SKILL_MAP: Dict[str, Skill] = {s.name: s for s in SKILLS}
