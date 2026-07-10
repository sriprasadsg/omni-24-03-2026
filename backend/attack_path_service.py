import logging
from datetime import datetime, timezone
import uuid
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class AttackPathService:
    def __init__(self, db=None):
        self.db = db

    async def ensure_attack_paths_collection(self):
        if not self.db:
            return
        collections = await self.db.list_collection_names()
        if "attack_paths" not in collections:
            await self.db.create_collection("attack_paths")

    async def get_attack_paths(self, tenant_id: str = None) -> List[Dict[str, Any]]:
        """
        Builds real attack paths by correlating assets and open vulnerabilities.
        Each path represents an exploit chain: vulnerable entry point → internal hop → target asset.
        Falls back to stored attack_paths collection if direct calculation is unavailable.
        """
        if not self.db:
            return []

        query = {"tenantId": tenant_id} if tenant_id else {}

        # 1. Check for already-computed paths stored in the collection
        stored = await self.db.attack_paths.find(query, {"_id": 0}).sort(
            "timestamp", -1
        ).to_list(length=50)
        if stored:
            return stored

        # 2. Build paths from real assets + open vulnerabilities
        assets = await self.db.assets.find(query, {"_id": 0}).to_list(length=500)
        vulns = await self.db.vulnerabilities.find(
            {**query, "status": {"$ne": "Fixed"}},
            {"_id": 0}
        ).to_list(length=500)

        if not assets and not vulns:
            # Check cspm_findings as alternative vulnerability source
            vulns = await self.db.cspm_findings.find(
                {**query, "status": {"$nin": ["Resolved", "Suppressed"]}},
                {"_id": 0}
            ).to_list(length=200)

        # Index assets by id/name for quick lookup
        asset_map: Dict[str, dict] = {}
        for a in assets:
            key = a.get("id") or a.get("name") or str(a.get("_id", ""))
            asset_map[key] = a

        # Group vulnerabilities by affected asset
        vuln_by_asset: Dict[str, List[dict]] = {}
        for v in vulns:
            asset_key = v.get("assetId") or v.get("asset_id") or v.get("resourceId") or "unknown"
            vuln_by_asset.setdefault(asset_key, []).append(v)

        # Tag assets as internet-facing (entry points) vs internal (targets)
        entry_assets = [a for a in assets if a.get("isInternetFacing") or a.get("type") in ("Web Server", "Load Balancer", "VPN Gateway", "Firewall")]
        target_assets = [a for a in assets if a.get("type") in ("Database", "Storage", "Domain Controller", "Secret Manager", "Data Warehouse") or a.get("sensitivityLevel") in ("High", "Critical")]

        if not entry_assets:
            entry_assets = assets[:len(assets)//2] or assets
        if not target_assets:
            target_assets = assets[len(assets)//2:] or assets

        paths = []
        seen_pairs: set = set()

        for entry in entry_assets[:5]:
            entry_vulns = vuln_by_asset.get(entry.get("id") or entry.get("name"), [])
            if not entry_vulns and not target_assets:
                continue

            for target in target_assets[:3]:
                pair = (entry.get("id"), target.get("id"))
                if pair in seen_pairs or entry.get("id") == target.get("id"):
                    continue
                seen_pairs.add(pair)

                # Choose the highest-severity vuln on the entry point
                entry_cve = "Unknown"
                if entry_vulns:
                    sev_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
                    best = sorted(entry_vulns, key=lambda v: sev_order.get(v.get("severity", "Low"), 99))
                    entry_cve = best[0].get("cveId") or best[0].get("id") or best[0].get("title") or "CVE-Unknown"

                entry_name = entry.get("name") or entry.get("hostname") or entry.get("id", "Entry Asset")
                target_name = target.get("name") or target.get("hostname") or target.get("id", "Target Asset")
                hop_name = "Internal Gateway"

                path_id = str(uuid.uuid4())
                node_e = {"id": f"{path_id}-0", "label": entry_name, "type": "entry", "risk": 0.85, "assetId": entry.get("id")}
                node_h = {"id": f"{path_id}-1", "label": hop_name, "type": "hop", "risk": 0.5}
                node_t = {"id": f"{path_id}-2", "label": target_name, "type": "target", "risk": 0.95, "assetId": target.get("id")}

                # Probability based on number of open vulns and severity
                crit_count = sum(1 for v in entry_vulns if v.get("severity") in ("Critical", "High"))
                probability = min(0.95, 0.2 + (crit_count * 0.15))

                path = {
                    "id": path_id,
                    "tenantId": tenant_id,
                    "name": f"{entry_name} → {target_name}",
                    "nodes": [node_e, node_h, node_t],
                    "edges": [
                        {"source": node_e["id"], "target": node_h["id"], "vulnerability": entry_cve},
                        {"source": node_h["id"], "target": node_t["id"], "vulnerability": "Lateral Movement"},
                    ],
                    "probability": round(probability, 2),
                    "impact": "Critical" if target.get("sensitivityLevel") == "Critical" else "High",
                    "openVulnerabilities": len(entry_vulns),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "simulated": False,
                }
                paths.append(path)

                # Persist computed path so subsequent reads are fast
                try:
                    await self.db.attack_paths.update_one(
                        {"id": path_id},
                        {"$set": path},
                        upsert=True
                    )
                except Exception as e:
                    logger.debug("Failed to persist attack path %s: %s", path_id, e)

        # No real data available — seed representative demo paths so the dashboard is not blank
        if not paths:
            paths = self._seed_demo_paths(tenant_id)
            for p in paths:
                try:
                    await self.db.attack_paths.update_one({"id": p["id"]}, {"$set": p}, upsert=True)
                except Exception as e:
                    logger.debug("Failed to persist demo attack path: %s", e)

        return paths

    @staticmethod
    def _seed_demo_paths(tenant_id: str) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc).isoformat()
        scenarios = [
            {
                "name": "Exposed API Gateway → Production Database",
                "entry": ("api-gateway-prod", "Public Asset", "CVE-2024-1234"),
                "hop": "Internal Kubernetes Cluster",
                "target": ("prod-postgres-db", "Crown Jewel"),
                "probability": 0.82,
                "impact": "Critical",
                "open_vulns": 4,
            },
            {
                "name": "VPN Endpoint → Domain Controller",
                "entry": ("vpn-endpoint-01", "Public Asset", "CVE-2023-20269"),
                "hop": "Corporate Network Segment",
                "target": ("dc-primary", "Crown Jewel"),
                "probability": 0.67,
                "impact": "Critical",
                "open_vulns": 2,
            },
            {
                "name": "Web Server → Secret Manager",
                "entry": ("web-app-server", "Public Asset", "CVE-2024-5678"),
                "hop": "Internal Service Mesh",
                "target": ("aws-secrets-manager", "Crown Jewel"),
                "probability": 0.54,
                "impact": "High",
                "open_vulns": 3,
            },
        ]
        paths = []
        for s in scenarios:
            pid = str(uuid.uuid4())
            node_e = {"id": f"{pid}-0", "label": s["entry"][0], "type": s["entry"][1], "risk": 0.85}
            node_h = {"id": f"{pid}-1", "label": s["hop"], "type": "Internal Service", "risk": 0.50}
            node_t = {"id": f"{pid}-2", "label": s["target"][0], "type": s["target"][1], "risk": 0.95}
            paths.append({
                "id": pid,
                "tenantId": tenant_id,
                "name": s["name"],
                "nodes": [node_e, node_h, node_t],
                "edges": [
                    {"source": node_e["id"], "target": node_h["id"], "vulnerability": s["entry"][2]},
                    {"source": node_h["id"], "target": node_t["id"], "vulnerability": "Lateral Movement"},
                ],
                "probability": s["probability"],
                "impact": s["impact"],
                "openVulnerabilities": s["open_vulns"],
                "timestamp": now,
                "simulated": True,
            })
        return paths


_attack_path_service = None

def get_attack_path_service(db=None):
    global _attack_path_service
    if _attack_path_service is None or db is not None:
        _attack_path_service = AttackPathService(db)
    return _attack_path_service
