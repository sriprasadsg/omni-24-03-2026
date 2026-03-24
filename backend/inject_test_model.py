import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import uuid
from datetime import datetime, timezone

async def seed_test_model():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.omni_platform
    
    model_id = "test-llama-expert"
    tenant_id = "platform-admin" # Default from super admin
    
    model_doc = {
        "id": model_id,
        "name": "Llama 3 Security Review Test",
        "tenantId": tenant_id,
        "description": "A test model for expert evaluation",
        "framework": "Ollama",
        "type": "LLM",
        "owner": "Compliance Team",
        "riskLevel": "Medium",
        "versions": [
            {
                "version": "1.0",
                "createdAt": datetime.now(timezone.utc).isoformat(),
                "createdBy": "admin",
                "status": "Production",
                "metrics": {"accuracy": 0.9}
            }
        ],
        "currentVersion": "1.0",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "updatedAt": datetime.now(timezone.utc).isoformat()
    }
    
    await db.ai_models.update_one({"id": model_id}, {"$set": model_doc}, upsert=True)
    print(f"Model {model_id} injected into database.")

if __name__ == "__main__":
    asyncio.run(seed_test_model())
