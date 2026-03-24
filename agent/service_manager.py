
import os
import sys
import platform
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class ServiceManager:
    """
    Manages the installation and lifecycle of the agent as a background service.
    Supports: Windows (Service), Linux (Systemd), MacOS (Launchd)
    """

    def __init__(self, agent_path=None):
        self.os_type = platform.system()
        if agent_path:
            self.agent_path = Path(agent_path).resolve()
        else:
            # Determine path to current executable or script
            if getattr(sys, 'frozen', False):
                self.agent_path = Path(sys.executable).resolve()
                self.is_binary = True
            else:
                self.agent_path = Path(sys.argv[0]).resolve()
                self.is_binary = False
        
        self.service_name = "OmniAgent"
        self.display_name = "Omni Enterprise Agent"
        self.description = "Autonomous Agent for Enterprise Security and Management"

    def install(self):
        """Install the agent as a system service"""
        logger.info(f"Installing {self.service_name} for {self.os_type}...")
        
        try:
            if self.os_type == "Windows":
                self._install_windows()
            elif self.os_type == "Linux":
                self._install_linux()
            elif self.os_type == "Darwin":
                self._install_macos()
            else:
                logger.error(f"Unsupported OS for service install: {self.os_type}")
                return False
                
            logger.info("✅ Service installed successfully.")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to install service: {e}")
            return False

    def uninstall(self):
        """Uninstall the agent service"""
        logger.info(f"Uninstalling {self.service_name}...")
        try:
            if self.os_type == "Windows":
                self._uninstall_windows()
            elif self.os_type == "Linux":
                self._uninstall_linux()
            elif self.os_type == "Darwin":
                self._uninstall_macos()
            else:
                return False
                
            logger.info("✅ Service uninstalled successfully.")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to uninstall service: {e}")
            return False

    def start(self):
        """Start the installed service"""
        logger.info(f"Starting {self.service_name} service...")
        try:
            if self.os_type == "Windows":
                subprocess.run(["sc", "start", self.service_name], check=True)
            elif self.os_type == "Linux":
                subprocess.run(["systemctl", "start", self.service_name], check=True)
            elif self.os_type == "Darwin":
                subprocess.run(["launchctl", "load", f"/Library/LaunchDaemons/com.omni.agent.plist"], check=True)
            return True
        except Exception as e:
            logger.error(f"Failed to start service: {e}")
            return False

    def stop(self):
        """Stop the service"""
        logger.info(f"Stopping {self.service_name} service...")
        try:
            if self.os_type == "Windows":
                subprocess.run(["sc", "stop", self.service_name], check=True)
            elif self.os_type == "Linux":
                subprocess.run(["systemctl", "stop", self.service_name], check=True)
            elif self.os_type == "Darwin":
                subprocess.run(["launchctl", "unload", f"/Library/LaunchDaemons/com.omni.agent.plist"], check=True)
            return True
        except Exception as e:
            logger.error(f"Failed to stop service: {e}")
            return False

    # --- Windows Implementation ---
    def _install_windows(self):
        # Construct binPath
        if self.is_binary:
            bin_path = str(self.agent_path)
        else:
            # If script, we need python.exe + script
            python_exe = sys.executable
            # Ensure we wrap in quotes for safety
            bin_path = f'"{python_exe}" "{self.agent_path}"'

        # Use sc.exe to create service
        # sc create OmniAgent binPath= "..." start= auto DisplayName= "..."
        cmd = [
            "sc", "create", self.service_name,
            "binPath=", bin_path,
            "start=", "auto",
            "DisplayName=", self.display_name
        ]
        subprocess.run(cmd, check=True)
        
        # Set description
        subprocess.run(["sc", "description", self.service_name, self.description], check=True)
        # Set recovery options (restart on failure)
        subprocess.run(["sc", "failure", self.service_name, "reset=", "86400", "actions=", "restart/60000/restart/60000/restart/60000"], check=True)

    def _uninstall_windows(self):
        subprocess.run(["sc", "delete", self.service_name], check=True)

    # --- Linux Implementation (Systemd) ---
    def _install_linux(self):
        unit_content = f"""[Unit]
Description={self.description}
After=network.target

[Service]
Type=simple
User=root
"""
        if self.is_binary:
            unit_content += f"ExecStart={self.agent_path}\n"
        else:
            unit_content += f"ExecStart={sys.executable} {self.agent_path}\n"

        unit_content += """Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
"""
        service_path = Path("/etc/systemd/system") / f"{self.service_name}.service"
        service_path.write_text(unit_content)
        
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "enable", self.service_name], check=True)

    def _uninstall_linux(self):
        subprocess.run(["systemctl", "disable", self.service_name], check=True)
        service_path = Path("/etc/systemd/system") / f"{self.service_name}.service"
        if service_path.exists():
            service_path.unlink()
        subprocess.run(["systemctl", "daemon-reload"], check=True)

    # --- MacOS Implementation (Launchd) ---
    def _install_macos(self):
        plist_name = "com.omni.agent.plist"
        
        cmd_array = ""
        if self.is_binary:
             cmd_array = f"<string>{self.agent_path}</string>"
        else:
             cmd_array = f"<string>{sys.executable}</string>\n<string>{self.agent_path}</string>"

        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.omni.agent</string>
    <key>ProgramArguments</key>
    <array>
        {cmd_array}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/var/log/omni-agent.log</string>
    <key>StandardErrorPath</key>
    <string>/var/log/omni-agent.error.log</string>
</dict>
</plist>
"""
        plist_path = Path("/Library/LaunchDaemons") / plist_name
        plist_path.write_text(plist_content)
        
        # Load it
        # subprocess.run(["launchctl", "load", str(plist_path)], check=True) 
        # (Start handles the load usually, but let's leave it to Start method)

    def _uninstall_macos(self):
        plist_path = Path("/Library/LaunchDaemons/com.omni.agent.plist")
        if plist_path.exists():
            subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
            plist_path.unlink()
