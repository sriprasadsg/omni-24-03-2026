import json
from pymongo import MongoClient
from bson import ObjectId

class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        return super().default(o)

db = MongoClient('mongodb://127.0.0.1:27017')['omni_platform']
data = {
    'Agents': list(db.agents.find({'id': 'agent-81e24d3d'})),
    'Tenant': list(db.tenants.find({'registrationKey': 'reg_86bac8a732a24020'})),
    'User': list(db.users.find({'email': 'admin@acmecorp.com'}))
}

with open('debug.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, cls=JSONEncoder, indent=2)
