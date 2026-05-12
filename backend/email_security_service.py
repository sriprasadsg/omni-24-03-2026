"""Email Security Service — phishing detection, DMARC/SPF/DKIM, threat analysis."""
from datetime import datetime, timedelta, timezone
import uuid


THREAT_TYPES = ["phishing", "spear_phishing", "malware_attachment", "bec", "spam", "credential_harvesting"]
VERDICTS = ["clean", "clean", "clean", "suspicious", "malicious", "quarantined"]
DMARC_POLICIES = ["none", "quarantine", "reject"]


class EmailSecurityService:
    def __init__(self, db):
        self.db = db
        self.col_threats = db["email_threats"]
        self.col_domains = db["email_domains"]
        self.col_quarantine = db["email_quarantine"]

    async def get_threats(self, tenant_id: str, threat_type: str = None, limit: int = 50):
        q = {"tenant_id": tenant_id}
        if threat_type:
            q["threat_type"] = threat_type
        cursor = self.col_threats.find(q).sort("detected_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_domain_health(self, tenant_id: str):
        cursor = self.col_domains.find({"tenant_id": tenant_id})
        return await cursor.to_list(length=100)

    async def get_quarantine(self, tenant_id: str, limit: int = 50):
        cursor = self.col_quarantine.find({"tenant_id": tenant_id}).sort("received_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def release_quarantine(self, email_id: str, tenant_id: str):
        await self.col_quarantine.update_one(
            {"_id": email_id, "tenant_id": tenant_id},
            {"$set": {"status": "released", "released_at": datetime.now(timezone.utc).isoformat()}}
        )

    async def get_summary(self, tenant_id: str):
        since_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        threats_24h = await self.col_threats.count_documents({"tenant_id": tenant_id, "detected_at": {"$gte": since_24h}})
        quarantined = await self.col_quarantine.count_documents({"tenant_id": tenant_id, "status": "quarantined"})
        domains = await self.col_domains.count_documents({"tenant_id": tenant_id})
        failing_dmarc = await self.col_domains.count_documents({"tenant_id": tenant_id, "dmarc_policy": "none"})
        return {"threats_24h": threats_24h, "quarantined_emails": quarantined,
                "monitored_domains": domains, "failing_dmarc": failing_dmarc}

    async def seed_demo(self, tenant_id: str):
        await self.col_threats.delete_many({"tenant_id": tenant_id})
        await self.col_domains.delete_many({"tenant_id": tenant_id})
        await self.col_quarantine.delete_many({"tenant_id": tenant_id})
        # Deterministic threat seed — fixed records exercising each threat type
        threat_records = [
            ("phishing",            "high",     "ceo@attacker.com",         "user12@company.com",  "Urgent: Password Reset",          "malicious",   0.97, 2,  "open"),
            ("spear_phishing",      "critical", "hr@phish.net",             "user3@company.com",   "Action Required: Invoice #1042",  "malicious",   0.99, 5,  "open"),
            ("malware_attachment",  "high",     "billing@evil.io",          "user27@company.com",  "Urgent: Wire Transfer",           "quarantined", 0.95, 8,  "open"),
            ("bec",                 "critical", "ceo@attacker.com",         "user5@company.com",   "Urgent: Account Verification",    "malicious",   0.98, 12, "open"),
            ("spam",                "low",      "support@legit-looking.com","user41@company.com",  "Limited Offer — Act Now",         "suspicious",  0.81, 18, "resolved"),
            ("credential_harvesting","high",    "hr@phish.net",             "user8@company.com",   "Your Password Expires Today",     "malicious",   0.96, 24, "open"),
            ("phishing",            "medium",   "billing@evil.io",          "user19@company.com",  "Urgent: Invoice",                 "suspicious",  0.88, 30, "open"),
            ("spear_phishing",      "high",     "ceo@attacker.com",         "user33@company.com",  "Re: Q4 Budget Review",            "malicious",   0.94, 36, "open"),
            ("malware_attachment",  "critical", "support@legit-looking.com","user7@company.com",   "Urgent: Invoice",                 "quarantined", 0.99, 40, "open"),
            ("spam",                "low",      "hr@phish.net",             "user22@company.com",  "Congratulations, You've Won!",    "clean",       0.72, 48, "resolved"),
        ]
        for ttype, sev, sender, recipient, subject, verdict, confidence, hours_ago, status in threat_records:
            await self.col_threats.insert_one({
                "_id": str(uuid.uuid4()), "tenant_id": tenant_id,
                "threat_type": ttype, "severity": sev,
                "sender": sender, "recipient": recipient,
                "subject": subject,
                "verdict": verdict,
                "confidence": confidence,
                "detected_at": (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat(),
                "status": status,
            })
        domain_records = [
            ("company.com",       "pass", "pass", "reject",    100, 98),
            ("subsidiary.io",     "pass", "fail", "quarantine", 75, 71),
            ("partner-domain.net","fail", "fail", "none",        0, 42),
        ]
        for domain, spf, dkim, dmarc_policy, dmarc_pct, health_score in domain_records:
            await self.col_domains.insert_one({
                "_id": str(uuid.uuid4()), "tenant_id": tenant_id, "domain": domain,
                "spf": spf, "dkim": dkim,
                "dmarc_policy": dmarc_policy,
                "dmarc_pct": dmarc_pct,
                "mx_records": [f"mail.{domain}"],
                "last_checked": datetime.now(timezone.utc).isoformat(),
                "health_score": health_score,
            })
        quarantine_records = [
            ("ceo@attacker.com",          "user12@company.com", "Action Required: Invoice",       "phishing_url",          3),
            ("billing@evil.io",           "user27@company.com", "Your Package Has Arrived",       "malicious_attachment",  7),
            ("hr@phish.net",              "user5@company.com",  "Verify Your Account Now",        "phishing_url",          11),
            ("support@legit-looking.com", "user41@company.com", "Urgent: Payment",                "dmarc_fail",            16),
            ("ceo@attacker.com",          "user3@company.com",  "Re: Meeting Tomorrow",           "spam_score",            22),
        ]
        for sender, recipient, subject, reason, hours_ago in quarantine_records:
            await self.col_quarantine.insert_one({
                "_id": str(uuid.uuid4()), "tenant_id": tenant_id,
                "sender": sender, "recipient": recipient,
                "subject": subject,
                "reason": reason,
                "received_at": (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat(),
                "status": "quarantined",
            })
