"""Dump one agent, tenant and user to debug.json for troubleshooting.

Usage: DEBUG_AGENT_ID=... DEBUG_TENANT_ID=... DEBUG_USER_EMAIL=... python debug.py

The output holds tenant secrets (registration key, API keys), so it is
gitignored and the user's password hash is never included. Identifiers come
from the environment — a hardcoded registration key here was committed once.
"""
import json
import os

from pymongo import MongoClient
from bson import ObjectId

class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        return super().default(o)

db = MongoClient('mongodb://127.0.0.1:27017')['omni_platform']
data = {
    'Agents': list(db.agents.find({'id': os.environ['DEBUG_AGENT_ID']}, {'agentSecretHash': 0})),
    'Tenant': list(db.tenants.find({'id': os.environ['DEBUG_TENANT_ID']})),
    'User': list(db.users.find({'email': os.environ['DEBUG_USER_EMAIL']}, {'password': 0})),
}

with open('debug.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, cls=JSONEncoder, indent=2)
