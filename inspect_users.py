
import asyncio
from backend.database import connect_to_mongo, get_database

async def list_users():
    await connect_to_mongo()
    db = get_database()
    users = await db.users.find({}, {"email": 1, "role": 1, "_id": 0}).to_list(length=100)
    print("--- USERS IN DB ---")
    for user in users:
        print(user)
    print("-------------------")

if __name__ == "__main__":
    asyncio.run(list_users())
