"""
Agent System Tray Icon

Shows a small icon in the system notification area (Windows taskbar /
Linux AppIndicator) when the Omni-Agent is running at an endpoint.

Right-clicking opens a menu so users can raise tickets without opening
a browser:
  • Install Software
  • Access Request
  • Report an Issue
  • Hardware Request
  • Security Concern
  • Custom Request

Gracefully degrades to a no-op if:
  - pystray is not installed
  - Running on a headless server (no display)
  - Pillow is not installed (icon image falls back to a plain colour)
"""

import logging
import os
import platform
import socket
import sys
import threading
import webbrowser
from typing import Callable, Dict, Any


def _collect_system_info() -> Dict[str, Any]:
    """Collect endpoint context to attach to user-raised tickets."""
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "unknown"
    try:
        ip_address = socket.gethostbyname(hostname)
    except Exception:
        ip_address = "unknown"
    username = (
        os.environ.get("USERNAME")
        or os.environ.get("USER")
        or "unknown"
    )
    return {
        "hostname":   hostname,
        "ip_address": ip_address,
        "os_name":    platform.system(),
        "os_version": platform.version(),
        "os_release": platform.release(),
        "machine":    platform.machine(),
        "username":   username,
    }

logger = logging.getLogger(__name__)

# ── Ticket request templates ───────────────────────────────────────────────────

TICKET_TEMPLATES = {
    "Install Software": {
        "type": "task",
        "priority": "medium",
        "title_prefix": "Software Install Request: ",
        "hint": "Enter the software name and version required\n(e.g. Visual Studio Code 1.89, Python 3.12)...",
    },
    "Access Request": {
        "type": "task",
        "priority": "medium",
        "title_prefix": "Access Request: ",
        "hint": "Describe the resource, system, or permissions you need access to...",
    },
    "Report an Issue": {
        "type": "bug",
        "priority": "high",
        "title_prefix": "Issue: ",
        "hint": "Describe the problem you are experiencing, including steps to reproduce...",
    },
    "Hardware Request": {
        "type": "task",
        "priority": "low",
        "title_prefix": "Hardware Request: ",
        "hint": "Describe the hardware or peripheral you need (model, quantity, reason)...",
    },
    "Security Concern": {
        "type": "security",
        "priority": "high",
        "title_prefix": "Security Concern: ",
        "hint": "Describe the suspicious activity, vulnerability, or security concern you observed...",
    },
    "Custom Request": {
        "type": "task",
        "priority": "medium",
        "title_prefix": "",
        "hint": "Describe your request in detail...",
    },
}

# ── Icon image ─────────────────────────────────────────────────────────────────

def _make_icon_image():
    """Return a 64×64 PIL Image for the tray icon, or None on failure."""
    try:
        from PIL import Image, ImageDraw, ImageFont

        SIZE = 64
        img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Rounded teal square
        draw.rounded_rectangle([2, 2, SIZE - 2, SIZE - 2], radius=14, fill=(0, 188, 180, 255))

        # "OA" label in white
        text = "OA"
        try:
            font = ImageFont.truetype("arial.ttf", 22)
        except Exception:
            try:
                font = ImageFont.truetype("DejaVuSans-Bold.ttf", 22)
            except Exception:
                font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((SIZE - tw) / 2 - bbox[0], (SIZE - th) / 2 - bbox[1]), text, fill="white", font=font)

        return img
    except Exception as exc:
        logger.debug("tray_icon: could not build icon image: %s", exc)
        return None


# ── Ticket dialog (Tkinter) ────────────────────────────────────────────────────

def _open_ticket_dialog(template_name: str, cfg: dict, agent_id: str) -> None:
    """
    Open a themed Tkinter form.  Each call runs in its own thread so the
    tray icon stays responsive while the dialog is open.
    """
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
        import requests as req
    except ImportError as exc:
        logger.warning("tray_icon: cannot open dialog — %s", exc)
        return

    template = TICKET_TEMPLATES.get(template_name, TICKET_TEMPLATES["Custom Request"])

    # ── Window ─────────────────────────────────────────────────────────────────
    root = tk.Tk()
    root.title(f"Omni-Agent — {template_name}")
    root.geometry("500x420")
    root.resizable(False, False)
    root.lift()
    root.attributes("-topmost", True)
    try:
        icon_img = _make_icon_image()
        if icon_img:
            from PIL import ImageTk
            tk_icon = ImageTk.PhotoImage(icon_img)
            root.iconphoto(True, tk_icon)
    except Exception:
        pass

    # ── Colours ────────────────────────────────────────────────────────────────
    BG     = "#1e2130"
    FG     = "#e0e6f0"
    ENTRY  = "#2a2f45"
    ACCENT = "#00bcb4"
    ERR    = "#ff6b6b"
    OK     = "#4caf50"

    root.configure(bg=BG)

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TLabel",    background=BG,  foreground=FG,     font=("Segoe UI", 10))
    style.configure("TEntry",    fieldbackground=ENTRY, foreground=FG, font=("Segoe UI", 10))
    style.configure("TCombobox", fieldbackground=ENTRY, foreground=FG, font=("Segoe UI", 10))
    style.configure(
        "Submit.TButton",
        background=ACCENT, foreground="white",
        font=("Segoe UI", 10, "bold"), padding=(12, 6),
    )
    style.map("Submit.TButton", background=[("active", "#009e98"), ("disabled", "#3a4060")])

    PAD = {"padx": 14, "pady": 5}

    # ── Header ─────────────────────────────────────────────────────────────────
    header = tk.Frame(root, bg=ACCENT, height=36)
    header.pack(fill="x")
    tk.Label(
        header, text=f"  {template_name}",
        bg=ACCENT, fg="white", font=("Segoe UI", 11, "bold"), anchor="w",
    ).pack(side="left", fill="y", padx=4)

    # ── Title ──────────────────────────────────────────────────────────────────
    ttk.Label(root, text="Title  *").pack(anchor="w", **PAD)
    title_var = tk.StringVar(value=template["title_prefix"])
    title_entry = ttk.Entry(root, textvariable=title_var, width=58)
    title_entry.pack(fill="x", padx=14, pady=2)
    title_entry.icursor(tk.END)
    title_entry.focus_set()

    # ── Description ────────────────────────────────────────────────────────────
    ttk.Label(root, text="Description").pack(anchor="w", **PAD)
    desc_frame = tk.Frame(root, bg=BG, padx=14)
    desc_frame.pack(fill="both", expand=True)
    desc_box = tk.Text(
        desc_frame, height=7,
        bg=ENTRY, fg="#8090b0", font=("Segoe UI", 10),
        relief="flat", wrap="word", insertbackground=FG, borderwidth=0,
    )
    desc_box.pack(fill="both", expand=True)
    desc_box.insert("1.0", template["hint"])

    def _clear_hint(event):
        if desc_box.get("1.0", "end-1c") == template["hint"]:
            desc_box.delete("1.0", "end")
            desc_box.configure(fg=FG)

    def _restore_hint(event):
        if not desc_box.get("1.0", "end-1c").strip():
            desc_box.insert("1.0", template["hint"])
            desc_box.configure(fg="#8090b0")

    desc_box.bind("<FocusIn>",  _clear_hint)
    desc_box.bind("<FocusOut>", _restore_hint)

    # ── Priority + submit row ──────────────────────────────────────────────────
    row = tk.Frame(root, bg=BG)
    row.pack(fill="x", padx=14, pady=8)

    ttk.Label(row, text="Priority:").pack(side="left")
    priority_var = tk.StringVar(value=template["priority"])
    ttk.Combobox(
        row, textvariable=priority_var,
        values=["low", "medium", "high", "critical"],
        state="readonly", width=10,
    ).pack(side="left", padx=8)

    status_var = tk.StringVar()
    status_lbl = tk.Label(row, textvariable=status_var, bg=BG, fg=FG, font=("Segoe UI", 9))
    status_lbl.pack(side="left", padx=12)

    # ── Submit logic ───────────────────────────────────────────────────────────
    def _submit():
        title = title_var.get().strip()
        raw_desc = desc_box.get("1.0", "end-1c").strip()
        description = "" if raw_desc == template["hint"] else raw_desc

        if not title or title == template["title_prefix"].strip():
            messagebox.showwarning("Required", "Please enter a title.", parent=root)
            return

        submit_btn.state(["disabled"])
        status_var.set("Submitting…")
        status_lbl.config(fg=FG)

        # Collect system context once, before the background thread
        sys_info = _collect_system_info()

        def _do():
            try:
                base_url = cfg.get("api_base_url", "http://localhost:5000").rstrip("/")
                token    = cfg.get("agent_token", "")
                headers  = {"Content-Type": "application/json"}
                if token:
                    headers["Authorization"] = f"Bearer {token}"

                resp = req.post(
                    f"{base_url}/api/agents/{agent_id}/raise-ticket",
                    json={
                        "title":         title,
                        "description":   description,
                        "type":          template["type"],
                        "priority":      priority_var.get(),
                        "tags":          ["user-raised", template_name.lower().replace(" ", "-")],
                        "endpoint_info": sys_info,
                    },
                    headers=headers,
                    timeout=10,
                )
                if resp.status_code in (200, 201):
                    root.after(0, lambda: [
                        status_var.set("Ticket queued successfully"),
                        status_lbl.config(fg=OK),
                    ])
                    root.after(1800, root.destroy)
                else:
                    msg = f"Server error {resp.status_code}"
                    root.after(0, lambda: [
                        status_var.set(msg),
                        status_lbl.config(fg=ERR),
                        submit_btn.state(["!disabled"]),
                    ])
            except Exception as exc:
                msg = f"Connection error: {exc}"
                root.after(0, lambda: [
                    status_var.set(msg),
                    status_lbl.config(fg=ERR),
                    submit_btn.state(["!disabled"]),
                ])

        threading.Thread(target=_do, daemon=True).start()

    submit_btn = ttk.Button(root, text="Submit Ticket", style="Submit.TButton", command=_submit)
    submit_btn.pack(pady=(0, 12))

    root.mainloop()


# ── Tray icon ──────────────────────────────────────────────────────────────────

class AgentTrayIcon:
    """
    System tray icon for the Omni-Agent endpoint client.

    Usage:
        tray = AgentTrayIcon(cfg, lambda: capability_mgr.agent_id)
        tray.start()   # non-blocking — runs in a daemon thread
    """

    def __init__(self, cfg: dict, agent_id_provider: Callable[[], str]):
        self._cfg              = cfg
        self._agent_id_provider = agent_id_provider

    def _agent_id(self) -> str:
        try:
            return self._agent_id_provider()
        except Exception:
            import socket
            return socket.gethostname()

    def _build_menu(self):
        import pystray

        def ticket_handler(name):
            def _action(icon, item):
                aid = self._agent_id()
                threading.Thread(
                    target=_open_ticket_dialog,
                    args=(name, self._cfg, aid),
                    daemon=True,
                    name=f"TicketDialog-{name}",
                ).start()
            return _action

        def open_platform(icon, item):
            base = self._cfg.get("api_base_url", "http://localhost:5000")
            url  = base.replace(":5000", ":3000")
            webbrowser.open(url)

        return pystray.Menu(
            pystray.MenuItem("Omni Agent", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Raise a Ticket",
                pystray.Menu(*[
                    pystray.MenuItem(name, ticket_handler(name))
                    for name in TICKET_TEMPLATES
                ]),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Platform", open_platform),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", lambda icon, item: icon.stop()),
        )

    def _run(self):
        # Headless guard — skip on servers without a display
        if sys.platform != "win32":
            display = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
            if not display:
                logger.debug("tray_icon: no display found — skipping tray icon")
                return

        try:
            import pystray
        except ImportError:
            logger.debug("tray_icon: pystray not installed — skipping")
            return

        icon_image = _make_icon_image()
        if icon_image is None:
            # Minimal fallback: 1×1 white pixel so pystray doesn't crash
            try:
                from PIL import Image
                icon_image = Image.new("RGB", (64, 64), (0, 188, 180))
            except Exception:
                logger.debug("tray_icon: Pillow unavailable — skipping")
                return

        try:
            icon = pystray.Icon(
                "omni-agent",
                icon_image,
                "Omni Agent",
                menu=self._build_menu(),
            )
            logger.info("System tray icon started")
            icon.run()
        except Exception as exc:
            logger.debug("tray_icon: failed to start: %s", exc)

    def start(self):
        """Start the tray icon in a background daemon thread (non-blocking)."""
        t = threading.Thread(target=self._run, daemon=True, name="AgentTrayIcon")
        t.start()
