from pymongo import MongoClient
import pprint

client = MongoClient("mongodb://localhost:27017/")
db = client['omni_platform']
agents_collection = db['agents']

# Find the local agent (assuming hostname matches)
# Or just find ANY agent with 'compliance_enforcement' in meta
agent = agents_collection.find_one({"meta.compliance_enforcement": {"$exists": True}})

if agent:
    print(f"\n=== COMPLIANCE DATA FOR {agent.get('hostname')} ===")
    import json
    # Use json dumps for clean formatting instead of pprint
    print(json.dumps(agent['meta']['compliance_enforcement'], indent=2))
else:
    print("No agent with compliance data found.")
