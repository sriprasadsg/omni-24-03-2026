import platform
import logging
import subprocess
import winreg
from typing import Dict, Any
from .base import BaseCapability

logger = logging.getLogger(__name__)

class RemoteAccessCapability(BaseCapability):
    @property
    def capability_id(self) -> str:
        return "remote_access"

    @property
    def capability_name(self) -> str:
        return "Remote Access Control"

    def collect(self) -> Dict[str, Any]:
        return self.get_status()

    def get_description(self) -> str:
        return "Manage remote access settings (RDP)"

    def is_compatible(self, system_info: Dict[str, Any]) -> bool:
        # RDP is primarily for Windows in this context
        return system_info.get("os") == "Windows"

    def run(self, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Default run method - checks status.
        """
        return self.get_status()

    def get_status(self) -> Dict[str, Any]:
        if platform.system() != "Windows":
            return {"status": "unsupported", "enabled": False}

        try:
            # Check Registry for fDenyTSConnections (0 = Enabled, 1 = Disabled)
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Terminal Server", 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, "fDenyTSConnections")
            winreg.CloseKey(key)
            
            enabled = (value == 0)
            return {"status": "success", "enabled": enabled}
        except Exception as e:
            return {"status": "error", "error": str(e), "enabled": False}

    def enable_rdp(self) -> Dict[str, Any]:
        if platform.system() != "Windows":
            return {"status": "error", "error": "Only supported on Windows"}

        try:
            # 1. Enable in Registry
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Terminal Server", 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "fDenyTSConnections", 0, winreg.REG_DWORD, 0)
            winreg.CloseKey(key)

            # 2. Allow in Firewall (using netsh)
            # "netsh advfirewall firewall set rule group="remote desktop" new enable=Yes"
            cmd = ['netsh', 'advfirewall', 'firewall', 'set', 'rule', 'group=remote desktop', 'new', 'enable=Yes']
            logger.info(f"Executing: {' '.join(cmd)}")
            subprocess.run(cmd, capture_output=True, check=True)
            
            return {"status": "success", "message": "RDP Enabled successfully", "enabled": True}
        except Exception as e:
            logger.error(f"Failed to enable RDP: {e}")
            return {"status": "error", "error": str(e)}

    def disable_rdp(self) -> Dict[str, Any]:
        if platform.system() != "Windows":
            return {"status": "error", "error": "Only supported on Windows"}

        try:
            # 1. Disable in Registry
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Terminal Server", 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "fDenyTSConnections", 0, winreg.REG_DWORD, 1)
            winreg.CloseKey(key)
            
            return {"status": "success", "message": "RDP Disabled successfully", "enabled": False}
        except Exception as e:
            logger.error(f"Failed to disable RDP: {e}")
            return {"status": "error", "error": str(e)}

    def start_reverse_shell(self, session_id: str, url: str):
        """
        Start a reverse shell connected to the WebSocket URL.
        Spawns a new thread to handle the connection to avoid blocking the agent.
        """
        import threading
        import websocket
        import os
        
        def run_shell():
            logger.info(f"Starting reverse shell for session {session_id} to {url}")
            
            # Determine shell
            system = platform.system()
            if system == "Windows":
                shell_cmd = ["powershell.exe", "-NoLogo"]
            else:
                shell_cmd = ["/bin/bash", "-i"]
                
            try:
                # Start process unbuffered
                process = subprocess.Popen(
                    shell_cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=0,
                    shell=False
                )
                
                def on_message(ws, message):
                    try:
                        if process.poll() is not None:
                            ws.close()
                            return
                        # Write to process stdin
                        if isinstance(message, str):
                            message = message.encode('utf-8')
                        process.stdin.write(message)
                        process.stdin.flush()
                    except Exception as e:
                        logger.error(f"Shell Input Error: {e}")

                def on_error(ws, error):
                    logger.error(f"WebSocket Error: {error}")

                def on_close(ws, close_status_code, close_msg):
                    logger.info("WebSocket Closed. Terminating shell.")
                    process.terminate()

                def on_open(ws):
                    logger.info("WebSocket Connection Opened. Starting output thread.")
                    
                    def forward_output():
                        try:
                            while True:
                                output = process.stdout.read(1024)
                                if not output:
                                    break
                                ws.send(output.decode('utf-8', errors='replace'))
                        except Exception as e:
                            logger.error(f"Shell Output Error: {e}")
                        finally:
                            ws.close()
                            
                    threading.Thread(target=forward_output, daemon=True).start()

                # Connection
                ws = websocket.WebSocketApp(
                    url,
                    on_open=on_open,
                    on_message=on_message,
                    on_error=on_error,
                    on_close=on_close
                )
                ws.run_forever()
                
            except Exception as e:
                logger.error(f"Failed to start reverse shell: {e}")

        # Start the WebSocket client in a separate thread so it doesn't block the main Agent loop
        thread = threading.Thread(target=run_shell, daemon=True)
        thread.start()
        
        return {"status": "success", "message": "Reverse shell thread started"}

    def start_desktop_stream(self, session_id: str, url: str):
        """
        Start sending desktop screenshots to the WebSocket URL.
        """
        import threading
        import websocket
        import json
        import time
        import base64
        import io
        import mss
        from PIL import Image

        def run_stream():
            logger.info(f"Starting desktop stream for session {session_id} to {url}")
            
            try:
                def on_error(ws, error):
                    logger.error(f"Desktop Stream WebSocket Error: {error}")

                def on_close(ws, close_status_code, close_msg):
                    logger.info("Desktop Stream WebSocket Closed.")

                def on_open(ws):
                    logger.info("Desktop Stream Connected. Starting frame capture.")
                    
                    with mss.mss() as sct:
                        # Use first monitor
                        monitor = sct.monitors[1]
                        
                        while True:
                            try:
                                # Capture
                                sct_img = sct.grab(monitor)
                                
                                # Convert to PIL Image
                                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                                
                                # Resize for performance (max 800px width)
                                max_width = 800
                                if img.width > max_width:
                                    ratio = max_width / img.width
                                    new_size = (max_width, int(img.height * ratio))
                                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                                
                                # Compress to JPEG
                                buffer = io.BytesIO()
                                img.save(buffer, format="JPEG", quality=50, optimize=True)
                                b64_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
                                
                                # Send
                                payload = {
                                    "type": "frame",
                                    "timestamp": time.time(),
                                    "data": b64_data
                                }
                                ws.send(json.dumps(payload))
                                
                                # Limit FPS (~5-10 FPS)
                                time.sleep(0.15)
                                
                            except Exception as capture_err:
                                logger.error(f"Frame Capture Error: {capture_err}")
                                time.sleep(1) # Backoff
                                # Check connection state? If send failed, loop might break or raise

                # Connection
                ws = websocket.WebSocketApp(
                    url,
                    on_open=on_open,
                    on_error=on_error,
                    on_close=on_close
                )
                ws.run_forever()

            except Exception as e:
                logger.error(f"Failed to start desktop stream: {e}")

        thread = threading.Thread(target=run_stream, daemon=True)
        thread.start()
        
        return {"status": "success", "message": "Desktop stream thread started"}
