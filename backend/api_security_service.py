"""API Security Service — inventory, abuse detection, schema enforcement."""
from datetime import datetime, timedelta
import uuid
import hashlib


class APISecurityService:
    def __init__(self, db):
        self.db = db
        self.col_endpoints = db["api_inventory"]
        self.col_alerts = db["api_security_alerts"]
        self.col_policies = db["api_security_policies"]

    @staticmethod
    def _compute_risk_score(method: str, path: str, auth_required: bool) -> float:
        """
        Compute a deterministic risk score (0.0–1.0) based on security properties.
        Higher = riskier. Factors:
          - Unauthenticated /api/ endpoint → +0.5
          - Mutating method (POST/PUT/PATCH/DELETE) → +0.2
          - Path contains sensitive keywords → +0.15
          - Write to admin/config paths → +0.15
        """
        score = 0.0
        if not auth_required and path.startswith("/api/"):
            score += 0.5
        if method in ("POST", "PUT", "PATCH", "DELETE"):
            score += 0.2
        sensitive = ("/admin", "/token", "/auth", "/secret", "/key", "/cred", "/password",
                     "/exec", "/run", "/reset", "/delete", "/upload", "/webhook")
        if any(kw in path.lower() for kw in sensitive):
            score += 0.15
        if any(kw in path.lower() for kw in ("/admin", "/config", "/settings", "/role")):
            score += 0.15
        return round(min(score, 1.0), 2)

    async def discover_endpoints(self, tenant_id: str):
        """Scan registered FastAPI routes and upsert into inventory."""
        from app import _fastapi_app as fastapi_app
        discovered = []
        for route in fastapi_app.routes:
            if hasattr(route, "methods") and hasattr(route, "path"):
                for method in (route.methods or ["GET"]):
                    endpoint_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{method}:{route.path}"))
                    auth_required = route.path not in ["/health", "/", "/docs", "/openapi.json"]
                    risk_score = self._compute_risk_score(method, route.path, auth_required)

                    # Only set telemetry fields on first insert; don't overwrite real counters
                    existing = await self.col_endpoints.find_one({"_id": endpoint_id})
                    base = {
                        "_id": endpoint_id,
                        "method": method,
                        "path": route.path,
                        "name": getattr(route, "name", ""),
                        "tags": list(getattr(route, "tags", []) or []),
                        "tenant_id": tenant_id,
                        "last_seen": datetime.now(timezone.utc).isoformat(),
                        "auth_required": auth_required,
                        "risk_score": risk_score,
                    }
                    if not existing:
                        base["request_count_24h"] = 0
                        base["avg_latency_ms"] = 0
                        base["error_rate"] = 0.0
                    await self.col_endpoints.update_one(
                        {"_id": endpoint_id},
                        {"$set": base, "$setOnInsert": {
                            "request_count_24h": 0,
                            "avg_latency_ms": 0,
                            "error_rate": 0.0,
                        }},
                        upsert=True,
                    )
                    discovered.append(base)
        return discovered

    async def get_endpoints(self, tenant_id: str, limit: int = 100):
        cursor = self.col_endpoints.find({"tenant_id": tenant_id}).sort("risk_score", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_alerts(self, tenant_id: str, severity: str = None, limit: int = 50):
        q = {"tenant_id": tenant_id}
        if severity:
            q["severity"] = severity
        cursor = self.col_alerts.find(q).sort("detected_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def analyze_endpoint(self, endpoint_id: str, tenant_id: str):
        ep = await self.col_endpoints.find_one({"_id": endpoint_id})
        if not ep:
            return None
        alerts = []
        if ep.get("error_rate", 0) > 0.1:
            alerts.append({"type": "high_error_rate", "severity": "high",
                            "message": f"Error rate {ep['error_rate']*100:.1f}% exceeds threshold"})
        if not ep.get("auth_required") and ep.get("path", "").startswith("/api/"):
            alerts.append({"type": "unauthenticated_api", "severity": "critical",
                            "message": f"API endpoint {ep['path']} accessible without authentication"})
        if ep.get("request_count_24h", 0) > 10000:
            alerts.append({"type": "high_volume", "severity": "medium",
                            "message": f"Endpoint receiving {ep['request_count_24h']} req/day — potential abuse"})
        for alert in alerts:
            alert.update({"_id": str(uuid.uuid4()), "endpoint_id": endpoint_id,
                          "tenant_id": tenant_id, "detected_at": datetime.now(timezone.utc).isoformat(),
                          "status": "open"})
            await self.col_alerts.insert_one(alert)
        return {"endpoint": ep, "alerts": alerts}

    async def get_summary(self, tenant_id: str):
        total = await self.col_endpoints.count_documents({"tenant_id": tenant_id})
        unauthenticated = await self.col_endpoints.count_documents({"tenant_id": tenant_id, "auth_required": False})
        high_risk = await self.col_endpoints.count_documents({"tenant_id": tenant_id, "risk_score": {"$gte": 0.7}})
        open_alerts = await self.col_alerts.count_documents({"tenant_id": tenant_id, "status": "open"})
        return {"total_endpoints": total, "unauthenticated": unauthenticated,
                "high_risk": high_risk, "open_alerts": open_alerts}
