import bcrypt
import traceback

print("Testing bcrypt hashing...")

try:
    salt = bcrypt.gensalt()
    hash = bcrypt.hashpw("password123".encode('utf-8'), salt).decode('utf-8')
    print(f"Success! Hash: {hash}")
except Exception as e:
    print("Failed to hash!")
    traceback.print_exc()

print("\nTesting user creation...")
try:
    from pymongo import MongoClient
    client = MongoClient('mongodb://localhost:27017')
    db = client['omni_platform']
    db.users.insert_one({"test": "entry"})
    print("MongoDB write success")
    db.users.delete_one({"test": "entry"})
except Exception as e:
    print("MongoDB fail!")
    traceback.print_exc()
