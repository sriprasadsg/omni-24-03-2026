
import asyncio
from database import get_database, connect_to_mongo, close_mongo_connection

async def seed_compliance_pricing():
    try:
        await connect_to_mongo()
        db = get_database()
        
        compliance_services = [
            {
                "id": "compliance_soc2",
                "name": "SOC2 as a Service",
                "unit": "per_month_flat",
                "price": 499.00,
                "category": "Compliance",
                "description": "Automated SOC2 compliance monitoring and evidence collection"
            },
            {
                "id": "compliance_iso27001",
                "name": "ISO27001 as a Service",
                "unit": "per_month_flat",
                "price": 699.00,
                "category": "Compliance",
                "description": "Automated ISO27001 compliance framework and controls"
            }
        ]
        
        for service in compliance_services:
            result = await db.service_pricing.update_one(
                {"id": service["id"]},
                {"$set": service},
                upsert=True
            )
            print(f"Upserted service: {service['name']}")
            
        print("Compliance pricing seeding completed.")
        
    except Exception as e:
        print(f"Error seeding pricing: {e}")
    finally:
        await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(seed_compliance_pricing())
