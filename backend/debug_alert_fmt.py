import asyncio
import os
import sys

# Add parent dir to path if needed, but we are running inside backend so it should be fine if dependencies are installed.
# Actually database.py is in backend/

from database import get_database, connect_to_mongo
from dotenv import load_dotenv

load_dotenv()

async def main():
    try:
        await connect_to_mongo()
        db = get_database()
        alert = await db.alerts.find_one()
        if alert:
            print(f"Timestamp: {alert.get('timestamp')}")
            print(f"Type: {type(alert.get('timestamp'))}")
        else:
            print("No alerts found")
            # If no alerts, insert one to test?
            # No, let's just see.
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
