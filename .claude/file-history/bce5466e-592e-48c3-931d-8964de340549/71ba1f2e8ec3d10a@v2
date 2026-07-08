"""Cookie Consent Management service — GDPR/ePrivacy compliant consent tracking."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

_CC_SUPER_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}

DEFAULT_CATEGORIES = [
    {
        "id": "necessary",
        "name": "Strictly Necessary",
        "description": "Essential cookies required for the website to function. Cannot be disabled.",
        "required": True,
        "cookies": [
            {"name": "session_id", "provider": "First party", "purpose": "Session management", "expiry": "Session"},
            {"name": "csrf_token", "provider": "First party", "purpose": "CSRF protection", "expiry": "Session"},
        ],
    },
    {
        "id": "analytics",
        "name": "Analytics",
        "description": "Help us understand how visitors interact with our website.",
        "required": False,
        "cookies": [
            {"name": "_ga", "provider": "Google Analytics", "purpose": "Track user behaviour", "expiry": "2 years"},
            {"name": "_gid", "provider": "Google Analytics", "purpose": "Distinguish users", "expiry": "24 hours"},
        ],
    },
    {
        "id": "marketing",
        "name": "Marketing",
        "description": "Used to track visitors and display relevant ads.",
        "required": False,
        "cookies": [
            {"name": "_fbp", "provider": "Facebook", "purpose": "Advertising", "expiry": "3 months"},
            {"name": "ads_id", "provider": "Google Ads", "purpose": "Conversion tracking", "expiry": "90 days"},
        ],
    },
    {
        "id": "preferences",
        "name": "Preferences",
        "description": "Remember your settings and personalisation choices.",
        "required": False,
        "cookies": [
            {"name": "lang", "provider": "First party", "purpose": "Language preference", "expiry": "1 year"},
            {"name": "theme", "provider": "First party", "purpose": "UI theme", "expiry": "1 year"},
        ],
    },
]


class CookieConsentService:
    def _db(self):
        from database import get_database
        return get_database()

    async def get_config(self, tenant_id: str) -> Dict:
        db = self._db()
        config = await db.cookie_consent_config.find_one({"tenantId": tenant_id}, {"_id": 0})
        if not config:
            return {"tenantId": tenant_id, "categories": DEFAULT_CATEGORIES, "version": "1.0", "bannerTitle": "Cookie Preferences", "bannerText": "We use cookies to improve your experience. Please review your preferences.", "privacyPolicyUrl": ""}
        return config

    async def update_config(self, tenant_id: str, data: Dict[str, Any]) -> Dict:
        db = self._db()
        now = datetime.now(timezone.utc).isoformat()
        allowed = {"categories", "version", "bannerTitle", "bannerText", "privacyPolicyUrl"}
        patch = {k: v for k, v in data.items() if k in allowed}
        patch["updated_at"] = now
        patch["tenantId"] = tenant_id
        await db.cookie_consent_config.update_one(
            {"tenantId": tenant_id}, {"$set": patch, "$setOnInsert": {"created_at": now}}, upsert=True
        )
        return await self.get_config(tenant_id)

    async def record_consent(self, tenant_id: str, session_id: str, consented_categories: List[str], metadata: Dict[str, Any]) -> Dict:
        db = self._db()
        now = datetime.now(timezone.utc).isoformat()
        config = await self.get_config(tenant_id)
        version = config.get("version", "1.0")
        record = {
            "id": f"cc-{uuid.uuid4().hex}",
            "tenantId": tenant_id,
            "sessionId": session_id,
            "userId": metadata.get("userId"),
            "ipAddress": metadata.get("ipAddress", ""),
            "userAgent": metadata.get("userAgent", ""),
            "consentedCategories": consented_categories,
            "allCategories": [c["id"] for c in config.get("categories", [])],
            "bannerVersion": version,
            "created_at": now,
        }
        await db.cookie_consent_records.update_one(
            {"tenantId": tenant_id, "sessionId": session_id},
            {"$set": record},
            upsert=True,
        )
        record.pop("_id", None)
        return record

    async def get_records(self, tenant_id: Optional[str], role: str, limit: int = 500) -> List[Dict]:
        db = self._db()
        query: Dict[str, Any] = {} if role in _CC_SUPER_ROLES else {"tenantId": tenant_id}
        return await db.cookie_consent_records.find(query, {"_id": 0}).sort("created_at", -1).to_list(length=limit)

    async def get_stats(self, tenant_id: str) -> Dict:
        db = self._db()
        records = await db.cookie_consent_records.find({"tenantId": tenant_id}, {"_id": 0}).to_list(length=10000)
        total = len(records)
        if not total:
            return {"total": 0, "byCategory": {}, "fullConsent": 0, "necessaryOnly": 0, "optOut": 0}
        config = await self.get_config(tenant_id)
        all_cats = [c["id"] for c in config.get("categories", [])]
        non_required = [c["id"] for c in config.get("categories", []) if not c.get("required")]
        by_cat: Dict[str, int] = {c: 0 for c in all_cats}
        full = 0
        necessary_only = 0
        for r in records:
            consented = r.get("consentedCategories", [])
            for cat in consented:
                if cat in by_cat:
                    by_cat[cat] += 1
            if all(c in consented for c in non_required):
                full += 1
            elif all(c not in consented for c in non_required):
                necessary_only += 1
        return {
            "total": total,
            "byCategory": by_cat,
            "byCategoryPct": {k: round(v / total * 100) for k, v in by_cat.items()},
            "fullConsent": full,
            "fullConsentPct": round(full / total * 100),
            "necessaryOnly": necessary_only,
            "optOut": necessary_only,
        }

    async def get_consent_for_session(self, tenant_id: str, session_id: str) -> Optional[Dict]:
        db = self._db()
        return await db.cookie_consent_records.find_one(
            {"tenantId": tenant_id, "sessionId": session_id}, {"_id": 0}
        )


cookie_consent_service = CookieConsentService()
