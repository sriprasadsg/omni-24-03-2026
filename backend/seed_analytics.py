
import asyncio
import random
from datetime import datetime, timedelta, timezone
from database import connect_to_mongo, get_database, close_mongo_connection

async def seed_analytics():
    print("Connecting to database...")
    await connect_to_mongo()
    db = get_database()

    print("Generating historical data...")
    
    # Generate dates for the last 6 months
    today = datetime.now(timezone.utc)
    months = []
    for i in range(6):
        d = today - timedelta(days=30 * (5 - i))
        months.append(d.strftime("%Y-%m-%d"))

    # Alerts Data (Critical, High, Medium)
    alerts_data = []
    for date in months:
        alerts_data.append({
            "date": date,
            "Critical": random.randint(2, 10),
            "High": random.randint(5, 20),
            "Medium": random.randint(10, 50)
        })

    # Compliance Data (Score)
    compliance_data = []
    base_score = 75
    for date in months:
        # Slowly improving score
        base_score = min(99, base_score + random.randint(0, 5))
        compliance_data.append({
            "date": date,
            "score": base_score
        })

    # Vulnerabilities Data (Critical, High)
    vuln_data = []
    for date in months:
        vuln_data.append({
            "date": date,
            "Critical": random.randint(0, 5),
            "High": random.randint(5, 15)
        })

    # Construct the document
    analytics_doc = {
        "date": today.isoformat(),
        "alerts": alerts_data,
        "compliance": compliance_data,
        "vulnerabilities": vuln_data
    }

    print("Inserting data into analytics_historical...")
    # Clear existing data to avoid confusion/duplicates piling up
    await db.analytics_historical.delete_many({})
    
    result = await db.analytics_historical.insert_one(analytics_doc)
    print(f"Inserted document with ID: {result.inserted_id}")

    await close_mongo_connection()
    print("Done!")

if __name__ == "__main__":
    asyncio.run(seed_analytics())
