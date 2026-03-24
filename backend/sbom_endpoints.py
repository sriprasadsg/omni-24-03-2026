from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from typing import List, Dict, Any
from datetime import datetime
import json
import uuid
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
from rbac_service import rbac_service
from tenant_context import get_tenant_id

router = APIRouter(prefix="/api/sboms", tags=["SBOM"])

@router.get("", response_model=List[Dict[str, Any]])
async def get_sboms(current_user: TokenData = Depends(rbac_service.has_permission("view:sbom"))):
    """
    Get all uploaded SBOMs for the current tenant.
    """
    db = get_database()
    tenant_id = get_tenant_id()
    sboms = await db.sboms.find({"tenantId": tenant_id}, {"_id": 0}).to_list(length=None)
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
        sbom_data = json.loads(content)
        
        db = get_database()
        tenant_id = get_tenant_id()
        
        sbom_id = f"sbom-{uuid.uuid4()}"
        
        # Basic parsing of CycloneDX
        metadata = sbom_data.get("metadata", {})
        component = metadata.get("component", {})
        app_name = component.get("name", file.filename)
        
        components = sbom_data.get("components", [])
        
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
                "vulnerabilities": [] # Placeholder for vuln scanning
            }
            component_docs.append(comp_doc)
            
        if component_docs:
            await db.software_components.insert_many(component_docs)
            for c in component_docs:
                if "_id" in c:
                    c["_id"] = str(c["_id"])
            
        return {"success": True, "sbom": new_sbom, "components": component_docs}
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format")
    except Exception as e:
        print(f"Error uploading SBOM: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/components", response_model=List[Dict[str, Any]])
async def get_software_components(current_user: TokenData = Depends(rbac_service.has_permission("view:sbom"))):
    """
    Get all software components from all SBOMs.
    """
    db = get_database()
    tenant_id = get_tenant_id()
    components = await db.software_components.find({"tenantId": tenant_id}, {"_id": 0}).to_list(length=None)
    return components
