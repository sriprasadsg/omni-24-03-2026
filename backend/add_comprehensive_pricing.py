"""
Add comprehensive service pricing for all platform features.
Adds 40 new services across all categories.
"""
import asyncio
from database import connect_to_mongo, get_database, close_mongo_connection

# Comprehensive service pricing list
SERVICES_TO_ADD = [
    # Security & Compliance (12 services)
    {
        "id": "soc_operations",
        "name": "Security Operations Center",
        "category": "Security",
        "unit": "per_agent_per_month",
        "price": 15.00,
        "description": "Real-time security monitoring and case management"
    },
    {
        "id": "soar_playbooks",
        "name": "SOAR Playbook Automation",
        "category": "Security",
        "unit": "per_unit_per_month",
        "price": 2.00,
        "description": "Automated security orchestration and response playbook executions"
    },
    {
        "id": "threat_intel",
        "name": "Threat Intelligence Feed",
        "category": "Security",
        "unit": "per_agent_per_month",
        "price": 10.00,
        "description": "Real-time threat intelligence integration and updates"
    },
    {
        "id": "cloud_security",
        "name": "Cloud Security Posture Management",
        "category": "Security",
        "unit": "per_unit_per_month",
        "price": 3.00,
        "description": "Cloud asset security monitoring and compliance"
    },
    {
        "id": "patch_management",
        "name": "Patch Management Service",
        "category": "Security",
        "unit": "per_agent_per_month",
        "price": 7.50,
        "description": "Automated patch deployment and vulnerability tracking"
    },
    {
        "id": "threat_hunting",
        "name": "Threat Hunting Platform",
        "category": "Security",
        "unit": "per_agent_per_month",
        "price": 12.00,
        "description": "Proactive threat detection and hunting capabilities"
    },
    {
        "id": "compliance_mgmt",
        "name": "Compliance Management",
        "category": "Security",
        "unit": "per_unit_per_month",
        "price": 50.00,
        "description": "Compliance framework monitoring and reporting"
    },
    {
        "id": "compliance_evidence",
        "name": "Compliance Evidence Collection",
        "category": "Security",
        "unit": "per_gb_per_month",
        "price": 0.50,
        "description": "Automated compliance evidence gathering and storage"
    },
    {
        "id": "audit_logging",
        "name": "Advanced Audit Logging",
        "category": "Security",
        "unit": "per_gb_per_month",
        "price": 0.30,
        "description": "Comprehensive audit trail storage and analysis"
    },
    {
        "id": "vulnerability_scanning",
        "name": "Vulnerability Scanning",
        "category": "Security",
        "unit": "per_unit_per_month",
        "price": 5.00,
        "description": "Automated vulnerability assessments per scan"
    },
    {
        "id": "security_analytics",
        "name": "Security Analytics Engine",
        "category": "Security",
        "unit": "per_agent_per_month",
        "price": 8.00,
        "description": "ML-powered security insights and anomaly detection"
    },
    {
        "id": "incident_response",
        "name": "Incident Response Module",
        "category": "Security",
        "unit": "per_unit_per_month",
        "price": 25.00,
        "description": "Guided incident response workflows and playbooks"
    },
    
    # Observability & Monitoring (9 services)
    {
        "id": "agent_fleet_mgmt",
        "name": "Agent Fleet Management",
        "category": "Infrastructure",
        "unit": "per_agent_per_month",
        "price": 3.00,
        "description": "Centralized agent lifecycle and configuration management"
    },
    {
        "id": "software_deployment",
        "name": "Software Deployment Hub",
        "category": "Infrastructure",
        "unit": "per_unit_per_month",
        "price": 1.50,
        "description": "Automated software distribution and updates"
    },
    {
        "id": "log_management",
        "name": "Log Explorer & Management",
        "category": "Observability",
        "unit": "per_gb_per_month",
        "price": 0.40,
        "description": "Centralized log aggregation, search, and analysis"
    },
    {
        "id": "asset_management",
        "name": "Asset Management Platform",
        "category": "Observability",
        "unit": "per_unit_per_month",
        "price": 2.00,
        "description": "IT asset discovery, tracking, and inventory management"
    },
    {
        "id": "distributed_tracing",
        "name": "Distributed Tracing",
        "category": "Observability",
        "unit": "per_gb_per_month",
        "price": 5.00,
        "description": "Application performance tracing and monitoring"
    },
    {
        "id": "network_observability",
        "name": "Network Observability",
        "category": "Observability",
        "unit": "per_agent_per_month",
        "price": 6.00,
        "description": "Network traffic analysis and monitoring"
    },
    {
        "id": "proactive_insights",
        "name": "AI-Powered Proactive Insights",
        "category": "Observability",
        "unit": "per_agent_per_month",
        "price": 9.00,
        "description": "Predictive analytics and intelligent recommendations"
    },
    {
        "id": "agent_remediation",
        "name": "Automated Agent Remediation",
        "category": "Observability",
        "unit": "per_unit_per_month",
        "price": 3.00,
        "description": "Self-healing agent capabilities and auto-remediation"
    },
    {
        "id": "metrics_monitoring",
        "name": "Infrastructure Metrics Monitoring",
        "category": "Observability",
        "unit": "per_agent_per_month",
        "price": 4.00,
        "description": "Real-time performance metrics and alerting"
    },
    
    # AI Governance (3 services)
    {
        "id": "ai_governance",
        "name": "AI Governance Platform",
        "category": "AI",
        "unit": "per_unit_per_month",
        "price": 50.00,
        "description": "AI model compliance, monitoring, and governance"
    },
    {
        "id": "ai_risk_mgmt",
        "name": "AI Risk Management",
        "category": "AI",
        "unit": "per_unit_per_month",
        "price": 30.00,
        "description": "AI risk assessment and mitigation strategies"
    },
    {
        "id": "ml_ops",
        "name": "MLOps Integration",
        "category": "AI",
        "unit": "per_unit_per_month",
        "price": 40.00,
        "description": "ML model deployment, monitoring, and lifecycle management"
    },
    
    # Automation (3 services)
    {
        "id": "workflow_automation",
        "name": "Workflow Automation Engine",
        "category": "Automation",
        "unit": "per_unit_per_month",
        "price": 0.50,
        "description": "Custom workflow orchestration and execution"
    },
    {
        "id": "automation_workflows",
        "name": "Pre-built Automation Workflows",
        "category": "Automation",
        "unit": "per_unit_per_month",
        "price": 15.00,
        "description": "Library of pre-built automation templates and workflows"
    },
    {
        "id": "api_automation",
        "name": "API Integration Platform",
        "category": "Automation",
        "unit": "per_request",
        "price": 0.01,
        "description": "Third-party service integrations and API orchestration"
    },
    
    # Developer Tools (4 services)
    {
        "id": "devsecops_dashboard",
        "name": "DevSecOps Dashboard",
        "category": "Developer",
        "unit": "per_user_per_month",
        "price": 25.00,
        "description": "Security-integrated development metrics and insights"
    },
    {
        "id": "developer_hub",
        "name": "Developer Portal",
        "category": "Developer",
        "unit": "per_user_per_month",
        "price": 15.00,
        "description": "Self-service developer workspace and documentation"
    },
    {
        "id": "ci_cd_integration",
        "name": "CI/CD Pipeline Integration",
        "category": "Developer",
        "unit": "per_unit_per_month",
        "price": 20.00,
        "description": "Continuous integration and deployment pipeline management"
    },
    {
        "id": "code_analysis",
        "name": "Security Code Analysis",
        "category": "Developer",
        "unit": "per_unit_per_month",
        "price": 30.00,
        "description": "Static and dynamic code security scanning"
    },
    
    # Advanced Platform (5 services)
    {
        "id": "dspm",
        "name": "Data Security Posture Management",
        "category": "Advanced",
        "unit": "per_unit_per_month",
        "price": 75.00,
        "description": "Data security posture management and classification"
    },
    {
        "id": "attack_path_analysis",
        "name": "Attack Path Analysis",
        "category": "Advanced",
        "unit": "per_agent_per_month",
        "price": 20.00,
        "description": "Automated attack vector and path identification"
    },
    {
        "id": "service_catalog",
        "name": "Service Catalog (IDP)",
        "category": "Advanced",
        "unit": "per_user_per_month",
        "price": 10.00,
        "description": "Internal developer platform and service catalog"
    },
    {
        "id": "dora_metrics",
        "name": "DORA Metrics Tracking",
        "category": "Advanced",
        "unit": "per_unit_per_month",
        "price": 35.00,
        "description": "DevOps Research and Assessment performance metrics"
    },
    {
        "id": "chaos_engineering",
        "name": "Chaos Engineering Platform",
        "category": "Advanced",
        "unit": "per_unit_per_month",
        "price": 50.00,
        "description": "Resilience testing and chaos experiment framework"
    },
    
    # General & Administration (4 services)
    {
        "id": "reporting_analytics",
        "name": "Advanced Reporting & Analytics",
        "category": "Analytics",
        "unit": "per_user_per_month",
        "price": 12.00,
        "description": "Custom reports, dashboards, and business intelligence"
    },
    {
        "id": "export_reports",
        "name": "Report Export Service",
        "category": "Analytics",
        "unit": "per_unit_per_month",
        "price": 1.00,
        "description": "PDF, CSV, and Excel report generation and export"
    },
    {
        "id": "api_access",
        "name": "API Key Management",
        "category": "Administration",
        "unit": "per_unit_per_month",
        "price": 5.00,
        "description": "Programmatic API access and key lifecycle management"
    },
    {
        "id": "role_management",
        "name": "Advanced Role Management",
        "category": "Administration",
        "unit": "per_unit_per_month",
        "price": 25.00,
        "description": "Fine-grained permission controls and RBAC management"
    }
]


async def add_comprehensive_services():
    """Add all comprehensive platform services to the database"""
    print("=" * 80)
    print("ADDING COMPREHENSIVE SERVICE PRICING")
    print("=" * 80)
    
    try:
        await connect_to_mongo()
        db = get_database()
        
        if not db:
            print("❌ Failed to connect to database")
            return
        
        print("✓ Connected to database\n")
        
        # Check existing services
        existing_count = await db.service_pricing.count_documents({})
        print(f"Current service count: {existing_count}")
        print(f"Services to add: {len(SERVICES_TO_ADD)}\n")
        
        print("-" * 80)
        print("ADDING SERVICES...")
        print("-" * 80)
        
        added_count = 0
        skipped_count = 0
        error_count = 0
        
        for service in SERVICES_TO_ADD:
            service_id = service["id"]
            service_name = service["name"]
            
            # Check if service already exists
            existing = await db.service_pricing.find_one({"id": service_id})
            
            if existing:
                skipped_count += 1
                print(f"⏭️  SKIP: {service_name} (ID: {service_id}) - Already exists")
            else:
                try:
                    await db.service_pricing.insert_one(service)
                    added_count += 1
                    print(f"✅ ADDED: {service_name} (${service['price']:.2f} {service['unit']})")
                except Exception as e:
                    error_count += 1
                    print(f"❌ ERROR: {service_name} - {e}")
        
        print("-" * 80)
        print("\n" + "=" * 80)
        print("ADDITION COMPLETE")
        print("=" * 80)
        print(f"Successfully added: {added_count}")
        print(f"Skipped (already exists): {skipped_count}")
        print(f"Errors: {error_count}")
        print("=" * 80)
        
        # Verify final count
        final_count = await db.service_pricing.count_documents({})
        print(f"\n✅ Total services in database: {final_count}")
        
        # Show breakdown by category
        print("\n" + "-" * 80)
        print("BREAKDOWN BY CATEGORY")
        print("-" * 80)
        
        categories = ["Infrastructure", "Software", "Security", "Observability", "AI", 
                      "Automation", "Developer", "Advanced", "Analytics", "Administration", "Support"]
        
        for category in categories:
            count = await db.service_pricing.count_documents({"category": category})
            if count > 0:
                print(f"{category}: {count} services")
        
        await close_mongo_connection()
        print("\nClosed MongoDB connection")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(add_comprehensive_services())
