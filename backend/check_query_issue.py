import asyncio
from database import get_database, connect_to_mongo
from tenant_context import set_tenant_id

async def check():
    await connect_to_mongo()
    
    acme_id = "tenant_f15daa22a46a"
    set_tenant_id(acme_id)
    
    db = get_database()
    from database import mongodb
    raw_coll = mongodb.db.agents
    
    print(f"Isolated DB: {db._db.name}, Collection: {db.agents._collection.name}")
    print(f"Raw DB: {mongodb.db.name}, Collection: {raw_coll.name}")
    print(f"Are they the same object? {db._db is mongodb.db}")
    
    raw_total = await raw_coll.count_documents({})
    iso_total = await db.agents._collection.count_documents({})
    print(f"Raw Total Count: {raw_total}")
    print(f"Iso Total Count: {iso_total}")
    
    # Redefine acme_id for clarity
    acme_id = "tenant_f15daa22a46a"
    
    print("\n--- Non-Online Find ---")
    query = {"status": {"$ne": "Online"}}
    count = 0
    async for agent in raw_coll.find(query):
        print(f"Match (Not Online): {agent.get('id')} - Status: {repr(agent.get('status'))}")
        count += 1
    print(f"Non-Online match count: {count}")
    print(f"Querying for: {query}")
    
    print("\n--- All Agents Raw (Summary) ---")
    async for agent in db.agents.find({}):
        tid = agent.get('tenantId')
        st = agent.get('status')
        print(f"Agent ID: {repr(agent.get('id'))}")
        print(f"  Tenant: {repr(tid)} (bytes: {tid.encode() if tid else b''})")
        print(f"  Status: {repr(st)} (bytes: {st.encode() if st else b''})")
    print("-" * 20)
    
    # Manual match check
    print("\n--- Manual Python Match ---")
    acme_id = "tenant_f15daa22a46a"
    status_to_check = "Online"
    match_count = 0
    async for agent in db.agents.find({}):
        tid = agent.get('tenantId')
        st = agent.get('status')
        print(f"Agent {agent.get('id')}:")
        print(f"  Status Value: {repr(st)}")
        print(f"  Status Type:  {type(st)}")
        print(f"  Status Hex:   {st.encode().hex() if st else ''}")
        print(f"  Target Hex:   {'Online'.encode().hex()}")
        print(f"  Equality:     {st == 'Online'}")
        
        if st == 'Online':
            match_count += 1
    print(f"Manual match count: {match_count}")

if __name__ == "__main__":
    asyncio.run(check())
