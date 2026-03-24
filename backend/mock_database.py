from mongomock_motor import AsyncMongoMockClient

class MockMongoDB:
    client = None
    db = None

mongodb = MockMongoDB()

async def connect_to_mongo():
    print("Using Mock MongoDB (mongomock-motor)")
    mongodb.client = AsyncMongoMockClient()
    mongodb.db = mongodb.client['omni_platform']
    print(f"Connected to Mock MongoDB database: omni_platform")

async def close_mongo_connection():
    # Mock client doesn't need explicit close usually, but for API consistency
    if mongodb.client:
        mongodb.client.close()
        print("Closed Mock MongoDB connection")

def get_database():
    if mongodb.db is None:
        return None
    # Assuming TenantIsolatedDatabase can handle the mock db object if it behaves like MotorDatabase
    from database import TenantIsolatedDatabase
    return TenantIsolatedDatabase(mongodb.db)
