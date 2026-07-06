"""IaC Scanner — 44 security checks (17 Terraform, 9 Kubernetes, 18 CloudFormation)."""
import re, uuid, json, logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

IAC_CHECKS = [
    # ─── Terraform checks ──────────────────────────────────────────────────
    # "vulnerable_marker": True  -> negative_pattern match confirms the VULNERABLE condition (status = FAIL if matched)
    # "vulnerable_marker": False (or absent) -> negative_pattern match confirms a MITIGATION is present (status = PASS if matched)
    {"id": "tf-s3-public-acl", "name": "S3 Bucket Public ACL", "description": "S3 bucket should not have public ACL", "provider": "terraform", "severity": "critical", "pattern": r'resource\s+"aws_s3_bucket"\s+"([^"]+)"', "negative_pattern": r'acl\s*=\s*"public-read"|acl\s*=\s*"public-read-write"', "vulnerable_marker": True},
    {"id": "tf-iam-wildcard", "name": "IAM Policy Wildcard Action", "description": "IAM policy should not use * action", "provider": "terraform", "severity": "critical", "pattern": r'resource\s+"aws_iam_role_policy"\s+"[^"]*"|resource\s+"aws_iam_policy"\s+"[^"]*"', "negative_pattern": r'Action\s*=\s*\[?\s*"\*"\s*\]?', "vulnerable_marker": True},
    {"id": "tf-sg-open-ssh", "name": "Security Group Open SSH", "description": "Security group should not allow 0.0.0.0/0 on port 22", "provider": "terraform", "severity": "critical", "pattern": r'resource\s+"aws_security_group"\s+"[^"]*"', "negative_pattern": r'cidr_blocks\s*=\s*\[?\s*"0\.0\.0\.0/0".*from_port\s*=\s*22|from_port\s*=\s*22.*cidr_blocks\s*=\s*\[?\s*"0\.0\.0\.0/0"', "vulnerable_marker": True},
    {"id": "tf-sg-open-rdp", "name": "Security Group Open RDP", "description": "Security group should not allow 0.0.0.0/0 on port 3389", "provider": "terraform", "severity": "critical", "pattern": r'resource\s+"aws_security_group"\s+"[^"]*"', "negative_pattern": r'cidr_blocks\s*=\s*\[?\s*"0\.0\.0\.0/0".*from_port\s*=\s*3389|from_port\s*=\s*3389.*cidr_blocks\s*=\s*\[?\s*"0\.0\.0\.0/0"', "vulnerable_marker": True},
    {"id": "tf-ebs-encrypted", "name": "EBS Volume Encryption Disabled", "description": "EBS volume should have encryption enabled", "provider": "terraform", "severity": "high", "pattern": r'resource\s+"aws_ebs_volume"\s+"[^"]*"', "negative_pattern": r'encrypted\s*=\s*false', "vulnerable_marker": True},
    {"id": "tf-rds-encrypted", "name": "RDS Storage Encryption Disabled", "description": "RDS instance should have storage encryption enabled", "provider": "terraform", "severity": "high", "pattern": r'resource\s+"aws_db_instance"\s+"[^"]*"', "negative_pattern": r'storage_encrypted\s*=\s*false', "vulnerable_marker": True},
    {"id": "tf-eks-public", "name": "EKS Cluster Public Endpoint", "description": "EKS cluster endpoint should be private", "provider": "terraform", "severity": "high", "pattern": r'resource\s+"aws_eks_cluster"\s+"[^"]*"', "negative_pattern": r'endpoint_public_access\s*=\s*true', "vulnerable_marker": True},
    {"id": "tf-ec2-public-ip", "name": "EC2 Instance with Public IP", "description": "EC2 instance should not have public IP", "provider": "terraform", "severity": "high", "pattern": r'resource\s+"aws_instance"\s+"[^"]*"', "negative_pattern": r'associate_public_ip_address\s*=\s*true', "vulnerable_marker": True},
    {"id": "tf-alb-http", "name": "ALB HTTP Listener (no redirect)", "description": "ALB listener should redirect HTTP to HTTPS", "provider": "terraform", "severity": "high", "pattern": r'resource\s+"aws_alb_listener"\s+"[^"]*"|resource\s+"aws_lb_listener"\s+"[^"]*"', "negative_pattern": r'port\s*=\s*80', "vulnerable_marker": True},
    {"id": "tf-kms-rotation", "name": "KMS Key Rotation Disabled", "description": "KMS key should have rotation enabled", "provider": "terraform", "severity": "medium", "pattern": r'resource\s+"aws_kms_key"\s+"[^"]*"', "negative_pattern": r'rotation_enabled\s*=\s*false', "vulnerable_marker": True},
    {"id": "tf-s3-logging", "name": "S3 Bucket Logging Disabled", "description": "S3 bucket should have access logging", "provider": "terraform", "severity": "medium", "pattern": r'resource\s+"aws_s3_bucket"\s+"([^"]+)"', "negative_pattern": r'logging\s*\{'},
    {"id": "tf-vpc-flow-logs", "name": "VPC Flow Logs Disabled", "description": "VPC flow logs should be enabled", "provider": "terraform", "severity": "medium", "pattern": r'resource\s+"aws_vpc"\s+"([^"]*)"', "negative_pattern": r'resource\s+"aws_flow_log"'},
    {"id": "tf-hardcoded-key", "name": "Hardcoded AWS Access Key", "description": "AWS access key should not be hardcoded", "provider": "terraform", "severity": "critical", "pattern": r'AKIA[0-9A-Z]{16}|aws_access_key_id|aws_secret_access_key', "negative_pattern": r'variable\s+"aws_access_key|var\.', "scope_lines": 2},
    {"id": "tf-plaintext-secret", "name": "Secret in Plaintext Variable", "description": "Sensitive variable without sensitive=true", "provider": "terraform", "severity": "critical", "pattern": r'variable\s+"(password|secret|token|key|credential|api_key)"', "negative_pattern": r'sensitive\s*=\s*true', "scope_lines": 5},
    {"id": "tf-ec2-admin", "name": "EC2 Admin Privileged True", "description": "EC2 instance should not run as admin", "provider": "terraform", "severity": "high", "pattern": r'resource\s+"aws_instance"\s+"[^"]*"', "negative_pattern": r'user_data.*admin|user_data.*root', "vulnerable_marker": True},
    {"id": "tf-s3-versioning", "name": "S3 Versioning Disabled", "description": "S3 versioning should be enabled", "provider": "terraform", "severity": "medium", "pattern": r'resource\s+"aws_s3_bucket"\s+"([^"]+)"', "negative_pattern": r'versioning\s*\{'},
    {"id": "tf-rds-deletion-protection", "name": "RDS Deletion Protection Disabled", "description": "RDS should have deletion protection", "provider": "terraform", "severity": "medium", "pattern": r'resource\s+"aws_db_instance"\s+"[^"]*"', "negative_pattern": r'deletion_protection\s*=\s*false', "vulnerable_marker": True},
    # ─── Kubernetes checks ──────────────────────────────────────────────────
    {"id": "k8s-privileged", "name": "Privileged Container Allowed", "description": "Container should not run privileged", "provider": "kubernetes", "severity": "critical", "pattern": r'privileged:\s*true', "negative_pattern": None},
    {"id": "k8s-run-as-root", "name": "Container Runs as Root", "description": "Container should set runAsNonRoot", "provider": "kubernetes", "severity": "high", "pattern": r'containers:', "negative_pattern": r'runAsNonRoot:\s*true|runAsUser:\s*[1-9]'},
    {"id": "k8s-host-network", "name": "hostNetwork Enabled", "description": "Pod should not use host network", "provider": "kubernetes", "severity": "high", "pattern": r'hostNetwork:\s*true', "negative_pattern": None},
    {"id": "k8s-host-pid", "name": "hostPID/hostIPC Enabled", "description": "Pod should not share host PID/IPC", "provider": "kubernetes", "severity": "high", "pattern": r'hostPID:\s*true|hostIPC:\s*true', "negative_pattern": None},
    {"id": "k8s-no-resource-limits", "name": "Container Without Resource Limits", "description": "Container should have resource limits", "provider": "kubernetes", "severity": "medium", "pattern": r'containers:', "negative_pattern": r'limits:'},
    {"id": "k8s-secrets-env", "name": "Secrets as Environment Variables", "description": "Use volume mounts not env vars for secrets", "provider": "kubernetes", "severity": "high", "pattern": r'env:\s*\n.*secretKeyRef|valueFrom:\s*\n.*secretKeyRef', "negative_pattern": None},
    {"id": "k8s-no-network-policy", "name": "NetworkPolicy Missing", "description": "Namespace should have NetworkPolicy", "provider": "kubernetes", "severity": "medium", "pattern": r'kind:\s*Namespace', "negative_pattern": r'kind:\s*NetworkPolicy'},
    {"id": "k8s-ro-not-set", "name": "readOnlyRootFilesystem Not Set", "description": "Container should set readOnlyRootFilesystem", "provider": "kubernetes", "severity": "medium", "pattern": r'containers:', "negative_pattern": r'readOnlyRootFilesystem:\s*true'},
    {"id": "k8s-no-probes", "name": "Liveness/Readiness Probe Missing", "description": "Container should have health probes", "provider": "kubernetes", "severity": "low", "pattern": r'containers:', "negative_pattern": r'livenessProbe:|readinessProbe:'},
    # ─── CloudFormation checks ──────────────────────────────────────────────
    {"id": "cfn-s3-public-access", "name": "S3 Bucket Public Access Not Blocked", "description": "S3 bucket should have PublicAccessBlockConfiguration blocking public ACLs/policies", "provider": "cloudformation", "severity": "critical", "pattern": r'Type"?\s*:?\s*"?AWS::S3::Bucket', "negative_pattern": r'PublicAccessBlockConfiguration', "scope_lines": 15},
    {"id": "cfn-s3-public-acl", "name": "S3 Bucket Public ACL", "description": "S3 bucket AccessControl should not be PublicRead/PublicReadWrite", "provider": "cloudformation", "severity": "critical", "pattern": r'Type"?\s*:?\s*"?AWS::S3::Bucket', "negative_pattern": r'AccessControl"?\s*:\s*"?PublicRead', "vulnerable_marker": True, "scope_lines": 15},
    {"id": "cfn-iam-wildcard-action", "name": "IAM Policy Wildcard Action", "description": "IAM policy Statement.Action should not be \"*\"", "provider": "cloudformation", "severity": "critical", "pattern": r'Type"?\s*:?\s*"?AWS::IAM::(Policy|Role)', "negative_pattern": r'Action"?\s*:\s*\[?\s*"?\*"?', "vulnerable_marker": True, "scope_lines": 20},
    {"id": "cfn-sg-open-ssh", "name": "Security Group Open SSH", "description": "SecurityGroupIngress should not allow 0.0.0.0/0 on port 22", "provider": "cloudformation", "severity": "critical", "pattern": r'Type"?\s*:?\s*"?AWS::EC2::SecurityGroup', "negative_pattern": r'CidrIp"?\s*:\s*"?0\.0\.0\.0/0.*(FromPort"?\s*:\s*22|ToPort"?\s*:\s*22)', "vulnerable_marker": True, "scope_lines": 15},
    {"id": "cfn-sg-open-rdp", "name": "Security Group Open RDP", "description": "SecurityGroupIngress should not allow 0.0.0.0/0 on port 3389", "provider": "cloudformation", "severity": "critical", "pattern": r'Type"?\s*:?\s*"?AWS::EC2::SecurityGroup', "negative_pattern": r'CidrIp"?\s*:\s*"?0\.0\.0\.0/0.*(FromPort"?\s*:\s*3389|ToPort"?\s*:\s*3389)', "vulnerable_marker": True, "scope_lines": 15},
    {"id": "cfn-ebs-not-encrypted", "name": "EBS Volume Encryption Disabled", "description": "AWS::EC2::Volume should have Encrypted: true", "provider": "cloudformation", "severity": "high", "pattern": r'Type"?\s*:?\s*"?AWS::EC2::Volume', "negative_pattern": r'Encrypted"?\s*:\s*false', "vulnerable_marker": True, "scope_lines": 10},
    {"id": "cfn-rds-not-encrypted", "name": "RDS Storage Encryption Disabled", "description": "AWS::RDS::DBInstance StorageEncrypted should be true", "provider": "cloudformation", "severity": "high", "pattern": r'Type"?\s*:?\s*"?AWS::RDS::DBInstance', "negative_pattern": r'StorageEncrypted"?\s*:\s*false', "vulnerable_marker": True, "scope_lines": 20},
    {"id": "cfn-eks-public-endpoint", "name": "EKS Cluster Public Endpoint", "description": "EndpointPublicAccess should be false (defaults to true if omitted)", "provider": "cloudformation", "severity": "high", "pattern": r'Type"?\s*:?\s*"?AWS::EKS::Cluster', "negative_pattern": r'EndpointPublicAccess"?\s*:\s*true', "vulnerable_marker": True, "scope_lines": 20},
    {"id": "cfn-ec2-public-ip", "name": "EC2 Instance with Public IP", "description": "NetworkInterfaces should not set AssociatePublicIpAddress: true", "provider": "cloudformation", "severity": "high", "pattern": r'Type"?\s*:?\s*"?AWS::EC2::Instance', "negative_pattern": r'AssociatePublicIpAddress"?\s*:\s*true', "vulnerable_marker": True, "scope_lines": 20},
    {"id": "cfn-elb-http-listener", "name": "Load Balancer HTTP Listener (no redirect)", "description": "ALB/NLB Listener should not use plain HTTP on port 80 without a redirect action", "provider": "cloudformation", "severity": "high", "pattern": r'Type"?\s*:?\s*"?AWS::ElasticLoadBalancingV2::Listener', "negative_pattern": r'Port"?\s*:\s*80\b', "vulnerable_marker": True, "scope_lines": 15},
    {"id": "cfn-kms-rotation-disabled", "name": "KMS Key Rotation Disabled", "description": "EnableKeyRotation defaults to false if omitted — should be explicitly true", "provider": "cloudformation", "severity": "medium", "pattern": r'Type"?\s*:?\s*"?AWS::KMS::Key', "negative_pattern": r'EnableKeyRotation"?\s*:\s*true', "scope_lines": 10},
    {"id": "cfn-s3-logging-disabled", "name": "S3 Bucket Logging Disabled", "description": "S3 bucket should configure LoggingConfiguration", "provider": "cloudformation", "severity": "medium", "pattern": r'Type"?\s*:?\s*"?AWS::S3::Bucket', "negative_pattern": r'LoggingConfiguration', "scope_lines": 15},
    {"id": "cfn-vpc-flow-logs-missing", "name": "VPC Flow Logs Disabled", "description": "A VPC resource should have an accompanying AWS::EC2::FlowLog", "provider": "cloudformation", "severity": "medium", "pattern": r'Type"?\s*:?\s*"?AWS::EC2::VPC\b', "negative_pattern": r'Type"?\s*:?\s*"?AWS::EC2::FlowLog'},
    {"id": "cfn-hardcoded-secret", "name": "Hardcoded AWS Access Key", "description": "AWS access key literal should not be hardcoded in template", "provider": "cloudformation", "severity": "critical", "pattern": r'AKIA[0-9A-Z]{16}'},
    {"id": "cfn-plaintext-secret-param", "name": "Secret Parameter Without NoEcho", "description": "Password/secret/token Parameters should set NoEcho: true", "provider": "cloudformation", "severity": "critical", "pattern": r'(?i)(Password|Secret|Token|ApiKey|Credential)"?\s*:\s*\{?\s*"?Type"?\s*:\s*"?String', "negative_pattern": r'NoEcho"?\s*:\s*true', "scope_lines": 6},
    {"id": "cfn-ec2-admin-userdata", "name": "EC2 UserData References Admin/Root", "description": "EC2 instance UserData should not reference admin/root elevation", "provider": "cloudformation", "severity": "high", "pattern": r'Type"?\s*:?\s*"?AWS::EC2::Instance', "negative_pattern": r'UserData.*(admin|root)', "scope_lines": 15},
    {"id": "cfn-s3-versioning-disabled", "name": "S3 Versioning Disabled", "description": "S3 bucket should configure VersioningConfiguration Status: Enabled", "provider": "cloudformation", "severity": "medium", "pattern": r'Type"?\s*:?\s*"?AWS::S3::Bucket', "negative_pattern": r'VersioningConfiguration', "scope_lines": 15},
    {"id": "cfn-rds-deletion-protection-disabled", "name": "RDS Deletion Protection Disabled", "description": "DeletionProtection defaults to false if omitted — should be explicitly true", "provider": "cloudformation", "severity": "medium", "pattern": r'Type"?\s*:?\s*"?AWS::RDS::DBInstance', "negative_pattern": r'DeletionProtection"?\s*:\s*true', "scope_lines": 20},
]


def _now() -> str: return datetime.now(timezone.utc).isoformat()


def scan_code(code: str, filename: str = "") -> dict:
    """Scan code against IAC_CHECKS. Returns results dict."""
    ext = filename.rsplit(".", 1)[-1].lower() if filename else ""
    provider = _detect_provider(code, ext)
    scan_id = f"iac-{uuid.uuid4().hex[:12]}"
    if provider == "unknown":
        return {"scan_id": scan_id, "provider": provider, "total": 0, "fail": 0, "findings": [],
                "scanned_at": _now(), "warning": "Could not determine IaC provider (Terraform/Kubernetes/CloudFormation) from file content or extension"}
    relevant = [c for c in IAC_CHECKS if c["provider"] == provider]
    findings = []
    for check in relevant:
        found = re.search(check["pattern"], code, re.MULTILINE | re.DOTALL)
        if not found:
            continue
        negative = check.get("negative_pattern")
        has_negative = False
        if negative:
            scope_lines = check.get("scope_lines")
            if scope_lines:
                # Scope the mitigation search to nearby lines instead of the whole file,
                # so an unrelated mitigation elsewhere can't mask this specific violation.
                lines = code.split("\n")
                match_line = code[:found.start()].count("\n")
                window = "\n".join(lines[max(0, match_line - scope_lines): match_line + scope_lines + 1])
                has_negative = bool(re.search(negative, window, re.MULTILINE | re.DOTALL))
            else:
                has_negative = bool(re.search(negative, code, re.MULTILINE | re.DOTALL))
        if check.get("vulnerable_marker"):
            # negative_pattern match confirms the vulnerable condition itself
            status = "FAIL" if has_negative else "PASS"
        else:
            # negative_pattern match confirms a mitigation is present (or there is no
            # negative_pattern at all, in which case has_negative is always False and
            # this branch correctly always yields FAIL)
            status = "PASS" if has_negative else "FAIL"
        line_no = code[:found.start()].count("\n") + 1
        findings.append({
            "check_id": check["id"], "check_name": check["name"],
            "severity": check["severity"], "status": status,
            "message": check["description"], "line": line_no,
        })
    return {"scan_id": scan_id, "provider": provider, "total": len(findings), "fail": sum(1 for f in findings if f["status"] == "FAIL"), "findings": findings, "scanned_at": _now()}


_CFN_TYPE_RE = re.compile(r'"?Type"?\s*:\s*"?AWS::')


def _detect_provider(code: str, ext: str) -> str:
    if ext in ("tf", "tfvars"):
        return "terraform"
    if ext in ("yaml", "yml"):
        if re.search(r'kind:\s*(Pod|Deployment|Service|Namespace|ConfigMap|Secret|NetworkPolicy|Ingress)', code):
            return "kubernetes"
        if _CFN_TYPE_RE.search(code):
            return "cloudformation"
    if ext in ("json", "template") and _CFN_TYPE_RE.search(code):
        return "cloudformation"
    if re.search(r'resource\s+"aws_', code):
        return "terraform"
    if re.search(r'apiVersion:\s*(v1|apps/|batch/|rbac/)', code):
        return "kubernetes"
    if _CFN_TYPE_RE.search(code):  # extension-less/unknown-extension fallback
        return "cloudformation"
    return "unknown"


async def save_result(db, tenant_id: str, result: dict) -> str:
    doc = {"tenantId": tenant_id, **result}
    await db._db.iac_scan_results.insert_one(doc)
    return result["scan_id"]


async def list_results(db, tenant_id: str) -> list:
    return await db._db.iac_scan_results.find({"tenantId": tenant_id}, {"_id": 0}).sort("scanned_at", -1).to_list(length=100)


async def get_config(db, tenant_id: str) -> dict:
    doc = await db._db.iac_scan_config.find_one({"tenantId": tenant_id}, {"_id": 0})
    return doc or {"excluded_paths": [], "severity_threshold": "low", "auto_scan_enabled": False}


async def set_config(db, tenant_id: str, config: dict) -> dict:
    doc = {**config, "tenantId": tenant_id, "updated_at": _now()}
    await db._db.iac_scan_config.update_one({"tenantId": tenant_id}, {"$set": doc}, upsert=True)
    return {k: v for k, v in doc.items() if k != "tenantId"}
