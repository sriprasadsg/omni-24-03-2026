import asyncio
from database import connect_to_mongo, get_database
from evidence_automation_service import get_evidence_service

async def test_evidence_suggestions():
    await connect_to_mongo()
    db = get_database()
    service = get_evidence_service(db)
    
    control_id = "iso27001-A.8.12" # Data Leakage Prevention
    control_data = {
        "name": "Data Leakage Prevention",
        "description": "Data leakage prevention measures shall be applied to systems, networks and any other devices."
    }
    
    print(f"🤖 Requesting AI suggestions for {control_id}...")
    suggestions = await service.get_evidence_collection_suggestions(control_id, control_data)
    
    print("\n--- AI SUGGESTIONS ---")
    print(suggestions)
    print("----------------------")
    
    # Wait for background tasks if any
    await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(test_evidence_suggestions())
