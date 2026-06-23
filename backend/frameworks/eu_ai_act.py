"""EU AI Act (Regulation 2024/1689) — High-Risk AI System Requirements."""
from __future__ import annotations
from typing import Any, Dict, List
from ._db_eval import evaluate_from_db

FRAMEWORK_ID = "eu_ai_act"
FRAMEWORK_NAME = "EU AI Act (Regulation 2024/1689)"
FRAMEWORK_VERSION = "2024"

CONTROLS: List[Dict[str, Any]] = [
    # Article 9 — Risk Management System
    {"id": "AIA-9.1", "title": "Risk Management System — Establishment",
     "description": "Establish, implement, document and maintain a risk management system for high-risk AI systems throughout the entire lifecycle.",
     "article": "Article 9(1)", "category": "Risk Management", "required": True},
    {"id": "AIA-9.2", "title": "Risk Management System — Continuous Iteration",
     "description": "The risk management system shall be an iterative process run throughout the entire lifecycle of a high-risk AI system.",
     "article": "Article 9(2)", "category": "Risk Management", "required": True},
    {"id": "AIA-9.4", "title": "Risk Management — Residual Risk Mitigation",
     "description": "Identify and analyse known and foreseeable risks. Adopt suitable risk management measures eliminating or reducing risks to the extent possible.",
     "article": "Article 9(4)", "category": "Risk Management", "required": True},
    {"id": "AIA-9.7", "title": "Risk Management — Testing",
     "description": "High-risk AI systems shall be tested for the purpose of identifying the most appropriate risk management measures.",
     "article": "Article 9(7)", "category": "Risk Management", "required": True},

    # Article 10 — Data Governance
    {"id": "AIA-10.1", "title": "Training Data Governance",
     "description": "Training, validation and testing data sets shall be subject to appropriate data governance and management practices.",
     "article": "Article 10(1)", "category": "Data Governance", "required": True},
    {"id": "AIA-10.2", "title": "Data Relevance and Representativeness",
     "description": "Training data sets shall be relevant, sufficiently representative, and to the best extent possible free of errors and complete.",
     "article": "Article 10(2)", "category": "Data Governance", "required": True},
    {"id": "AIA-10.3", "title": "Data Quality Metrics",
     "description": "Examine data sets for possible biases that could affect health, safety or fundamental rights.",
     "article": "Article 10(3)", "category": "Data Governance", "required": True},
    {"id": "AIA-10.5", "title": "Special Category Data Controls",
     "description": "Special category personal data processed for bias monitoring shall be subject to appropriate safeguards.",
     "article": "Article 10(5)", "category": "Data Governance", "required": True},

    # Article 11 — Technical Documentation
    {"id": "AIA-11.1", "title": "Technical Documentation — Pre-market",
     "description": "Technical documentation shall be drawn up before the high-risk AI system is placed on the market and kept up to date.",
     "article": "Article 11(1)", "category": "Technical Documentation", "required": True},
    {"id": "AIA-11.2", "title": "Technical Documentation — Annex IV Coverage",
     "description": "Technical documentation shall contain the information set out in Annex IV: system description, design specs, development process, validation results.",
     "article": "Article 11(2)", "category": "Technical Documentation", "required": True},

    # Article 12 — Record-keeping / Automatic Logging
    {"id": "AIA-12.1", "title": "Automatic Logging Capability",
     "description": "High-risk AI systems shall technically allow for the automatic recording of events (logs) over the system's lifetime.",
     "article": "Article 12(1)", "category": "Record-Keeping", "required": True},
    {"id": "AIA-12.2", "title": "Log Retention",
     "description": "Logging capabilities shall ensure a level of traceability of the AI system's functioning for the duration appropriate to the intended purpose.",
     "article": "Article 12(2)", "category": "Record-Keeping", "required": True},
    {"id": "AIA-12.4", "title": "Automatic Event Logging — High-Risk",
     "description": "For high-risk AI systems in credit scoring, biometric identification: logs shall cover period of use. Deployers retain logs for minimum 6 months.",
     "article": "Article 12(4)", "category": "Record-Keeping", "required": True},

    # Article 13 — Transparency and Information to Deployers
    {"id": "AIA-13.1", "title": "Transparency to Deployers",
     "description": "High-risk AI systems shall be designed and developed in such a way to ensure sufficient transparency to enable deployers to interpret outputs and use them appropriately.",
     "article": "Article 13(1)", "category": "Transparency", "required": True},
    {"id": "AIA-13.3", "title": "Instructions for Use",
     "description": "Instructions for use shall include: identity of provider, capabilities and limitations, performance levels, expected outputs, human oversight measures, computational resource requirements.",
     "article": "Article 13(3)", "category": "Transparency", "required": True},

    # Article 14 — Human Oversight
    {"id": "AIA-14.1", "title": "Human Oversight — Design",
     "description": "High-risk AI systems shall be designed and developed with human oversight capability to minimise risks and enable effective oversight by natural persons.",
     "article": "Article 14(1)", "category": "Human Oversight", "required": True},
    {"id": "AIA-14.3", "title": "Human Oversight — Interface",
     "description": "Humans to whom oversight is assigned shall be able to understand relevant AI capabilities and limitations; detect anomalies, dysfunctions and unexpected performance; and disregard, override or reverse AI outputs.",
     "article": "Article 14(3)", "category": "Human Oversight", "required": True},
    {"id": "AIA-14.4", "title": "Automatic Override Stop",
     "description": "Where AI systems operate with a degree of autonomy, enable the natural person to intervene or interrupt the system through a 'stop' button or similar procedure.",
     "article": "Article 14(4)", "category": "Human Oversight", "required": True},

    # Article 15 — Accuracy, Robustness and Cybersecurity
    {"id": "AIA-15.1", "title": "Accuracy Performance Levels",
     "description": "High-risk AI systems shall achieve appropriate levels of accuracy, robustness and cybersecurity, and perform consistently in those respects throughout their lifecycle.",
     "article": "Article 15(1)", "category": "Accuracy & Robustness", "required": True},
    {"id": "AIA-15.3", "title": "Resilience to Errors",
     "description": "High-risk AI systems shall be resilient as regards errors, faults or inconsistencies that may occur within the system or its environment.",
     "article": "Article 15(3)", "category": "Accuracy & Robustness", "required": True},
    {"id": "AIA-15.4", "title": "Adversarial Robustness",
     "description": "Technical robustness measures against attempts to alter the use, outputs or performance of high-risk AI systems through adversarial attacks exploiting system vulnerabilities.",
     "article": "Article 15(4)", "category": "Accuracy & Robustness", "required": True},

    # Article 16 — Obligations of Providers
    {"id": "AIA-16.a", "title": "Quality Management System",
     "description": "Providers shall put in place a quality management system pursuant to Article 17.",
     "article": "Article 16(a)", "category": "Provider Obligations", "required": True},
    {"id": "AIA-16.b", "title": "Technical Documentation Maintenance",
     "description": "Draw up technical documentation of the high-risk AI system in accordance with Article 11 and Annex IV.",
     "article": "Article 16(b)", "category": "Provider Obligations", "required": True},
    {"id": "AIA-16.f", "title": "Conformity Assessment",
     "description": "Carry out the conformity assessment procedure in accordance with Article 43 prior to placing the AI system on the market.",
     "article": "Article 16(f)", "category": "Provider Obligations", "required": True},

    # Article 17 — Quality Management System
    {"id": "AIA-17.1", "title": "QMS Written Policies",
     "description": "Providers shall put in place a quality management system covering: compliance strategy, design control and verification, testing, post-market monitoring, incident reporting.",
     "article": "Article 17(1)", "category": "Quality Management", "required": True},

    # Article 26 — Obligations of Deployers
    {"id": "AIA-26.1", "title": "Deployer — Intended Purpose",
     "description": "Deployers shall take appropriate technical and organisational measures to ensure they use high-risk AI systems in accordance with the instructions for use.",
     "article": "Article 26(1)", "category": "Deployer Obligations", "required": True},
    {"id": "AIA-26.5", "title": "Deployer — Human Oversight Assignment",
     "description": "Deployers shall assign the task of human oversight to natural persons who have the necessary competence, training and authority.",
     "article": "Article 26(5)", "category": "Deployer Obligations", "required": True},
    {"id": "AIA-26.6", "title": "Deployer — Fundamental Rights Impact Assessment",
     "description": "Before deploying certain high-risk AI systems, carry out a fundamental rights impact assessment.",
     "article": "Article 26(6)", "category": "Deployer Obligations", "required": False},

    # Article 53 — GPAI Models
    {"id": "AIA-53.1", "title": "GPAI Model — Technical Documentation",
     "description": "Providers of general-purpose AI models shall draw up and keep up to date technical documentation for the model.",
     "article": "Article 53(1)(a)", "category": "GPAI Models", "required": False},
    {"id": "AIA-53.2", "title": "GPAI Model — Copyright Policy",
     "description": "Put in place a policy to comply with Union copyright law, including implementing a rights reservation mechanism under Article 4(3) of Directive 2019/790.",
     "article": "Article 53(1)(c)", "category": "GPAI Models", "required": False},

    # Article 62 — Reporting of Serious Incidents
    {"id": "AIA-62.1", "title": "Serious Incident Reporting",
     "description": "Providers of high-risk AI systems placed on the Union market shall report serious incidents to market surveillance authorities of Member States.",
     "article": "Article 62(1)", "category": "Incident Reporting", "required": True},
    {"id": "AIA-62.3", "title": "Incident Reporting Timeline",
     "description": "Providers shall report immediately and in any event not later than 15 days after becoming aware of any serious incident.",
     "article": "Article 62(3)", "category": "Incident Reporting", "required": True},
]


async def evaluate_controls(db) -> List[Dict[str, Any]]:
    """Evaluate EU AI Act controls with AI governance evidence from DB."""
    results = await evaluate_from_db(db, "eu_ai_act")

    ai_gov_count = await db.ai_governance_assessments.count_documents({})
    risk_count = await db.ai_risk_assessments.count_documents({})
    log_count = await db.audit_logs.count_documents({})

    for r in results:
        category = r.get("category", "")
        if category == "Risk Management" and risk_count > 0:
            r["status"] = "pass"
            r["evidence"] = f"{risk_count} AI risk assessment(s) on record"
        elif category == "Record-Keeping" and log_count > 50:
            r["status"] = "pass"
            r["evidence"] = f"{log_count} audit log entries"
        elif category in ("Provider Obligations", "Deployer Obligations") and ai_gov_count > 0:
            r["status"] = "partial"
            r["evidence"] = f"{ai_gov_count} AI governance assessment(s) on record"
    return results
