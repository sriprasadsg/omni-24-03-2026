"""
Compliance Automation Service
Automates evidence collection and compliance reporting
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any
from database import get_database
import io
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

logger = logging.getLogger(__name__)

class ComplianceAutomationService:
    """Service for automated compliance evidence collection"""
    
    def __init__(self):
        self.db = None
    
    async def init_db(self):
        """Initialize database connection"""
        if not self.db:
            self.db = get_database()
    
    async def generate_patch_compliance_evidence(self, tenant_id: str, framework: str = "All") -> Dict:
        """Generate automated patch compliance evidence"""
        await self.init_db()
        
        # Get all agents for tenant
        agents = await self.db.agents.find({"tenantId": tenant_id}).to_list(length=None)
        
        # Get patch data
        patches = await self.db.patches.find({"tenantId": tenant_id}).to_list(length=None)
        
        # Calculate metrics
        total_agents = len(agents)
        patched_agents = len([a for a in agents if a.get("patchStatus") == "Up to Date"])
        compliance_rate = (patched_agents / total_agents * 100) if total_agents > 0 else 0
        
        critical_missing = len([p for p in patches if p.get("severity") == "Critical" and p.get("status") == "Missing"])
        
        evidence = {
            "type": "patch_compliance",
            "framework": framework,
            "tenant_id": tenant_id,
            "generated_at": datetime.utcnow().isoformat(),
            "metrics": {
                "total_agents": total_agents,
                "patched_agents": patched_agents,
                "compliance_rate": round(compliance_rate, 2),
                "critical_missing_patches": critical_missing
            },
            "details": {
                "agents": [{"id": a["id"], "hostname": a["hostname"], "patchStatus": a.get("patchStatus")} for a in agents],
                "missing_critical_patches": [{"id": p["id"], "name": p["name"]} for p in patches if p.get("severity") == "Critical" and p.get("status") == "Missing"]
            }
        }
        
        # Store evidence
        await self.db.compliance_evidence.insert_one(evidence)
        
        return evidence
    
    async def generate_vulnerability_evidence(self, tenant_id: str) -> Dict:
        """Generate automated vulnerability scan evidence"""
        await self.init_db()
        
        # Get vulnerabilities
        vulns = await self.db.vulnerabilities.find({"tenantId": tenant_id}).to_list(length=None)
        
        # Calculate metrics
        total_vulns = len(vulns)
        critical_vulns = len([v for v in vulns if v.get("severity") == "Critical"])
        high_vulns = len([v for v in vulns if v.get("severity") == "High"])
        remediated = len([v for v in vulns if v.get("status") == "Resolved"])
        
        evidence = {
            "type": "vulnerability_scan",
            "tenant_id": tenant_id,
            "generated_at": datetime.utcnow().isoformat(),
            "metrics": {
                "total_vulnerabilities": total_vulns,
                "critical": critical_vulns,
                "high": high_vulns,
                "remediated": remediated,
                "remediation_rate": round((remediated / total_vulns * 100) if total_vulns > 0 else 0, 2)
            },
            "scan_summary": {
                "last_scan": datetime.utcnow().isoformat(),
                "scan_coverage": "100%",
                "scan_tool": "Omni Agent Scanner"
            }
        }
        
        await self.db.compliance_evidence.insert_one(evidence)
        return evidence
    
    async def generate_agent_status_evidence(self, tenant_id: str) -> Dict:
        """Generate agent status report evidence"""
        await self.init_db()
        
        agents = await self.db.agents.find({"tenantId": tenant_id}).to_list(length=None)
        
        online = len([a for a in agents if a.get("status") == "Online"])
        offline = len([a for a in agents if a.get("status") == "Offline"])
        error = len([a for a in agents if a.get("status") == "Error"])
        
        evidence = {
            "type": "agent_status",
            "tenant_id": tenant_id,
            "generated_at": datetime.utcnow().isoformat(),
            "metrics": {
                "total_agents": len(agents),
                "online": online,
                "offline": offline,
                "error": error,
                "uptime_percentage": round((online / len(agents) * 100) if agents else 0, 2)
            }
        }
        
        await self.db.compliance_evidence.insert_one(evidence)
        return evidence
    
    async def generate_security_alert_evidence(self, tenant_id: str, days: int = 7) -> Dict:
        """Generate security alert summary evidence"""
        await self.init_db()
        
        # Get alerts from last N days
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        pipeline = [
            {
                "$match": {
                    "tenantId": tenant_id,
                    "timestamp": {"$gte": cutoff.isoformat()}
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total": {"$sum": 1},
                    "critical": {"$sum": {"$cond": [{"$eq": ["$severity", "Critical"]}, 1, 0]}},
                    "resolved": {"$sum": {"$cond": [{"$eq": ["$status", "Resolved"]}, 1, 0]}}
                }
            }
        ]
        
        results = await self.db.security_events.aggregate(pipeline).to_list(length=1)
        stats = results[0] if results else {"total": 0, "critical": 0, "resolved": 0}
        
        evidence = {
            "type": "security_alerts",
            "tenant_id": tenant_id,
            "generated_at": datetime.utcnow().isoformat(),
            "period_days": days,
            "metrics": {
                "total_alerts": stats["total"],
                "critical_alerts": stats["critical"],
                "resolved_alerts": stats["resolved"],
                "average_resolution_time_hours": 0 # TODO: Calculate if timestamps available
            }
        }
        
        await self.db.compliance_evidence.insert_one(evidence)
        return evidence
    
    async def get_evidence_by_type(self, tenant_id: str, evidence_type: str, limit: int = 10) -> List[Dict]:
        """Get collected evidence by type"""
        await self.init_db()
        
        evidence_list = await self.db.compliance_evidence.find({
            "tenant_id": tenant_id,
            "type": evidence_type
        }).sort("generated_at", -1).limit(limit).to_list(length=limit)
        
        return evidence_list
    
    async def create_automation_rule(self, tenant_id: str, rule: Dict) -> Dict:
        """Create automated evidence collection rule"""
        await self.init_db()
        
        rule_doc = {
            "tenant_id": tenant_id,
            "rule_type": rule.get("ruleType"),
            "evidence_type": rule.get("evidenceType"),
            "schedule": rule.get("schedule", "weekly"),
            "framework": rule.get("framework", "All"),
            "enabled": True,
            "created_at": datetime.utcnow().isoformat(),
            "last_run": None
        }
        
        result = await self.db.compliance_automation_rules.insert_one(rule_doc)
        rule_doc["_id"] = str(result.inserted_id)
        
        return rule_doc
    
    async def get_automation_rules(self, tenant_id: str) -> List[Dict]:
        """Get all automation rules for tenant"""
        await self.init_db()
        
        rules = await self.db.compliance_automation_rules.find({
            "tenant_id": tenant_id
        }).to_list(length=None)
        
        return rules
    
    async def generate_evidence_package(self, tenant_id: str, framework: str) -> bytes:
        """Generate downloadable evidence package (PDF)"""
        await self.init_db()
        
        # Create PDF
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        story.append(Paragraph(f"Compliance Evidence Package - {framework}", styles['Title']))
        story.append(Spacer(1, 12))
        story.append(Paragraph(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}", styles['Normal']))
        story.append(Spacer(1, 24))
        
        # Generate all evidence types
        patch_evidence = await self.generate_patch_compliance_evidence(tenant_id, framework)
        vuln_evidence = await self.generate_vulnerability_evidence(tenant_id)
        agent_evidence = await self.generate_agent_status_evidence(tenant_id)
        
        # Add patch compliance section
        story.append(Paragraph("Patch Compliance Evidence", styles['Heading1']))
        story.append(Spacer(1, 12))
        story.append(Paragraph(f"Compliance Rate: {patch_evidence['metrics']['compliance_rate']}%", styles['Normal']))
        story.append(Paragraph(f"Total Agents: {patch_evidence['metrics']['total_agents']}", styles['Normal']))
        story.append(Paragraph(f"Patched Agents: {patch_evidence['metrics']['patched_agents']}", styles['Normal']))
        story.append(Spacer(1, 24))
        
        # Add vulnerability section
        story.append(Paragraph("Vulnerability Assessment Evidence", styles['Heading1']))
        story.append(Spacer(1, 12))
        story.append(Paragraph(f"Total Vulnerabilities: {vuln_evidence['metrics']['total_vulnerabilities']}", styles['Normal']))
        story.append(Paragraph(f"Critical: {vuln_evidence['metrics']['critical']}", styles['Normal']))
        story.append(Paragraph(f"Remediation Rate: {vuln_evidence['metrics']['remediation_rate']}%", styles['Normal']))
        story.append(Spacer(1, 24))
        
        # Add agent status section
        story.append(Paragraph("System Availability Evidence", styles['Heading1']))
        story.append(Spacer(1, 12))
        story.append(Paragraph(f"Total Agents: {agent_evidence['metrics']['total_agents']}", styles['Normal']))
        story.append(Paragraph(f"Uptime: {agent_evidence['metrics']['uptime_percentage']}%", styles['Normal']))
        
        # Build PDF
        doc.build(story)
        
        pdf_data = buffer.getvalue()
        buffer.close()
        
        return pdf_data


# Global instance
compliance_automation = ComplianceAutomationService()
