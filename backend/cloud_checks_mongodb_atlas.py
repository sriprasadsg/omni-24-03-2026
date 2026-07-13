from typing import List, Dict, Any

MONGODB_ATLAS_CHECKS = [
    {
        "id": "atlas-net-001",
        "name": "No 0.0.0.0/0 IP access list",
        "description": "Ensure no IP access list entries allow access from all IP addresses.",
        "provider": "mongodb_atlas",
        "service": "database",
        "severity": "critical",
        "frameworks": ["NIST-SC-7", "CIS-MongoDB-2.1"],
        "remediation": "Remove 0.0.0.0/0 from the project IP access list and add specific allowed CIDRs."
    },
    {
        "id": "atlas-enc-002",
        "name": "Encryption at rest enabled",
        "description": "Ensure encryption at rest is enabled for all database deployments.",
        "provider": "mongodb_atlas",
        "service": "database",
        "severity": "high",
        "frameworks": ["NIST-SC-28", "HIPAA-164.312"],
        "remediation": "Enable encryption at rest in the MongoDB Atlas project configuration."
    },
    {
        "id": "atlas-audit-003",
        "name": "Database auditing enabled",
        "description": "Ensure database auditing is enabled to track access and actions.",
        "provider": "mongodb_atlas",
        "service": "database",
        "severity": "medium",
        "frameworks": ["NIST-AU-2", "ISO27001-A.12.4.1"],
        "remediation": "Enable database auditing for all Atlas clusters in the project."
    },
    {
        "id": "atlas-vpc-004",
        "name": "Private network access enabled",
        "description": "Ensure network access is restricted via VPC peering or Private Link.",
        "provider": "mongodb_atlas",
        "service": "network",
        "severity": "high",
        "frameworks": ["NIST-SC-7", "SOC2-CC6.6"],
        "remediation": "Configure VPC peering or AWS PrivateLink for secure database access."
    },
    {
        "id": "atlas-role-005",
        "name": "Least privilege roles enforced",
        "description": "Ensure project and database users follow the principle of least privilege.",
        "provider": "mongodb_atlas",
        "service": "identity",
        "severity": "medium",
        "frameworks": ["NIST-AC-6", "PCI-DSS-7.1"],
        "remediation": "Review and restrict MongoDB Atlas user roles to only necessary privileges."
    },
    {
        "id": "atlas-backup-006",
        "name": "Automated backups with PITR",
        "description": "Ensure automated backups with Point-in-Time Recovery are enabled.",
        "provider": "mongodb_atlas",
        "service": "database",
        "severity": "medium",
        "frameworks": ["NIST-CP-9", "ISO27001-A.17.1.2"],
        "remediation": "Enable automated backups and PITR for all production Atlas clusters."
    }
]
