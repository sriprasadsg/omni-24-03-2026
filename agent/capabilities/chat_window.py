"""
Chat Window Capability
Displays a GUI popup on the endpoint desktop when an admin initiates a
direct chat with the asset. Does not require knowing the user's account.

Window behaviour:
  - Always-on-top so the user can't miss it
  - Scrollable message history
  - Text input + Send button (Enter to send)
  - Polls /api/agent-chat/sessions/{id}/messages every 3 s for admin replies
  - "Close Chat" button ends the session and notifies backend
"""
import logging
import platform
import threading
import time
from typing import Dict, Any, Optional

import requests

from .base import BaseCapability

logger = logging.getLogger(__name__)

# Active sessions: session_id → {"running": bool}  (for external close signals)
_active_sessions: Dict[str, Dict[str, Any]] = {}


class ChatWindowCapability(BaseCapability):

    @property
    def capability_id(self) -> str:
        return "chat_window"

    @property
    def capability_name(self) -> str:
        return "Admin Chat Window"

    def collect(self) -> Dict[str, Any]:
        return {"status": "available", "active_sessions": list(_active_sessions.keys())}

    def get_description(self) -> str:
        return "Display a chat popup when an admin sends a direct message to this endpoint"

    def is_compatible(self, system_info: Dict[str, Any]) -> bool:
        return True  # Supported on all platforms (tkinter is stdlib)

    def run(self, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        return {"status": "idle", "active_sessions": len(_active_sessions)}

    def start_chat(self, session_id: str, subject: str, initial_message: str,
                   backend_url: str, auth_headers: dict,
                   sender: str = "Administrator") -> Dict[str, Any]:
        """Open a chat window on the endpoint desktop in a background thread."""
        if session_id in _active_sessions:
            return {"status": "already_active", "session_id": session_id}

        _active_sessions[session_id] = {"running": True}

        t = threading.Thread(
            target=self._run_window,
            args=(session_id, subject, initial_message, backend_url, auth_headers, sender),
            daemon=True,
            name=f"agent-chat-{session_id[:8]}",
        )
        t.start()
        logger.info("[ChatWindow] Started chat session %s", session_id)
        return {"status": "started", "session_id": session_id}

    def close_chat(self, session_id: str) -> Dict[str, Any]:
        """Signal an active window to close (called from outside the thread)."""
        if session_id in _active_sessions:
            _active_sessions[session_id]["running"] = False
        return {"status": "close_signal_sent"}

    # ── Window implementation ─────────────────────────────────────────────────

    def _run_window(self, session_id: str, subject: str, initial_message: str,
                    backend_url: str, auth_headers: dict, sender: str):
        try:
            import tkinter as tk
            from tkinter import scrolledtext
        except ImportError:
            logger.warning("[ChatWindow] tkinter unavailable — using console fallback")
            self._console_fallback(session_id, initial_message, backend_url, auth_headers)
            return

        state = _active_sessions.get(session_id, {"running": True})
        last_poll_time = [time.time()]

        # ── Root window ───────────────────────────────────────────────────────
        root = tk.Tk()
        root.title("📨 Message from IT Administrator")
        root.geometry("460x540")
        root.minsize(380, 400)
        root.configure(bg="#1a1a2e")
        root.attributes("-topmost", True)
        # Prevent accidental close via the X button
        root.protocol("WM_DELETE_WINDOW", lambda: None)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(root, bg="#0f3460", pady=12)
        hdr.pack(fill=tk.X)
        tk.Label(
            hdr, text="🔒  IT Administrator",
            font=("Segoe UI", 13, "bold"), fg="#e94560", bg="#0f3460",
        ).pack()
        tk.Label(
            hdr, text=subject[:70],
            font=("Segoe UI", 9), fg="#a8b2d8", bg="#0f3460",
        ).pack(pady=(2, 0))

        # ── Message area ──────────────────────────────────────────────────────
        msg_frame = tk.Frame(root, bg="#1a1a2e")
        msg_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(10, 4))

        msg_area = scrolledtext.ScrolledText(
            msg_frame, wrap=tk.WORD, state=tk.DISABLED,
            font=("Segoe UI", 10), bg="#16213e", fg="#dde1e7",
            relief=tk.FLAT, borderwidth=0, padx=10, pady=8,
        )
        msg_area.pack(fill=tk.BOTH, expand=True)

        msg_area.tag_config("admin_lbl",   foreground="#e94560", font=("Segoe UI", 9, "bold"))
        msg_area.tag_config("user_lbl",    foreground="#3ec9a7", font=("Segoe UI", 9, "bold"))
        msg_area.tag_config("body",        foreground="#dde1e7", font=("Segoe UI", 10))
        msg_area.tag_config("ts",          foreground="#6c757d", font=("Segoe UI", 8))
        msg_area.tag_config("sys",         foreground="#9b59b6", font=("Segoe UI", 9, "italic"))

        def _append(label: str, label_tag: str, content: str):
            ts = time.strftime("%H:%M")
            msg_area.config(state=tk.NORMAL)
            msg_area.insert(tk.END, f"{label}  ", label_tag)
            msg_area.insert(tk.END, f"{ts}\n", "ts")
            msg_area.insert(tk.END, f"{content}\n\n", "body")
            msg_area.config(state=tk.DISABLED)
            msg_area.see(tk.END)

        def _sys(text: str):
            msg_area.config(state=tk.NORMAL)
            msg_area.insert(tk.END, f"— {text} —\n\n", "sys")
            msg_area.config(state=tk.DISABLED)
            msg_area.see(tk.END)

        # Render the first admin message
        _append(f"Administrator ({sender})", "admin_lbl", initial_message)

        # ── Input area ────────────────────────────────────────────────────────
        input_frame = tk.Frame(root, bg="#1a1a2e", pady=6)
        input_frame.pack(fill=tk.X, padx=12)

        entry = tk.Text(
            input_frame, height=3, font=("Segoe UI", 10),
            bg="#16213e", fg="#dde1e7", relief=tk.FLAT,
            insertbackground="white", wrap=tk.WORD,
        )
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def _send(event=None):
            content = entry.get("1.0", tk.END).strip()
            if not content or not state.get("running"):
                return "break"
            entry.delete("1.0", tk.END)
            _append("You", "user_lbl", content)
            threading.Thread(
                target=_post_reply,
                args=(session_id, content, backend_url, auth_headers),
                daemon=True,
            ).start()
            return "break"  # Prevent default newline on Enter

        entry.bind("<Return>", _send)

        btn_col = tk.Frame(input_frame, bg="#1a1a2e")
        btn_col.pack(side=tk.LEFT, padx=(6, 0))
        tk.Button(
            btn_col, text="Send",
            font=("Segoe UI", 9, "bold"), bg="#0f3460", fg="white",
            relief=tk.FLAT, padx=14, pady=6, command=_send,
        ).pack()

        # ── Footer ────────────────────────────────────────────────────────────
        footer = tk.Frame(root, bg="#0f3460", pady=5)
        footer.pack(fill=tk.X)

        status_var = tk.StringVar(value="● Connected")
        tk.Label(
            footer, textvariable=status_var, font=("Segoe UI", 8),
            fg="#3ec9a7", bg="#0f3460",
        ).pack(side=tk.LEFT, padx=10)

        def _close():
            _sys("You closed the chat.")
            state["running"] = False
            try:
                requests.patch(
                    f"{backend_url}/api/agent-chat/sessions/{session_id}/close",
                    headers=auth_headers, timeout=5,
                )
            except Exception:
                pass
            root.after(800, root.destroy)

        tk.Button(
            footer, text="Close Chat",
            font=("Segoe UI", 8, "bold"), bg="#e94560", fg="white",
            relief=tk.FLAT, padx=10, pady=3, command=_close,
        ).pack(side=tk.RIGHT, padx=10)

        # ── Poll for new admin messages ────────────────────────────────────────
        def _poll():
            if not state.get("running"):
                return
            try:
                resp = requests.get(
                    f"{backend_url}/api/agent-chat/sessions/{session_id}/messages",
                    params={"since": last_poll_time[0]},
                    headers=auth_headers,
                    timeout=5,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for msg in data.get("messages", []):
                        root.after(0, _append,
                                   f"Administrator ({sender})", "admin_lbl", msg["content"])
                    last_poll_time[0] = time.time()
                    if data.get("status") == "closed":
                        root.after(0, _on_server_close)
            except Exception:
                pass
            root.after(3000, _poll)

        def _on_server_close():
            state["running"] = False
            status_var.set("● Session ended by administrator")
            entry.config(state=tk.DISABLED)
            _sys("Administrator closed the chat.")

        def _watchdog():
            """Exit the window if the external close signal was sent."""
            if not state.get("running"):
                try:
                    root.destroy()
                except Exception:
                    pass
                return
            root.after(1000, _watchdog)

        root.after(3000, _poll)
        root.after(1000, _watchdog)
        root.mainloop()

        # Cleanup after window closes
        _active_sessions.pop(session_id, None)
        logger.info("[ChatWindow] Session %s closed", session_id)

    # ── Console fallback (headless / no GUI) ──────────────────────────────────

    def _console_fallback(self, session_id: str, initial_message: str,
                           backend_url: str, auth_headers: dict):
        logger.info("[AgentChat] Administrator: %s", initial_message)
        logger.info("[AgentChat] Session %s — no GUI available on this endpoint", session_id)


def _post_reply(session_id: str, content: str, backend_url: str, auth_headers: dict):
    """POST user reply to backend (background thread)."""
    try:
        requests.post(
            f"{backend_url}/api/agent-chat/sessions/{session_id}/user-message",
            json={"content": content},
            headers=auth_headers,
            timeout=10,
        )
    except Exception as e:
        logger.error("[ChatWindow] Failed to send reply: %s", e)
