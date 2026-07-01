"""
Agent WebSocket Client for Remote Control
Handles WebSocket connection to backend for receiving remote commands
"""

import asyncio
import websockets
import json
import subprocess
import sys
import os
import logging
from typing import Callable, Dict

logger = logging.getLogger(__name__)

class AgentWebSocketClient:
    """WebSocket client for agent remote control"""
    
    def __init__(self, server_url: str, agent_id: str):
        self.server_url = server_url
        self.agent_id = agent_id
        self.websocket = None
        self.is_connected = False
        self.command_handlers = {
            "execute": self._handle_execute_command,
            "restart": self._handle_restart,
            "update_config": self._handle_update_config
        }
    
    async def connect(self):
        """Connect to backend WebSocket server"""
        # Convert HTTP URL to WebSocket URL
        ws_url = self.server_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url.rstrip('/')}/api/agents/remote/ws/agent/{self.agent_id}"
        
        while True:
            try:
                async with websockets.connect(ws_url) as websocket:
                    self.websocket = websocket
                    self.is_connected = True
                    logger.info(f"[WebSocket] Connected to {ws_url}")
                    
                    # Listen for incoming commands
                    async for message in websocket:
                        await self._handle_incoming_message(message)
                        
            except websockets.exceptions.ConnectionClosed:
                self.is_connected = False
                logger.warning("[WebSocket] Connection closed, reconnecting in 5s...")
                await asyncio.sleep(5)
            except Exception as e:
                self.is_connected = False
                logger.error(f"[WebSocket] Error: {e}, reconnecting in 5s...")
                await asyncio.sleep(5)
    
    async def _handle_incoming_message(self, message: str):
        """Process incoming WebSocket message"""
        try:
            command = json.loads(message)
            command_type = command.get("type")
            command_id = command.get("command_id")
            user_id = command.get("user_id")
            
            logger.info(f"[WebSocket] Received command: {command_type} (ID: {command_id})")
            
            handler = self.command_handlers.get(command_type)
            if handler:
                result = await handler(command)
                await self._send_response(command_id, user_id, result)
            else:
                await self._send_response(
                    command_id,
                    user_id,
                    {"success": False, "error": f"Unknown command type: {command_type}"}
                )
        except Exception as e:
            logger.error(f"[WebSocket] Error handling message: {e}")
    
    async def _handle_execute_command(self, command: dict) -> dict:
        """Execute a shell command"""
        try:
            cmd = command.get("command")
            args = command.get("args", [])
            full_cmd = f"{cmd} {' '.join(args)}" if args else cmd
            
            logger.info(f"[WebSocket] Executing command: {full_cmd}")
            
            # Execute with timeout
            result = subprocess.run(
                full_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Command timed out (30s limit)"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _handle_restart(self, command: dict) -> dict:
        """Restart the agent process"""
        try:
            logger.warning("[WebSocket] Agent restart requested!")
            # Schedule restart after sending response
            asyncio.create_task(self._perform_restart())
            return {"success": True, "message": "Restart initiated"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _perform_restart(self):
        """Actually restart the agent process"""
        await asyncio.sleep(1)  # Allow response to be sent first
        logger.info("[WebSocket] Restarting agent process...")
        os.execv(sys.executable, ['python'] + sys.argv)
    
    async def _handle_update_config(self, command: dict) -> dict:
        """Update agent configuration"""
        try:
            new_config = command.get("config", {})
            logger.info(f"[WebSocket] Config update requested: {new_config}")
            
            # Implement config file update logic
            import yaml
            
            # Assuming config.yaml is in the current working directory
            config_path = "config.yaml"
            
            try:
                # Read existing
                with open(config_path, "r") as f:
                    current_config = yaml.safe_load(f) or {}
                
                # Update with new values
                current_config.update(new_config)
                
                # Save back
                with open(config_path, "w") as f:
                    yaml.dump(current_config, f, default_flow_style=False)
                    
                logger.info("Configuration saved to config.yaml")
                
                return {
                    "success": True,
                    "message": "Config updated and saved. Some changes may require restart."
                }
            except Exception as file_err:
                logger.error(f"Failed to save config: {file_err}")
                return {
                    "success": False,
                    "error": f"Failed to save config file: {str(file_err)}"
                }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _send_response(self, command_id: str, user_id: str, result: dict):
        """Send command result back to backend"""
        if self.websocket and self.is_connected:
            try:
                response = {
                    "type": "command_response",
                    "command_id": command_id,
                    "user_id": user_id,
                    **result
                }
                await self.websocket.send(json.dumps(response))
                logger.info(f"[WebSocket] Sent response for command {command_id}")
            except Exception as e:
                logger.error(f"[WebSocket] Failed to send response: {e}")
    
    def start_background(self):
        """Start WebSocket connection in background thread"""
        import threading
        
        def run_async_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.connect())
        
        thread = threading.Thread(target=run_async_loop, daemon=True)
        thread.start()
        logger.info("[WebSocket] Started WebSocket client in background thread")
