from datetime import datetime, timedelta, timezone
import random
from typing import Dict, List, Any

class BiAnalyticsService:
    def __init__(self, db):
        self.db = db

    async def ensure_bi_metrics_collection(self):
        """Ensure BI metrics collection exists (no seed data)"""
        if not self.db:
            return
            
        collections = await self.db.list_collection_names()
        
        # Create collection if it doesn't exist, but don't seed data
        if "bi_metrics" not in collections:
            await self.db.create_collection("bi_metrics")

    def _generate_metrics(self) -> Dict[str, Any]:
        """Generate BI metrics data"""
        # 1. Risk Profile (Radar Chart Data)
        risk_profile = [
            {"subject": "Security", "A": random.randint(60, 95), "fullMark": 100},
            {"subject": "Compliance", "A": random.randint(70, 98), "fullMark": 100},
            {"subject": "Cost Efficiency", "A": random.randint(50, 90), "fullMark": 100},
            {"subject": "Performance", "A": random.randint(80, 99), "fullMark": 100},
            {"subject": "Reliability", "A": random.randint(75, 95), "fullMark": 100},
        ]

        # 2. Predictive Trends (Composed Chart Data: Historical + Forecast)
        now = datetime.now(timezone.utc)
        trends = []
        for i in range(-6, 4):  # 6 months back, 3 months forward
            date = now + timedelta(days=i*30)
            month_str = date.strftime("%b %Y")
            
            # Historical data (i <= 0)
            actual = random.randint(70, 90) if i <= 0 else None
            # Forecasted data (i >= 0)
            forecast = 80 + (i * 2) + random.randint(-2, 2)
            
            trends.append({
                "name": month_str,
                "actual": actual,
                "forecast": forecast,
                "isForecast": i > 0
            })

        # 3. Efficiency Stats
        efficiency = {
            "mttr": round(random.uniform(2.5, 8.0), 1),
            "automation_rate": random.randint(65, 92),
            "patch_success_rate": random.randint(88, 99),
            "remediation_velocity": round(random.uniform(10, 25), 1)
        }

        # 4. Asset Distribution (Treemap Data)
        asset_distribution = [
            {
                "name": "Cloud Resources",
                "children": [
                    {"name": "AWS EC2", "size": random.randint(100, 500)},
                    {"name": "Azure VM", "size": random.randint(50, 200)},
                    {"name": "GCP Compute", "size": random.randint(30, 150)},
                ]
            },
            {
                "name": "On-Premise",
                "children": [
                    {"name": "Windows Server", "size": random.randint(200, 600)},
                    {"name": "Linux Nodes", "size": random.randint(300, 800)},
                    {"name": "Workstations", "size": random.randint(500, 1200)},
                ]
            }
        ]

        return {
            "risk_profile": risk_profile,
            "trends": trends,
            "efficiency": efficiency,
            "asset_distribution": asset_distribution,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    async def get_bi_metrics(self, tenant_id: str = None) -> Dict[str, Any]:
        """
        Get advanced BI metrics from MongoDB.
        """
        await self.ensure_bi_metrics_collection()
        
        # Get latest metrics from MongoDB
        latest = await self.db.bi_metrics.find_one({}, {"_id": 0}, sort=[("timestamp", -1)])
        
        if not latest:
            # Return empty structure instead of generating mock data
            return {
                "risk_profile": [],
                "trends": [],
                "efficiency": {"mttr": 0, "automation_rate": 0, "patch_success_rate": 0, "remediation_velocity": 0},
                "asset_distribution": [],
                "message": "No BI metrics available. Connect data sources."
            }
        
        return latest

def get_bi_analytics_service(db):
    return BiAnalyticsService(db)
