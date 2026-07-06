"""Tests for Phase 24 — IaC Scanner + Container Scanner."""
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from starlette.testclient import TestClient
import iac_scanner_service as iac

def _mkuser(t="tenant-a", r="admin"):
    u = MagicMock(); u.tenant_id = t; u.role = r; return u

def _mkdb(collections=("iac_scan_results", "iac_scan_config", "container_scan_results")):
    db = MagicMock()
    for col in collections:
        c = MagicMock()
        c.insert_one = AsyncMock(return_value=MagicMock(inserted_id="x"))
        c.find = MagicMock(return_value=MagicMock(sort=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))))
        c.find_one = AsyncMock(return_value=None)
        c.update_one = AsyncMock()
        setattr(db._db, col, c)
    # rbac_service.get_user_permissions falls back to its in-memory default_roles
    # table for any non-super-admin role as long as the DB lookup resolves to None.
    db.roles = MagicMock()
    db.roles.find_one = AsyncMock(return_value=None)
    return db

def _build(module_name, mock_db, user):
    import importlib
    mod = importlib.import_module(module_name)
    from authentication_service import get_current_user
    app = FastAPI(); app.include_router(mod.router)
    t = MagicMock(); t.tenant_id = user.tenant_id; t.role = user.role
    # has_permission(...) is a factory — every route decorator call produces a
    # distinct closure, so overriding by re-calling it here never matches the
    # object actually bound into the router. get_current_user is the stable,
    # singleton dependency every has_permission(...) closure wraps, so override
    # that instead (see test_notification_service.py for the same pattern).
    app.dependency_overrides[get_current_user] = lambda: t
    patcher = patch(f"{module_name}.get_database", return_value=mock_db); patcher.start()
    rbac_patcher = patch("rbac_service.get_database", return_value=mock_db); rbac_patcher.start()
    return TestClient(app, raise_server_exceptions=False)

def test_iac_scan_terraform_s3_public_acl():
    code = 'resource "aws_s3_bucket" "bad" { bucket = "public-bucket"; acl = "public-read" }'
    r = iac.scan_code(code, "main.tf")
    s3 = [f for f in r["findings"] if f["check_id"] == "tf-s3-public-acl"]
    assert len(s3) > 0, f"No S3 findings in {r['findings']}"
    assert s3[0]["status"] == "FAIL"

def test_iac_scan_k8s_privileged():
    code = 'apiVersion: v1\nkind: Pod\nmetadata:\n  name: bad\nspec:\n  containers:\n  - name: app\n    securityContext:\n      privileged: true'
    r = iac.scan_code(code, "pod.yaml")
    priv = [f for f in r["findings"] if f["check_id"] == "k8s-privileged"]
    assert len(priv) > 0
    assert priv[0]["status"] == "FAIL"

def test_iac_scan_clean_tf():
    code = 'resource "aws_s3_bucket" "good" { bucket = "good-bucket" }'
    r = iac.scan_code(code, "main.tf")
    s3 = [f for f in r["findings"] if f["check_id"] == "tf-s3-public-acl"]
    assert len(s3) == 0 or s3[0]["status"] == "PASS"

def test_iac_scan_config():
    db = _mkdb(); u = _mkuser(); c = _build("iac_scanner_endpoints", db, u)
    r = c.get("/api/iac/scan-config")
    assert r.status_code == 200
    r2 = c.post("/api/iac/scan-config", json={"severity_threshold": "high", "auto_scan_enabled": True})
    assert r2.status_code == 200

def test_container_scan_image():
    import container_scanner_service as cs
    with patch("container_scanner_service._find_trivy", return_value=None):
        r = cs.scan_image("nginx:latest")
    assert "scan_id" in r
    assert r["image"] == "nginx:latest"
    assert r["total"] > 0
    assert "vulns" in r

def test_container_list_results():
    db = _mkdb(); u = _mkuser(); c = _build("container_scanner_endpoints", db, u)
    r = c.get("/api/container/results")
    assert r.status_code == 200

def test_iac_tenant_isolation():
    db = _mkdb()
    seeded = [
        {"tenantId": "tenant-a", "scan_id": "a-1", "provider": "terraform", "total": 1, "fail": 0, "findings": [], "scanned_at": "2026-01-01T00:00:00Z"},
        {"tenantId": "tenant-b", "scan_id": "b-1", "provider": "terraform", "total": 1, "fail": 0, "findings": [], "scanned_at": "2026-01-01T00:00:00Z"},
    ]
    def _find(query, *a, **kw):
        matched = [d for d in seeded if d.get("tenantId") == query.get("tenantId")]
        m = MagicMock(); m.sort = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=matched)))
        return m
    db._db.iac_scan_results.find = MagicMock(side_effect=_find)
    u = _mkuser("tenant-a", "user"); c = _build("iac_scanner_endpoints", db, u)
    with patch("iac_scanner_endpoints.get_tenant_id", return_value="tenant-a"):
        r = c.get("/api/iac/results")
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(i["scan_id"] == "a-1" for i in items), "tenant-a's own scan is missing"
    assert all(i["scan_id"] != "b-1" for i in items), "tenant-b's scan leaked into tenant-a's results"
    db._db.iac_scan_results.find.assert_called_with({"tenantId": "tenant-a"}, {"_id": 0})

def test_container_vuln_severity_counts():
    import container_scanner_service as cs
    with patch("container_scanner_service._find_trivy", return_value=None):
        r = cs.scan_image("test:latest")
    assert r["critical"] + r["high"] + r["medium"] + r["low"] == r["total"]

def test_iac_scan_cfn_s3_public_acl():
    code = 'Resources:\n  MyBucket:\n    Type: AWS::S3::Bucket\n    Properties:\n      AccessControl: PublicRead'
    r = iac.scan_code(code, "template.yaml")
    assert r["provider"] == "cloudformation"
    s3 = [f for f in r["findings"] if f["check_id"] == "cfn-s3-public-acl"]
    assert len(s3) > 0, f"No cfn-s3-public-acl findings in {r['findings']}"
    assert s3[0]["status"] == "FAIL"

def test_iac_scan_cfn_sg_open_ssh():
    code = (
        'Resources:\n'
        '  MySG:\n'
        '    Type: AWS::EC2::SecurityGroup\n'
        '    Properties:\n'
        '      SecurityGroupIngress:\n'
        '        - CidrIp: 0.0.0.0/0\n'
        '          FromPort: 22\n'
        '          ToPort: 22\n'
        '          IpProtocol: tcp\n'
    )
    r = iac.scan_code(code, "template.yaml")
    assert r["provider"] == "cloudformation"
    sg = [f for f in r["findings"] if f["check_id"] == "cfn-sg-open-ssh"]
    assert len(sg) > 0, f"No cfn-sg-open-ssh findings in {r['findings']}"
    assert sg[0]["status"] == "FAIL"

def test_iac_scan_cfn_rds_not_encrypted():
    code = (
        'Resources:\n'
        '  MyDB:\n'
        '    Type: AWS::RDS::DBInstance\n'
        '    Properties:\n'
        '      Engine: mysql\n'
        '      StorageEncrypted: false\n'
    )
    r = iac.scan_code(code, "template.yaml")
    assert r["provider"] == "cloudformation"
    rds = [f for f in r["findings"] if f["check_id"] == "cfn-rds-not-encrypted"]
    assert len(rds) > 0, f"No cfn-rds-not-encrypted findings in {r['findings']}"
    assert rds[0]["status"] == "FAIL"

def test_detect_provider_yaml_cloudformation():
    code = 'Resources:\n  B:\n    Type: AWS::S3::Bucket'
    assert iac._detect_provider(code, "yaml") == "cloudformation"

def test_detect_provider_json_cloudformation():
    code = '{"Resources": {"B": {"Type": "AWS::S3::Bucket"}}}'
    assert iac._detect_provider(code, "json") == "cloudformation"

def test_iac_scan_cfn_redos_bounded():
    import time
    vulnerable_block = (
        'Resources:\n'
        '  BadInstance:\n'
        '    Type: AWS::EC2::Instance\n'
        '    Properties:\n'
        '      UserData: "IyEvYmluL2Jhc2ggYWRtaW4gc2V0dXA="\n'
        '      # references admin setup in userdata\n'
    )
    filler_line = '  # ' + ('x' * 60) + '\n'
    filler_count = 400000 // len(filler_line)
    code = vulnerable_block + (filler_line * filler_count)
    start = time.perf_counter()
    r = iac.scan_code(code, "template.yaml")
    elapsed = time.perf_counter() - start
    assert r["provider"] == "cloudformation"
    assert elapsed < 5.0, f"CFN scan took {elapsed}s on a large template (possible ReDoS)"
