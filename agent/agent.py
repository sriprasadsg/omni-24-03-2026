import sys
import os
import time
import socket
import platform
from pathlib import Path
import logging

import requests
import yaml
import json
import sqlite3
import psutil

from capabilities import CAPABILITY_REGISTRY
from fim import FIMMonitor
from secure_logs import setup_secure_logging

AGENT_VERSION = "2.0.1"

# ─────────────────────────────────────────────
# Setup logging
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Optional Agentic Core imports
# ─────────────────────────────────────────────
try:
    from agentic_core.llm_engine import AgenticLLM
    from agentic_core.safety import SafetyGuardrails
    from agentic_core.reasoning import AgenticReasoningEngine
    from autonomous_actions.remediation import AutonomousRemediationEngine
    from goal_system.manager import GoalManager
    from knowledge_base.memory import AgentMemory
    from swarm.coordinator import SwarmCoordinator
except ImportError:
    AgenticLLM = None
    SafetyGuardrails = None
    AgenticReasoningEngine = None
    AutonomousRemediationEngine = None
    GoalManager = None
    AgentMemory = None
    SwarmCoordinator = None

from security import SecurityManager
from platform_utils import PlatformUtils


# ─────────────────────────────────────────────
# Offline message buffer (SQLite)
# ─────────────────────────────────────────────
class MessageBuffer:
    def __init__(self, db_path="buffer.db", security_mgr=None):
        self.db_path = db_path
        self.security_mgr = security_mgr
        self.init_db()

    def init_db(self):
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS messages
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          payload TEXT,
                          timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Buffer Init Error: {e}")

    def add_message(self, payload):
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            data = json.dumps(payload)
            if self.security_mgr:
                data = self.security_mgr.encrypt_data(data)
            c.execute("INSERT INTO messages (payload) VALUES (?)", (data,))
            conn.commit()
            conn.close()
            logging.info("Buffered failed message to SQLite")
        except Exception as e:
            logging.error(f"Buffer Add Error: {e}")

    def get_messages(self, limit=10):
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("SELECT id, payload FROM messages ORDER BY id ASC LIMIT ?", (limit,))
            rows = c.fetchall()
            conn.close()
            decrypted_rows = []
            for msg_id, data in rows:
                try:
                    if self.security_mgr:
                        try:
                            plaintext = self.security_mgr.decrypt_data(data)
                        except Exception:
                            plaintext = data
                    else:
                        plaintext = data
                    decrypted_rows.append((msg_id, plaintext))
                except Exception as e:
                    logging.error(f"Failed to process buffered message {msg_id}: {e}")
            return decrypted_rows
        except Exception as e:
            logging.error(f"Buffer Read Error: {e}")
            return []

    def delete_message(self, msg_id):
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("DELETE FROM messages WHERE id=?", (msg_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Buffer Delete Error: {e}")


# ─────────────────────────────────────────────
# Config loader
# ─────────────────────────────────────────────
def load_config():
    if getattr(sys, 'frozen', False):
        base_path = Path(sys.executable).parent
    else:
        base_path = Path(__file__).parent.resolve()

    cfg_path = base_path / "config.yaml"
    security_mgr = SecurityManager(base_path)
    config = security_mgr.load_encrypted_config(cfg_path)
    
    if not config:
        import argparse
        parser = argparse.ArgumentParser(description="OmniAgent Configuration")
        parser.add_argument("--url", help="API Base URL (e.g. http://localhost:5000)")
        parser.add_argument("--key", help="Tenant Registration Key")
        
        # Parse known args so we don't conflict with Windows service args
        args, _ = parser.parse_known_args()
        
        api_base_url = args.url
        registration_key = args.key
        
        print("\n--- OmniAgent Setup ---")
        if not api_base_url:
            api_base_url = input("Enter API Base URL [http://localhost:5000]: ").strip()
            if not api_base_url:
                api_base_url = "http://localhost:5000"
                
        if not registration_key:
            while not registration_key:
                registration_key = input("Enter Tenant Registration Key: ").strip()
                if not registration_key:
                    print("Registration Key is required.")
                    
        print("-----------------------\n")

        config = {
            "api_base_url": api_base_url,
            "registration_key": registration_key,
            "interval_seconds": 5
        }
        
        # Pre-save the config so it exists for next boots
        config['_cfg_path'] = cfg_path
        save_config(config)
        
    config['_security_mgr'] = security_mgr
    config['_cfg_path'] = cfg_path
    
    # Switch to secure encrypted logging
    setup_secure_logging("agent.log", security_mgr)
    
    return config


def save_config(cfg):
    """Persist updated config values (e.g. agent_token, agent_id) back to config.yaml."""
    cfg_path = cfg.get('_cfg_path')
    if not cfg_path:
        return
    try:
        # Build a clean copy without private keys
        clean = {k: v for k, v in cfg.items() if not k.startswith('_')}
        with open(cfg_path, 'w') as f:
            yaml.dump(clean, f, default_flow_style=False)
        logger.info("Config saved.")
    except Exception as e:
        logger.error(f"Failed to save config: {e}")


def get_ip_address():
    return PlatformUtils.get_ip_address()


# ─────────────────────────────────────────────
# Fix 3: Agent Registration Flow
# ─────────────────────────────────────────────
def register_agent(cfg) -> bool:
    """
    Exchange registration_key for a permanent agent_token + agent_id.
    Persists the result back to config.yaml so subsequent runs skip this step.
    Returns True if (already registered) or (registration succeeded).
    """
    # Already registered
    if cfg.get("agent_token") and cfg.get("agent_id"):
        logger.info(f"✅ Agent already registered — ID: {cfg['agent_id']}")
        return True

    base_url = cfg.get("api_base_url", "http://localhost:5000").rstrip("/")
    reg_key  = cfg.get("registration_key", "")
    hostname = socket.gethostname()

    try:
        logger.info(f"Registering agent '{hostname}' with backend at {base_url} …")
        resp = requests.post(
            f"{base_url}/api/agents/register",
            json={
                "hostname":        hostname,
                "registrationKey": reg_key,
                "tenant_id":       cfg.get("tenant_id"),
                "device_id":       cfg.get("_security_mgr").device_id if cfg.get("_security_mgr") else "unknown",
                "platform":        platform.system(),
                "version":         AGENT_VERSION,
                "ipAddress":      get_ip_address(),
            },
            timeout=10,
        )

        if resp.status_code in (200, 201):
            data = resp.json()
            agent_token = data.get("token") or data.get("agent_token") or data.get("access_token") or "dummy-token"
            agent_id    = data.get("agent_id") or data.get("agentId") or data.get("id")

            if agent_token and agent_id:
                cfg["agent_token"] = agent_token
                cfg["agent_id"]    = agent_id
                save_config(cfg)
                logger.info(f"✅ Registration successful — Agent ID: {agent_id}")
                return True
            else:
                logger.warning(f"Registration response missing token/id: {data}")
                # Fall back: if backend responded with a hostname-based ID use it
                if agent_id:
                    cfg["agent_id"] = agent_id

                return False

        else:
            logger.warning(f"Registration failed (HTTP {resp.status_code}): {resp.text[:200]}")
            # Fallback: derive an ID from hostname so instruction polling still works
            cfg.setdefault("agent_id", hostname)
            return False

    except Exception as e:
        logger.error(f"Registration error: {e}")
        # Fallback degraded mode — use hostname as agent_id so polling can try
        cfg.setdefault("agent_id", hostname)
        return False


# ─────────────────────────────────────────────
# Capability Manager
# ─────────────────────────────────────────────
class AgentCapabilityManager:
    """Manages agent capabilities dynamically based on backend configuration"""

    def __init__(self, cfg):
        self.cfg = cfg
        self.agent_id = cfg.get("agent_id") or f"agent-{socket.gethostname()}"
        self.enabled_capabilities = []
        self.collection_intervals = {}
        self.capability_instances = {}

        # Agentic AI Components
        self.llm_engine = None
        self.safety      = None
        self.reasoning   = None
        self.remediation = None
        self.goal_manager = None
        self.memory      = None
        self.swarm       = None

        # Initialize Agentic Core if enabled
        if self.cfg.get('agentic_mode_enabled', False):
            if AgenticLLM and SafetyGuardrails and AgenticReasoningEngine:
                logger.info("Initializing Agentic AI Core…")
                try:
                    llm_config = self.cfg.get('llm_config', {}).copy()
                    if llm_config.get('provider') == 'backend':
                        llm_config['api_base_url'] = self.cfg.get('api_base_url')
                        llm_config['api_key']       = self.cfg.get('agent_token')

                    self.llm_engine = AgenticLLM(llm_config)
                    self.safety     = SafetyGuardrails(self.cfg.get('autonomous_actions', {}))

                    if AgentMemory:
                        self.memory = AgentMemory()
                        logger.info("Initialized Agent Memory")

                    self.reasoning = AgenticReasoningEngine(
                        self.llm_engine,
                        self.safety,
                        self.cfg.get('autonomous_actions', {})
                    )
                    if self.memory:
                        self.reasoning.memory = self.memory

                    self.remediation = AutonomousRemediationEngine(
                        self.reasoning,
                        self.cfg.get('autonomous_actions', {})
                    )

                    if GoalManager:
                        self.goal_manager = GoalManager(self.llm_engine, self.cfg)

                    # Fix: use coordinator_url from swarm config properly
                    swarm_cfg = self.cfg.get('swarm', {})
                    if SwarmCoordinator and swarm_cfg.get('enabled', False):
                        swarm_init = swarm_cfg.copy()
                        if 'coordinator_url' not in swarm_init:
                            swarm_init['coordinator_url'] = self.cfg.get('api_base_url')
                        self.swarm = SwarmCoordinator(self.agent_id, swarm_init)
                        self.swarm.join_swarm()

                    logger.info("✅ Agentic AI Core fully initialized (LLM+Safety+Reasoning+Remediation+Goals+Memory+Swarm)")
                except Exception as e:
                    logger.error(f"Failed to initialize Agentic AI Core: {e}")
            else:
                logger.warning("Agentic Core modules not found. AI features disabled.")
        else:
            logger.info("Agentic AI mode is disabled in config")

        # Initialize all capability instances
        for cap_id, cap_class in CAPABILITY_REGISTRY.items():
            try:
                instance = cap_class()
                self.capability_instances[cap_id] = instance
                logger.info(f"Initialized capability: {cap_id}")
                if hasattr(instance, "start_watching"):
                    logger.info(f"Starting streamer for {cap_id}…")
                    try:
                        instance.start_watching()
                    except Exception as e:
                        logger.error(f"Failed to start watcher for {cap_id}: {e}")
            except Exception as e:
                logger.error(f"Failed to initialize {cap_id}: {e}")

    # ── Remote Session ──────────────────────────────────────────────────────
    def execute_remote_session(self, payload: dict) -> dict:
        session_id   = payload.get("session_id")
        url          = payload.get("url")
        session_type = payload.get("type", "shell")

        logger.info(f"Starting Remote Session {session_id} ({session_type}) to {url}")
        remote_cap = self.capability_instances.get('remote_access')
        if remote_cap:
            import threading
            if session_type == "desktop":
                t = threading.Thread(target=remote_cap.start_desktop_stream, args=(session_id, url))
            else:
                t = threading.Thread(target=remote_cap.start_reverse_shell, args=(session_id, url))
            t.daemon = True
            t.start()
            return {"status": "started", "session_id": session_id}
        return {"status": "error", "error": "Remote Access capability not available"}

    # ── Single Instruction Dispatcher ──────────────────────────────────────
    def execute_single_instruction(self, instruction: str, payload: dict = None) -> dict:
        """Dispatches a single text instruction to the appropriate capability."""
        import re

        # ── PII Scanner ────────────────────────────────────────────────────
        if "Run PII Scan" in instruction or "pii_scan" in instruction:
            cap = self.capability_instances.get('pii_scanner')
            if cap:
                logger.info("Direct Execution: Running PII Scan")
                result = cap.collect()
                # Report findings to backend
                try:
                    url = self.cfg.get("api_base_url").rstrip("/") + "/api/security/pii-findings"
                    headers = self._auth_headers()
                    requests.post(url, json=result, headers=headers, timeout=10)
                except Exception as e:
                    logger.error(f"Failed to report PII findings: {e}")
                return result
            return {"status": "error", "error": "PII Scanner capability not available"}

        # ── Cloud Metadata ─────────────────────────────────────────────────
        if "Collect Cloud Metadata" in instruction or "cloud_metadata" in instruction:
            cap = self.capability_instances.get('cloud_metadata')
            if cap:
                logger.info("Direct Execution: Collecting Cloud Metadata")
                return cap.collect()
            return {"status": "error", "error": "Cloud Metadata capability not available"}

        # ── Process Injection Simulation ───────────────────────────────────
        if "Simulate Process Injection" in instruction or "simulate_process_injection" in instruction:
            technique   = "memory_write"
            target      = "notepad.exe" if os.name == "nt" else "cat"
            tech_match   = re.search(r'technique=(\S+)', instruction)
            target_match = re.search(r'target=(\S+)', instruction)
            if tech_match:  technique = tech_match.group(1).rstrip(',')
            if target_match: target   = target_match.group(1).rstrip(',')
            cap = self.capability_instances.get('process_injection_simulation')
            if cap:
                return cap.run_simulation({"technique": technique, "target_process": target})
            return {"status": "error", "error": "Process Injection Simulation capability not available"}

        # ── Persistence Detection ──────────────────────────────────────────
        if "Scan for Persistence" in instruction or "scan_persistence" in instruction:
            cap = self.capability_instances.get('persistence_detection')
            if cap:
                return cap.execute()
            return {"status": "error", "error": "Persistence Detection capability not available"}

        # ── Patch Installation ─────────────────────────────────────────────
        if "Install Patches" in instruction or "install_patches" in instruction:
            kb_match  = re.findall(r'KB\d+', instruction)
            job_match = re.search(r'Job:\s*(\S+)', instruction)
            if kb_match:
                patch_ids = kb_match
                job_id    = job_match.group(1) if job_match else "unknown"
                cap = self.capability_instances.get('patch_installer')
                if cap:
                    result = cap.execute_deployment(patch_ids, job_id)
                    try:
                        url = self.cfg.get('api_base_url').rstrip('/') + f"/api/deployments/{job_id}/result"
                        requests.post(url, json=result, timeout=10)
                    except Exception as e:
                        logger.error(f"Failed to report deployment result: {e}")
                    return result
                return {"status": "error", "error": "Patch Installer capability not available"}

        # ── Patch Rollback ─────────────────────────────────────────────────
        if "Rollback Patches" in instruction or "rollback_patches" in instruction:
            kb_match  = re.findall(r'KB\d+', instruction)
            job_match = re.search(r'Job:\s*(\S+)', instruction)
            if kb_match:
                patch_ids = kb_match
                job_id    = job_match.group(1) if job_match else "unknown"
                cap = self.capability_instances.get('patch_installer')
                if cap:
                    result = cap.execute_rollback(patch_ids, job_id)
                    try:
                        url = self.cfg.get('api_base_url').rstrip('/') + f"/api/deployments/{job_id}/result"
                        requests.post(url, json=result, timeout=10)
                    except Exception as e:
                        logger.error(f"Failed to report rollback result: {e}")
                    return result
                return {"status": "error", "error": "Patch Installer capability not available"}

        # ── Custom Software Install ────────────────────────────────────────
        if "Download and install custom software" in instruction:
            match = re.search(r"custom software '([^']+)'", instruction)
            if match:
                filename     = match.group(1)
                install_args = None
                flags_match  = re.search(r"with flags: (.+)$", instruction)
                if flags_match:
                    install_args = flags_match.group(1).strip()
                base_url     = self.cfg.get('api_base_url', 'http://localhost:5000').rstrip('/')
                download_url = f"{base_url}/api/software/download/{filename}"
                cap = self.capability_instances.get('software_management')
                if cap:
                    return cap.install_from_url(download_url, filename, install_args=install_args)
                return {"status": "error", "error": "Software Management capability not enabled"}

        # ── Software Hub: Install ──────────────────────────────────────────
        if instruction.startswith("install_software:"):
            package_id = instruction.split(":", 1)[1].strip()
            cap = self.capability_instances.get('software_management')
            if cap:
                return cap.install_software(package_id)
            return {"status": "error", "error": "Software Management capability not enabled"}

        # ── Software Hub: Upgrade ──────────────────────────────────────────
        if instruction.startswith("upgrade_software:"):
            package_id = instruction.split(":", 1)[1].strip()
            pkg_type   = payload.get("pkg_type") if payload else None
            download_url = payload.get("download_url") if payload else None
            
            cap = self.capability_instances.get('software_management')
            if cap:
                return cap.upgrade_software(package_id, pkg_type=pkg_type, download_url=download_url, headers=self._auth_headers())
            return {"status": "error", "error": "Software Management capability not enabled"}

        # ── Software Hub: Uninstall ────────────────────────────────────────
        if instruction.startswith("uninstall_software:"):
            package_id = instruction.split(":", 1)[1].strip()
            cap = self.capability_instances.get('software_management')
            if cap:
                return cap.uninstall_software(package_id)
            return {"status": "error", "error": "Software Management capability not enabled"}

        # ── Install from Repo ──────────────────────────────────────────────
        if instruction.startswith("install_from_repo:"):
            parts        = instruction.split(":", 2)
            filename     = parts[1].strip() if len(parts) > 1 else ""
            install_args = parts[2].strip() if len(parts) > 2 else None
            base_url     = self.cfg.get('api_base_url', 'http://localhost:5000').rstrip('/')
            download_url = f"{base_url}/api/software/download/{filename}"
            cap = self.capability_instances.get('software_management')
            if cap:
                return cap.install_from_url(download_url, filename, install_args=install_args)
            return {"status": "error", "error": "Software Management capability not enabled"}



        # ── Network Scan ───────────────────────────────────────────────────
        if "Start Network Scan" in instruction:
            cap = self.capability_instances.get('network_discovery')
            if cap:
                results = cap.start_scan()
                try:
                    url = self.cfg.get("api_base_url").rstrip("/") + f"/api/agents/{self.agent_id}/discovery/results"
                    requests.post(url, json=results, headers=self._auth_headers(), timeout=10)
                except Exception as e:
                    logger.error(f"Failed to send scan results: {e}")
                return results
            return {"status": "error", "error": "Network Discovery capability not enabled"}

        # ── Compliance Scan ────────────────────────────────────────────────
        if "Run Compliance Scan" in instruction:
            cap = self.capability_instances.get('compliance_enforcement')
            if cap:
                results = cap.collect()
                try:
                    payload = {
                        "compliance_checks": results.get("compliance_checks", []),
                        "total_checks":      results.get("total_checks", 0),
                        "passed":            results.get("passed", 0),
                        "failed":            results.get("failed", 0),
                        "compliance_score":  results.get("compliance_score", 0),
                        "timestamp":         time.strftime('%Y-%m-%dT%H:%M:%S%z')
                    }
                    url = self.cfg.get("api_base_url").rstrip("/") + f"/api/agents/{self.agent_id}/instructions/result"
                    requests.post(url, json=payload, headers=self._auth_headers(), timeout=10)
                except Exception as e:
                    logger.error(f"Failed to send compliance results: {e}")
                return results
            return {"status": "error", "error": "Compliance Enforcement capability not enabled"}

        # ── Compliance Fix ─────────────────────────────────────────────────
        if "Fix Compliance:" in instruction:
            check_name = instruction.split("Fix Compliance:")[1].strip()
            cap = self.capability_instances.get('compliance_enforcement')
            if cap:
                result = cap.remediate(check_name)
                if result.get("status") == "success":
                    cap.collect()
                return result
            return {"status": "error", "error": "Compliance Enforcement capability not enabled"}

        # ── Desktop Stream ─────────────────────────────────────────────────
        if "Start Desktop Stream" in instruction:
            match = re.search(r"Start Desktop Stream (\S+) (\S+)", instruction)
            if match:
                cap = self.capability_instances.get('remote_access')
                if cap:
                    return cap.start_desktop_stream(match.group(1), match.group(2))
            return {"status": "error", "error": "Remote Access capability not enabled"}

        # ── Shell Session ──────────────────────────────────────────────────
        if "Start Remote Session" in instruction:
            match = re.search(r"Start Remote Session (\S+) (\S+)", instruction)
            if match:
                cap = self.capability_instances.get('remote_access')
                if cap:
                    return cap.start_reverse_shell(match.group(1), match.group(2))
            return {"status": "error", "error": "Remote Access capability not enabled"}

        # ── RDP Enable/Disable ─────────────────────────────────────────────
        if "Remote Access" in instruction or "RDP" in instruction:
            cap = self.capability_instances.get('remote_access')
            if cap:
                if re.search(r"(Enable|Active) (Remote Access|RDP)", instruction, re.IGNORECASE):
                    return cap.enable_rdp()
                if re.search(r"(Disable|Stop) (Remote Access|RDP)", instruction, re.IGNORECASE):
                    return cap.disable_rdp()
            return {"status": "error", "error": "Remote Access capability not enabled"}

        # ── Agent Self-Update ──────────────────────────────────────────────
        if "Update Agent" in instruction or "update_agent" in instruction:
            cap = self.capability_instances.get('agent_update')
            if cap:
                return cap.execute()
            return {"status": "error", "error": "Agent Update capability not enabled"}

        # ── Fallback: LLM Reasoning ────────────────────────────────────────
        if not self.reasoning:
            return {
                "status": "simulated",
                "message": "Reasoning Engine not active, returning mock response.",
                "instruction": instruction
            }
        try:
            decision = self.reasoning.decide_action({"instruction": instruction, "context": "instruction_dispatch"})
            return {
                "status":        "success",
                "instruction":   instruction,
                "plan":          decision.get("plan", {}),
                "decision":      decision,
                "execution_log": ["Analyzed instruction", f"Recommended: {decision.get('action')}", "Complete"]
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _auth_headers(self) -> dict:
        """Build Authorization headers from stored token or registration key."""
        headers = {}
        token   = self.cfg.get("agent_token")
        reg_key = self.cfg.get("registration_key")
        if token and token != "dummy-token":
            headers["Authorization"] = f"Bearer {token}"
        elif reg_key:
            headers["X-Tenant-Key"] = reg_key
        return headers

    def query_knowledge_base(self, query: str) -> str:
        url = f"{self.cfg['api_base_url'].rstrip('/')}/api/knowledge/query"
        try:
            resp = requests.post(url, json={"query": query}, timeout=10)
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if not results:
                    return "No relevant information found."
                return "\n".join([f"- {r['content']} (Source: {r['source']})" for r in results])
            return f"Error querying knowledge base: {resp.status_code}"
        except Exception as e:
            logger.error(f"RAG Error: {e}")
            return f"Error connecting to knowledge base: {e}"

    def fetch_configuration(self):
        """Fetch enabled capabilities from backend."""
        base_url = self.cfg.get('api_base_url', 'http://localhost:5000')
        url      = f"{base_url.rstrip('/')}/api/agents/{self.agent_id}/capabilities/configuration"
        try:
            resp = requests.get(url, headers=self._auth_headers(), timeout=5)
            if resp.status_code == 200:
                config = resp.json()
                self.enabled_capabilities  = config.get("enabledCapabilities", [])
                self.collection_intervals  = config.get("collectionIntervals", {})
                logger.info(f"✅ Configuration loaded: {len(self.enabled_capabilities)} capabilities enabled")
                return True
            else:
                logger.warning(f"Failed to fetch configuration (HTTP {resp.status_code}), using defaults")
                self._use_default_configuration()
                return False
        except Exception as e:
            logger.warning(f"Cannot reach backend: {e}. Using default configuration.")
            self._use_default_configuration()
            return False

    def _use_default_configuration(self):
        self.enabled_capabilities = [
            "metrics_collection",
            "log_collection",
            "fim",
            "compliance_enforcement",
            "runtime_security",
            "predictive_health",
            "ueba",
            "sbom_analysis",
            "system_patching",
            "software_management",
            "persistence_detection",
            "process_injection_simulation",
            "pii_scanner",
            "cloud_metadata",
            "shadow_ai",
            "web_monitor",
        ]
        self.collection_intervals = {
            "metrics_collection":           60,
            "log_collection":               300,
            "fim":                          600,
            "vulnerability_scanning":       3600,
            "compliance_enforcement":       3600,
            "runtime_security":             180,
            "predictive_health":            600,
            "ueba":                         300,
            "sbom_analysis":                3600,
            "system_patching":              3600,
            "software_management":          3600,
            "network_discovery":            7200,
            "persistence_detection":        3600,
            "process_injection_simulation": 3600,
            "pii_scanner":                  7200,
            "cloud_metadata":               3600,
            "shadow_ai":                    3600,
            "web_monitor":                  300,
        }
        logger.info(f"Using default configuration: {len(self.enabled_capabilities)} capabilities")

    def handle_remediation(self, remediation: dict):
        action = remediation.get("action")
        reason = remediation.get("reason")
        logger.warning(f"⚠️ SELF-HEALING TRIGGERED: {action} - {reason}")
        if action == "restart_agent":
            logger.info("Restarting agent…")
            try:
                os.execv(sys.executable, [sys.executable] + sys.argv)
            except Exception as e:
                logger.error(f"Failed to restart agent: {e}")
        elif action == "throttle":
            logger.info("Throttling agent execution…")
            time.sleep(60)

    def collect_all_data(self):
        results = {}
        for cap_id in self.enabled_capabilities:
            capability = self.capability_instances.get(cap_id)
            if capability:
                try:
                    interval = self.collection_intervals.get(cap_id, 60)
                    if capability.should_run(interval):
                        logger.info(f"Collecting data from: {cap_id}")
                        result = capability.execute()
                        results[cap_id] = result

                        from datetime import datetime
                        capability.last_run = datetime.now()

                        if isinstance(result, dict) and result.get("remediation"):
                            self.handle_remediation(result["remediation"])

                        # Special handling: push compliance results immediately
                        if cap_id == "compliance_enforcement":
                            try:
                                payload = {
                                    "compliance_checks": result.get("compliance_checks", []),
                                    "total_checks":      result.get("total_checks", 0),
                                    "passed":            result.get("passed", 0),
                                    "failed":            result.get("failed", 0),
                                    "compliance_score":  result.get("compliance_score", 0),
                                    "timestamp":         time.strftime('%Y-%m-%dT%H:%M:%S%z')
                                }
                                url = self.cfg.get("api_base_url").rstrip("/") + f"/api/agents/{self.agent_id}/instructions/result"
                                requests.post(url, json=payload, headers=self._auth_headers(), timeout=10)
                            except Exception as e:
                                logger.error(f"Failed to send compliance results: {e}")

                except Exception as e:
                    logger.error(f"Error executing {cap_id}: {e}")
                    results[cap_id] = {"capability": cap_id, "status": "error", "error": str(e)}
        return results

    def get_all_capabilities_status(self):
        return [
            {
                "id":      cap_id,
                "name":    self.capability_instances[cap_id].capability_name
                           if cap_id in self.capability_instances else cap_id,
                "enabled": cap_id in self.enabled_capabilities,
                "status":  "active" if cap_id in self.enabled_capabilities else "disabled"
            }
            for cap_id in CAPABILITY_REGISTRY.keys()
        ]


# ─────────────────────────────────────────────
# Heartbeat
# ─────────────────────────────────────────────
def send_heartbeat(cfg, capability_mgr, buffer_mgr=None):
    """Send heartbeat with full capability + hardware data."""
    logger.info("Sending heartbeat…")

    sys_info         = PlatformUtils.get_system_info()
    capability_data  = capability_mgr.collect_all_data()
    cpu_info         = PlatformUtils.get_cpu_info()
    memory_info      = PlatformUtils.get_memory_info()
    disks_info       = PlatformUtils.get_storage_info()
    mac_address      = PlatformUtils.get_mac_address()
    serial_number    = PlatformUtils.get_serial_number()

    installed_software = []
    try:
        installed_software = PlatformUtils.get_installed_software()
        logger.info(f"Collected {len(installed_software)} installed applications")
    except Exception as e:
        logger.error(f"Failed to collect software: {e}")

    # Phase 11: Collect live software inventory (outdated packages + OS patches)
    software_inventory, os_patches = [], {"pending_count": 0, "items": []}
    try:
        software_inventory, os_patches = collect_software_inventory()
    except Exception as e:
        logger.error(f"Failed to collect live software inventory: {e}")

    meta = {
        "os":                 sys_info["os"],
        "os_full_name":       sys_info["os_full_name"],
        "os_release":         sys_info["os_release"],
        "os_version_detail":  sys_info["os_version_detail"],
        "service_pack":       sys_info["service_pack"],
        "os_version":         sys_info["os_version"],
        "kernel_version":     sys_info["os_version_detail"],
        "python_version":     sys_info["python_version"],
        "cpu_model":          cpu_info,
        "memory_gb":          memory_info,
        "disks":              disks_info,
        "mac_address":        mac_address,
        "serial_number":      serial_number,
        "installed_software": installed_software,
        # Phase 11: live patch data reported to backend for /api/patches/outdated + /os
        "software_inventory": software_inventory,
        "os_patches":         os_patches,
    }

    for cap_id, cap_result in capability_data.items():
        if cap_result.get("status") == "success":
            data = cap_result.get("data", {})
            meta[cap_id] = data
            if cap_id == "metrics_collection":
                meta["current_cpu"]       = data.get("cpu", {}).get("percent", 0)
                meta["current_memory"]    = data.get("memory", {}).get("percent", 0)
                disks = data.get("disk", [])
                if disks:
                    meta["disk_usage"]    = disks[0].get("percent", 0)
                    meta["disk_total_gb"] = round(disks[0].get("total", 0) / (1024**3), 2)
                    meta["disk_used_gb"]  = round(disks[0].get("used",  0) / (1024**3), 2)
                    meta["disk_free_gb"]  = round(disks[0].get("free",  0) / (1024**3), 2)
                meta["total_memory_gb"]     = round(data.get("memory", {}).get("total",     0) / (1024**3), 2)
                meta["available_memory_gb"] = round(data.get("memory", {}).get("available", 0) / (1024**3), 2)

    meta["capabilities"]        = list(CAPABILITY_REGISTRY.keys())
    meta["capabilities_status"] = capability_mgr.get_all_capabilities_status()

    payload = {
        "hostname":  socket.gethostname(),
        "tenantId":  cfg.get("tenant_id"),
        "status":    "Online",
        "platform":  sys_info["os"],
        "version":   AGENT_VERSION,
        "ipAddress": get_ip_address(),
        "device_id": cfg.get("_security_mgr").device_id if cfg.get("_security_mgr") else "unknown",
        "meta":      meta,
    }

    headers = capability_mgr._auth_headers()
    url     = cfg["api_base_url"].rstrip("/") + f"/api/agents/{capability_mgr.agent_id}/heartbeat"

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        logger.info(f"Heartbeat → {resp.status_code}")

        if resp.status_code == 200:
            # Drain offline buffer
            if buffer_mgr:
                pending = buffer_mgr.get_messages(limit=5)
                for msg_id, msg_str in pending:
                    try:
                        msg_payload = json.loads(msg_str)
                        r = requests.post(url, json=msg_payload, headers=headers, timeout=10)
                        if r.status_code == 200:
                            buffer_mgr.delete_message(msg_id)
                        else:
                            break
                    except Exception as e:
                        logger.error(f"Error syncing buffered message {msg_id}: {e}")
                        break
            return True
        else:
            if buffer_mgr:
                buffer_mgr.add_message(payload)
            return False

    except Exception as e:
        logger.error(f"Heartbeat connection failed: {e}")
        if buffer_mgr:
            buffer_mgr.add_message(payload)
        return False

# ─────────────────────────────────────────────
# Phase 11: Live Software Inventory Collection
# ─────────────────────────────────────────────
def collect_software_inventory():
    """
    Collect live software inventory and pending OS patches.
    Returns: (software_inventory list, os_patches dict)

    - Linux:   apt list --installed (+ --upgradable for pending patches)
    - Linux:   pip list --outdated --format=json
    - Windows: Get-Package | Select Name,Version via PowerShell
    - Windows: winget upgrade --include-unknown (pending updates)
    - Both:    pip list --outdated --format=json (Python packages)
    """
    import subprocess
    import json as _json
    import platform as _platform
    import shutil
    import time

    software_inventory = []  # [{name, current_version, pkg_type}]
    os_patches = {"pending_count": 0, "items": [], "last_checked": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}

    system = _platform.system().lower()

    def run_cmd(cmd, timeout=30):
        """Run a shell command and return stdout, or None on error."""
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
                shell=isinstance(cmd, str)
            )
            return result.stdout.strip() if result.returncode in (0, 1) else None
        except Exception:
            return None

    # ── Linux apt ──────────────────────────────────────────────────────────
    if system == "linux" and shutil.which("apt"):
        try:
            # Installed packages with versions
            raw = run_cmd(["dpkg-query", "-W", "-f=${Package}\t${Version}\n"])
            if raw:
                for line in raw.splitlines()[:200]:  # Cap at 200
                    parts = line.split("\t")
                    if len(parts) == 2 and parts[1]:
                        software_inventory.append({
                            "name": parts[0], "current_version": parts[1], "pkg_type": "apt"
                        })

            # Pending upgradable packages
            upgradable = run_cmd(["apt", "list", "--upgradable"], timeout=15)
            if upgradable:
                items = []
                for line in upgradable.splitlines():
                    if "/" in line and "upgradable" not in line:
                        pkg_name = line.split("/")[0]
                        items.append(pkg_name)
                os_patches["pending_count"] = len(items)
                os_patches["items"] = items[:50]  # Cap display
        except Exception as e:
            logger.warning(f"[software_inventory] apt collection error: {e}")

    # ── Windows winget / PowerShell ────────────────────────────────────────
    elif system == "windows":
        try:
            if shutil.which("winget"):
                raw = run_cmd("winget upgrade --include-unknown --accept-source-agreements", timeout=30)
                if raw:
                    lines = raw.splitlines()
                    for line in lines[2:]:  # Skip header rows
                        parts = line.split()
                        if len(parts) >= 4:
                            software_inventory.append({
                                "name": parts[0], "current_version": parts[1],
                                "latest_version": parts[2], "pkg_type": "winget"
                            })
                            os_patches["items"].append(parts[0])
                    os_patches["pending_count"] = len(os_patches["items"])

            # Windows OS patches via PowerShell Get-HotFix
            hotfix = run_cmd("powershell -Command \"Get-HotFix | Select HotFixID,InstalledOn | ConvertTo-Json -Compress\"", timeout=20)
            if hotfix:
                hf_data = _json.loads(hotfix)
                if isinstance(hf_data, dict):
                    hf_data = [hf_data]
                for hf in hf_data[:20]:
                    kb_id = hf.get("HotFixID", "")
                    if kb_id:
                        software_inventory.append({
                            "name": kb_id, "current_version": "installed",
                            "installed_on": str(hf.get("InstalledOn", "")),
                            "pkg_type": "windows_update"
                        })
        except Exception as e:
            logger.warning(f"[software_inventory] Windows collection error: {e}")

    # ── Python pip (all platforms) ─────────────────────────────────────────
    try:
        pip_raw = run_cmd([sys.executable, "-m", "pip", "list", "--outdated", "--format=json"], timeout=30)
        if pip_raw:
            pip_outdated = _json.loads(pip_raw)
            for pkg in pip_outdated[:100]:  # Cap at 100
                software_inventory.append({
                    "name":            pkg.get("name", ""),
                    "current_version": pkg.get("version", ""),
                    "latest_version":  pkg.get("latest_version", ""),
                    "pkg_type":        "pip",
                    "is_outdated":     True
                })
    except Exception as e:
        logger.warning(f"[software_inventory] pip outdated error: {e}")

    logger.info(f"[software_inventory] Collected {len(software_inventory)} packages, {os_patches['pending_count']} OS patches pending")
    return software_inventory, os_patches



# ─────────────────────────────────────────────
# Fix 3: Instruction Polling (uses real agent_id)
# ─────────────────────────────────────────────
def check_and_execute_instructions(cfg, capability_mgr):
    """Poll backend for pending instructions using the registered agent_id."""
    agent_id = capability_mgr.agent_id   # Always resolves to DB ID or hostname fallback
    base_url = cfg.get("api_base_url", "http://localhost:5000").rstrip("/")
    url      = f"{base_url}/api/agents/{agent_id}/instructions"
    headers  = capability_mgr._auth_headers()
    
    logger.info(f"[DEBUG] Polling instructions from {url}")

    try:
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            instructions = resp.json()
            if not instructions:
                return
            logger.info(f"Received {len(instructions)} pending instruction(s)")
            for item in instructions:
                instr_type = item.get("instruction")
                payload    = item.get("payload")

                if instr_type == "start_remote_session":
                    result = capability_mgr.execute_remote_session(payload)
                elif instr_type == "run_software_scan":
                    # Phase 11: Live software inventory scan on demand
                    logger.info("[instruction] Running on-demand software inventory scan...")
                    sw_inventory, os_patches_data = collect_software_inventory()
                    result = {
                        "status": "success",
                        "software_inventory": sw_inventory,
                        "os_patches": os_patches_data,
                        "packages_found": len(sw_inventory)
                    }
                    # Report back to backend
                    try:
                        report_url = cfg.get("api_base_url", "").rstrip("/") + f"/api/agents/{capability_mgr.agent_id}/software-inventory"
                        requests.post(report_url, json=result, headers=capability_mgr._auth_headers(), timeout=10)
                    except Exception as e:
                        logger.warning(f"[run_software_scan] Failed to report: {e}")
                elif instr_type:
                    result = capability_mgr.execute_single_instruction(instr_type, payload=payload)
                else:
                    result = {"status": "skipped", "reason": "No instruction text"}

                logger.info(f"Instruction '{instr_type}' result: {result.get('status', result)}")
        elif resp.status_code == 404:
            logger.debug(f"No instructions endpoint for agent {agent_id}")
        else:
            logger.debug(f"Instruction poll: HTTP {resp.status_code}")
    except Exception as e:
        logger.error(f"[DEBUG] Instruction poll CRITICAL error: {e}")


# ─────────────────────────────────────────────
# Phase J/K: Autonomous Response Tasks Polling
# ─────────────────────────────────────────────
def poll_response_tasks(cfg, capability_mgr):
    """Poll backend for pending EDR response tasks and execute them using registered capabilities."""
    agent_id = capability_mgr.agent_id
    base_url = cfg.get("api_base_url", "http://localhost:5000").rstrip("/")
    url      = f"{base_url}/api/response/tasks/{agent_id}"
    headers  = capability_mgr._auth_headers()

    try:
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code != 200:
            return
        tasks = resp.json()
        if not tasks:
            return

        logger.info(f"Received {len(tasks)} pending response tasks.")

        # Grab pre-instantiated capability objects
        vss_cap  = capability_mgr.capability_instances.get("vss_manager")
        ar_cap   = capability_mgr.capability_instances.get("autonomous_response")

        for task in tasks:
            task_id = task.get("task_id")
            action  = task.get("action")
            params  = task.get("params", {})

            logger.warning(f"Executing Response Action: {action} (Task {task_id})")
            result = {"success": False, "message": "No handler found for action"}

            try:
                # ── Ransomware rollback via VSS Manager ─────────────────────
                if action == "rollback_ransomware":
                    if vss_cap:
                        result = vss_cap.execute_rollback(params)
                    else:
                        result = {"success": False, "message": "VSS Manager capability not enabled"}

                # ── EDR actions via Autonomous Response capability ───────────
                elif action in ("kill_process", "quarantine_file",
                                "isolate_host", "restore_host",
                                "unquarantine_file"):
                    if ar_cap:
                        result = ar_cap.execute(action, **params)
                    else:
                        # Lightweight fallback for kill_process only
                        if action == "kill_process" and params.get("pid"):
                            import psutil
                            psutil.Process(params["pid"]).terminate()
                            result = {"success": True, "message": f"Terminated PID {params['pid']}"}
                        else:
                            result = {"success": False, "message": "autonomous_response capability not enabled"}

                # ── CISSP 8-domain assessment ────────────────────────────────
                elif action == "cissp_assessment":
                    try:
                        from capabilities.cissp_analysis import run_cissp_assessment
                        result = run_cissp_assessment()
                        result["success"] = True
                    except Exception as ce:
                        result = {"success": False, "message": f"CISSP assessment failed: {ce}"}

                # ── Process snapshot ─────────────────────────────────────────
                elif action == "process_snapshot":
                    pm_cap = capability_mgr.capability_instances.get("process_monitor")
                    if pm_cap:
                        result = pm_cap.collect()
                        result["success"] = True
                    else:
                        result = {"success": False, "message": "process_monitor capability not enabled"}

                # ── Submit result back to backend ────────────────────────────
                result_url = f"{base_url}/api/response/tasks/{task_id}/result"
                requests.post(result_url, json=result, headers=headers, timeout=5)
                logger.info(f"Response task {task_id} ({action}) completed: success={result.get('success')}")

            except Exception as ex:
                logger.error(f"Failed to execute response task {task_id} ({action}): {ex}")
                try:
                    requests.post(
                        f"{base_url}/api/response/tasks/{task_id}/result",
                        json={"success": False, "message": str(ex)},
                        headers=headers, timeout=5
                    )
                except Exception:
                    pass
    except Exception:
        pass  # Silently ignore network errors between polls


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def main(service_instance=None):
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    else:
        application_path = os.getcwd()
    try:
        os.chdir(application_path)
    except Exception as e:
        logger.error(f"Failed to change CWD to {application_path}: {e}")

    cfg          = load_config()
    security_mgr = cfg.get('_security_mgr')
    interval     = int(cfg.get("interval_seconds", 30))

    logger.info(f"Starting Omni Agent v{AGENT_VERSION} — interval={interval}s")
    logger.info(f"Hostname: {socket.gethostname()}")
    logger.info(f"Available capabilities: {len(CAPABILITY_REGISTRY)}")

    # ── Fix 4: Register at startup ──────────────────────────────────────────
    register_agent(cfg)

    # ── Initialize capability manager ──────────────────────────────────────
    capability_mgr = AgentCapabilityManager(cfg)
    logger.info(f"Agent ID in use: {capability_mgr.agent_id}")

    # ── Initialize message buffer ──────────────────────────────────────────
    buffer_mgr = MessageBuffer(security_mgr=security_mgr)
    logger.info(f"Initialized Message Buffer at {buffer_mgr.db_path}")

    # ── Verify LLM availability ────────────────────────────────────────────
    try:
        if cfg.get('agentic_mode_enabled', False):
            llm_config = cfg.get('llm_config', {})
            provider   = llm_config.get('provider', 'ollama')
            logger.info(f"Checking AI Model availability (Provider: {provider})…")
            if provider == 'backend':
                from agentic_core.llm_engine import AgenticLLM
                check_config = llm_config.copy()
                check_config['api_base_url'] = cfg.get('api_base_url')
                check_config['api_key']      = cfg.get('agent_token')
                temp_engine = AgenticLLM(check_config)
                if temp_engine.is_available():
                    logger.info("✅ AI Model ready (Backend).")
                else:
                    logger.warning("⚠️ Backend AI unreachable. Agentic features may be limited.")
            else:
                from agentic_core.llm_manager import LLMManager
                if LLMManager().ensure_model_available():
                    logger.info("✅ AI Model ready (Local Ollama).")
                else:
                    logger.warning("⚠️ Local AI Model (Ollama) not available.")
    except Exception as e:
        logger.warning(f"Failed to initialize AI Model: {e}")

    # ── Fetch initial remote capability config ─────────────────────────────
    capability_mgr.fetch_configuration()

    # ── Start EDR Real-Time ETW listener background thread ────────────────
    try:
        edr_cap = capability_mgr.capability_instances.get("edr_realtime")
        if edr_cap and hasattr(edr_cap, "start_etw_listener"):
            edr_cap.start_etw_listener()   # launches daemon thread internally
            logger.info("✅ EDR Real-Time ETW listener started")
        else:
            logger.info("EDR real-time capability not enabled — skipping ETW thread")
    except Exception as edr_err:
        logger.warning(f"Could not start EDR ETW listener: {edr_err}")

    # ── Main loop ──────────────────────────────────────────────────────────
    heartbeat_count = 0
    while True:
        if service_instance:
            try:
                if win32event.WaitForSingleObject(service_instance.hWaitStop, 0) == win32event.WAIT_OBJECT_0:
                    logger.info("Service Stop Signal Received. Stopping Agent.")
                    break
            except Exception:
                pass

        try:
            # Refresh config from backend every 10 heartbeats
            if heartbeat_count % 10 == 0:
                capability_mgr.fetch_configuration()

            # CPU throttle guard
            current_cpu = psutil.cpu_percent(interval=1.0)
            max_cpu     = int(cfg.get("max_cpu_percent", 20))
            if current_cpu > max_cpu:
                logger.warning(f"High CPU ({current_cpu}%). Throttling…")
                time.sleep(5)

            send_heartbeat(cfg, capability_mgr, buffer_mgr)
            check_and_execute_instructions(cfg, capability_mgr)
            poll_response_tasks(cfg, capability_mgr)

            # Goal evaluation (if enabled)
            if capability_mgr.goal_manager:
                failing_goals = capability_mgr.goal_manager.evaluate_goals()
                if failing_goals:
                    logger.warning(f"{len(failing_goals)} failing goal(s). Generating plans…")
                    for goal in failing_goals:
                        strategy = capability_mgr.goal_manager.generate_strategic_plan(
                            goal, {"system_status": "degraded"}
                        )
                        logger.info(f"Plan for {goal.name}: {strategy.get('strategy', 'N/A')}")

            heartbeat_count += 1
            time.sleep(interval)

        except KeyboardInterrupt:
            logger.info("Agent stopped by user.")
            break
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
            time.sleep(interval)


# ─────────────────────────────────────────────
# Windows Service Support
# ─────────────────────────────────────────────
try:
    import win32serviceutil
    import win32service
    import win32event
    WINDOWS_SERVICE_AVAILABLE = True
except ImportError:
    WINDOWS_SERVICE_AVAILABLE = False

if WINDOWS_SERVICE_AVAILABLE:
    import servicemanager

    class AppServerSvc(win32serviceutil.ServiceFramework):
        _svc_name_         = "OmniAgent"
        _svc_display_name_ = "Enterprise Omni Agent"
        _svc_description_  = "AI-Powered Enterprise Security Agent"

        def __init__(self, args):
            win32serviceutil.ServiceFramework.__init__(self, args)
            self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self.hWaitStop)

        def SvcDoRun(self):
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, '')
            )
            main(self)


if __name__ == "__main__":
    from service_manager import ServiceManager

    if len(sys.argv) > 1:
        svc_mgr = ServiceManager()
        if "--install" in sys.argv:
            if svc_mgr.install():
                svc_mgr.start()
            sys.exit(0)
        elif "--uninstall" in sys.argv:
            svc_mgr.stop()
            svc_mgr.uninstall()
            sys.exit(0)
        elif "--start-service" in sys.argv:
            svc_mgr.start()
            sys.exit(0)
        elif "--stop-service" in sys.argv:
            svc_mgr.stop()
            sys.exit(0)

    if WINDOWS_SERVICE_AVAILABLE and len(sys.argv) == 1:
        try:
            servicemanager.Initialize()
            servicemanager.PrepareToHostSingle(AppServerSvc)
            servicemanager.StartServiceCtrlDispatcher()
        except Exception:
            main()
    else:
        main()
