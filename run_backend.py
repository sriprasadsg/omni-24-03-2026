
import sys
import uvicorn

# Ensure backend can import its dependencies
sys.path.append('backend')

if __name__ == "__main__":
    print("Starting backend on port 5000...")
    # backend.app:app is now the socket.io-wrapped ASGI app (app = socket_app at module end)
    uvicorn.run("backend.app:app", host="0.0.0.0", port=5000, reload=False)
