import asyncio
import json
import os
from database import connect_to_mongo, get_database, close_mongo_connection
import google.generativeai as genai

async def generate_security_training_data():
    """
    Generate a synthetic Q&A dataset based on security standards for future fine-tuning.
    """
    await connect_to_mongo()
    db = get_database()
    
    # Initialize LLM for data generation
    settings = await db.system_settings.find_one({"type": "llm"})
    api_key = os.getenv("GEMINI_API_KEY") or (settings.get("apiKey") if settings else None)
    
    genai_model = None
    if api_key:
        try:
            genai.configure(api_key=api_key)
            genai_model = genai.GenerativeModel("gemini-2.0-flash")
            print("[INFO] Using Gemini for data generation.")
        except Exception as e:
            print(f"[WARNING] Gemini init failed: {e}")

    # Fallback to Ollama if Gemini is missing
    ollama_service = None
    if not genai_model:
        from ai_service import IncidentAnalyzer
        analyzer = IncidentAnalyzer()
        await analyzer.initialize()
        if analyzer.is_configured:
            ollama_service = analyzer
            print("[INFO] Falling back to Ollama for data generation.")
        else:
            print("[ERROR] No AI provider available for training data generation.")
            await close_mongo_connection()
            return
    
    frameworks = await db.compliance_frameworks.find({}).to_list(length=100)
    
    training_data = []
    
    for fw in frameworks:
        fw_name = fw.get("name")
        controls = fw.get("controls", [])[:10] # Limit to 10 per framework for demo
        
        for control in controls:
            prompt = f"""
            Based on this security control, generate 3 professional Q&A pairs for a security expert training dataset.
            The questions should be about what the control is, how to implement it, and how to collect evidence for it.
            
            CONTROL:
            Framework: {fw_name}
            ID: {control['id']}
            Name: {control['name']}
            Description: {control['description']}
            
            RESPOND ONLY WITH RAW JSON in this format:
            [
                {{"instruction": "Question", "input": "Context (optional)", "output": "Detailed Answer"}},
                ...
            ]
            """
            
            try:
                if genai_model:
                    response = genai_model.generate_content(prompt)
                    cleaned_text = response.text.replace("```json", "").replace("```", "").strip()
                else:
                    response_text = await ollama_service.provider.generate(prompt)
                    cleaned_text = response_text.replace("```json", "").replace("```", "").strip()
                
                pairs = json.loads(cleaned_text)
                training_data.extend(pairs)
                print(f"[OK] Generated {len(pairs)} pairs for {control['id']}")
            except Exception as e:
                print(f"[ERROR] Failed for {control['id']}: {e}")
                
    # Save to file
    output_file = "d:/Downloads/enterprise-omni-agent-ai-platform/data/security_training_data.jsonl"
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, "w", encoding='utf-8') as f:
        for item in training_data:
            f.write(json.dumps(item) + "\n")
            
    print(f"[FINISHED] Generated {len(training_data)} training pairs saved to {output_file}")
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(generate_security_training_data())
