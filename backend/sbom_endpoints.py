from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from typing import List, Dict, Any
import logging
from datetime import datetime
import json
import uuid
from database import get_database
from auth_types import TokenData
from rbac_service import rbac_service
from tenant_context import get_tenant_id

logger = logging.getLogger(__name__)


async def _correlate_vulnerabilities(db, components: list) -> Dict[str, list]:
    """
    Cross-reference SBOM components against the patches and vulnerabilities
    collections. Returns a dict keyed by component id → list of matched CVEs.
    """
    if not components:
        return {}

    # Build a name→component lookup for batch querying
    name_to_ids: Dict[str, list] = {}
    for c in components:
        name = (c.get("name") or "").lower().strip()
        if name:
            name_to_ids.setdefault(name, []).append(c["id"])

    if not name_to_ids:
        return {}

    results: Dict[str, list] = {}

    try:
        # Query patches where affectedSoftware matches any component name
        import re as _re
        name_regexes = [{"affectedSoftware": {"$regex": _re.escape(name), "$options": "i"}} for name in name_to_ids]
        patch_cursor = db.patches.find(
            {"$or": name_regexes},
            {"_id": 0, "cveId": 1, "severity": 1, "affectedSoftware": 1, "description": 1, "cvss_score": 1},
        )
        patches = await patch_cursor.to_list(length=500)

        for patch in patches:
            affected = (patch.get("affectedSoftware") or "").lower()
            for name, ids in name_to_ids.items():
                if name in affected or affected in name:
                    vuln_entry = {
                        "cveId": patch.get("cveId", ""),
                        "severity": patch.get("severity", "Unknown"),
                        "description": patch.get("description", ""),
                        "cvss": patch.get("cvss_score"),
                        "source": "patches",
                    }
                    for comp_id in ids:
                        results.setdefault(comp_id, []).append(vuln_entry)

        # Also query vulnerabilities collection
        import re as _re
        vuln_cursor = db.vulnerabilities.find(
            {"$or": [{"affectedSoftware": {"$regex": _re.escape(name), "$options": "i"}} for name in name_to_ids]},
            {"_id": 0, "cveId": 1, "severity": 1, "affectedSoftware": 1, "description": 1},
        )
        vulns = await vuln_cursor.to_list(length=500)

        for vuln in vulns:
            affected = (vuln.get("affectedSoftware") or "").lower()
            for name, ids in name_to_ids.items():
                if name in affected or affected in name:
                    vuln_entry = {
                        "cveId": vuln.get("cveId", ""),
                        "severity": vuln.get("severity", "Unknown"),
                        "description": vuln.get("description", ""),
                        "cvss": None,
                        "source": "vulnerabilities",
                    }
                    for comp_id in ids:
                        existing = results.get(comp_id, [])
                        if not any(e["cveId"] == vuln_entry["cveId"] for e in existing):
                            results.setdefault(comp_id, []).append(vuln_entry)
    except Exception as exc:
        logger.warning("SBOM vulnerability correlation failed: %s", exc)

    return results

router = APIRouter(prefix="/api/sboms", tags=["SBOM"])

@router.get("", response_model=List[Dict[str, Any]])
async def get_sboms(_current_user: TokenData = Depends(rbac_service.has_permission("view:sbom"))):
    """
    Get all uploaded SBOMs for the current tenant.
    """
    db = get_database()
    tenant_id = get_tenant_id()
    sboms = await db.sboms.find({"tenantId": tenant_id}, {"_id": 0}).to_list(length=500)
    return sboms

@router.post("/upload")
async def upload_sbom(
    file: UploadFile = File(...),
    current_user: TokenData = Depends(rbac_service.has_permission("manage:sbom")) # Specific permission
):
    """
    Upload and parse an SBOM file (CycloneDX JSON).
    """
    try:
        content = await file.read()
        if len(content) > 50 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="SBOM file too large (max 50 MB)")
        sbom_data = json.loads(content)
        
        db = get_database()
        tenant_id = get_tenant_id()
        
        sbom_id = f"sbom-{uuid.uuid4()}"
        
        # Basic parsing of CycloneDX
        metadata = sbom_data.get("metadata", {})
        component = metadata.get("component", {})
        app_name = component.get("name", file.filename)
        
        components = sbom_data.get("components", [])[:2000]
        
        new_sbom = {
            "id": sbom_id,
            "tenantId": tenant_id,
            "applicationName": app_name,
            "uploadedAt": datetime.now().isoformat(),
            "componentCount": len(components),
            "uploadedBy": current_user.username
        }
        
        await db.sboms.insert_one(new_sbom)
        new_sbom["_id"] = str(new_sbom["_id"])
        
        # Store individual components
        component_docs = []
        for comp in components:
            comp_id = f"comp-{uuid.uuid4()}"
            comp_doc = {
                "id": comp_id,
                "tenantId": tenant_id,
                "sbomId": sbom_id,
                "name": comp.get("name"),
                "version": comp.get("version"),
                "type": comp.get("type", "library"),
                "purl": comp.get("purl"),
                "supplier": comp.get("supplier", {}).get("name") or comp.get("publisher") or comp.get("group"),
                "licenses": [{"id": l.get("license", {}).get("id"), "name": l.get("license", {}).get("name")} for l in comp.get("licenses", []) if l.get("license")],
                "hashes": {h["alg"]: h["content"] for h in comp.get("hashes", [])},
                "vulnerabilities": []
            }
            component_docs.append(comp_doc)
            
        if component_docs:
            # Correlate vulnerabilities before storing
            vuln_map = await _correlate_vulnerabilities(db, component_docs)
            for comp_doc in component_docs:
                comp_doc["vulnerabilities"] = vuln_map.get(comp_doc["id"], [])

            await db.software_components.insert_many(component_docs)
            for c in component_docs:
                if "_id" in c:
                    c["_id"] = str(c["_id"])

        vuln_count = sum(len(c.get("vulnerabilities", [])) for c in component_docs)
        return {"success": True, "sbom": new_sbom, "components": component_docs, "vulnerabilityCount": vuln_count}
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format")
    except Exception as e:
        logger.error("Error uploading SBOM: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/components", response_model=List[Dict[str, Any]])
async def get_software_components(_current_user: TokenData = Depends(rbac_service.has_permission("view:sbom"))):
    """
    Get all software components from all SBOMs.
    """
    db = get_database()
    tenant_id = get_tenant_id()
    components = await db.software_components.find({"tenantId": tenant_id}, {"_id": 0}).to_list(length=500)
    return components


@router.get("/{sbom_id}", response_model=Dict[str, Any])
async def get_sbom(
    sbom_id: str,
    _current_user: TokenData = Depends(rbac_service.has_permission("view:sbom")),
):
    """Get a single SBOM with its components."""
    db = get_database()
    tenant_id = get_tenant_id()
    sbom = await db.sboms.find_one({"id": sbom_id, "tenantId": tenant_id}, {"_id": 0})
    if not sbom:
        raise HTTPException(status_code=404, detail="SBOM not found")
    components = await db.software_components.find(
        {"sbomId": sbom_id, "tenantId": tenant_id}, {"_id": 0}
    ).to_list(length=500)
    return {**sbom, "components": components}


@router.post("/{sbom_id}/scan-vulnerabilities")
async def scan_sbom_vulnerabilities(
    sbom_id: str,
    _current_user: TokenData = Depends(rbac_service.has_permission("view:sbom")),
):
    """Re-run vulnerability correlation for an existing SBOM."""
    db = get_database()
    tenant_id = get_tenant_id()

    sbom = await db.sboms.find_one({"id": sbom_id, "tenantId": tenant_id}, {"_id": 0})
    if not sbom:
        raise HTTPException(status_code=404, detail="SBOM not found")

    components = await db.software_components.find(
        {"sbomId": sbom_id, "tenantId": tenant_id}, {"_id": 0}
    ).to_list(length=500)

    if not components:
        return {"sbomId": sbom_id, "vulnerabilityCount": 0, "components": []}

    vuln_map = await _correlate_vulnerabilities(db, components)
    updated = []
    for comp in components:
        vulns = vuln_map.get(comp["id"], [])
        await db.software_components.update_one(
            {"id": comp["id"], "tenantId": tenant_id},
            {"$set": {"vulnerabilities": vulns}},
        )
        updated.append({**comp, "vulnerabilities": vulns})

    vuln_count = sum(len(c["vulnerabilities"]) for c in updated)
    return {"sbomId": sbom_id, "vulnerabilityCount": vuln_count, "components": updated}


@router.post("/generate")
async def generate_sbom(
    request: Dict[str, Any],
    current_user: TokenData = Depends(rbac_service.has_permission("manage:sbom")),
):
    """
    Generate an SBOM for the current host using Syft (if available) or pip/npm fallback.
    Stores the result and correlates vulnerabilities automatically.
    """
    import subprocess, shutil, tempfile, os, platform
    from pathlib import Path

    raw_target = request.get("target", ".")
    app_name = request.get("app_name", "host-system")

    # Resolve and validate target path to prevent directory traversal and symlink escapes
    try:
        target_path = Path(raw_target).resolve(strict=True)
    except (OSError, Exception):
        raise HTTPException(status_code=400, detail="Invalid target path")

    # Reject symlinks at any component of the resolved path
    if os.path.islink(raw_target):
        raise HTTPException(status_code=400, detail="Symlinked targets are not permitted")

    allowed_root = Path(".").resolve()
    if not (target_path == allowed_root or str(target_path).startswith(str(allowed_root) + os.sep)):
        raise HTTPException(status_code=400, detail="Target path must be within the working directory")

    target = str(target_path)

    db = get_database()
    tenant_id = get_tenant_id()
    sbom_id = f"sbom-{uuid.uuid4()}"

    components: List[Dict[str, Any]] = []
    source = "unknown"

    # ── Strategy 1: Syft CLI ───────────────────────────────────────────────────
    if shutil.which("syft"):
        try:
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
                tmp_path = tmp.name
            subprocess.run(
                ["syft", target, "-o", f"cyclonedx-json={tmp_path}"],
                capture_output=True, timeout=120, check=True,
            )
            with open(tmp_path) as f:
                syft_data = json.load(f)
            os.unlink(tmp_path)

            for comp in syft_data.get("components", []):
                components.append({
                    "id": f"comp-{uuid.uuid4()}",
                    "tenantId": tenant_id,
                    "sbomId": sbom_id,
                    "name": comp.get("name", ""),
                    "version": comp.get("version", ""),
                    "type": comp.get("type", "library"),
                    "purl": comp.get("purl", ""),
                    "supplier": None,
                    "licenses": [
                        {"id": lic.get("license", {}).get("id"), "name": lic.get("license", {}).get("name")}
                        for lic in comp.get("licenses", []) if lic.get("license")
                    ],
                    "hashes": {h["alg"]: h["content"] for h in comp.get("hashes", [])},
                    "vulnerabilities": [],
                })
            source = "syft"
            logger.info("[SBOM] Generated %d components via Syft", len(components))
        except Exception as exc:
            logger.warning("[SBOM] Syft failed (%s), falling back to pip/npm", exc)

    # ── Strategy 2: pip list (Python packages) ────────────────────────────────
    if not components:
        try:
            py_exe = "python" if platform.system() == "Windows" else "python3"
            out = subprocess.check_output(
                [py_exe, "-m", "pip", "list", "--format=json"],
                stderr=subprocess.DEVNULL, timeout=30,
            ).decode()
            for pkg in json.loads(out):
                components.append({
                    "id": f"comp-{uuid.uuid4()}",
                    "tenantId": tenant_id,
                    "sbomId": sbom_id,
                    "name": pkg["name"],
                    "version": pkg["version"],
                    "type": "library",
                    "purl": f"pkg:pypi/{pkg['name'].lower()}@{pkg['version']}",
                    "supplier": None,
                    "licenses": [],
                    "hashes": {},
                    "vulnerabilities": [],
                })
            source = "pip"
            logger.info("[SBOM] Generated %d Python components via pip", len(components))
        except Exception as exc:
            logger.warning("[SBOM] pip fallback failed: %s", exc)

    # ── Strategy 3: npm list (Node packages) ─────────────────────────────────
    if shutil.which("npm"):
        try:
            out = subprocess.check_output(
                ["npm", "list", "-g", "--json", "--depth=0"],
                stderr=subprocess.DEVNULL, timeout=30,
            ).decode()
            data = json.loads(out)
            for name, info in (data.get("dependencies") or {}).items():
                ver = info.get("version", "")
                if ver:
                    components.append({
                        "id": f"comp-{uuid.uuid4()}",
                        "tenantId": tenant_id,
                        "sbomId": sbom_id,
                        "name": name,
                        "version": ver,
                        "type": "library",
                        "purl": f"pkg:npm/{name}@{ver}",
                        "supplier": None,
                        "licenses": [],
                        "hashes": {},
                        "vulnerabilities": [],
                    })
            if not source or source == "unknown":
                source = "npm"
        except Exception:
            pass

    if not components:
        raise HTTPException(status_code=500, detail="SBOM generation failed: no package managers available (syft, pip, npm)")

    # ── Correlate vulnerabilities then store ──────────────────────────────────
    vuln_map = await _correlate_vulnerabilities(db, components)
    for comp in components:
        comp["vulnerabilities"] = vuln_map.get(comp["id"], [])

    sbom_doc = {
        "id": sbom_id,
        "tenantId": tenant_id,
        "applicationName": app_name,
        "generatedAt": datetime.now().isoformat(),
        "source": source,
        "target": target,
        "componentCount": len(components),
        "uploadedBy": current_user.username,
    }

    await db.sboms.insert_one(sbom_doc)
    sbom_doc.pop("_id", None)
    if components:
        await db.software_components.insert_many(components)
        for c in components:
            c.pop("_id", None)

    vuln_count = sum(len(c.get("vulnerabilities", [])) for c in components)
    return {
        "success": True,
        "sbom": sbom_doc,
        "components": components[:50],  # cap response; full data in DB
        "component_count": len(components),
        "vulnerability_count": vuln_count,
        "generation_source": source,
    }
