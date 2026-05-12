import logging
from fastapi import HTTPException
from database import get_database
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class FinOpsService:
    def __init__(self):
        # Simulation parameters
        self.daily_budget = 500.00
        self.resource_costs = {
            "compute_unit": 0.05, # per hour
            "storage_gb": 0.02,   # per month
            "network_gb": 0.01    # per GB transfer
        }
        
        # In-memory store for Service Pricing (initialized with data.ts content)
        self.service_pricing = [
            # Management & Settings
            { "id": 'price-sys-settings', "name": 'System Settings', "unit": 'included', "price": 0, "category": 'Management & Settings', "description": 'Core system configuration and branding.' },
            { "id": 'price-rbac', "name": 'Role & Permission Management', "unit": 'per_user_mo', "price": 2.00, "category": 'Management & Settings', "description": 'Advanced RBAC with custom roles.' },
            { "id": 'price-api-keys', "name": 'API Key Management', "unit": 'per_key_mo', "price": 0.50, "category": 'Management & Settings', "description": 'Secure API key generation and rotation.' },
            { "id": 'price-finops', "name": 'FinOps & Billing', "unit": 'percent_cloud_spend', "price": 0.01, "category": 'Management & Settings', "description": 'Cloud cost analytics and optimization.' },
            { "id": 'price-user-profile', "name": 'User Profile', "unit": 'included', "price": 0, "category": 'Management & Settings', "description": 'Individual user profile settings.' },
            { "id": 'price-tenant-mgmt', "name": 'Tenant Management', "unit": 'per_tenant_mo', "price": 10.00, "category": 'Management & Settings', "description": 'Multi-tenancy and isolation management.' },
            { "id": 'price-webhooks', "name": 'Webhook Management', "unit": 'per_million_events', "price": 1.00, "category": 'Management & Settings', "description": 'Outbound event notifications.' },
            { "id": 'price-data-warehouse', "name": 'Data Warehouse', "unit": 'per_gb_storage_mo', "price": 0.50, "category": 'Management & Settings', "description": 'Long-term analytical storage.' },
            
            # Security & Compliance
            { "id": 'price-sec-ops', "name": 'Security Operations Center', "unit": 'per_analyst_mo', "price": 150.00, "category": 'Security', "description": 'Centralized dashboard for security monitoring.' },
            { "id": 'price-case-mgmt', "name": 'Manage Security Cases', "unit": 'per_case', "price": 5.00, "category": 'Security', "description": 'Incident case management and tracking.' },
            { "id": 'price-soar', "name": 'Manage SOAR Playbooks', "unit": 'per_playbook_run', "price": 0.50, "category": 'Security', "description": 'Automated incident response workflows.' },
            { "id": 'price-threat-intel', "name": 'Threat Intelligence Feed', "unit": 'per_month', "price": 500.00, "category": 'Security', "description": 'Premium threat feeds and enrichment.' },
            { "id": 'price-cloud-sec', "name": 'Cloud Security (CSPM)', "unit": 'per_resource_mo', "price": 0.05, "category": 'Security', "description": 'Cloud posture management and compliance.' },
            { "id": 'price-patch-mgmt', "name": 'Patch Management', "unit": 'per_asset_mo', "price": 3.00, "category": 'Security', "description": 'Vulnerability patching and reporting.' },
            { "id": 'price-edr', "name": 'EDR — Endpoint Detection & Response', "unit": 'per_agent_mo', "price": 8.00, "category": 'Security', "description": 'Real-time endpoint telemetry, threat detection, and automated response.' },
            { "id": 'price-mdr', "name": 'MDR — Managed Detection & Response', "unit": 'per_agent_mo', "price": 15.00, "category": 'Security', "description": 'Autonomous response policy engine with quarantine and remediation actions.' },
            { "id": 'price-xdr', "name": 'XDR — Extended Detection & Response', "unit": 'per_month', "price": 499.00, "category": 'Security', "description": 'Cross-domain correlation, MITRE ATT&CK mapping, and automated threat hunting.' },
             
            # Observability
            { "id": 'price-agent-fleet', "name": 'Agent Fleet Management', "unit": 'per_agent_mo', "price": 5.00, "category": 'Observability', "description": 'Centralized agent control and health monitoring.' },
            { "id": 'price-soft-hub', "name": 'Software Deployment Hub', "unit": 'per_deploy_job', "price": 0.20, "category": 'Observability', "description": 'Bulk software installation and updates.' },
            { "id": 'price-view-logs', "name": 'View Agent Logs', "unit": 'per_gb_ingest', "price": 0.30, "category": 'Observability', "description": 'Real-time log streaming from agents.' },
            { "id": 'price-log-explorer', "name": 'Log Explorer', "unit": 'per_query_hour', "price": 5.00, "category": 'Observability', "description": 'Advanced log search and visualization.' },
            { "id": 'price-insights', "name": 'Proactive Insights', "unit": 'per_insight', "price": 2.00, "category": 'Observability', "description": 'AI-driven system health insights.' },
            { "id": 'price-dist-trace', "name": 'Distributed Tracing', "unit": 'per_million_spans', "price": 10.00, "category": 'Observability', "description": 'End-to-end request tracing.' },
            
            # AI Governance
            { "id": 'price-ai-gov', "name": 'AI Governance Platform', "unit": 'per_model_mo', "price": 100.00, "category": 'AI Governance', "description": 'Model registry and policy enforcement.' },
            
            # Automation
            { "id": 'price-auto-workflow', "name": 'Automation Workflows', "unit": 'per_workflow_mo', "price": 20.00, "category": 'Automation', "description": 'Custom automation workflow builder.' },
            
             # Developer Tools
            { "id": 'price-devsecops', "name": 'DevSecOps Dashboard', "unit": 'per_repo_mo', "price": 10.00, "category": 'Developer Tools', "description": 'Pipeline security and vulnerability visibility.' }
        ]
        
    async def calculate_current_spend(self, tenant_id: str = None) -> Dict[str, Any]:
        """
        Aggregate current month's spend based on service pricing and usage records.
        Scoped to tenant_id when provided.
        """
        db = get_database()
        if not db:
            logger.warning("FinOps: no DB connection — returning simulated spend data")
            return await self._generate_simulated_spend()

        # Aggregate usage from DB — scoped to tenant when provided
        start_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        match_stage: dict = {"timestamp": {"$gte": start_date}}
        if tenant_id:
            match_stage["tenantId"] = tenant_id

        pipeline = [
            {"$match": match_stage},
            {"$group": {
                "_id": "$serviceId",
                "total_usage": {"$sum": "$amount"}
            }}
        ]

        usage_cursor = db.usage_records.aggregate(pipeline)
        usage_by_service = {item["_id"]: item["total_usage"] for item in await usage_cursor.to_list(length=100)}

        if not usage_by_service:
            logger.warning("FinOps: no usage records found for tenant=%s — returning simulated spend data", tenant_id)
            return await self._generate_simulated_spend()

        total = 0.0
        breakdown = {
            "Compute": 0.0,
            "Storage": 0.0,
            "Network": 0.0,
            "Security": 0.0,
            "AI Services": 0.0
        }
        
        # Map services to categories and calculate costs
        for p in self.service_pricing:
            usage_val = usage_by_service.get(self._map_pricing_id_to_service_id(p["id"]), 0)
            if usage_val == 0:
                continue
                
            cost = usage_val * p.get("price", 0)
            cat = p.get("category", "Management & Settings")
            
            # Simplified category mapping for the summary breakdown
            if "Security" in cat: breakdown["Security"] += cost
            elif "AI" in cat: breakdown["AI Services"] += cost
            elif "Observability" in cat: breakdown["Compute"] += cost # Mapping agents to compute for now
            else: breakdown["Network"] += cost # Default
            
            total += cost

        return {
            "total_spend": round(total, 2),
            "breakdown": {k: round(v, 2) for k, v in breakdown.items()},
            "currency": "USD",
            "budget_usage_percent": round((total / (self.daily_budget * 30)) * 100, 1) if total > 0 else 0.5
        }

    def _map_pricing_id_to_service_id(self, pricing_id: str) -> str:
        mapping = {
            "price-sec-ops": "security_operations",
            "price-ai-gov": "ai_services",
            "price-agent-fleet": "agent_management",
            "price-finops": "finops_analytics",
            "price-compliance": "compliance_monitoring",
            "price-edr": "edr_telemetry",
            "price-mdr": "mdr_response",
            "price-xdr": "xdr_correlation"
        }
        return mapping.get(pricing_id, "general_api")

    async def _generate_simulated_spend(self) -> Dict[str, Any]:
        """
        Estimate spend from real asset/agent counts when no usage_records exist.
        Uses deterministic per-asset/per-agent pricing rates — no random values.
        """
        db = get_database()
        agent_count = await db.agents.count_documents({}) if db else 0
        asset_count = await db.assets.count_documents({}) if db else 0
        tenant_count = await db.tenants.count_documents({}) if db else 1

        # Derive estimated usage from real counts
        estimated = {
            "agent_management":     agent_count * 5.00,   # $5/agent/mo
            "security_operations":  asset_count * 0.10,   # $0.10/asset/mo
            "edr_telemetry":        agent_count * 8.00,   # $8/agent/mo
            "ai_services":          tenant_count * 100.0, # $100/tenant/mo
            "finops_analytics":     asset_count * 0.01,
        }

        total = sum(estimated.values())
        breakdown = {
            "Compute":     round(estimated["agent_management"], 2),
            "Security":    round(estimated["security_operations"] + estimated["edr_telemetry"], 2),
            "AI Services": round(estimated["ai_services"], 2),
            "Storage":     round(estimated["finops_analytics"], 2),
            "Network":     0.0,
        }
        return {
            "total_spend": round(total, 2),
            "breakdown": breakdown,
            "currency": "USD",
            "budget_usage_percent": round((total / (self.daily_budget * 30)) * 100, 1),
        }

    async def get_cost_forecast(self) -> Dict[str, Any]:
        """Predict end-of-month bill"""
        current = await self.calculate_current_spend()
        avg_daily = current["total_spend"] / 20
        forecast_total = avg_daily * 30
        return {
            "forecast_total": round(forecast_total, 2),
            "budget": self.daily_budget * 30,
            "status": "OVER_BUDGET" if forecast_total > (self.daily_budget * 30) else "ON_TRACK"
        }

    async def get_cost_history(self) -> List[Dict[str, Any]]:
        """Aggregate last 30 days of real usage costs from DB; zero-fill missing days."""
        from database import get_database
        db = get_database()
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=29)

        pipeline = [
            {"$match": {"recorded_at": {"$gte": start.isoformat()}}},
            {"$group": {
                "_id": {"$substr": ["$recorded_at", 0, 10]},
                "total_cost": {"$sum": "$cost"},
            }},
        ]
        try:
            rows = await db.usage_records.aggregate(pipeline).to_list(length=100)
        except Exception:
            rows = []

        cost_by_date = {row["_id"]: round(row["total_cost"], 2) for row in rows}

        history = []
        for i in range(30):
            date = start + timedelta(days=i)
            date_str = date.isoformat()
            history.append({
                "date": date_str,
                "cost": cost_by_date.get(date_str, 0.0),
            })
        return history

    def generate_recommendations(self) -> List[Dict[str, Any]]:
        """Generate cost optimization recommendations."""
        return [
            {"id": "rec-001", "title": "Right-size over-provisioned compute instances", "savings": 240.00, "effort": "Low", "category": "Compute"},
            {"id": "rec-002", "title": "Enable S3 Intelligent-Tiering for cold data", "savings": 120.00, "effort": "Low", "category": "Storage"},
            {"id": "rec-003", "title": "Purchase 1-year Reserved Instances for baseline workloads", "savings": 890.00, "effort": "Medium", "category": "Compute"},
            {"id": "rec-004", "title": "Delete 12 unattached EBS volumes", "savings": 55.00, "effort": "Low", "category": "Storage"},
            {"id": "rec-005", "title": "Consolidate dev/test environments to use spot instances", "savings": 310.00, "effort": "Medium", "category": "Compute"},
            {"id": "rec-006", "title": "Remove idle NAT Gateways in us-east-1", "savings": 64.80, "effort": "Low", "category": "Network"},
        ]

    async def refresh_cost_recommendations(self, db=None) -> None:
        """Persist current recommendations to db.cost_recommendations."""
        if db is None:
            db = get_database()
        recs = self.generate_recommendations()
        for rec in recs:
            await db.cost_recommendations.update_one(
                {"id": rec["id"]},
                {"$set": rec},
                upsert=True,
            )


    async def _raise_cost_alert(self, tenant_id: str, alert_type: str, message: str, severity: str = "High") -> None:
        """Insert a cost anomaly alert into the alerts collection."""
        try:
            import uuid as _uuid
            db = get_database()
            await db.alerts.insert_one({
                "id": str(_uuid.uuid4()),
                "_id": str(_uuid.uuid4()),
                "type": alert_type,
                "description": message,
                "severity": severity,
                "tenantId": tenant_id,
                "source": {"hostname": "finops-engine"},
                "status": "open",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as _e:
            import logging
            logging.getLogger(__name__).warning("FinOps alert creation failed: %s", _e)

    def generate_ai_analysis(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate AI-powered FinOps analysis and raise alerts for detected anomalies."""
        import asyncio
        analysis_points = []
        recommendations = []

        current_cost = data.get('currentMonthCost', 0)
        forecast = data.get('forecastedCost', 0)
        tenant_id = data.get('tenantId', 'platform')

        if forecast > current_cost * 1.2:
            analysis_points.append("Projected spend is trending 20% higher than current run rate.")
            recommendations.append("Investigate recent compute provisioning spikes.")
            try:
                asyncio.get_event_loop().create_task(
                    self._raise_cost_alert(
                        tenant_id, "COST_SPIKE_FORECAST",
                        f"Forecasted cost ${forecast:.2f} exceeds current run rate ${current_cost:.2f} by >20%.",
                        "High",
                    )
                )
            except RuntimeError:
                pass  # No running event loop in sync context

        breakdown = data.get('costBreakdown', [])
        storage_cost = next((item['cost'] for item in breakdown if item['service'] == 'Storage'), 0)
        if current_cost > 0 and storage_cost > current_cost * 0.3:
            analysis_points.append("Storage costs account for >30% of total spend.")
            recommendations.append("Enable detailed monitoring on storage buckets.")
            try:
                asyncio.get_event_loop().create_task(
                    self._raise_cost_alert(
                        tenant_id, "STORAGE_COST_ANOMALY",
                        f"Storage cost ${storage_cost:.2f} is {storage_cost/current_cost*100:.0f}% of total spend (threshold: 30%).",
                        "Medium",
                    )
                )
            except RuntimeError:
                pass

        analysis_text = " ".join(analysis_points) if analysis_points else "Spending patterns appear distinct and stable."

        return {
            "analysis": f"AI Analysis: {analysis_text} Resource utilization metrics indicate opportunities for rightsizing.",
            "recommendations": recommendations + [
                "Review idle load balancers in US-East region",
                "Purchase Compute Savings Plans for consistent baseline usage"
            ]
        }

    async def recalculate_tenant_costs(self, tenant_id: str) -> Dict[str, Any]:
        """Trigger a fresh cost calculation for a specific tenant using real usage data."""
        current = await self.calculate_current_spend(tenant_id=tenant_id)
        forecast = await self.get_cost_forecast()
        history = await self.get_cost_history()
        recommendations = self.generate_recommendations()
        potential_savings = sum(
            r.get("savings", 0) for r in recommendations if isinstance(r.get("savings"), (int, float))
        )
        breakdown = [
            {"service": k, "cost": v}
            for k, v in current.get("breakdown", {}).items()
        ]
        return {
            "currentMonthCost": current.get("total_spend", 0.0),
            "forecastedCost": forecast.get("forecast_total", 0.0),
            "potentialSavings": round(potential_savings, 2),
            "costBreakdown": breakdown,
            "costTrend": history,
        }

    def _generate_random_trend(self):
        # Deterministic 6-month spend trend — slight upward curve
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
        _actuals = [920.0, 950.0, 980.0, 1010.0, 1040.0, 1080.0]
        return [
            {"month": m, "actual": a, "forecast": round(a * 1.05, 2)}
            for m, a in zip(months, _actuals)
        ]
        
    def get_tenant_finops_data(self, tenant_id: str) -> Dict[str, Any]:
        return self.recalculate_tenant_costs(tenant_id)

    # --- Service Pricing Logic ---
    def get_service_pricing(self) -> List[Dict[str, Any]]:
        return self.service_pricing

    def create_service_pricing(self, service_data: Dict[str, Any]) -> Dict[str, Any]:
        self.service_pricing.append(service_data)
        return service_data

    def update_service_pricing(self, service_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        for i, service in enumerate(self.service_pricing):
            if service["id"] == service_id:
                self.service_pricing[i].update(updates)
                self.service_pricing[i]["updatedAt"] = datetime.now().isoformat()
                return self.service_pricing[i]
        raise HTTPException(status_code=404, detail="Service not found")

    def delete_service_pricing(self, service_id: str) -> Dict[str, Any]:
        for i, service in enumerate(self.service_pricing):
            if service["id"] == service_id:
                deleted = self.service_pricing.pop(i)
                return deleted
        raise HTTPException(status_code=404, detail="Service not found")

# Global instance
finops_service = FinOpsService()
