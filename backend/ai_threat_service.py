import json
import logging
import re
from database import get_database
from ai_service import ai_service
import requests

logger = logging.getLogger(__name__)

class AIThreatService:
    def __init__(self):
        pass

    async def process_query(self, user_query: str, tenant_id: str = None) -> dict:
        """
        Convert natural language query into MongoDB aggregation pipeline and execute it.
        """
        # Ensure AI service is ready
        if not ai_service.is_configured:
            await ai_service.initialize()
            
        if not ai_service.is_configured:
            # Fallback to Ollama if Gemini not configured? 
            # For now, return error or try local default
            pass

        # context: Schema definition
        schema_context = """
        Collection: 'metrics'
        Document Structure:
        {
            "agent_id": "string",
            "timestamp": "ISO8601 string",
            "cpu": { "percent": float, "count": int },
            "memory": { "total": int, "available": int, "percent": float },
            "disk": [ { "mountpoint": "string", "percent": float, "total": int, "used": int } ],
            "network": { "bytes_sent": int, "bytes_recv": int },
            "installedSoftware": [ { "name": "string", "version": "string", "updateAvailable": bool } ]
        }
        
        Collection: 'logs'
        Document Structure:
        {
           "agent_id": "string",
           "timestamp": "ISO8601 string",
           "level": "INFO|ERROR|WARN",
           "source": "string",
           "message": "string"
        }
        """

        prompt = f"""
        You are a MongoDB Expert and Security Analyst.
        Convert the following Natural Language Query into a VALID JSON MongoDB Aggregation Pipeline for the 'metrics' (or 'logs' if specified) collection.
        
        Schema Context:
        {schema_context}
        
        Query: "{user_query}"
        
        Rules:
        1. Return ONLY the JSON list representing the pipeline. No markdown, no explanations.
        2. Use strictly valid JSON (double quotes).
        3. If querying 'metrics', usually filter by 'timestamp' (last 1 hour if not specified).
        4. If the query implies 'latest' status, use $sort and $group by agent_id.
        
        Example Output:
        [
            {{"$match": {{"cpu.percent": {{"$gt": 80}}}}}},
            {{"$project": {{"agent_id": 1, "cpu.percent": 1}}}}
        ]
        """

        # Use unified AI Service (Gemini or Ollama)
        pipeline_text = await ai_service.generate_text(prompt)

        # Clean up response
        pipeline_text = pipeline_text.replace("```json", "").replace("```", "").strip()
        
        # Additional cleanup for safety (remove any leading non-json)
        if not pipeline_text.startswith("["):
            # Try simple regex finding
            match = re.search(r'\[.*\]', pipeline_text, re.DOTALL)
            if match:
                pipeline_text = match.group(0)
            
        pipeline = json.loads(pipeline_text)
        
        # Execute
        db = get_database()
        # Determine collection based on query keywords (simple heuristic)
        collection_name = "metrics"
        if "log" in user_query.lower():
            collection_name = "agent_logs" # mapped name
        
        # Safety checks for pipeline
        if not isinstance(pipeline, list):
            return {"success": False, "error": "Generated invalid pipeline format"}
            
        # Inject tenant_id filter into pipeline
        if tenant_id:
            tenant_filter = {"$match": {"tenantId": tenant_id}}
            # If there's already a $match at the beginning, we can merge them or just prepend
            pipeline.insert(0, tenant_filter)
            
        # EXECUTE
        results = await db[collection_name].aggregate(pipeline).to_list(length=50)
        
        # Format numbers
        # (Optional post-processing)
        
        return {
            "success": True,
            "data": results,
            "generated_pipeline": pipeline,
            "collection": collection_name
        }

threat_service = AIThreatService()
