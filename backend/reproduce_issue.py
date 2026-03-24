
import asyncio
from typing import Dict, Any
from datetime import datetime, timezone
import uuid

# Mock the database
class MockDB:
    class jobs:
        @staticmethod
        async def insert_one(doc):
            print(f"Inserted: {doc}")
            return True

# Mock the dependency
def get_database():
    return MockDB()

# Import the code to test
# We need to mock the imports inside jobs_endpoints first or just copy the logic
# Copying logic for isolation test to verify Python syntax/logic errors

# From auth_types.py
from dataclasses import dataclass
from typing import Optional

@dataclass
class TokenData:
    username: Optional[str] = None
    role: Optional[str] = "user"
    tenant_id: Optional[str] = None

# Logic from jobs_endpoints.py (stripped of imports)
async def create_job_logic(job_data: Dict[str, Any], current_user: Any):
    try:
        # Debug extraction
        user_debug = f"Type: {type(current_user)}, Val: {current_user}"
        print(f"DEBUG: create_job called. User: {user_debug}")
        
        username = "unknown"
        if hasattr(current_user, "username"):
            username = current_user.username
        elif isinstance(current_user, dict):
            username = current_user.get("sub") or current_user.get("username")
        
        if not username:
            raise ValueError(f"Could not extract username from {user_debug}")

        job_id = f"job-{uuid.uuid4().hex[:8]}"
        new_job = {
            "id": job_id,
            "type": job_data.get("type", "generic_task"),
            "status": "pending",
            "progress": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": username,
            "details": job_data.get("details", {}),
            "result": None
        }
        
        # await db.jobs.insert_one(new_job) # Mocked above
        print(f"SUCCESS: Job payload constructed: {new_job}")
        return new_job
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"ERROR: {e}")

async def run_test():
    print("--- Test 1: TokenData object ---")
    user1 = TokenData(username="testuser", role="admin")
    await create_job_logic({"type": "test"}, user1)
    
    print("\n--- Test 2: Dictionary (Legacy/JWT) ---")
    user2 = {"sub": "testuser_jwt", "role": "user"}
    await create_job_logic({"type": "test"}, user2)
    
    print("\n--- Test 3: None (Error Case) ---")
    await create_job_logic({"type": "test"}, None)

if __name__ == "__main__":
    asyncio.run(run_test())
