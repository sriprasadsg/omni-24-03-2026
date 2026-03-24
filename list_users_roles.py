from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

client = MongoClient(os.getenv('MONGODB_URL', 'mongodb://localhost:27017/'))
db = client[os.getenv('MONGODB_DB_NAME', 'omni_agent_db')]

users = list(db.users.find({}, {'_id': 0, 'email': 1, 'name': 1, 'role': 1}))
print('\nExisting Users:')
for u in users:
    print(f"  {u.get('email')} - {u.get('name')} ({u.get('role')})")

# Get roles
print('\n\nExisting Roles:')
roles = list(db.roles.find({}, {'_id': 0, 'name': 1, 'permissions': 1}))
for r in roles:
    perms = r.get('permissions', [])
    has_remediate = 'remediate:agents' in perms
    has_view = 'view:agents' in perms
    print(f"\n  Role: {r.get('name')}")
    print(f"    Total permissions: {len(perms)}")
    print(f"    Has 'view:agents': {has_view}")
    print(f"    Has 'remediate:agents': {has_remediate}")

client.close()
