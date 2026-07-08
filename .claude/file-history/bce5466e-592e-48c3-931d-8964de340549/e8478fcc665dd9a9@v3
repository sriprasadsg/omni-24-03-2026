"""Cloud Security Checks Engine — Prowler-style checks for AWS, Azure, GCP."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

_CC_SUPER_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}

# Check definitions: each entry is {id, name, description, provider, service, severity, frameworks, remediation}
CLOUD_CHECKS: List[Dict[str, Any]] = [
    # ─── AWS IAM ───────────────────────────────────────────────────────────────
    {"id": "aws-iam-001", "name": "Root account MFA enabled", "description": "AWS root account must have MFA enabled", "provider": "aws", "service": "iam", "severity": "critical", "frameworks": ["CIS-1.1", "NIST-IA-2", "PCI-8.3", "SOC2-CC6.1"], "remediation": "Enable MFA for the root account via IAM console."},
    {"id": "aws-iam-002", "name": "No root account access keys", "description": "Root account should not have active access keys", "provider": "aws", "service": "iam", "severity": "critical", "frameworks": ["CIS-1.4", "NIST-IA-5", "PCI-8.2"], "remediation": "Delete root account access keys in IAM console."},
    {"id": "aws-iam-003", "name": "MFA enabled for all IAM users", "description": "All IAM users with console access should have MFA", "provider": "aws", "service": "iam", "severity": "high", "frameworks": ["CIS-1.5", "NIST-IA-2", "SOC2-CC6.1"], "remediation": "Enable MFA for all IAM users via console or policy."},
    {"id": "aws-iam-004", "name": "IAM password policy minimum length 14", "description": "Password policy must require at least 14 characters", "provider": "aws", "service": "iam", "severity": "medium", "frameworks": ["CIS-1.8", "NIST-IA-5", "PCI-8.3.6"], "remediation": "Update account password policy to require minimum 14 characters."},
    {"id": "aws-iam-005", "name": "IAM password policy requires symbols", "description": "Password policy must require at least one symbol", "provider": "aws", "service": "iam", "severity": "medium", "frameworks": ["CIS-1.9", "NIST-IA-5"], "remediation": "Enable symbol requirement in account password policy."},
    {"id": "aws-iam-006", "name": "Access keys rotated every 90 days", "description": "IAM user access keys must be rotated every 90 days", "provider": "aws", "service": "iam", "severity": "high", "frameworks": ["CIS-1.14", "NIST-IA-5", "PCI-8.3.9"], "remediation": "Rotate access keys that are older than 90 days."},
    {"id": "aws-iam-007", "name": "No inline IAM policies on users", "description": "Use managed policies instead of inline policies on IAM users", "provider": "aws", "service": "iam", "severity": "medium", "frameworks": ["CIS-1.16", "NIST-AC-6"], "remediation": "Replace inline policies with managed policies."},
    {"id": "aws-iam-008", "name": "IAM roles used instead of IAM users for services", "description": "EC2 instances should use IAM roles, not long-term keys", "provider": "aws", "service": "iam", "severity": "medium", "frameworks": ["CIS-1.18", "NIST-AC-6"], "remediation": "Attach IAM role to EC2 instances; remove hardcoded credentials."},
    # ─── AWS S3 ────────────────────────────────────────────────────────────────
    {"id": "aws-s3-001", "name": "S3 bucket public access blocked", "description": "All S3 buckets should have public access blocked", "provider": "aws", "service": "s3", "severity": "critical", "frameworks": ["CIS-2.1.5", "NIST-SC-7", "PCI-1.3", "SOC2-CC6.6"], "remediation": "Enable S3 Block Public Access settings at account and bucket level."},
    {"id": "aws-s3-002", "name": "S3 bucket server-side encryption enabled", "description": "S3 buckets must have default encryption enabled", "provider": "aws", "service": "s3", "severity": "high", "frameworks": ["CIS-2.1.1", "NIST-SC-28", "PCI-3.4", "SOC2-CC6.7"], "remediation": "Enable S3 bucket default encryption using SSE-S3 or SSE-KMS."},
    {"id": "aws-s3-003", "name": "S3 bucket versioning enabled", "description": "S3 buckets storing critical data should have versioning enabled", "provider": "aws", "service": "s3", "severity": "medium", "frameworks": ["CIS-2.1.3", "NIST-CP-10"], "remediation": "Enable versioning on S3 buckets storing important data."},
    {"id": "aws-s3-004", "name": "S3 bucket logging enabled", "description": "S3 server access logging should be enabled", "provider": "aws", "service": "s3", "severity": "medium", "frameworks": ["CIS-2.1.2", "NIST-AU-2"], "remediation": "Enable server access logging on all S3 buckets."},
    {"id": "aws-s3-005", "name": "S3 bucket policy does not allow * principal", "description": "S3 bucket policies must not allow access to all principals", "provider": "aws", "service": "s3", "severity": "critical", "frameworks": ["CIS-2.1.5", "NIST-AC-3", "PCI-1.3"], "remediation": "Review and restrict bucket policies that use Principal: *."},
    # ─── AWS EC2 ───────────────────────────────────────────────────────────────
    {"id": "aws-ec2-001", "name": "Security groups do not allow unrestricted SSH (port 22)", "description": "Security groups should not allow inbound 0.0.0.0/0 on port 22", "provider": "aws", "service": "ec2", "severity": "critical", "frameworks": ["CIS-5.2", "NIST-SC-7", "PCI-1.2.1", "SOC2-CC6.6"], "remediation": "Restrict SSH access to known IP ranges in security groups."},
    {"id": "aws-ec2-002", "name": "Security groups do not allow unrestricted RDP (port 3389)", "description": "Security groups should not allow inbound 0.0.0.0/0 on port 3389", "provider": "aws", "service": "ec2", "severity": "critical", "frameworks": ["CIS-5.3", "NIST-SC-7", "PCI-1.2.1"], "remediation": "Restrict RDP access to known IP ranges in security groups."},
    {"id": "aws-ec2-003", "name": "EBS volumes encrypted at rest", "description": "All EBS volumes must be encrypted", "provider": "aws", "service": "ec2", "severity": "high", "frameworks": ["CIS-2.2.1", "NIST-SC-28", "PCI-3.4"], "remediation": "Enable EBS encryption by default or encrypt existing volumes."},
    {"id": "aws-ec2-004", "name": "VPC flow logs enabled", "description": "VPC flow logs must be enabled for all VPCs", "provider": "aws", "service": "ec2", "severity": "medium", "frameworks": ["CIS-3.9", "NIST-AU-2", "SOC2-CC7.2"], "remediation": "Enable VPC flow logs and send to CloudWatch or S3."},
    {"id": "aws-ec2-005", "name": "No default security group allows inbound traffic", "description": "Default VPC security group should have no inbound rules", "provider": "aws", "service": "ec2", "severity": "medium", "frameworks": ["CIS-5.4", "NIST-SC-7"], "remediation": "Remove all inbound rules from the default security group."},
    # ─── AWS CloudTrail ────────────────────────────────────────────────────────
    {"id": "aws-cloudtrail-001", "name": "CloudTrail enabled in all regions", "description": "CloudTrail must be enabled and logging in all regions", "provider": "aws", "service": "cloudtrail", "severity": "critical", "frameworks": ["CIS-3.1", "NIST-AU-2", "PCI-10.1", "SOC2-CC7.2"], "remediation": "Enable a multi-region CloudTrail trail."},
    {"id": "aws-cloudtrail-002", "name": "CloudTrail log file validation enabled", "description": "Log file integrity validation must be enabled", "provider": "aws", "service": "cloudtrail", "severity": "high", "frameworks": ["CIS-3.2", "NIST-AU-9"], "remediation": "Enable log file integrity validation on all CloudTrail trails."},
    {"id": "aws-cloudtrail-003", "name": "CloudTrail logs encrypted with KMS", "description": "CloudTrail logs must be encrypted using KMS CMK", "provider": "aws", "service": "cloudtrail", "severity": "medium", "frameworks": ["CIS-3.7", "NIST-SC-28", "PCI-10.5"], "remediation": "Configure KMS encryption for CloudTrail log files."},
    # ─── AWS RDS ───────────────────────────────────────────────────────────────
    {"id": "aws-rds-001", "name": "RDS instances not publicly accessible", "description": "RDS instances must not be publicly accessible", "provider": "aws", "service": "rds", "severity": "critical", "frameworks": ["CIS-2.3.2", "NIST-SC-7", "PCI-1.3"], "remediation": "Set PubliclyAccessible to false on all RDS instances."},
    {"id": "aws-rds-002", "name": "RDS storage encrypted at rest", "description": "All RDS instances must have storage encryption enabled", "provider": "aws", "service": "rds", "severity": "high", "frameworks": ["CIS-2.3.1", "NIST-SC-28", "PCI-3.4"], "remediation": "Enable storage encryption when creating RDS instances."},
    {"id": "aws-rds-003", "name": "RDS automated backups enabled", "description": "RDS instances must have automated backups enabled", "provider": "aws", "service": "rds", "severity": "medium", "frameworks": ["NIST-CP-9", "SOC2-A1.2"], "remediation": "Enable automated backups with retention period of at least 7 days."},
    {"id": "aws-rds-004", "name": "RDS multi-AZ enabled for production", "description": "Production RDS instances should use multi-AZ deployment", "provider": "aws", "service": "rds", "severity": "medium", "frameworks": ["NIST-CP-10", "SOC2-A1.1"], "remediation": "Enable Multi-AZ for RDS instances in production environments."},
    # ─── AWS Lambda ────────────────────────────────────────────────────────────
    {"id": "aws-lambda-001", "name": "Lambda functions have resource-based policies reviewed", "description": "Lambda resource policies should not allow public access", "provider": "aws", "service": "lambda", "severity": "high", "frameworks": ["NIST-AC-3", "SOC2-CC6.3"], "remediation": "Review and restrict Lambda resource-based policies."},
    {"id": "aws-lambda-002", "name": "Lambda functions use latest runtime", "description": "Lambda functions must not use deprecated runtime versions", "provider": "aws", "service": "lambda", "severity": "medium", "frameworks": ["CIS-2.8", "NIST-SA-22"], "remediation": "Update Lambda functions to use current supported runtimes."},
    # ─── AWS KMS ───────────────────────────────────────────────────────────────
    {"id": "aws-kms-001", "name": "KMS CMK rotation enabled", "description": "Customer managed KMS keys must have automatic rotation enabled", "provider": "aws", "service": "kms", "severity": "medium", "frameworks": ["CIS-3.8", "NIST-SC-12", "PCI-3.6"], "remediation": "Enable automatic key rotation for all KMS CMKs."},
    # ─── AWS Config ────────────────────────────────────────────────────────────
    {"id": "aws-config-001", "name": "AWS Config enabled in all regions", "description": "AWS Config must be enabled in all regions for compliance recording", "provider": "aws", "service": "config", "severity": "high", "frameworks": ["CIS-3.5", "NIST-CA-7", "SOC2-CC7.2"], "remediation": "Enable AWS Config recording in all regions."},
    # ─── AWS GuardDuty ─────────────────────────────────────────────────────────
    {"id": "aws-guardduty-001", "name": "GuardDuty enabled in all regions", "description": "GuardDuty threat detection must be active in all regions", "provider": "aws", "service": "guardduty", "severity": "high", "frameworks": ["CIS-3.10", "NIST-IR-4", "SOC2-CC7.4"], "remediation": "Enable GuardDuty in all AWS regions."},
    # ─── AWS SecurityHub ───────────────────────────────────────────────────────
    {"id": "aws-securityhub-001", "name": "Security Hub enabled", "description": "AWS Security Hub must be enabled for centralised findings", "provider": "aws", "service": "securityhub", "severity": "medium", "frameworks": ["NIST-CA-7", "SOC2-CC7.2"], "remediation": "Enable Security Hub and subscribe to CIS and PCI standards."},
    # ─── AZURE IAM ─────────────────────────────────────────────────────────────
    {"id": "azure-iam-001", "name": "Azure MFA enabled for all users", "description": "Multi-factor authentication must be enabled for all Azure AD users", "provider": "azure", "service": "iam", "severity": "critical", "frameworks": ["CIS-1.1.2", "NIST-IA-2", "SOC2-CC6.1"], "remediation": "Enable MFA via Conditional Access or per-user MFA in Azure AD."},
    {"id": "azure-iam-002", "name": "No guest users with administrative roles", "description": "Guest users should not be assigned administrative directory roles", "provider": "azure", "service": "iam", "severity": "high", "frameworks": ["CIS-1.2.2", "NIST-AC-6"], "remediation": "Remove administrative role assignments from guest users."},
    {"id": "azure-iam-003", "name": "Privileged Identity Management (PIM) enabled", "description": "PIM should be used for privileged role management", "provider": "azure", "service": "iam", "severity": "high", "frameworks": ["CIS-1.2.3", "NIST-AC-6", "SOC2-CC6.3"], "remediation": "Enable Azure AD PIM for just-in-time privileged access."},
    {"id": "azure-iam-004", "name": "Conditional access policy for admin roles", "description": "Conditional Access policies must protect administrative accounts", "provider": "azure", "service": "iam", "severity": "high", "frameworks": ["CIS-1.2.1", "NIST-IA-2", "SOC2-CC6.1"], "remediation": "Create Conditional Access policy requiring MFA for all admin sign-ins."},
    # ─── AZURE STORAGE ─────────────────────────────────────────────────────────
    {"id": "azure-storage-001", "name": "Storage accounts require HTTPS only", "description": "Azure storage accounts must enforce HTTPS connections only", "provider": "azure", "service": "storage", "severity": "high", "frameworks": ["CIS-3.1", "NIST-SC-8", "PCI-4.1"], "remediation": "Enable Secure transfer required on all storage accounts."},
    {"id": "azure-storage-002", "name": "Storage accounts not publicly accessible", "description": "Public blob access must be disabled on storage accounts", "provider": "azure", "service": "storage", "severity": "critical", "frameworks": ["CIS-3.5", "NIST-SC-7", "SOC2-CC6.6"], "remediation": "Disable Allow Blob Public Access on all storage accounts."},
    {"id": "azure-storage-003", "name": "Storage account encryption with CMK", "description": "Storage accounts should use customer-managed keys for encryption", "provider": "azure", "service": "storage", "severity": "medium", "frameworks": ["CIS-3.2", "NIST-SC-28", "PCI-3.4"], "remediation": "Configure storage account encryption to use CMK stored in Key Vault."},
    # ─── AZURE NETWORK ─────────────────────────────────────────────────────────
    {"id": "azure-network-001", "name": "NSG restricts SSH/RDP from internet", "description": "Network Security Groups must not allow SSH/RDP from any source", "provider": "azure", "service": "network", "severity": "critical", "frameworks": ["CIS-6.1", "NIST-SC-7", "PCI-1.2.1", "SOC2-CC6.6"], "remediation": "Remove inbound NSG rules allowing port 22 or 3389 from 0.0.0.0/0."},
    {"id": "azure-network-002", "name": "Azure DDoS Protection Standard enabled", "description": "DDoS Protection Standard should be enabled on virtual networks", "provider": "azure", "service": "network", "severity": "medium", "frameworks": ["NIST-SC-5", "SOC2-A1.1"], "remediation": "Enable Azure DDoS Protection Standard on all production VNets."},
    {"id": "azure-network-003", "name": "Azure Firewall or WAF deployed", "description": "Web-facing resources should be protected by WAF or Azure Firewall", "provider": "azure", "service": "network", "severity": "high", "frameworks": ["CIS-6.5", "NIST-SC-7", "PCI-6.4"], "remediation": "Deploy Azure WAF or Azure Firewall in front of internet-facing resources."},
    # ─── AZURE SQL ─────────────────────────────────────────────────────────────
    {"id": "azure-sql-001", "name": "Azure SQL transparent data encryption enabled", "description": "TDE must be enabled on all Azure SQL databases", "provider": "azure", "service": "sql", "severity": "high", "frameworks": ["CIS-4.1.2", "NIST-SC-28", "PCI-3.4"], "remediation": "Enable Transparent Data Encryption on all SQL databases."},
    {"id": "azure-sql-002", "name": "Azure SQL Advanced Threat Protection enabled", "description": "Advanced Threat Protection must be enabled on SQL servers", "provider": "azure", "service": "sql", "severity": "high", "frameworks": ["CIS-4.2.1", "NIST-IR-4", "SOC2-CC7.3"], "remediation": "Enable Microsoft Defender for SQL on all SQL servers."},
    {"id": "azure-sql-003", "name": "SQL server auditing enabled", "description": "Azure SQL server auditing must be enabled", "provider": "azure", "service": "sql", "severity": "medium", "frameworks": ["CIS-4.1.3", "NIST-AU-2", "PCI-10.1"], "remediation": "Enable auditing at the SQL server level to Log Analytics or Storage."},
    # ─── AZURE KEY VAULT ───────────────────────────────────────────────────────
    {"id": "azure-kv-001", "name": "Key Vault soft delete enabled", "description": "Azure Key Vault soft-delete must be enabled to prevent accidental deletion", "provider": "azure", "service": "keyvault", "severity": "high", "frameworks": ["CIS-8.1", "NIST-CP-10"], "remediation": "Enable soft-delete and purge protection on all Key Vaults."},
    {"id": "azure-kv-002", "name": "Key Vault key expiry date set", "description": "All Key Vault keys must have an expiry date configured", "provider": "azure", "service": "keyvault", "severity": "medium", "frameworks": ["CIS-8.2", "NIST-SC-12"], "remediation": "Set expiry dates on all Key Vault keys and certificates."},
    # ─── AZURE MONITORING ──────────────────────────────────────────────────────
    {"id": "azure-monitor-001", "name": "Azure Defender for Cloud enabled", "description": "Microsoft Defender for Cloud must be enabled on all subscriptions", "provider": "azure", "service": "monitor", "severity": "high", "frameworks": ["CIS-2.1.15", "NIST-CA-7", "SOC2-CC7.2"], "remediation": "Enable Microsoft Defender for Cloud on all Azure subscriptions."},
    {"id": "azure-monitor-002", "name": "Activity log alerts for critical operations", "description": "Alerts must exist for create/update/delete of critical resources", "provider": "azure", "service": "monitor", "severity": "medium", "frameworks": ["CIS-5.2.1", "NIST-AU-6"], "remediation": "Create activity log alerts for key administrative operations."},
    # ─── GCP IAM ───────────────────────────────────────────────────────────────
    {"id": "gcp-iam-001", "name": "No service accounts with project owner role", "description": "Service accounts must not be assigned project Owner role", "provider": "gcp", "service": "iam", "severity": "critical", "frameworks": ["CIS-1.5", "NIST-AC-6", "SOC2-CC6.3"], "remediation": "Remove Owner role from service accounts; use least privilege roles."},
    {"id": "gcp-iam-002", "name": "Service account keys rotated every 90 days", "description": "User-managed service account keys must be rotated every 90 days", "provider": "gcp", "service": "iam", "severity": "high", "frameworks": ["CIS-1.7", "NIST-IA-5"], "remediation": "Rotate service account keys and delete keys older than 90 days."},
    {"id": "gcp-iam-003", "name": "No user-managed service account keys", "description": "Prefer Workload Identity over user-managed service account keys", "provider": "gcp", "service": "iam", "severity": "medium", "frameworks": ["CIS-1.6", "NIST-IA-5"], "remediation": "Use Workload Identity Federation instead of service account key files."},
    {"id": "gcp-iam-004", "name": "MFA enforced for all users", "description": "2-Step Verification must be enforced for all Google accounts", "provider": "gcp", "service": "iam", "severity": "critical", "frameworks": ["CIS-1.2", "NIST-IA-2", "SOC2-CC6.1"], "remediation": "Enforce 2-Step Verification in Google Admin console."},
    # ─── GCP STORAGE ───────────────────────────────────────────────────────────
    {"id": "gcp-storage-001", "name": "GCS buckets not publicly accessible", "description": "GCS buckets must not allow public access (allUsers or allAuthenticatedUsers)", "provider": "gcp", "service": "storage", "severity": "critical", "frameworks": ["CIS-5.1", "NIST-SC-7", "PCI-1.3", "SOC2-CC6.6"], "remediation": "Remove allUsers and allAuthenticatedUsers from GCS bucket IAM policies."},
    {"id": "gcp-storage-002", "name": "GCS bucket uniform access control enabled", "description": "Uniform bucket-level access should be enabled on all GCS buckets", "provider": "gcp", "service": "storage", "severity": "medium", "frameworks": ["CIS-5.2", "NIST-AC-3"], "remediation": "Enable uniform bucket-level access on all GCS buckets."},
    {"id": "gcp-storage-003", "name": "GCS bucket logging enabled", "description": "GCS data access logging must be enabled", "provider": "gcp", "service": "storage", "severity": "medium", "frameworks": ["CIS-5.3", "NIST-AU-2"], "remediation": "Enable data access audit logs for Google Cloud Storage."},
    # ─── GCP COMPUTE ───────────────────────────────────────────────────────────
    {"id": "gcp-compute-001", "name": "VM instances have no public IP", "description": "Compute Engine instances should not have public IP addresses", "provider": "gcp", "service": "compute", "severity": "high", "frameworks": ["CIS-4.9", "NIST-SC-7", "SOC2-CC6.6"], "remediation": "Remove external IPs from VM instances; use Cloud NAT for outbound access."},
    {"id": "gcp-compute-002", "name": "OS login enabled on VM instances", "description": "OS Login must be enabled for centralized SSH key management", "provider": "gcp", "service": "compute", "severity": "medium", "frameworks": ["CIS-4.4", "NIST-IA-3"], "remediation": "Set enable-oslogin metadata key to TRUE on project or instance."},
    {"id": "gcp-compute-003", "name": "VM instances use shielded VM features", "description": "Secure Boot and vTPM must be enabled on VM instances", "provider": "gcp", "service": "compute", "severity": "medium", "frameworks": ["CIS-4.8", "NIST-SI-7"], "remediation": "Enable Secure Boot, vTPM, and Integrity Monitoring on VM instances."},
    {"id": "gcp-compute-004", "name": "Firewall rules do not allow unrestricted SSH/RDP", "description": "VPC firewall rules must not allow 0.0.0.0/0 on port 22 or 3389", "provider": "gcp", "service": "compute", "severity": "critical", "frameworks": ["CIS-3.6", "NIST-SC-7", "PCI-1.2.1"], "remediation": "Restrict firewall rules to known source IP ranges for SSH and RDP."},
    # ─── GCP SQL ───────────────────────────────────────────────────────────────
    {"id": "gcp-sql-001", "name": "Cloud SQL instances not publicly accessible", "description": "Cloud SQL instances must not have authorised network 0.0.0.0/0", "provider": "gcp", "service": "sql", "severity": "critical", "frameworks": ["CIS-6.2", "NIST-SC-7", "PCI-1.3"], "remediation": "Remove 0.0.0.0/0 from Cloud SQL authorised networks; use Cloud SQL Auth Proxy."},
    {"id": "gcp-sql-002", "name": "Cloud SQL backups enabled", "description": "Automated backups must be enabled for all Cloud SQL instances", "provider": "gcp", "service": "sql", "severity": "medium", "frameworks": ["CIS-6.7", "NIST-CP-9"], "remediation": "Enable automated backups and point-in-time recovery on Cloud SQL instances."},
    {"id": "gcp-sql-003", "name": "Cloud SQL SSL required for connections", "description": "Cloud SQL must require SSL for all connections", "provider": "gcp", "service": "sql", "severity": "high", "frameworks": ["CIS-6.4", "NIST-SC-8", "PCI-4.1"], "remediation": "Enable Require SSL in Cloud SQL instance settings."},
    # ─── GCP LOGGING ───────────────────────────────────────────────────────────
    {"id": "gcp-logging-001", "name": "Cloud Audit Logs enabled for all services", "description": "Data Access audit logs must be enabled for all Google Cloud services", "provider": "gcp", "service": "logging", "severity": "high", "frameworks": ["CIS-2.1", "NIST-AU-2", "SOC2-CC7.2"], "remediation": "Enable Data Access audit logs at the organisation or project level."},
    {"id": "gcp-logging-002", "name": "Log metric filter for project IAM changes", "description": "Alerts must exist for IAM policy changes", "provider": "gcp", "service": "logging", "severity": "medium", "frameworks": ["CIS-2.4", "NIST-AU-6"], "remediation": "Create log metric and alert for IAM policy change events."},
    {"id": "gcp-logging-003", "name": "Log metric filter for network route changes", "description": "Alerts must exist for VPC network route changes", "provider": "gcp", "service": "logging", "severity": "medium", "frameworks": ["CIS-2.8", "NIST-SC-7"], "remediation": "Create log metric and alert for VPC network route change events."},
    # ─── GCP KMS ───────────────────────────────────────────────────────────────
    {"id": "gcp-kms-001", "name": "KMS cryptokeys have rotation period", "description": "Cloud KMS cryptographic keys must have rotation period set", "provider": "gcp", "service": "kms", "severity": "medium", "frameworks": ["CIS-1.9", "NIST-SC-12"], "remediation": "Set rotation period of 90 days or less on all KMS cryptokeys."},
    {"id": "gcp-kms-002", "name": "KMS keys not publicly accessible", "description": "Cloud KMS keys must not be accessible by allUsers or allAuthenticatedUsers", "provider": "gcp", "service": "kms", "severity": "critical", "frameworks": ["CIS-1.10", "NIST-SC-12", "SOC2-CC6.7"], "remediation": "Remove public IAM bindings from Cloud KMS keyring and key resources."},
    # ─── CROSS-PROVIDER ────────────────────────────────────────────────────────
    {"id": "cross-001", "name": "No secrets in cloud resource tags/labels", "description": "Resource tags and labels must not contain sensitive values", "provider": "aws", "service": "general", "severity": "high", "frameworks": ["NIST-SA-3", "PCI-3.2"], "remediation": "Scan resource tags for secrets and rotate any exposed credentials."},
    {"id": "cross-002", "name": "Monitoring alerts for root/admin logins", "description": "Alerts must be triggered on root or privileged account sign-in", "provider": "aws", "service": "cloudwatch", "severity": "high", "frameworks": ["CIS-4.3", "NIST-AC-2", "SOC2-CC7.3"], "remediation": "Create CloudWatch/Monitor alert for root or admin login events."},
    # ─── KUBERNETES (CIS Benchmark v1.8 + NSA Hardening Guide) ────────────────
    {"id": "k8s-rbac-001", "name": "No anonymous API server access", "description": "Kubernetes API server must not allow anonymous authentication", "provider": "kubernetes", "service": "rbac", "severity": "critical", "frameworks": ["CIS-K8s-1.2.1", "NIST-AC-3", "NSA-K8s"], "remediation": "Set --anonymous-auth=false on the API server."},
    {"id": "k8s-rbac-002", "name": "RBAC enabled", "description": "Role-Based Access Control must be enabled on the API server", "provider": "kubernetes", "service": "rbac", "severity": "critical", "frameworks": ["CIS-K8s-1.2.7", "NIST-AC-3", "SOC2-CC6.3"], "remediation": "Set --authorization-mode=RBAC (or Node,RBAC) on the API server."},
    {"id": "k8s-rbac-003", "name": "No cluster-admin rolebinding to service accounts", "description": "Service accounts must not be bound to the cluster-admin ClusterRole", "provider": "kubernetes", "service": "rbac", "severity": "critical", "frameworks": ["CIS-K8s-5.1.1", "NIST-AC-6"], "remediation": "Remove cluster-admin ClusterRoleBindings for service accounts; use least-privilege roles."},
    {"id": "k8s-rbac-004", "name": "No wildcard verbs on core resources", "description": "ClusterRoles must not grant wildcard (*) verbs on core API group resources", "provider": "kubernetes", "service": "rbac", "severity": "high", "frameworks": ["CIS-K8s-5.1.3", "NIST-AC-6"], "remediation": "Replace wildcard verb rules in ClusterRoles with explicit allowed verbs."},
    {"id": "k8s-network-001", "name": "Network policies enforced", "description": "All namespaces must have at least one NetworkPolicy to restrict pod traffic", "provider": "kubernetes", "service": "network", "severity": "high", "frameworks": ["CIS-K8s-5.3.2", "NIST-SC-7", "NSA-K8s"], "remediation": "Apply NetworkPolicy objects to restrict pod-to-pod communication."},
    {"id": "k8s-network-002", "name": "API server not exposed on public internet", "description": "Kubernetes API server endpoint must not be publicly accessible", "provider": "kubernetes", "service": "network", "severity": "critical", "frameworks": ["CIS-K8s-1.2.1", "NIST-SC-7", "SOC2-CC6.6"], "remediation": "Enable authorized IP ranges or private endpoint on managed Kubernetes clusters."},
    {"id": "k8s-secrets-001", "name": "Secrets encrypted at rest in etcd", "description": "Kubernetes Secrets must be encrypted at rest in etcd using a KMS provider", "provider": "kubernetes", "service": "secrets", "severity": "critical", "frameworks": ["CIS-K8s-1.2.33", "NIST-SC-28", "PCI-3.4"], "remediation": "Configure EncryptionConfiguration with a KMS provider for Secrets resources."},
    {"id": "k8s-secrets-002", "name": "No plaintext secrets in Pod environment variables", "description": "Container environment variables must not contain sensitive values directly", "provider": "kubernetes", "service": "secrets", "severity": "high", "frameworks": ["CIS-K8s-5.4.1", "NIST-SA-3"], "remediation": "Reference Kubernetes Secrets via secretKeyRef rather than hardcoded env values."},
    {"id": "k8s-pods-001", "name": "Pod Security Admission enforced (restricted profile)", "description": "Namespaces must enforce Pod Security Admission with at minimum baseline profile", "provider": "kubernetes", "service": "pods", "severity": "high", "frameworks": ["CIS-K8s-5.2.1", "NIST-SI-3", "NSA-K8s"], "remediation": "Add pod-security.kubernetes.io/enforce labels to namespaces."},
    {"id": "k8s-pods-002", "name": "Containers do not run as root", "description": "All containers must set runAsNonRoot: true or runAsUser != 0", "provider": "kubernetes", "service": "pods", "severity": "high", "frameworks": ["CIS-K8s-5.2.6", "NIST-AC-6", "NSA-K8s"], "remediation": "Set securityContext.runAsNonRoot: true in pod specs."},
    {"id": "k8s-pods-003", "name": "Containers have read-only root filesystem", "description": "Container root filesystems should be read-only to limit persistence", "provider": "kubernetes", "service": "pods", "severity": "medium", "frameworks": ["CIS-K8s-5.2.4", "NIST-SI-7", "NSA-K8s"], "remediation": "Set securityContext.readOnlyRootFilesystem: true in container specs."},
    {"id": "k8s-pods-004", "name": "Privileged containers not allowed", "description": "No containers should run in privileged mode", "provider": "kubernetes", "service": "pods", "severity": "critical", "frameworks": ["CIS-K8s-5.2.1", "NIST-AC-6", "NSA-K8s"], "remediation": "Set securityContext.privileged: false in all container specs."},
    {"id": "k8s-pods-005", "name": "CPU and memory limits set on all containers", "description": "All containers must define CPU and memory resource limits", "provider": "kubernetes", "service": "pods", "severity": "medium", "frameworks": ["CIS-K8s-5.2.5", "NIST-SI-3"], "remediation": "Define resources.limits.cpu and resources.limits.memory for every container."},
    {"id": "k8s-audit-001", "name": "Kubernetes audit logging enabled", "description": "API server audit logging must be enabled and configured with an audit policy", "provider": "kubernetes", "service": "audit", "severity": "high", "frameworks": ["CIS-K8s-3.2.1", "NIST-AU-2", "SOC2-CC7.2"], "remediation": "Configure --audit-log-path and --audit-policy-file on the API server."},
    {"id": "k8s-audit-002", "name": "Audit logs retained for 30 days minimum", "description": "Kubernetes audit log retention must be at least 30 days", "provider": "kubernetes", "service": "audit", "severity": "medium", "frameworks": ["CIS-K8s-3.2.2", "NIST-AU-11", "PCI-10.7"], "remediation": "Set --audit-log-maxage=30 or ship logs to long-term storage."},
    {"id": "k8s-etcd-001", "name": "etcd peer communications encrypted", "description": "etcd must use TLS for peer-to-peer communication", "provider": "kubernetes", "service": "etcd", "severity": "high", "frameworks": ["CIS-K8s-2.1", "NIST-SC-8"], "remediation": "Set --peer-cert-file, --peer-key-file, and --peer-client-cert-auth on etcd."},
    {"id": "k8s-images-001", "name": "Container images from trusted registries only", "description": "Pods must only pull images from approved container registries", "provider": "kubernetes", "service": "images", "severity": "high", "frameworks": ["CIS-K8s-5.5.1", "NIST-SI-7", "SOC2-CC6.8"], "remediation": "Use OPA/Kyverno admission policy to restrict allowed image registries."},
    {"id": "k8s-images-002", "name": "Image tags pinned (no :latest)", "description": "Container images must use pinned version tags, not :latest", "provider": "kubernetes", "service": "images", "severity": "medium", "frameworks": ["CIS-K8s-5.5.1", "NIST-SA-10"], "remediation": "Replace :latest tags with specific digest or version tags in pod specs."},
    {"id": "k8s-admission-001", "name": "Admission controllers include NodeRestriction", "description": "NodeRestriction admission plugin must be enabled to limit node API permissions", "provider": "kubernetes", "service": "admission", "severity": "high", "frameworks": ["CIS-K8s-1.2.17", "NIST-AC-6"], "remediation": "Add NodeRestriction to --enable-admission-plugins on the API server."},
    {"id": "k8s-admission-002", "name": "AlwaysPullImages admission controller enabled", "description": "AlwaysPullImages ensures fresh pulls and prevents using cached unauthorized images", "provider": "kubernetes", "service": "admission", "severity": "medium", "frameworks": ["CIS-K8s-1.2.11", "NIST-SI-7"], "remediation": "Add AlwaysPullImages to --enable-admission-plugins on the API server."},
]

_CHECKS_BY_ID: Dict[str, Dict] = {c["id"]: c for c in CLOUD_CHECKS}


class CloudChecksService:
    def _db(self):
        from database import get_database
        return get_database()

    def list_checks(self, provider: Optional[str] = None, service: Optional[str] = None, severity: Optional[str] = None) -> List[Dict]:
        checks = CLOUD_CHECKS
        if provider:
            checks = [c for c in checks if c["provider"] == provider]
        if service:
            checks = [c for c in checks if c["service"] == service]
        if severity:
            checks = [c for c in checks if c["severity"] == severity]
        return checks

    async def get_results(self, tenant_id: Optional[str], role: str, provider: Optional[str] = None, account_id: Optional[str] = None) -> List[Dict]:
        db = self._db()
        query: Dict[str, Any] = {} if role in _CC_SUPER_ROLES else {"tenantId": tenant_id}
        if provider:
            query["provider"] = provider
        if account_id:
            query["accountId"] = account_id
        return await db.cloud_check_results.find(query, {"_id": 0}).sort("checked_at", -1).to_list(length=5000)

    async def run_checks(self, account_id: str, provider: str, tenant_id: str, credentials_hint: Optional[str] = None) -> Dict:
        """Evaluate checks against the account's imported findings from native scanners."""
        db = self._db()
        account = await db.cloud_accounts.find_one({"id": account_id, "tenantId": tenant_id}, {"_id": 0})
        if not account:
            return {"error": "Cloud account not found", "ran": 0}

        findings_raw = await db.cloud_findings.find(
            {"accountId": account_id, "tenantId": tenant_id}, {"_id": 0}
        ).to_list(length=10000)
        finding_titles = {f.get("title", "").lower() for f in findings_raw}
        failing_ids = {f.get("checkId", "").lower() for f in findings_raw if f.get("severity") in ("critical", "high", "medium")}

        now = datetime.now(timezone.utc).isoformat()
        upserted = 0
        provider_checks = [c for c in CLOUD_CHECKS if c["provider"] == provider]
        for check in provider_checks:
            cid = check["id"]
            name_lower = check["name"].lower()
            in_findings = cid.lower() in failing_ids or any(kw in finding_titles for kw in name_lower.split()[:3])
            result = "FAIL" if in_findings else "PASS"
            doc = {
                "id": f"ccr-{uuid.uuid4().hex}",
                "tenantId": tenant_id,
                "accountId": account_id,
                "provider": provider,
                "checkId": cid,
                "checkName": check["name"],
                "service": check["service"],
                "severity": check["severity"],
                "result": result,
                "frameworks": check["frameworks"],
                "remediation": check["remediation"],
                "detail": "Based on imported findings from native cloud scanner." if in_findings else "No matching findings found.",
                "checked_at": now,
            }
            await db.cloud_check_results.update_one(
                {"tenantId": tenant_id, "accountId": account_id, "checkId": cid},
                {"$set": doc},
                upsert=True,
            )
            upserted += 1
        return {"ran": upserted, "accountId": account_id, "provider": provider, "checked_at": now}

    async def get_summary(self, tenant_id: Optional[str], role: str, account_id: Optional[str] = None) -> Dict:
        results = await self.get_results(tenant_id, role, account_id=account_id)
        if not results:
            total_checks = len(CLOUD_CHECKS)
            return {"total": total_checks, "pass": 0, "fail": 0, "bySeverity": {}, "byProvider": {}, "byService": {}, "coverage": 0}
        total = len(results)
        passed = sum(1 for r in results if r.get("result") == "PASS")
        failed = sum(1 for r in results if r.get("result") == "FAIL")
        by_sev: Dict[str, int] = {}
        by_prov: Dict[str, Dict] = {}
        by_svc: Dict[str, int] = {}
        for r in results:
            sev = r.get("severity", "unknown")
            if r.get("result") == "FAIL":
                by_sev[sev] = by_sev.get(sev, 0) + 1
            prov = r.get("provider", "unknown")
            if prov not in by_prov:
                by_prov[prov] = {"pass": 0, "fail": 0}
            by_prov[prov][r.get("result", "FAIL").lower()] = by_prov[prov].get(r.get("result", "FAIL").lower(), 0) + 1
            svc = r.get("service", "unknown")
            if r.get("result") == "FAIL":
                by_svc[svc] = by_svc.get(svc, 0) + 1
        return {
            "total": total,
            "pass": passed,
            "fail": failed,
            "passPct": round(passed / max(total, 1) * 100),
            "bySeverity": by_sev,
            "byProvider": by_prov,
            "byService": by_svc,
            "coverage": round(total / len(CLOUD_CHECKS) * 100),
        }


cloud_checks_service = CloudChecksService()
