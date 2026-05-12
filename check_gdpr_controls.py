import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    db = client['omni_platform']
    
    framework = await db.compliance_frameworks.find_one({'id': 'gdpr'})
    if framework:
        controls = framework.get('controls', [])
        print(f"GDPR Framework: {framework.get('name')}")
        print(f"Total controls: {len(controls)}")
        if controls:
            print(f"First control: {controls[0].get('id')} - {controls[0].get('name')}")
    else:
        print("GDPR NOT found")
        
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
