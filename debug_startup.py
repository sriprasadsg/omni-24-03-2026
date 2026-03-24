
import asyncio
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

try:
    from database import connect_to_mongo, get_database, close_mongo_connection
    from app import seed_database
    from authentication_service import verify_token
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

async def test_startup():
    print("--- Testing Database Connection ---")
    try:
        await connect_to_mongo()
        print("[OK] MongoDB Connected")
    except Exception as e:
        print(f"[FAIL] MongoDB Connection Failed: {e}")
        return

    print("\n--- Testing Seeding ---")
    try:
        await seed_database()
        print("[OK] Database Seeded")
    except Exception as e:
        print(f"[FAIL] Database Seeding Failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n--- Testing Auth Logic ---")
    try:
        from auth_utils import hash_password, verify_password
        pwd = "password123"
        hashed = hash_password(pwd)
        print(f"Hashed: {hashed[:10]}...")
        assert verify_password(pwd, hashed)
        print("[OK] Auth Utils (Bcrypt) Working")
    except Exception as e:
        print(f"[FAIL] Auth Utils Failed: {e}")
        import traceback
        traceback.print_exc()

    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(test_startup())
