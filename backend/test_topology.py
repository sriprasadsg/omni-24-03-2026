
import asyncio
import json
from database import connect_to_mongo, get_database
from network_topology_service import NetworkTopologyService

async def test_topology():
    await connect_to_mongo()
    db = get_database()
    
    devices = await db.network_devices.find({"tenantId": "default"}).to_list(length=10)
    print(f"Found {len(devices)} devices in DB for tenant 'default'")
    
    data = await NetworkTopologyService.get_topology_data("default")
    print("Topology Logic Result:")
    print(f"Nodes: {len(data['elements']['nodes'])}")
    print(f"Edges: {len(data['elements']['edges'])}")
    
    # print(json.dumps(data, indent=2))

if __name__ == "__main__":
    asyncio.run(test_topology())
