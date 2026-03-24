import asyncio
from typing import Dict, List, Optional
from fastapi import WebSocket, WebSocketDisconnect

class ConnectionManager:
    """
    Manages active WebSocket connections for Remote Access sessions.
    
    Structure:
    - User/Frontend connects to a specific 'session_id'.
    - Agent connects to the same 'session_id' (acting as the host).
    - Manager bridges the messages between them.
    """
    def __init__(self):
        # session_id -> { "user": WebSocket, "agent": WebSocket }
        self.active_sessions: Dict[str, Dict[str, Optional[WebSocket]]] = {}

    async def connect_user(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        if session_id not in self.active_sessions:
            self.active_sessions[session_id] = {"user": None, "agent": None}
        self.active_sessions[session_id]["user"] = websocket
        print(f"User connected to session {session_id}")

    async def connect_agent(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        if session_id not in self.active_sessions:
            self.active_sessions[session_id] = {"user": None, "agent": None}
        self.active_sessions[session_id]["agent"] = websocket
        print(f"Agent connected to session {session_id}")
        
        # Notify user that agent is ready
        user_ws = self.active_sessions[session_id]["user"]
        if user_ws:
            await user_ws.send_text("System: Agent Connected. Terminal Ready.\r\n")

    def disconnect(self, session_id: str, role: str):
        if session_id in self.active_sessions:
            self.active_sessions[session_id][role] = None
            print(f"{role.capitalize()} disconnected from session {session_id}")
            
            # Cleanup if empty
            if not self.active_sessions[session_id]["user"] and not self.active_sessions[session_id]["agent"]:
                del self.active_sessions[session_id]

    async def broadcast_to_partner(self, session_id: str, sender_role: str, message: str):
        """
        Relays message from User -> Agent OR Agent -> User
        """
        if session_id not in self.active_sessions:
            return

        target_role = "agent" if sender_role == "user" else "user"
        target_socket = self.active_sessions[session_id].get(target_role)

        if target_socket:
            await target_socket.send_text(message)

# Global Instance
manager = ConnectionManager()
