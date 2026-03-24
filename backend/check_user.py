import asyncio
from database import get_database, connect_to_mongo

async def check_user():
    await connect_to_mongo()
    db = get_database()
    user = await db.users.find_one({'email': 'super@omni.ai'})
    
    if user:
        print(f"✅ User found!")
        print(f"  Email: {user.get('email')}")
        print(f"  Username: {user.get('username', 'N/A')}")
        print(f"  Role: {user.get('role')}")
        print(f"  Has password field: {bool(user.get('password'))}")
    else:
        print("❌ User NOT found in database")
        print("\nTrying admin@omnisec.io instead...")
        user2 = await db.users.find_one({'email': 'admin@omnisec.io'})
        if user2:
            print(f"✅ Found admin@omnisec.io")
            print(f"  Role: {user2.get('role')}")

asyncio.run(check_user())
