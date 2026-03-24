from fastapi import APIRouter, Depends, HTTPException, Query, Body
from typing import List, Optional, Dict, Any
from database import get_database
from authentication_service import get_current_user
import datetime
import uuid

router = APIRouter(prefix="/api/network-devices", tags=["Network"])

@router.get("")
async def get_network_devices(
    tenant_id: Optional[str] = None,
    current_user: Any = Depends(get_current_user)
):
    """
    Get network devices.
    """
    db = get_database()
    
    # Filter by user's tenant if not explicitly overridden by an admin (and logic permitted)
    user_tenant_id = getattr(current_user, "tenant_id", None)
    
    query = {}
    if user_tenant_id and user_tenant_id != "platform-admin":
        query["tenantId"] = user_tenant_id
    elif tenant_id:
        query["tenantId"] = tenant_id
        
    devices = await db.network_devices.find(query, {"_id": 0}).to_list(length=1000)
    return devices

@router.post("")
async def add_network_device(
    device_data: Dict[str, Any] = Body(...),
    current_user: Any = Depends(get_current_user)
):
    """
    Manually add a network device.
    """
    db = get_database()
    
    tenant_id = getattr(current_user, "tenant_id", "default")
    
    device_id = f"net-dev-{uuid.uuid4().hex[:12]}"
    
    new_device = {
        "id": device_id,
        "tenantId": tenant_id,
        "status": "Up",
        "lastSeen": datetime.datetime.utcnow().isoformat(),
        "interfaces": [], 
        "configBackups": [], 
        "vulnerabilities": [],
        **device_data
    }
    
    
    await db.network_devices.insert_one(new_device)
    
    return new_device

@router.get("/subnets")
async def get_network_subnets(
     current_user: Any = Depends(get_current_user)
):
    """
    Get unique subnets from discovered devices.
    """
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", "default")
    
    # Aggregation to find distinct subnets
    pipeline = [
        {"$match": {"tenantId": tenant_id}},
        {"$group": {"_id": "$subnet"}},
        {"$sort": {"_id": 1}}
    ]
    
    results = await db.network_devices.aggregate(pipeline).to_list(length=100)
    subnets = [r["_id"] for r in results if r["_id"]]
    return subnets

@router.post("/scan")
async def trigger_server_scan(
    scan_all_networks: bool = Query(True, description="Scan all network interfaces"),
    subnet: Optional[str] = Query(None, description="Specific subnet to scan (e.g. 192.168.1.0/24)"),
    current_user: Any = Depends(get_current_user)
):
    """
    Trigger a network scan from the server side.
    Args:
        scan_all_networks: If True, scan all detected network interfaces. If False, scan only primary subnet.
        subnet: Specific subnet to scan. Overrides scan_all_networks if provided.
    """
    try:
        # Import dynamically to avoid circular deps or startup issues
        try:
            from .server_discovery import ServerDiscovery
        except ImportError:
            from server_discovery import ServerDiscovery
            
        import uuid
        
        db = get_database()
        tenant_id = getattr(current_user, "tenant_id", "default")
        
        # Run the scan with multi-network support
        print(f"Starting server scan (scan_all_networks={scan_all_networks}, subnet={subnet})...")
        results = ServerDiscovery.start_scan(scan_all_networks=scan_all_networks, subnet=subnet)
        print(f"Scan finished. Found {len(results)} devices.")
        
        # Process results and update DB with Smart Merge
        for device in results:
            ip = device["ip"]
            mac = device.get("mac", "Unknown")
            
            # 1. Find ALL existing devices that match this IP OR MAC for the current tenant 
            # OR (if platform admin) any devices that might be the same physical device.
            match_query = {
                "$or": [
                    {"ipAddress": ip},
                    {"macAddress": mac if mac != "Unknown" else "NonExistentMAC"}
                ]
            }
            
            # If current_user is platform-admin, we look across ALL tenants to find a definitive match
            # But if a match is found in another tenant, we should probably stick to it or update it 
            # to avoid duplication.
            # Otherwise, restrict to user tenant.
            if tenant_id != "platform-admin":
                match_query["tenantId"] = tenant_id
            
            existing_matches = await db.network_devices.find(match_query).to_list(length=10)
            
            if existing_matches:
                # 2. Consolidation Logic
                # If we have multiple matches, we take the "best" one to keep and delete the others.
                # Prioritize: 
                # a) The one with a valid MAC
                # b) The one matching the user's current tenant (if possible)
                
                # Sort matches: valid MAC first, then tenant match
                existing_matches.sort(key=lambda x: (
                    1 if x.get("macAddress") and x.get("macAddress") != "Unknown" else 0,
                    1 if x.get("tenantId") == tenant_id else 0
                ), reverse=True)
                
                primary = existing_matches[0]
                others_to_delete = existing_matches[1:]
                
                # 3. Merge data from scan and other matching records into the primary
                update_fields = {
                    "lastSeen": device["lastSeen"],
                    "status": "Up",
                    "hostname": device["hostname"] if device["hostname"] != ip else primary.get("hostname", device["hostname"]),
                    "subnet": device.get("subnet", primary.get("subnet", "Unknown")),
                    "vendor": device.get("vendor") if device.get("vendor") != "Unknown" else primary.get("vendor", "Unknown"),
                    "osVersion": device.get("os_version") if device.get("os_version") != "Unknown" else primary.get("osVersion", "Unknown"),
                    "scanEngine": device.get("params", "unknown")
                }
                
                # Update ports union
                existing_ports = set(primary.get("openPorts", []))
                for m in others_to_delete:
                    existing_ports.update(m.get("openPorts", []))
                existing_ports.update(device.get("open_ports", []))
                update_fields["openPorts"] = list(existing_ports)
                
                # Update IP if it changed (DHCP)
                if primary.get("ipAddress") != ip:
                    update_fields["ipAddress"] = ip
                
                # Update MAC if we finally found one
                if mac != "Unknown":
                    update_fields["macAddress"] = mac
                
                # Apply updates to primary
                await db.network_devices.update_one({"_id": primary["_id"]}, {"$set": update_fields})
                
                # Delete redundant entries
                if others_to_delete:
                    other_ids = [m["_id"] for m in others_to_delete]
                    await db.network_devices.delete_many({"_id": {"$in": other_ids}})
                    print(f"Consolidated and merged {len(others_to_delete)} duplicate(s) for {ip}/{mac}")
            else:
                # 4. Insert new device
                new_dev = {
                    "id": f"net-dev-{uuid.uuid4().hex[:12]}",
                    "tenantId": tenant_id,
                    "hostname": device["hostname"],
                    "ipAddress": ip,
                    "macAddress": mac,
                    "deviceType": device["device_type"],
                    "model": "Unknown",
                    "vendor": device.get("vendor", "Unknown"),
                    "osVersion": device.get("os_version", "Unknown"),
                    "openPorts": device.get("open_ports", []),
                    "scanEngine": device.get("params", "unknown"),
                    "status": "Up",
                    "lastSeen": device["lastSeen"],
                    "subnet": device.get("subnet", "Unknown"),
                    "interfaces": [],
                    "configBackups": [],
                    "vulnerabilities": []
                }
                await db.network_devices.insert_one(new_dev)
                
        return {"status": "success", "devices_found": len(results)}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/topology-image")
async def get_network_topology_image(
    current_user: Any = Depends(get_current_user)
):
    """
    Generate and return the network topology image.
    """
    try:
        from fastapi.responses import FileResponse
        # Import dynamically to avoid circular deps or startup issues
        try:
            from .visualize_network import generate_network_graph
        except ImportError:
            from visualize_network import generate_network_graph
            
        # Generate the graph
        image_path = generate_network_graph()
        
        return FileResponse(image_path)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/topology")
async def get_network_topology(
    current_user: Any = Depends(get_current_user)
):
    """
    Get network topology data (JSON) for interactive map.
    """
    try:
        # Import dynamically
        try:
            from .network_topology_service import NetworkTopologyService
        except ImportError:
            from network_topology_service import NetworkTopologyService
            
        tenant_id = getattr(current_user, "tenant_id", "default")
        topology_data = await NetworkTopologyService.get_topology_data(tenant_id)
        
        return topology_data
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
