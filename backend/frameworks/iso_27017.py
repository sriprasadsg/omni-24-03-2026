"""ISO/IEC 27017:2015 — Cloud Security Controls."""
from __future__ import annotations
from typing import Any, Dict, List
FRAMEWORK_ID = "iso_27017"
FRAMEWORK_NAME = "ISO/IEC 27017:2015"
FRAMEWORK_VERSION = "2015"
CONTROLS: List[Dict[str, Any]] = [
    {"id": "ISO27017-6.3.1", "theme": "Cloud Shared Responsibilities", "check_type": "documents_exist", "title": "Shared roles and responsibilities", "description": "Cloud service roles and responsibilities shall be defined and documented."},
    {"id": "ISO27017-6.3.2", "theme": "Cloud Shared Responsibilities", "check_type": "contracts_signed", "title": "Removal of cloud service customer assets", "description": "Provide procedure for removal of customer assets."},
    {"id": "ISO27017-7.1.1", "theme": "Asset Management", "check_type": "inventory", "title": "Virtual asset inventory", "description": "Maintain inventory of virtual assets."},
    {"id": "ISO27017-7.1.2", "theme": "Asset Management", "check_type": "baseline_config", "title": "Virtual asset configuration", "description": "Baseline virtual asset configurations."},
    {"id": "ISO27017-7.1.3", "theme": "Asset Management", "check_type": "disposal_verified", "title": "Virtual asset disposal", "description": "Verify disposal of virtual assets."},
    {"id": "ISO27017-8.1.1", "theme": "Access Control", "check_type": "rbac_configured", "title": "Customer access to cloud management", "description": "Restrict customer access to management interfaces."},
    {"id": "ISO27017-8.1.2", "theme": "Access Control", "check_type": "separation_of_duties", "title": "Separation of virtual environments", "description": "Separate virtual environments per customer."},
    {"id": "ISO27017-8.1.3", "theme": "Access Control", "check_type": "least_privilege", "title": "Virtual machine hardening", "description": "Harden and restrict virtual machines."},
    {"id": "ISO27017-9.1.1", "theme": "Cryptography", "check_type": "disk_encrypted", "title": "Virtual disk encryption", "description": "Encrypt virtual disks for confidentiality."},
    {"id": "ISO27017-9.1.2", "theme": "Cryptography", "check_type": "kms_configured", "title": "Key management for cloud", "description": "Manage keys for cloud encryption."},
    {"id": "ISO27017-10.1.1", "theme": "Operations", "check_type": "backup_completed", "title": "Backup of virtual machines", "description": "Back up virtual machines regularly."},
    {"id": "ISO27017-10.1.2", "theme": "Operations", "check_type": "backup_dr", "title": "Availability of cloud services", "description": "Maintain availability of cloud services."},
    {"id": "ISO27017-11.1.1", "theme": "Network Security", "check_type": "vlan_segmentation", "title": "Virtual network segmentation", "description": "Segment virtual networks between customers."},
    {"id": "ISO27017-11.1.2", "theme": "Network Security", "check_type": "fw_blocked", "title": "Virtual firewall", "description": "Deploy virtual firewall per customer."},
    {"id": "ISO27017-11.1.3", "theme": "Network Security", "check_type": "tls_enabled", "title": "Cloud service network protection", "description": "Protect cloud service networks."},
    {"id": "ISO27017-12.1.1", "theme": "Operations Security", "check_type": "audit_log_volume", "title": "Monitoring of cloud services", "description": "Monitor cloud services for security events."},
    {"id": "ISO27017-12.1.2", "theme": "Operations Security", "check_type": "logs_shipped", "title": "Collection of customer audit logs", "description": "Provide customers access to their audit logs."},
    {"id": "ISO27017-13.1.1", "theme": "Incident Management", "check_type": "incident_handling", "title": "Incident reporting for cloud", "description": "Define cloud incident reporting procedures."},
    {"id": "ISO27017-13.1.2", "theme": "Incident Management", "check_type": "incident_reporting", "title": "Customer breach notification", "description": "Notify customers of security breaches."},
    {"id": "ISO27017-14.1.1", "theme": "Compliance", "check_type": "assessments_performed", "title": "Cloud service compliance", "description": "Comply with regulatory requirements for cloud services."},
    {"id": "ISO27017-14.1.2", "theme": "Compliance", "check_type": "pen_testing", "title": "Independent cloud audits", "description": "Facilitate independent audits of cloud services."},
    {"id": "ISO27017-15.1.1", "theme": "Supply Chain", "check_type": "supplier_assessment", "title": "Cloud supply chain", "description": "Manage cloud service supply chain."},
    {"id": "ISO27017-15.1.2", "theme": "Supply Chain", "check_type": "supplier_monitoring", "title": "Subcontractors", "description": "Monitor and control cloud subcontractors."},
    {"id": "ISO27017-16.1.1", "theme": "Interoperability", "check_type": "tests_performed", "title": "Data portability", "description": "Support data portability and service migration."},
]
