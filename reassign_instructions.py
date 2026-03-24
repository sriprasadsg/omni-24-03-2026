from pymongo import MongoClient
client = MongoClient('mongodb://localhost:27017')
db = client['omni_platform']
target_id = 'agent-cd82b8d0'
result = db.agent_instructions.update_many(
    {'status': 'pending'},
    {'$set': {'agent_id': target_id}}
)
print(f"Successfully re-assigned {result.modified_count} instructions to {target_id}")
