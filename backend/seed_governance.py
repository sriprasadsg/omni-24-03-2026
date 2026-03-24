import asyncio
import uuid
from datetime import datetime, timezone
from database import connect_to_mongo, close_mongo_connection, get_database

async def seed_governance():
    await connect_to_mongo()
    db = get_database()
    
    print("🌱 Seeding Governance, Risk, and Vendor Data...")

    # 1. Seed Risks
    risks = [
        {
            "id": "risk-1",
            "title": "Unauthenticated API Access",
            "description": "Potential for unauthorized parties to access sensitive management endpoints.",
            "category": "Cyber",
            "status": "Mitigated",
            "likelihood": 4,
            "impact": 5,
            "risk_score": 20,
            "owner": "Security Team",
            "mitigation_plan": "Implemented JWT authentication and RBAC across all endpoints.",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": "risk-2",
            "title": "Cloud Misconfiguration",
            "description": "Exposed S3 buckets or open security groups in AWS environment.",
            "category": "Enterprise",
            "status": "Open",
            "likelihood": 2,
            "impact": 4,
            "risk_score": 8,
            "owner": "Cloud Ops",
            "mitigation_plan": "Running daily CSPM scans and automated remediation scripts.",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": "risk-3",
            "title": "AI Model Bias",
            "description": "Predictive health models showing bias in hardware failure predictions for specific vendors.",
            "category": "AI",
            "status": "In Progress",
            "likelihood": 3,
            "impact": 3,
            "risk_score": 9,
            "owner": "Data Science",
            "mitigation_plan": "Implementing fairness auditing and diverse training datasets.",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
    ]

    for risk in risks:
        await db.risks.update_one({"id": risk["id"]}, {"$set": risk}, upsert=True)
    print(f"✅ Seeded {len(risks)} Risks")

    # 2. Seed Vendors
    vendors = [
        {
            "id": "vendor-1",
            "name": "CloudServices Inc.",
            "website": "https://cloudservices.example.com",
            "criticality": "Critical",
            "category": "SaaS",
            "contact_name": "Jane Doe",
            "contact_email": "jane@cloudservices.example.com",
            "contract_start": "2025-01-01",
            "contract_end": "2026-01-01",
            "status": "Active",
            "assessments": [
                {
                    "id": str(uuid.uuid4()),
                    "vendor_id": "vendor-1",
                    "assessment_date": "2025-02-15",
                    "reviewer": "Security Lead",
                    "risk_score": 85,
                    "status": "Completed",
                    "questionnaire_responses": {"mfa": "Yes", "encryption": "AES-256"},
                    "findings": ["SOC2 report valid until 2026"]
                }
            ]
        },
        {
            "id": "vendor-2",
            "name": "Legacy Hardware Corp",
            "website": "https://legacyhq.example.com",
            "criticality": "Medium",
            "category": "Hardware",
            "contact_name": "John Smith",
            "contact_email": "john@legacyhq.example.com",
            "contract_start": "2024-06-01",
            "contract_end": "2027-06-01",
            "status": "Active",
            "assessments": []
        }
    ]

    for vendor in vendors:
        await db.vendors.update_one({"id": vendor["id"]}, {"$set": vendor}, upsert=True)
    print(f"✅ Seeded {len(vendors)} Vendors")

    # 3. Seed Trust Center Data
    profile = {
        "company_name": "Omni-Agent Corp",
        "description": "Leading provider of AI-driven enterprise security solutions.",
        "contact_email": "security@omni-agent.com",
        "logo_url": "/logo.png",
        "compliance_frameworks": ["SOC2", "ISO 27001", "GDPR", "HIPAA"],
        "public_documents": [
            {"name": "Security Whitepaper", "url": "/docs/whitepaper.pdf"},
            {"name": "Privacy Policy", "url": "/docs/privacy.pdf"}
        ],
        "private_documents": [
            {"name": "SOC2 Type II Report (2025)", "url": "/docs/soc2-2025.pdf"},
            {"name": "Penetration Test Result (Q3 2025)", "url": "/docs/pentest-q3.pdf"}
        ]
    }
    await db.trust_profile.update_one({}, {"$set": profile}, upsert=True)
    
    request = {
        "id": "req-1",
        "requester_email": "auditor@bigfirm.com",
        "company": "Big Audit Firm",
        "reason": "Annual Audit",
        "status": "Pending",
        "requested_at": datetime.now(timezone.utc).isoformat()
    }
    await db.trust_requests.update_one({"id": request["id"]}, {"$set": request}, upsert=True)
    print("✅ Seeded Trust Center data")

    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(seed_governance())
