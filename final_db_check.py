import asyncio
import motor.motor_asyncio

async def main():
    client = motor.motor_asyncio.AsyncIOMotorClient('mongodb://localhost:27017')
    db = client['omni_agent']
    docs = await db['asset_compliance'].find({}, {'controlId': 1}).limit(20).to_list(length=20)
    ids = [d['controlId'] for d in docs]
    print(f"Control IDs: {ids}")
    
    prefixed = [i for i in ids if '-' in i and any(p in i for p in ['nist', 'iso', 'pci', 'hipaa', 'gdpr'])]
    if prefixed:
        print(f"Found prefixed IDs: {prefixed}")
    else:
        print("All IDs appear to be correctly stripped of prefixes!")

if __name__ == '__main__':
    asyncio.run(main())
