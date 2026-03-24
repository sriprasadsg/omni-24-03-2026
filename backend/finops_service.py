import random
from fastapi import HTTPException
from database import get_database
from datetime import datetime, timedelta, timezone

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
        """
        db = get_database()
        if not db:
            return self._generate_simulated_spend()

        # Aggregate usage from DB
        # Look at the last 30 days
        start_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        
        pipeline = [
            {"$match": {"timestamp": {"$gte": start_date}}},
            {"$group": {
                "_id": "$serviceId",
                "total_usage": {"$sum": "$amount"}
            }}
        ]

        usage_cursor = db.usage_records.aggregate(pipeline)
        usage_by_service = {item["_id"]: item["total_usage"] for item in await usage_cursor.to_list(length=100)}

        if not usage_by_service:
            return self._generate_simulated_spend()

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
            "price-compliance": "compliance_monitoring"
        }
        return mapping.get(pricing_id, "general_api")

    def _generate_simulated_spend(self) -> Dict[str, Any]:
        """Fallback simulation if no data is present"""
        total = 0.0
        breakdown = {"Compute": 0.0, "Storage": 0.0, "Network": 0.0, "Security": 0.0, "AI Services": 0.0}
        for p in self.service_pricing:
            cat = p.get("category", "Management & Settings")
            usage = random.randint(5, 50)
            cost = (usage * p.get("price", 0)) / 5.0
            if "Security" in cat: breakdown["Security"] += cost
            elif "AI" in cat: breakdown["AI Services"] += cost
            else: breakdown["Compute"] += cost
            total += cost
        return {
            "total_spend": round(total, 2),
            "breakdown": {k: round(v, 2) for k, v in breakdown.items()},
            "currency": "USD",
            "budget_usage_percent": round((total / (self.daily_budget * 30)) * 100, 1)
        }

    def get_cost_forecast(self) -> Dict[str, Any]:
        """Predict end-of-month bill"""
        current = self.calculate_current_spend()
        avg_daily = current["total_spend"] / 20
        forecast_total = avg_daily * 30
        return {
            "forecast_total": round(forecast_total, 2),
            "budget": self.daily_budget * 30,
            "status": "OVER_BUDGET" if forecast_total > (self.daily_budget * 30) else "ON_TRACK"
        }

    def get_cost_history(self) -> List[Dict[str, Any]]:
        """Generate last 30 days history"""
        history = []
        today = datetime.now(timezone.utc)
        base_cost = 150.0 
        for i in range(30):
            date = today - timedelta(days=29-i)
            daily_cost = base_cost + random.uniform(-20, 50)
            history.append({
                "date": date.strftime("%Y-%m-%d"),
                "cost": round(daily_cost, 2)
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


    def generate_ai_analysis(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate AI-powered FinOps analysis."""
        analysis_points = []
        recommendations = []
        
        current_cost = data.get('currentMonthCost', 0)
        forecast = data.get('forecastedCost', 0)
        
        if forecast > current_cost * 1.2:
            analysis_points.append("Projected spend is trending 20% higher than current run rate.")
            recommendations.append("Investigate recent compute provisioning spikes.")
            
        breakdown = data.get('costBreakdown', [])
        storage_cost = next((item['cost'] for item in breakdown if item['service'] == 'Storage'), 0)
        if storage_cost > current_cost * 0.3:
            analysis_points.append("Storage costs account for >30% of total spend.")
            recommendations.append("Enable detailed monitoring on storage buckets.")
            
        analysis_text = " ".join(analysis_points) if analysis_points else "Spending patterns appear distinct and stable."
        
        return {
            "analysis": f"AI Analysis: {analysis_text} Resource utilization metrics indicate opportunities for rightsizing.",
            "recommendations": recommendations + [
                "Review idle load balancers in US-East region",
                "Purchase Compute Savings Plans for consistent baseline usage"
            ]
        }

    def recalculate_tenant_costs(self, tenant_id: str) -> Dict[str, Any]:
        """Trigger a fresh cost calculation for a specific tenant."""
        return {
            "currentMonthCost": round(random.uniform(500, 1500), 2),
            "forecastedCost": round(random.uniform(1600, 2500), 2),
            "potentialSavings": round(random.uniform(100, 500), 2),
            "costBreakdown": [
                {"service": "Compute", "cost": round(random.uniform(300, 800), 2)},
                {"service": "Storage", "cost": round(random.uniform(100, 300), 2)},
                {"service": "Database", "cost": round(random.uniform(150, 400), 2)},
                {"service": "Network", "cost": round(random.uniform(50, 150), 2)},
                {"service": "AI Services", "cost": round(random.uniform(50, 200), 2)}
            ],
            "costTrend": self._generate_random_trend()
        }

    def _generate_random_trend(self):
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
        trend = []
        for m in months:
            actual = random.uniform(800, 1200)
            trend.append({
                "month": m,
                "actual": round(actual, 2),
                "forecast": round(actual * random.uniform(0.9, 1.1), 2)
            })
        return trend
        
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
