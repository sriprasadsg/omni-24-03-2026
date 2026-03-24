from pymongo import MongoClient
import socket
import os

client = MongoClient('mongodb://localhost:27017')
db = client['omni_platform']

print('--- SYSTEM INFO ---')
print(f'Hostname: {socket.gethostname()}')

print('\n--- AGENTS IN DB ---')
for a in db.agents.find():
    print(f"ID: {a.get('id')}, Hostname: {a.get('hostname')}, Status: {a.get('status')}, Tenant: {a.get('tenantId')}")

print('\n--- RECENT INSTRUCTIONS ---')
# Show the most recent 10 instructions
cursor = db.agent_instructions.find().sort('created_at', -1).limit(10)
for doc in cursor:
    print(f"ID: {doc.get('_id')}, AgentID: {doc.get('agent_id')}, Status: {doc.get('status')}, Type: {doc.get('type')}, Tenant: {doc.get('tenantId')}")
    print(f"  Instr: {doc.get('instruction')}")
    print(f"  Payload: {doc.get('payload')}")

print('\n--- PENDING COUNTS BY AGENT ---')
pipeline = [
    {"$match": {"status": "pending"}},
    {"$group": {"_id": "$agent_id", "count": {"$sum": 1}}}
]
for result in db.agent_instructions.aggregate(pipeline):
    print(f"Agent {result['_id']}: {result['count']} pending")
