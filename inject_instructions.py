import datetime
from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017')
db = client['omni_platform']
tenant = db.tenants.find_one({'registrationKey': 'reg_60125ea96bb44936'})
tenant_id = tenant.get('id') if tenant else 'default_tenant'
print(f'Using tenant ID: {tenant_id}')

instructions = [
    {
        'agent_id': 'agent-cd82b8d0',
        'instruction': 'upgrade_software: accelerate',
        'status': 'pending',
        'created_at': datetime.datetime.utcnow().isoformat(),
        'type': 'upgrade_software: accelerate',
        'payload': {'package': 'accelerate', 'pkg_type': 'pip'},
        'tenantId': tenant_id
    },
    {
        'agent_id': 'agent-cd82b8d0',
        'instruction': 'upgrade_software: pytest',
        'status': 'pending',
        'created_at': datetime.datetime.utcnow().isoformat(),
        'type': 'upgrade_software: pytest',
        'payload': {'package': 'pytest', 'pkg_type': 'pip'},
        'tenantId': tenant_id
    }
]
res = db.agent_instructions.insert_many(instructions)
print(f'Inserted {len(res.inserted_ids)} instructions')
