
import asyncio
import websockets
import sys

async def test_remote_shell_socket():
    uri = "ws://localhost:5000/api/ws/remote/rust-agent-verification"
    print(f"Connecting to {uri}...")
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ Connected to WebSocket")
            
            # Simulate Agent sending Shell Ready
            await websocket.send("Shell Ready")
            print("Sent: Shell Ready")
            
            response = await websocket.recv()
            print(f"Received: {response}")
            
            if "Hello from Backend" in response:
                print("✅ Backend Handshake Verified")
            else:
                print("❌ Unexpected Response")
                sys.exit(1)
                
    except Exception as e:
        print(f"❌ Connection Failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(test_remote_shell_socket())
    except ImportError:
        # Fallback if websockets not installed, try to use generic tools or just skip
        print("websockets lib not found, skipping active verification")
