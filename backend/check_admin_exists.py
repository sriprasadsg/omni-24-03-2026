
from backend.database import get_database
import asyncio

async def check_user():
    db = get_database()
    user = await db.users.find_one({"email": "admin@example.com"})
    if user:
        print(f"User FOUND: {user['email']}, Role: {user.get('role')}")
    else:
        print("User NOT FOUND")

if __name__ == "__main__":
    asyncio.run(check_user())
