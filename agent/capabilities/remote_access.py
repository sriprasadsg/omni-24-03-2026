import platform
import logging
import subprocess
from typing import Dict, Any
from .base import BaseCapability

# winreg is a Windows-only stdlib module. Every call site below already
# checks platform.system() == "Windows" before touching it, but the bare
# import breaks importing this module (and the whole capabilities package)
# on Linux/macOS.
if platform.system() == "Windows":
    import winreg
else:
    winreg = None

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

    def start_desktop_stream(self, session_id: str, url: str, tenant_key: str = "",
                             requester_name: str = "", requester_email: str = "",
                             tenant_name: str = "", control: bool = False):
        """
        Start sending desktop screenshots to the WebSocket URL.
        If `control` is True, run the interactive-control consent flow (D-01..D-12):
        ask the endpoint user to accept before any input is replayed, then
        replay gated browser→agent input frames and show the persistent stop bar.
        """
        import threading
        import websocket
        import json
        import time
        import base64
        import io
        import mss

        ws_headers = [f"X-Tenant-Key: {tenant_key}"] if tenant_key else None
        from PIL import Image

        def send_json(ws, obj):
            try:
                ws.send(json.dumps(obj))
            except Exception as e:
                logger.warning(f"send_json: {e}")

        def run_stream():
            logger.info(f"Starting desktop stream for session {session_id} to {url}")

            # Interactive-control consent flow (D-01): no SendInput before the
            # endpoint user accepts. Consent runs on a daemon thread so the
            # socket can keep processing control_stop / admin force-close while
            # the endpoint user decides. State messages are only sent once ws
            # exists (on open) — a pre-open send hits a reference-before-
            # assignment NameError that previously killed the whole stream.
            from . import consent_ui
            from .control_input import ConsentGate, parse_input_frame, replay_input_event

            gate = ConsentGate()
            stop_bar_shown = False

            def on_message(ws, message):
                # Only input frames from an accepted+active control session
                # are replayed, and only while the gate authorises (D-01).
                if not control or not gate.authorised():
                    return
                try:
                    if isinstance(message, bytes):
                        message = message.decode("utf-8")
                    ev = parse_input_frame(message)
                    replay_input_event(ev)
                except ValueError as e:
                    logger.warning(f"input frame rejected: {e}")

            def on_error(ws, error):
                logger.error(f"Desktop Stream WebSocket Error: {error}")

            def on_close(ws, close_status_code, close_msg):
                logger.info("Desktop Stream WebSocket Closed.")
                if stop_bar_shown:
                    try:
                        consent_ui.hide_stop_bar(session_id)
                    except Exception:
                        pass

            def consent_flow(ws):
                # Runs on a daemon thread; concedes the gate (or ends the
                # session) once the endpoint user decides.
                nonlocal stop_bar_shown
                if platform.system() != "Windows":
                    send_json(ws, {"type": "error", "reason": "unsupported_platform",
                                   "message": "interactive control requires Windows"})
                    return
                try:
                    decision = consent_ui.request_consent(
                        session_id, requester_name, requester_email,
                        tenant_name, timeout_secs=60)
                except consent_ui.ConsentError as ce:
                    reason = "no_interactive_desktop" if "no interactive" in ce.reason else (
                        "consent_declined")
                    send_json(ws, {"type": "error", "reason": reason, "message": ce.reason})
                    return
                if decision == consent_ui.ConsentDecision.Accept:
                    gate.concede()
                    send_json(ws, {"type": "control_state", "state": "active",
                                   "message": "consent granted"})
                    try:
                        consent_ui.show_stop_bar(session_id, requester_name)
                        stop_bar_shown = True
                    except consent_ui.ConsentError:
                        pass
                else:
                    reason = ("consent_timeout" if decision == consent_ui.ConsentDecision.Timeout
                             else "consent_declined")
                    send_json(ws, {"type": "control_state", "state": "ended",
                                   "reason": reason, "message": "consent not granted"})

            def on_open(ws):
                logger.info("Desktop Stream Connected. Starting frame capture.")
                if control:
                    send_json(ws, {"type": "control_state", "state": "awaiting_consent",
                                   "message": "consent required before control"})
                    threading.Thread(target=consent_flow, args=(ws,), daemon=True).start()

                with mss.mss() as sct:
                    # Use first monitor
                    monitor = sct.monitors[1]

                    while True:
                        # Endpoint stop bar one-click revocation (D-09).
                        if control and consent_ui.stop_requested(session_id):
                            gate.revoke()
                            send_json(ws, {"type": "control_state", "state": "ended",
                                           "reason": "user_stopped",
                                           "message": "control stopped by endpoint user"})
                            if stop_bar_shown:
                                try:
                                    consent_ui.hide_stop_bar(session_id)
                                except Exception:
                                    pass
                            break

                        # No screen before consent (D-01): a refused control
                        # session must not leak frames to the requester.
                        if control and not gate.authorised():
                            time.sleep(0.3)
                            continue

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
                            time.sleep(1)  # Backoff

            # Connection
            ws = websocket.WebSocketApp(
                url,
                header=ws_headers,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            try:
                ws.run_forever()
            except Exception as e:
                logger.error(f"Failed to start desktop stream: {e}")

        thread = threading.Thread(target=run_stream, daemon=True)
        thread.start()

        return {"status": "success", "message": "Desktop stream thread started"}

    def start_reverse_shell(self, session_id: str, url: str, tenant_key: str = ""):
        """
        Start a reverse shell connected to the WebSocket URL.
        Spawns a new thread to handle the connection to avoid blocking the agent.
        """
        import threading
        import websocket
        import os

        ws_headers = [f"X-Tenant-Key: {tenant_key}"] if tenant_key else None

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
                    header=ws_headers,
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
