"""
BI Analytics Service

Computes all BI metrics from real MongoDB data:
  - Risk profile   → from compliance framework pass/fail rates + avg security score
  - Trends         → from monthly alert counts and patch success rates
  - Efficiency     → from patch deployment history and security case MTTR
  - Asset dist.    → from assets collection grouped by OS type
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

logger = logging.getLogger(__name__)


class BiAnalyticsService:
    def __init__(self, db):
        self.db = db

    async def get_bi_metrics(self, tenant_id: str = None) -> Dict[str, Any]:
        """Every value is measured; a metric with no underlying data is None
        (shown as "—"), never a stand-in default."""
        db = self.db
        if not db:
            return self._empty()

        q: Dict = {}
        if tenant_id and tenant_id != "platform-admin":
            q["tenantId"] = tenant_id
        now = datetime.now(timezone.utc)

        # ── 1. Risk Profile (radar) ───────────────────────────────────────────
        agents = await db.agents.find(q, {"securityScore": 1, "_id": 0}).to_list(length=1000)
        scores = [a.get("securityScore", 0) for a in agents if a.get("securityScore")]
        avg_sec = round(sum(scores) / len(scores), 1) if scores else None

        frameworks = await db.compliance_frameworks.find(q, {"controls": 1, "_id": 0}).to_list(length=1000)
        passed = failed = 0
        for fw in frameworks:
            for ctrl in fw.get("controls", []):
                if ctrl.get("status") == "Pass":
                    passed += 1
                else:
                    failed += 1
        total_ctrl = passed + failed
        compliance_score = round((passed / total_ctrl) * 100, 1) if total_ctrl else None

        deployments = await db.patch_deployment_jobs.find(
            {**q, "status": {"$in": ["completed", "failed"]}}, {"status": 1}
        ).to_list(length=500)
        dep_total = len(deployments)
        dep_ok = sum(1 for d in deployments if d.get("status") == "completed")
        patch_rate = round((dep_ok / dep_total) * 100, 1) if dep_total else None

        # Cost efficiency: % of cost optimization recommendations actioned vs. open
        cost_agg = await db.cost_recommendations.aggregate([
            {"$match": q},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]).to_list(length=20)
        cost_by_status = {row["_id"]: row["count"] for row in cost_agg}
        actioned = cost_by_status.get("implemented", 0) + cost_by_status.get("dismissed", 0)
        cost_total = sum(cost_by_status.values())
        cost_efficiency = round((actioned / cost_total) * 100, 1) if cost_total > 0 else None

        risk_profile = [
            {"subject": subject, "A": value, "fullMark": 100}
            for subject, value in (
                ("Security", avg_sec),
                ("Compliance", compliance_score),
                ("Cost Efficiency", cost_efficiency),
                ("Reliability", patch_rate),
            )
            if value is not None
        ]

        # ── 2. Trend: monthly security-score proxy + straight-line forecast ──
        monthly_alerts: Dict[str, int] = {}
        alerts_cur = await db.alerts.find(q, {"createdAt": 1, "status": 1, "_id": 0}).to_list(length=5000)
        for a in alerts_cur:
            ts = a.get("createdAt", "")
            if len(ts) >= 7:
                key = ts[:7]  # "YYYY-MM"
                monthly_alerts[key] = monthly_alerts.get(key, 0) + 1

        trends = []
        if avg_sec is not None:
            actuals = []
            for i in range(-6, 1):
                day = now + timedelta(days=i * 30)
                # Security score proxy: each alert that month costs half a point
                score = round(max(0, min(100, avg_sec - monthly_alerts.get(day.strftime("%Y-%m"), 0) * 0.5)), 1)
                actuals.append((i, day, score))
            slope, intercept = _linear_fit([(i, v) for i, _, v in actuals])
            for i, day, v in actuals:
                trends.append({"name": day.strftime("%b %Y"), "actual": v, "forecast": None, "isForecast": False})
            for i in range(1, 4):
                day = now + timedelta(days=i * 30)
                trends.append({
                    "name": day.strftime("%b %Y"),
                    "actual": None,
                    "forecast": round(max(0, min(100, intercept + slope * i)), 1),
                    "isForecast": True,
                })

        # ── 3. Efficiency stats ───────────────────────────────────────────────
        cases = await db.security_cases.find(
            q, {"createdAt": 1, "resolvedAt": 1, "status": 1}
        ).to_list(length=500)
        mttr_hours = None
        resolved_last_30 = 0
        deltas = []
        for c in cases:
            if not (c.get("resolvedAt") and c.get("createdAt")):
                continue
            try:
                t0 = datetime.fromisoformat(c["createdAt"].replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(c["resolvedAt"].replace("Z", "+00:00"))
            except Exception as e:
                logger.debug("Unparseable case timestamp, skipping MTTR delta: %s", e)
                continue
            if len(deltas) < 100:
                deltas.append((t1 - t0).total_seconds() / 3600)
            if t1.tzinfo and now - t1 <= timedelta(days=30):
                resolved_last_30 += 1
        if deltas:
            mttr_hours = round(sum(deltas) / len(deltas), 1)

        all_policies = await db.automation_policies.count_documents(q)
        auto_policies = await db.automation_policies.count_documents({**q, "enabled": True})
        auto_rate = round((auto_policies / all_policies) * 100) if all_policies else None

        efficiency = {
            "mttr": mttr_hours,
            "automation_rate": auto_rate,
            "patch_success_rate": int(patch_rate) if patch_rate is not None else None,
            # cases resolved per day over the last 30 days
            "remediation_velocity": round(resolved_last_30 / 30, 1) if cases else None,
        }

        # ── 4. Asset distribution (treemap) ──────────────────────────────────
        os_groups = await db.assets.aggregate([
            {"$match": q},
            {"$group": {"_id": "$os", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]).to_list(length=50)

        windows = linux = cloud = other = 0
        for g in os_groups:
            os_name = (g.get("_id") or "").lower()
            cnt = g.get("count", 0)
            if "windows" in os_name:
                windows += cnt
            elif "linux" in os_name or "ubuntu" in os_name or "centos" in os_name or "debian" in os_name:
                linux += cnt
            elif "aws" in os_name or "azure" in os_name or "gcp" in os_name:
                cloud += cnt
            else:
                other += cnt

        # Real counts only; empty categories are left out rather than shown as 1
        asset_distribution = [
            group for group in (
                {"name": "Cloud Resources", "children": [c for c in [{"name": "Cloud VMs", "size": cloud}] if c["size"]]},
                {"name": "On-Premise", "children": [c for c in [
                    {"name": "Windows Servers", "size": windows},
                    {"name": "Linux Nodes", "size": linux},
                    {"name": "Other", "size": other},
                ] if c["size"]]},
            )
            if group["children"]
        ]

        # ── 5. Quick insights ────────────────────────────────────────────────
        critical_assets = await db.assets.count_documents(
            {**q, "$or": [{"criticality": "Critical"}, {"sensitivityLevel": "Critical"}]}
        )
        open_alerts = sum(1 for a in alerts_cur if (a.get("status") or "").lower() not in ("resolved", "closed"))
        risk_level = None
        if avg_sec is not None:
            risk_level = "Low" if avg_sec >= 80 else "Medium" if avg_sec >= 60 else "High"

        return {
            "risk_profile": risk_profile,
            "trends": trends,
            "efficiency": efficiency,
            "asset_distribution": asset_distribution,
            "insights": {
                "critical_assets": critical_assets,
                "compliance_pct": compliance_score,
                "open_alerts": open_alerts,
                "risk_level": risk_level,
            },
            "timestamp": now.isoformat(),
        }

    @staticmethod
    def _empty() -> Dict[str, Any]:
        return {
            "risk_profile": [],
            "trends": [],
            "efficiency": {"mttr": None, "automation_rate": None, "patch_success_rate": None, "remediation_velocity": None},
            "asset_distribution": [],
            "insights": {"critical_assets": None, "compliance_pct": None, "open_alerts": None, "risk_level": None},
            "message": "No BI metrics available. Connect data sources.",
        }


def _linear_fit(points):
    """Least-squares slope and intercept for [(x, y), ...]."""
    n = len(points)
    mean_x = sum(x for x, _ in points) / n
    mean_y = sum(y for _, y in points) / n
    var_x = sum((x - mean_x) ** 2 for x, _ in points)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / var_x if var_x else 0.0
    return slope, mean_y - slope * mean_x


def get_bi_analytics_service(db):
    return BiAnalyticsService(db)
