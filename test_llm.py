import asyncio
import sys
import os

# Ensure backend modules are found
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from backend.ai_service import OllamaProvider

async def test_ollama():
    print("🧪 Testing Ollama Provider...")
    provider = OllamaProvider()
    
    # Configure with defaults (localhost:11434, llama3)
    # You can change model here if needed, e.g., "llama3.2:3b" or "mistral"
    settings = {
        "ollamaUrl": "http://localhost:11434",
        "ollamaModel": "llama3.2:3b" 
    }
    
    is_connected = await provider.configure(settings)
    if is_connected:
        print(f"✅ Connected to Ollama at {settings['ollamaUrl']}")
    else:
        print(f"❌ Could not connect to Ollama at {settings['ollamaUrl']}")
        # We continue to try generation to see the error
    
    print("\n📝 Sending Prompt: 'Explain Quantum Computing in one sentence.'")
    try:
        response = await provider.generate("Explain Quantum Computing in one sentence.")
        print("\n✨ Response:")
        print(response)
        print("\n✅ Verification Successful!")
    except Exception as e:
        print(f"\n❌ Generation Failed: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(test_ollama())
    except KeyboardInterrupt:
        pass
