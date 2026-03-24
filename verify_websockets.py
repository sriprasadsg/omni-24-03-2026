import socketio
import asyncio
import time
import requests
import json

# Agent Configuration
AGENT_ID = "agent-test-remote"
TENANT_ID = "platform-admin"
BASE_URL = "http://127.0.0.1:5000"

sio = socketio.AsyncClient()

@sio.event
async def connect():
    print(f"✅ [Agent] Connected to WebSocket server as {AGENT_ID}")

@sio.event
async def connected(data):
    print(f"ℹ️ [Agent] Welcome message: {data}")

@sio.event
async def command(data):
    print(f"🚀 [Agent] RECEIVED COMMAND: {json.dumps(data, indent=2)}")
    # Simulate processing
    await asyncio.sleep(1)

@sio.event
async def disconnect():
    print("❌ [Agent] Disconnected from server")

async def run_agent():
    while True:
        try:
            print(f"⏳ [Agent] Connecting to {BASE_URL}...")
            # Connect with Agent Auth
            await sio.connect(BASE_URL, auth={
                'tenant_id': TENANT_ID,
                'type': 'agent',
                'agent_id': AGENT_ID
            })
            print(f"✅ [Agent] Connected! Waiting for commands...")
            await sio.wait() 
        except Exception as e:
            print(f"⚠️ Connection failed: {e}. Retrying in 2s...")
            await asyncio.sleep(2)

if __name__ == '__main__':
    try:
        asyncio.run(run_agent())
    except KeyboardInterrupt:
        print("Agent stopped.")
