"""
Patch Management Service - Enterprise Features
Handles CVE/CVSS scoring, inventory management, and patch prioritization
"""

import aiohttp
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any


class PatchManagementService:
    """Enterprise patch management with CVE/CVSS integration"""
    
    def __init__(self, nvd_api_key: Optional[str] = None):
        self.nvd_api_key = nvd_api_key
        self.nvd_base_url = "https://services.nvd.nist.gov/rest/json/cves/2.0"
        self.epss_base_url = "https://api.first.org/data/v1/epss"
    
    async def get_cve_details(self, cve_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch CVE details from NVD API
        Returns CVSS scores, severity, description, etc.
        """
        try:
            headers = {}
            if self.nvd_api_key:
                headers["apiKey"] = self.nvd_api_key
            
            async with aiohttp.ClientSession() as session:
                url = f"{self.nvd_base_url}?cveId={cve_id}"
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("vulnerabilities"):
                            vuln = data["vulnerabilities"][0]
                            cve_data = vuln.get("cve", {})
                            
                            # Extract CVSS scores
                            metrics = cve_data.get("metrics", {})
                            cvss_v3 = metrics.get("cvssMetricV31", [{}])[0].get("cvssData", {}) if metrics.get("cvssMetricV31") else {}
                            cvss_v2 = metrics.get("cvssMetricV2", [{}])[0].get("cvssData", {}) if metrics.get("cvssMetricV2") else {}
                            
                            return {
                                "cve_id": cve_id,
                                "description": cve_data.get("descriptions", [{}])[0].get("value", ""),
                                "published_date": cve_data.get("published"),
                                "last_modified": cve_data.get("lastModified"),
                                "cvss_v3_score": cvss_v3.get("baseScore"),
                                "cvss_v3_severity": cvss_v3.get("baseSeverity"),
                                "cvss_v3_vector": cvss_v3.get("vectorString"),
                                "cvss_v2_score": cvss_v2.get("baseScore"),
                                "cvss_v2_severity": cvss_v2.get("baseSeverity"),
                                "references": [ref.get("url") for ref in cve_data.get("references", [])],
                                "weaknesses": [w.get("description", [{}])[0].get("value") for w in cve_data.get("weaknesses", [])]
                            }
            return None
        except Exception as e:
            print(f"Error fetching CVE {cve_id}: {e}")
            return None
    
    async def get_epss_score(self, cve_id: str) -> Optional[Dict[str, Any]]:
        """
        Get EPSS (Exploit Prediction Scoring System) for a CVE
        Returns probability of exploitation in next 30 days
        """
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.epss_base_url}?cve={cve_id}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("data"):
                            epss_data = data["data"][0]
                            return {
                                "cve_id": cve_id,
                                "epss_score": float(epss_data.get("epss", 0)),
                                "epss_percentile": float(epss_data.get("percentile", 0)),
                                "date": epss_data.get("date")
                            }
            return None
        except Exception as e:
            print(f"Error fetching EPSS for {cve_id}: {e}")
            return None
    
    def calculate_patch_priority(self, cvss_score: float, epss_score: float, 
                                 business_criticality: float, asset_count: int) -> float:
        """
        Calculate intelligent patch priority score (0-100)
        
        Factors:
        - CVSS score (0-10) - vulnerability severity
        - EPSS score (0-1) - exploit probability  
        - Business criticality (0-10) - asset importance
        - Asset count - number of affected systems
        
        Returns priority score 0-100 (higher = more urgent)
        """
        # Normalize inputs
        cvss_normalized = cvss_score / 10.0  # 0-1
        epss_normalized = epss_score  # already 0-1
        criticality_normalized = business_criticality / 10.0  # 0-1
        asset_impact = min(asset_count / 100.0, 1.0)  # Cap at 100 assets
        
        # Weighted calculation
        priority = (
            cvss_normalized * 0.35 +      # 35% weight on severity
            epss_normalized * 0.30 +       # 30% weight on exploit likelihood
            criticality_normalized * 0.25 + # 25% weight on business impact
            asset_impact * 0.10            # 10% weight on scale
        ) * 100
        
        return round(priority, 2)
    
    def determine_severity_from_cvss(self, cvss_score: float) -> str:
        """Map CVSS score to severity level"""
        if cvss_score >= 9.0:
            return "Critical"
        elif cvss_score >= 7.0:
            return "High"
        elif cvss_score >= 4.0:
            return "Medium"
        else:
            return "Low"
    def calculate_patch_sla_hours(self, severity: str, framework: str = "SOC2") -> int:
        """
        Calculate patch SLA based on severity and compliance framework
        
        Returns: Number of hours to patch
        """
        sla_mappings = {
            "SOC2": {
                "Critical": 72,   # 3 days
                "High": 168,      # 7 days
                "Medium": 720,    # 30 days
                "Low": 2160       # 90 days
            },
            "PCI-DSS": {
                "Critical": 24,   # 1 day
                "High": 72,       # 3 days
                "Medium": 168,    # 7 days
                "Low": 720        # 30 days
            },
            "HIPAA": {
                "Critical": 48,   # 2 days
                "High": 168,      # 7 days
                "Medium": 720,    # 30 days
                "Low": 2160       # 90 days
            },
            "ISO27001": {
                "Critical": 72,   # 3 days
                "High": 336,      # 14 days
                "Medium": 720,    # 30 days
                "Low": 2160       # 90 days
            }
        }
        
        return sla_mappings.get(framework, sla_mappings["SOC2"]).get(severity, 720)
    
    async def enrich_patch_with_intelligence(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich patch data with CVE/CVSS/EPSS intelligence
        
        Input patch should have: id, name, severity, affected_assets, cve_ids (optional)
        Returns enriched patch with intelligence data
        """
        enriched = patch.copy()
        
        # If patch has CVE IDs, fetch intelligence
        cve_ids = patch.get("cve_ids", [])
        if not cve_ids and "CVE-" in patch.get("name", ""):
            # Try to extract CVE from patch name
            import re
            cve_pattern = r'CVE-\d{4}-\d{4,7}'
            cve_ids = re.findall(cve_pattern, patch["name"])
        
        if cve_ids:
            # Fetch CVE and EPSS data in parallel
            cve_tasks = [self.get_cve_details(cve_id) for cve_id in cve_ids[:5]]  # Limit to 5 CVEs
            epss_tasks = [self.get_epss_score(cve_id) for cve_id in cve_ids[:5]]
            
            cve_results = await asyncio.gather(*cve_tasks, return_exceptions=True)
            epss_results = await asyncio.gather(*epss_tasks, return_exceptions=True)
            
            # Filter out errors
            cve_data = [r for r in cve_results if r and not isinstance(r, Exception)]
            epss_data = [r for r in epss_results if r and not isinstance(r, Exception)]
            
            if cve_data:
                # Use highest CVSS score
                cvss_scores = [c.get("cvss_v3_score") or c.get("cvss_v2_score") or 0 for c in cve_data]
                max_cvss = max(cvss_scores) if cvss_scores else None
                
                enriched["cve_details"] = cve_data
                enriched["cvss_score"] = max_cvss
                if max_cvss:
                    enriched["severity"] = self.determine_severity_from_cvss(max_cvss)
                    enriched["cvss_severity"] = self.determine_severity_from_cvss(max_cvss)
            
            if epss_data:
                # Use highest EPSS score
                epss_scores = [e.get("epss_score", 0) for e in epss_data]
                max_epss = max(epss_scores) if epss_scores else 0
                
                enriched["epss_details"] = epss_data
                enriched["epss_score"] = max_epss
                enriched["exploit_probability"] = f"{max_epss * 100:.2f}%"
            
            # Calculate priority score
            cvss_score = enriched.get("cvss_score", 5.0)
            epss_score = enriched.get("epss_score", 0.1)
            asset_count = len(patch.get("affected_assets", []))
            business_criticality = 7.0  # Default, could be per-asset
            
            enriched["priority_score"] = self.calculate_patch_priority(
                cvss_score, epss_score, business_criticality, asset_count
            )
            
            # Calculate SLA
            severity = enriched.get("severity", "Medium")
            enriched["sla_hours"] = self.calculate_patch_sla_hours(severity)
            enriched["patch_deadline"] = datetime.now(timezone.utc).timestamp() + (enriched["sla_hours"] * 3600)
        
        return enriched

    def check_software_sla(self, package: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check if an outdated package has breached its SLA.
        
        SLA Criteria (Default):
        - Major version gap: 7 days
        - Minor version gap: 14 days
        - Patch/Other: 30 days
        """
        update_status = package.get("update_status", "unknown")
        # In a real system, we'd use the 'detected_at' timestamp.
        # For now, we use current time if not present.
        detected_at = package.get("detected_at")
        if not detected_at:
             # If we don't know when it was first detected, we can't accurately check SLA.
             # We return a 'warning' status.
             return {"breached": False, "days_remaining": "N/A", "status": "tracking"}

        detected_dt = datetime.fromisoformat(detected_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        age_days = (now - detected_dt).days

        sla_days = 30
        if update_status == "major": sla_days = 7
        elif update_status == "minor": sla_days = 14

        breached = age_days > sla_days
        days_remaining = sla_days - age_days

        return {
            "breached": breached,
            "sla_days": sla_days,
            "age_days": age_days,
            "days_remaining": days_remaining,
            "status": "breached" if breached else "compliant"
        }


# Singleton instance
_patch_service = None

def get_patch_service(nvd_api_key: Optional[str] = None) -> PatchManagementService:
    """Get or create patch management service singleton"""
    global _patch_service
    if _patch_service is None:
        _patch_service = PatchManagementService(nvd_api_key)
    return _patch_service
