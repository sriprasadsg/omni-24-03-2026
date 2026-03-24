import asyncio
import os
from database import connect_to_mongo, get_database, close_mongo_connection
from rag_service import rag_service
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ingest_security")

async def ingest_security_standards():
    """
    Extract security controls from MongoDB and ingest them into ChromaDB (RAG).
    """
    await connect_to_mongo()
    db = get_database()
    
    logger.info("🔍 Fetching compliance framework controls from MongoDB...")
    frameworks = await db.compliance_frameworks.find({}).to_list(length=100)
    
    if not frameworks:
        logger.warning("⚠️ No frameworks found. Run expansion scripts first.")
        await close_mongo_connection()
        return

    total_ingested = 0
    for fw in frameworks:
        fw_name = fw.get("name", "Unknown Framework")
        fw_id = fw.get("id", "unknown")
        controls = fw.get("controls", [])
        
        logger.info(f"📦 Processing {len(controls)} controls for {fw_name}...")
        
        for control in controls:
            control_id = control.get("id")
            name = control.get("name")
            description = control.get("description")
            category = control.get("category", "General")
            
            # Create a rich text representation for the RAG engine
            content = f"""
Framework: {fw_name} ({fw_id})
Control ID: {control_id}
Control Name: {name}
Category: {category}
Description: {description}
            """.strip()
            
            # Ingest into RAG
            source = f"mongodb_framework_{fw_id}"
            rag_service.ingest_text(content, source=source)
            total_ingested += 1
            
    logger.info(f"✅ Successfully ingested {total_ingested} security controls into RAG engine.")
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(ingest_security_standards())
