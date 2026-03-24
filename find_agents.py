from pymongo import MongoClient
client = MongoClient('mongodb://localhost:27017')
db = client['omni_platform']
hostname = 'EILT0197'
print(f'--- Agents for {hostname} ---')
for a in db.agents.find({'hostname': hostname}):
    print(f"ID: {a.get('id')}, Status: {a.get('status')}, LastSeen: {a.get('lastSeen')}")
