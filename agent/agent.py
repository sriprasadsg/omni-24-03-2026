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

# ---------------------------------------------
# Setup logging
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ---------------------------------------------
# Optional Agentic Core imports
# ─────────────────────────────────────────────
def _try_import(module_path: str, class_name: str):
    """Import a single optional class; return (class, None) or (None, error_msg)."""
    try:
        import importlib
        mod = importlib.import_module(module_path)
        return getattr(mod, class_name), None
    except Exception as _e:
        return None, str(_e)

_degraded: list[str] = []
AgenticLLM,               _e = _try_import("agentic_core.llm_engine",          "AgenticLLM")
if _e: _degraded.append(f"llm_engine ({_e})")

SafetyGuardrails,         _e = _try_import("agentic_core.safety",              "SafetyGuardrails")
if _e: _degraded.append(f"safety_guardrails ({_e})")

AgenticReasoningEngine,   _e = _try_import("agentic_core.reasoning",           "AgenticReasoningEngine")
if _e: _degraded.append(f"reasoning_engine ({_e})")

AutonomousRemediationEngine, _e = _try_import("autonomous_actions.remediation", "AutonomousRemediationEngine")
if _e: _degraded.append(f"autonomous_remediation ({_e})")

GoalManager,              _e = _try_import("goal_system.manager",              "GoalManager")
if _e: _degraded.append(f"goal_manager ({_e})")

AgentMemory,              _e = _try_import("knowledge_base.memory",            "AgentMemory")
if _e: _degraded.append(f"agent_memory ({_e})")

SwarmCoordinator,         _e = _try_import("swarm.coordinator",                "SwarmCoordinator")
if _e: _degraded.append(f"swarm_coordinator ({_e})")

if _degraded:
    logging.warning(
        "[Agent] Running in degraded mode — %d agentic module(s) unavailable: %s. "
        "Autonomous reasoning, remediation, and swarm coordination are DISABLED for those modules.",
        len(_degraded),
        ", ".join(_degraded),
    )
else:
    logging.info("[Agent] All agentic core modules loaded successfully.")

from security import SecurityManager
from platform_utils import PlatformUtils

# Thread-safe buffer: completed response-task outcomes flushed via next heartbeat
_pending_task_feedback: list = []


# ---------------------------------------------
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


# ---------------------------------------------
# Fix 3: Agent Registration Flow
# ---------------------------------------------
def register_agent(cfg) -> bool:
    """
    Exchange registration_key for a permanent agent_token + agent_id.
    Persists the result back to config.yaml so subsequent runs skip this step.
    Returns True if (already registered) or (registration succeeded).
    """
    # Already registered
    if cfg.get("agent_token") and cfg.get("agent_id"):
        logger.info(f"[SUCCESS] Agent already registered - ID: {cfg['agent_id']}")
        return True

    base_url = cfg.get("api_base_url", "http://localhost:5000").rstrip("/")
    reg_key  = cfg.get("registration_key", "")
    hostname = socket.gethostname()

    try:
        logger.info(f"Registering agent '{hostname}' with backend at {base_url}...")
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
            agent_token = data.get("token") or data.get("agent_token") or data.get("access_token")
            agent_id    = data.get("agent_id") or data.get("agentId") or data.get("id")

            if agent_token and agent_id:
                cfg["agent_token"] = agent_token
                cfg["agent_id"]    = agent_id
                save_config(cfg)
                logger.info(f"[SUCCESS] Registration successful - Agent ID: {agent_id}")
                return True
            else:
                logger.warning(f"Registration response missing token or agent_id: {data}")
                # Do NOT fall back to hostname-as-id or store a partial config —
                # operating without a valid token would broadcast the registration key.
                return False

        else:
            logger.warning(f"Registration failed (HTTP {resp.status_code}): {resp.text[:200]}")
            return False

    except Exception as e:
        logger.error(f"Registration error: {e}")
        # Fallback degraded mode — use hostname as agent_id so polling can try
        cfg.setdefault("agent_id", hostname)
        return False


# ---------------------------------------------
# Capability Manager
# ---------------------------------------------
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
                        self.cfg.get('autonomous_actions', {}),
                        memory=self.memory,
                    )

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
                        self.swarm.capability_mgr = self  # enable task dispatch
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
                # Pass real cfg, not an empty default — real_fim, threat_intel,
                # predictive_health, remediation, ticket_reporter, and log_shipper
                # all read self.config expecting api_base_url/agent_id/agent_token/
                # tunable thresholds; passing nothing here silently gave every one
                # of them an empty dict, so they fell back to hardcoded
                # localhost:5000 + agent_id "unknown" + no auth token —
                # log_shipper's every POST 404'd/misrouted as a direct result.
                # A handful of capability classes still override __init__ with a
                # zero-arg or non-config signature (e.g. AutonomousResponseCapability,
                # PIIScannerCapability) — TypeError falls back to the old zero-arg
                # call so those keep working exactly as before.
                try:
                    instance = cap_class(self.cfg)
                except TypeError:
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
            tenant_key = self.cfg.get('registration_key', '') if hasattr(self, 'cfg') else ''
            if session_type == "desktop":
                t = threading.Thread(target=remote_cap.start_desktop_stream, args=(session_id, url, tenant_key))
            else:
                t = threading.Thread(target=remote_cap.start_reverse_shell, args=(session_id, url, tenant_key))
            t.daemon = True
            t.start()
            return {"status": "started", "session_id": session_id}
        return {"status": "error", "error": "Remote Access capability not available"}

    # ── Agent Chat Window ──────────────────────────────────────────────────
    def execute_agent_chat(self, payload: dict, cfg: dict) -> dict:
        """Open a chat popup window on the endpoint desktop."""
        session_id      = payload.get("session_id")
        subject         = payload.get("subject", "Message from IT Administrator")
        initial_message = payload.get("initial_message", "")
        backend_url     = payload.get("backend_url") or cfg.get("api_base_url", "").rstrip("/")
        sender          = payload.get("sender", "Administrator")

        chat_cap = self.capability_instances.get("chat_window")
        if chat_cap:
            return chat_cap.start_chat(
                session_id=session_id,
                subject=subject,
                initial_message=initial_message,
                backend_url=backend_url,
                auth_headers=self._auth_headers(),
                sender=sender,
            )
        return {"status": "error", "error": "chat_window capability not available"}

    def deliver_chat_message(self, payload: dict) -> dict:
        """Deliver a follow-up admin message to an already-open chat window.
        The window polls the backend itself, so this just signals it's there."""
        session_id = payload.get("session_id")
        chat_cap   = self.capability_instances.get("chat_window")
        if chat_cap and session_id:
            # Window polls independently — no direct injection needed
            logger.debug("[AgentChat] New message queued for session %s", session_id)
            return {"status": "acknowledged", "session_id": session_id}
        return {"status": "no_active_window", "session_id": session_id}

    # ── Single Instruction Dispatcher ──────────────────────────────────────
    def execute_single_instruction(self, instruction: str, payload: dict = None) -> dict:
        """Dispatches a single text instruction to the appropriate capability."""
        import re

        # ── Create Ticket ──────────────────────────────────────────────────
        if instruction == "create_ticket" or "create_ticket" in instruction:
            cap = self.capability_instances.get("ticket_reporter")
            if cap:
                p = payload or {}
                # Prefer tenant from payload (set by backend), fall back to agent config
                tenant_id = p.get("tenantId") or self.cfg.get("tenant_id", "")
                if tenant_id:
                    cap.config["tenant_id"] = tenant_id
                ticket = cap.raise_ticket(
                    title=p.get("title", "Agent-raised ticket"),
                    description=p.get("description", ""),
                    ticket_type=p.get("type", "task"),
                    priority=p.get("priority", "medium"),
                    assignee=p.get("assignee", ""),
                    tags=p.get("tags", ["user-raised"]),
                    endpoint_info=p.get("endpoint_info"),  # forwarded from tray icon payload
                )
                if ticket:
                    logger.info("Ticket created by agent instruction: %s", ticket.get("ticket_number"))
                    return {"status": "success", "ticket_number": ticket.get("ticket_number"), "ticket_id": ticket.get("id")}
                return {"status": "error", "error": "Ticket creation failed"}
            return {"status": "error", "error": "TicketReporter capability not available"}

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
                download_url = payload.get("download_url") if payload else None
                install_args = payload.get("install_args") if payload else None
                if download_url:
                    # Resolve relative URL to absolute using api_base_url
                    if download_url.startswith("/"):
                        base_url = self.cfg.get('api_base_url', 'http://localhost:5000').rstrip('/')
                        download_url = base_url + download_url
                    return cap.install_from_url(
                        download_url, package_id,
                        install_args=install_args,
                        headers=self._auth_headers(),
                    )
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

        # ── Run VirusTotal Scan ──────────────────────────────────────
        if instruction in ("run_virustotal_scan", "Run VirusTotal Scan"):
            cap = self.capability_instances.get('virustotal_scan')
            if cap:
                logger.info("Direct Execution: Running VirusTotal Endpoint Scan")
                result = cap.collect() if hasattr(cap, 'collect') else cap.execute()
                try:
                    url = self.cfg.get("api_base_url").rstrip("/") + f"/api/agents/{self.agent_id}/virustotal-results"
                    requests.post(url, json={"results": result}, headers=self._auth_headers(), timeout=15)
                except Exception as e:
                    logger.error(f"Failed to report VirusTotal scan: {e}")
                return result
            return {"status": "error", "error": "virustotal_scan capability not available"}

        # ── Run Vulnerability Scan ─────────────────────────────────────────
        if instruction in ("run_vulnerability_scan", "Run Vulnerability Scan"):
            cap = self.capability_instances.get('vulnerability_scanning')
            if cap:
                logger.info("Direct Execution: Running Vulnerability Scan")
                result = cap.collect() if hasattr(cap, 'collect') else cap.execute()
                try:
                    url = self.cfg.get("api_base_url").rstrip("/") + f"/api/agents/{self.agent_id}/vulnerability-scan"
                    requests.post(url, json=result, headers=self._auth_headers(), timeout=10)
                except Exception as e:
                    logger.error(f"Failed to report vuln scan: {e}")
                return result
            return {"status": "error", "error": "vulnerability_scanning capability not available"}

        # ── Run Process Snapshot ───────────────────────────────────────────
        if instruction in ("run_process_snapshot", "Run Process Snapshot"):
            pm_cap = self.capability_instances.get('process_monitor')
            if pm_cap:
                logger.info("Direct Execution: Running Process Snapshot")
                result = pm_cap.collect() if hasattr(pm_cap, 'collect') else pm_cap.execute()
                try:
                    url = self.cfg.get("api_base_url").rstrip("/") + f"/api/agents/{self.agent_id}/process-snapshot"
                    requests.post(url, json=result, headers=self._auth_headers(), timeout=10)
                except Exception as e:
                    logger.error(f"Failed to report process snapshot: {e}")
                return result
            return {"status": "error", "error": "process_monitor capability not available"}

        # ── Run Patch Scan ─────────────────────────────────────────────────
        if instruction in ("run_patch_scan", "Run Patch Scan"):
            cap = self.capability_instances.get('system_patching')
            if cap:
                logger.info("Direct Execution: Running Patch Scan")
                result = cap.collect() if hasattr(cap, 'collect') else cap.execute()
                return result
            return {"status": "error", "error": "system_patching capability not available"}

        # ── Run Shadow AI Scan ─────────────────────────────────────────────
        if instruction in ("run_shadow_ai_scan", "Run Shadow AI Scan"):
            cap = self.capability_instances.get('shadow_ai')
            if cap:
                logger.info("Direct Execution: Running Shadow AI Scan")
                result = cap.collect() if hasattr(cap, 'collect') else cap.execute()
                return result
            return {"status": "error", "error": "shadow_ai capability not available"}

        # ── Autonomous Threat Hunt ─────────────────────────────────────────
        if instruction in ("run_threat_hunt", "Run Threat Hunt"):
            logger.warning("⚡ THREAT HUNT TRIGGERED — running comprehensive scan")
            results = {}
            for cap_id in ("vulnerability_scanning", "compliance_enforcement",
                           "process_monitor", "persistence_detection", "shadow_ai"):
                cap = self.capability_instances.get(cap_id)
                if cap:
                    try:
                        results[cap_id] = cap.collect() if hasattr(cap, 'collect') else cap.execute()
                    except Exception as e:
                        results[cap_id] = {"error": str(e)}
            try:
                url = self.cfg.get("api_base_url").rstrip("/") + f"/api/agents/{self.agent_id}/threat-hunt-results"
                requests.post(
                    url,
                    json={"results": results, "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())},
                    headers=self._auth_headers(), timeout=15,
                )
            except Exception as e:
                logger.error(f"Failed to report threat hunt: {e}")
            return {"status": "success", "capabilities_run": list(results.keys())}

        # ── Kill-Chain Pre-staged Defenses ────────────────────────────────
        if instruction in ("enable_enhanced_auth_logging", "Enable Enhanced Auth Logging"):
            logger.info("Enabling enhanced authentication logging")
            return self._enable_enhanced_auth_logging()

        if instruction in ("enable_privilege_monitoring", "Enable Privilege Monitoring"):
            logger.info("Enabling privilege escalation monitoring")
            return self._enable_privilege_monitoring()

        if instruction in ("enable_data_loss_monitoring", "Enable Data Loss Monitoring"):
            logger.info("Enabling data loss monitoring")
            results = {}
            for cap_id in ("shadow_ai", "fim"):
                cap = self.capability_instances.get(cap_id)
                if cap:
                    try:
                        results[cap_id] = cap.collect() if hasattr(cap, 'collect') else cap.execute()
                    except Exception as e:
                        results[cap_id] = {"error": str(e)}
            return {"status": "success", "message": "Data loss monitoring activated", "results": results}

        if instruction in ("create_vss_snapshot", "Create VSS Snapshot"):
            vss_cap = self.capability_instances.get('vss_manager')
            if vss_cap:
                try:
                    fn = getattr(vss_cap, 'create_snapshot', None) or getattr(vss_cap, 'execute', None)
                    result = fn() if fn else {"status": "error", "error": "no create_snapshot method"}
                    return {"status": "success", "message": "VSS snapshot created", "result": result}
                except Exception as e:
                    return {"status": "error", "error": str(e)}
            return {"status": "error", "error": "vss_manager capability not available"}

        if instruction in ("run_vss_rollback_check", "Run VSS Rollback Check"):
            vss_cap = self.capability_instances.get('vss_manager')
            if vss_cap:
                try:
                    fn = getattr(vss_cap, 'check_snapshots', None) or getattr(vss_cap, 'execute', None)
                    result = fn() if fn else {"status": "error", "error": "no check_snapshots method"}
                    return {"status": "success", "result": result}
                except Exception as e:
                    return {"status": "error", "error": str(e)}
            return {"status": "error", "error": "vss_manager capability not available"}

        # ── Chaos Engineering ──────────────────────────────────────────────
        _chaos_type = (payload or {}).get("metadata", {}).get("chaos_type", "") if payload else ""
        if not _chaos_type:
            # Infer from instruction text
            if "chaos_cpu_hog" in instruction or "stress --cpu" in instruction or "CPU stress" in instruction:
                _chaos_type = "CPU Hog"
            elif "chaos_latency" in instruction or "tc qdisc" in instruction or "netem delay" in instruction:
                _chaos_type = "Latency Injection"
            elif "chaos_process_kill" in instruction or "kill -9" in instruction or "chaos_process" in instruction:
                _chaos_type = "Pod Failure"
            elif "chaos_disk_fill" in instruction or "dd if=/dev/zero" in instruction:
                _chaos_type = "Disk Fill"
            elif "chaos_memory" in instruction or "bytearray" in instruction and "chaos" in instruction:
                _chaos_type = "Memory Leak"

        if _chaos_type:
            import subprocess, platform as _platform, threading as _threading
            _os = _platform.system()
            _result = {"chaos_type": _chaos_type, "platform": _os}

            def _run(cmd, shell=True, timeout=90):
                try:
                    r = subprocess.run(cmd, shell=shell, capture_output=True, text=True, timeout=timeout)
                    return {"rc": r.returncode, "stdout": r.stdout[:500], "stderr": r.stderr[:200]}
                except subprocess.TimeoutExpired:
                    return {"rc": -1, "note": "timeout (experiment still running)"}
                except Exception as exc:
                    return {"rc": -1, "error": str(exc)}

            try:
                if _chaos_type == "CPU Hog":
                    if _os == "Windows":
                        # Busy-loop in a background thread for 60 s
                        def _cpu_burn():
                            import time
                            end = time.time() + 60
                            while time.time() < end:
                                _ = sum(i * i for i in range(10000))
                        for _ in range(4):
                            t = _threading.Thread(target=_cpu_burn, daemon=True)
                            t.start()
                        _result.update({"status": "success", "note": "4 CPU-burn threads started for 60s"})
                    else:
                        _r = _run("stress --cpu 4 --timeout 60s 2>/dev/null || stress-ng --cpu 4 --timeout 60s 2>/dev/null || true", timeout=5)
                        _result.update({"status": "success", "note": "stress started in background", **_r})

                elif _chaos_type == "Latency Injection":
                    if _os != "Windows":
                        iface = "eth0"
                        _run(f"tc qdisc del dev {iface} root 2>/dev/null || true", timeout=5)
                        _r = _run(f"tc qdisc add dev {iface} root netem delay 200ms 2>/dev/null || true", timeout=5)
                        # Auto-clean after 60 s
                        def _clean_tc():
                            import time; time.sleep(60)
                            subprocess.run(f"tc qdisc del dev {iface} root 2>/dev/null || true", shell=True)
                        _threading.Thread(target=_clean_tc, daemon=True).start()
                        _result.update({"status": "success", "note": "200ms latency injected for 60s", **_r})
                    else:
                        _result.update({"status": "skipped", "note": "tc/netem not available on Windows"})

                elif _chaos_type == "Pod Failure":
                    import re as _re
                    target = (payload or {}).get("metadata", {}).get("target", "")
                    if not target:
                        m = _re.search(r'pgrep -f ([^\s)]+)', instruction)
                        target = m.group(1) if m else ""
                    # Validate: only allow safe process-name characters (alphanumeric, hyphen, dot, underscore)
                    if target and not _re.fullmatch(r'[\w\-\.]+', target):
                        _result.update({"status": "error", "note": f"Rejected unsafe target value: {target!r}"})
                    elif target and _os != "Windows":
                        import subprocess as _sp
                        pgrep = _sp.run(["pgrep", "-f", target], capture_output=True, text=True)
                        pids = pgrep.stdout.split()
                        if pids:
                            _sp.run(["kill", "-9"] + pids, capture_output=True)
                        _r = {"stdout": pgrep.stdout, "returncode": pgrep.returncode}
                        _result.update({"status": "success", "note": f"SIGKILL sent to processes matching '{target}'", **_r})
                    elif target and _os == "Windows":
                        import subprocess as _sp
                        _r = _sp.run(["taskkill", "/F", "/IM", target], capture_output=True, text=True)
                        _result.update({"status": "success", "note": f"taskkill attempted for '{target}'",
                                        "stdout": _r.stdout, "returncode": _r.returncode})
                    else:
                        _result.update({"status": "skipped", "note": "no target process specified"})

                elif _chaos_type == "Disk Fill":
                    tmp = "C:\\Windows\\Temp\\chaos_fill.bin" if _os == "Windows" else "/tmp/chaos_fill.bin"
                    def _fill_and_clean():
                        import time
                        try:
                            with open(tmp, "wb") as f:
                                f.write(b"\x00" * (512 * 1024 * 1024))
                        except Exception:
                            pass
                        time.sleep(60)
                        try:
                            import os as _os2; _os2.remove(tmp)
                        except Exception:
                            pass
                    _threading.Thread(target=_fill_and_clean, daemon=True).start()
                    _result.update({"status": "success", "note": "512 MB written to temp, will auto-delete in 60s"})

                elif _chaos_type == "Memory Leak":
                    def _alloc():
                        import time
                        data = [bytearray(1024 * 1024) for _ in range(256)]
                        time.sleep(60)
                        del data
                    _threading.Thread(target=_alloc, daemon=True).start()
                    _result.update({"status": "success", "note": "256 MB allocated for 60s then released"})

            except Exception as exc:
                _result.update({"status": "error", "error": str(exc)})

            # Report back to backend
            _exp_id = (payload or {}).get("metadata", {}).get("experiment_id", "")
            if _exp_id and self.agent_id:
                try:
                    import requests as _req
                    _req.post(
                        f"{self.cfg.get('api_base_url', '').rstrip('/')}/api/chaos/experiments/{_exp_id}/result",
                        json={"agent_id": self.agent_id, "result": _result},
                        headers=self._auth_headers(), timeout=5,
                    )
                except Exception:
                    pass

            return _result

        # ── Fallback: LLM Reasoning ────────────────────────────────────────
        if not self.reasoning:
            # Try to run the instruction directly via any matching capability
            for cap_id, cap_instance in self.capability_instances.items():
                if hasattr(cap_instance, "execute") and cap_id in instruction.lower():
                    try:
                        result = cap_instance.execute({"instruction": instruction})
                        return {"status": "success", "instruction": instruction, "source": cap_id, **result}
                    except Exception:
                        pass
            return {
                "status": "unavailable",
                "message": "Reasoning Engine not active; no matching capability found.",
                "instruction": instruction
            }
        try:
            decision = self.reasoning.decide_action({"instruction": instruction, "context": "instruction_dispatch"})
            # Post to backend for audit/approval when agent cannot act autonomously
            if not decision.get("is_autonomous") and self.agent_id and self.api_base_url:
                try:
                    requests.post(
                        f"{self.api_base_url.rstrip('/')}/api/agents/{self.agent_id}/agentic-decision",
                        json={
                            "context":             {"instruction": instruction},
                            "recommended_action":  decision.get("action", "none"),
                            "confidence":          decision.get("plan", {}).get("confidence", 0.0),
                            "reasoning":           decision.get("reason", ""),
                            "requires_approval":   True,
                        },
                        headers=self._auth_headers(),
                        timeout=5,
                    )
                except Exception as _de:
                    logger.debug("Failed to post agentic decision: %s", _de)
            return {
                "status":        "success",
                "instruction":   instruction,
                "plan":          decision.get("plan", {}),
                "decision":      decision,
                "execution_log": ["Analyzed instruction", f"Recommended: {decision.get('action')}", "Complete"]
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _enable_enhanced_auth_logging(self) -> dict:
        """Enable verbose authentication event logging (platform-specific)."""
        import subprocess, platform as _platform
        try:
            if _platform.system() == "Windows":
                subprocess.run(
                    ["auditpol", "/set", "/subcategory:Logon", "/success:enable", "/failure:enable"],
                    capture_output=True, timeout=15, check=False,
                )
                subprocess.run(
                    ["auditpol", "/set", "/subcategory:Account Logon", "/success:enable", "/failure:enable"],
                    capture_output=True, timeout=15, check=False,
                )
            else:
                subprocess.run(
                    ["bash", "-c", "auditctl -a always,exit -F arch=b64 -S execve -k auth_monitoring 2>/dev/null || true"],
                    capture_output=True, timeout=10, check=False,
                )
            logger.info("Enhanced auth logging enabled")
            return {"status": "success", "message": "Enhanced authentication logging enabled"}
        except Exception as e:
            logger.warning("_enable_enhanced_auth_logging: %s", e)
            return {"status": "partial", "message": str(e)}

    def _enable_privilege_monitoring(self) -> dict:
        """Enable privilege escalation monitoring (platform-specific)."""
        import subprocess, platform as _platform
        try:
            if _platform.system() == "Windows":
                subprocess.run(
                    ["auditpol", "/set", "/subcategory:Sensitive Privilege Use", "/success:enable", "/failure:enable"],
                    capture_output=True, timeout=15, check=False,
                )
            else:
                subprocess.run(
                    ["bash", "-c", "auditctl -a always,exit -F arch=b64 -S setuid -S setgid -k priv_escalation 2>/dev/null || true"],
                    capture_output=True, timeout=10, check=False,
                )
            logger.info("Privilege escalation monitoring enabled")
            return {"status": "success", "message": "Privilege escalation monitoring enabled"}
        except Exception as e:
            logger.warning("_enable_privilege_monitoring: %s", e)
            return {"status": "partial", "message": str(e)}

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
                # Apply per-capability settings pushed from the dashboard
                capability_settings = config.get("capabilitySettings", {})
                for cap_id, settings in capability_settings.items():
                    instance = self.capability_instances.get(cap_id)
                    if instance is not None and isinstance(settings, dict):
                        instance.config.update(settings)
                        logger.info(f"Applied server config to capability '{cap_id}': {list(settings.keys())}")
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
            "virustotal_scan", # ADDED: VirusTotal scanning capability
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
            "virustotal_scan":              3600, # ADDED
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
                if not hasattr(capability, "should_run"):
                    # On-demand action executors (e.g. autonomous_response) aren't
                    # polled on an interval — they're invoked directly by name.
                    continue
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
    device_type_info = PlatformUtils.detect_device_type()
    capability_data  = capability_mgr.collect_all_data()
    cpu_info         = PlatformUtils.get_cpu_info()
    memory_info      = PlatformUtils.get_memory_info()
    disks_info       = PlatformUtils.get_storage_info()
    mac_address      = PlatformUtils.get_mac_address()
    serial_number    = PlatformUtils.get_serial_number()
    install_date     = PlatformUtils.get_os_install_date()

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
        "os_release":         sys_info["os_release"],          # e.g. "23H2"
        "os_version_detail":  sys_info["os_version_detail"],   # e.g. "10.0.26200.2803"
        "os_version":         sys_info["os_version"],          # same as above
        "kernel_version":     sys_info["os_version_detail"],   # alias used by backend
        "os_build_number":    sys_info.get("os_build_number", ""),  # "26200" bare
        "os_ubr":             sys_info.get("os_ubr", ""),           # "2803"
        "service_pack":       sys_info.get("service_pack", ""),
        "python_version":     sys_info["python_version"],
        "cpu_model":          cpu_info,
        "memory_gb":          memory_info,
        "disks":              disks_info,
        "mac_address":        mac_address,
        "serial_number":      serial_number,
        "install_date":       install_date,
        "device_type":        device_type_info.get("device_type", "unknown"),
        "chassis_label":      device_type_info.get("chassis_label", "Unknown"),
        "is_virtual":         device_type_info.get("is_virtual", False),
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

    meta["available_capabilities"] = list(CAPABILITY_REGISTRY.keys())
    meta["capabilities_status"]    = capability_mgr.get_all_capabilities_status()

    # Update GoalManager progress from live capability metrics
    if capability_mgr.goal_manager:
        try:
            metrics_data = capability_data.get("metrics_collection", {}).get("data", {})
            patch_data   = capability_data.get("software_management", {}).get("data", {})
            health_data  = capability_data.get("predictive_health",   {}).get("data", {})
            rt_data      = capability_data.get("runtime_security",     {}).get("data", {})
            _gm = capability_mgr.goal_manager
            if metrics_data:
                _gm.update_goal_progress("system_uptime",    float(100 - metrics_data.get("cpu", {}).get("percent", 0)))
            if patch_data:
                _gm.update_goal_progress("patch_critical_cves", float(patch_data.get("compliance_pct", 0)))
            if health_data:
                _gm.update_goal_progress("predictive_health_score", float(health_data.get("health_score", 0)))
            if rt_data:
                _gm.update_goal_progress("threat_detection_rate", float(rt_data.get("detections_count", 0)))
        except Exception as _gme:
            logger.debug("Goal progress update failed: %s", _gme)

    # Post shadow AI scan results to dedicated endpoint
    shadow_data = capability_data.get("shadow_ai", {})
    if shadow_data.get("status") == "success" and shadow_data.get("data"):
        try:
            sd = shadow_data["data"]
            if sd.get("detected_count", 0) > 0:
                shadow_payload = {
                    "detected_count":    sd.get("detected_count", 0),
                    "ai_connections":    sd.get("ai_connections", []),
                    "local_ai_processes": sd.get("local_ai_processes", []),
                    "local_ai_ports":    sd.get("local_ai_ports", []),
                }
                shadow_url = cfg["api_base_url"].rstrip("/") + f"/api/agents/{capability_mgr.agent_id}/shadow-ai-scan"
                requests.post(shadow_url, json=shadow_payload, headers=capability_mgr._auth_headers(), timeout=10)
                logger.info("[Heartbeat] Shadow AI scan posted (%d detections)", sd.get("detected_count", 0))
        except Exception as _se:
            logger.debug("Shadow AI scan post failed: %s", _se)

    # Post vulnerability scan results to dedicated endpoint
    vuln_data = capability_data.get("vulnerability_scanner", {})
    if vuln_data.get("status") == "success" and vuln_data.get("data"):
        try:
            vd = vuln_data["data"]
            vscan_payload = {
                "total_packages":      vd.get("total_packages", 0),
                "vulnerable_packages": vd.get("vulnerable_packages", []),
                "total_cves":          vd.get("total_cves", 0),
                "scan_source":         vd.get("scan_source", "osv"),
                "os_patches":          vd.get("os_patches", {}),
            }
            vscan_url = cfg["api_base_url"].rstrip("/") + f"/api/agents/{capability_mgr.agent_id}/vulnerability-scan"
            requests.post(vscan_url, json=vscan_payload, headers=capability_mgr._auth_headers(), timeout=15)
            logger.info("[Heartbeat] Vulnerability scan results posted (%d CVEs)", vscan_payload["total_cves"])
        except Exception as _ve:
            logger.debug("Vulnerability scan post failed: %s", _ve)

    # Post persistence findings to dedicated endpoint
    persist_data = capability_data.get("persistence_detection", {})
    if persist_data.get("status") == "success" and persist_data.get("data"):
        try:
            pd = persist_data["data"]
            persist_payload = {
                "total_entries":      pd.get("total_entries", 0),
                "suspicious_entries": pd.get("suspicious_entries", []),
                "critical_count":     pd.get("critical_count", 0),
                "high_count":         pd.get("high_count", 0),
                "platform":           pd.get("platform", sys_info.get("os", "unknown")),
            }
            persist_url = cfg["api_base_url"].rstrip("/") + f"/api/agents/{capability_mgr.agent_id}/persistence-findings"
            requests.post(persist_url, json=persist_payload, headers=capability_mgr._auth_headers(), timeout=15)
            logger.info("[Heartbeat] Persistence findings posted (%d suspicious)", pd.get("total_entries", 0))
        except Exception as _pe:
            logger.debug("Persistence findings post failed: %s", _pe)

    # Flush buffered task feedback (batch resilience for offline periods)
    global _pending_task_feedback
    if _pending_task_feedback:
        meta["task_feedback"] = _pending_task_feedback[:20]
        _pending_task_feedback = _pending_task_feedback[20:]

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
            if resp.status_code == 403:
                try:
                    auth_error = resp.json().get("error", "")
                except Exception:
                    auth_error = ""
                if auth_error in ("Invalid Agent Token", "Agent token has been revoked", "Invalid Tenant Key"):
                    logger.warning(f"Agent token rejected ({auth_error}) — re-registering")
                    cfg["agent_token"] = None
                    save_config(cfg)
                    register_agent(cfg)
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
                task_id    = item.get("task_id")

                try:
                    if instr_type == "start_remote_session":
                        result = capability_mgr.execute_remote_session(payload)
                    elif instr_type == "start_agent_chat":
                        result = capability_mgr.execute_agent_chat(payload, cfg)
                    elif instr_type == "agent_chat_message":
                        result = capability_mgr.deliver_chat_message(payload)
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
                except Exception as _instr_err:
                    logger.error(
                        "Instruction '%s' raised unhandled exception — skipping to next: %s",
                        instr_type, _instr_err, exc_info=True
                    )
                    result = {"status": "error", "error": str(_instr_err)}

                logger.info(f"Instruction '{instr_type}' result: {result.get('status', result)}")

                # Report result back so backend can update task status for UI polling
                if task_id and instr_type and instr_type != "skipped":
                    try:
                        result_url = cfg.get("api_base_url", "").rstrip("/") + f"/api/agents/{agent_id}/instructions/result"
                        requests.post(
                            result_url,
                            json={**result, "task_id": task_id, "type": instr_type},
                            headers=capability_mgr._auth_headers(),
                            timeout=10,
                        )
                    except Exception as _re:
                        logger.warning(f"Failed to report instruction result for task {task_id}: {_re}")

                # Store every instruction outcome so the agent learns what works
                if instr_type and instr_type != "skipped":
                    _instr_success = result.get("status") not in ("error", "simulated")
                    if capability_mgr.memory:
                        try:
                            capability_mgr.memory.store_experience(
                                context={"instruction": instr_type, "payload": payload or {}},
                                action=instr_type,
                                outcome={
                                    "success": _instr_success,
                                    "score":   0.0 if result.get("status") == "error" else 1.0,
                                    "status":  result.get("status", "unknown"),
                                },
                            )
                        except Exception as _me:
                            logger.debug("Memory store_experience (instruction) failed: %s", _me)
                    if capability_mgr.llm_engine:
                        try:
                            capability_mgr.llm_engine.record_outcome(
                                success=_instr_success,
                                reasoning=f"instruction:{instr_type} status:{result.get('status','unknown')}",
                            )
                        except Exception as _le:
                            logger.debug("LLM record_outcome (instruction) failed: %s", _le)
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

                # Buffer feedback for batch delivery via next heartbeat
                _pending_task_feedback.append({
                    "task_id": task_id,
                    "success": bool(result.get("success", False)),
                    "false_positive": False,
                    "message": str(result.get("message", ""))[:200],
                })
                if len(_pending_task_feedback) > 50:
                    _pending_task_feedback.pop(0)

                # Store experience so the agent learns from each outcome
                _task_success = bool(result.get("success", False))
                if capability_mgr.memory:
                    try:
                        capability_mgr.memory.store_experience(
                            context={"action": action, "params": params, "task_id": task_id},
                            action=action,
                            outcome={
                                "success": _task_success,
                                "score": 1.0 if _task_success else 0.0,
                                "message": str(result.get("message", ""))[:200],
                            },
                        )
                    except Exception as _me:
                        logger.debug("Memory store_experience failed: %s", _me)
                if capability_mgr.llm_engine:
                    try:
                        capability_mgr.llm_engine.record_outcome(
                            success=_task_success,
                            reasoning=f"task:{action} success:{_task_success}",
                        )
                    except Exception as _le:
                        logger.debug("LLM record_outcome (task) failed: %s", _le)

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
    except Exception as _net_err:
        logger.debug("poll_response_tasks: network error: %s", _net_err)


# ─────────────────────────────────────────────
# IoC Broadcast Polling
# ─────────────────────────────────────────────
def poll_threat_intel(cfg, capability_mgr):
    """
    Poll backend for IoC broadcasts from the correlation engine.
    Each broadcast contains IOCs (IPs, hashes, domains) that should trigger
    local defensive actions immediately.
    """
    agent_id = capability_mgr.agent_id
    base_url = cfg.get("api_base_url", "http://localhost:5000").rstrip("/")
    url      = f"{base_url}/api/agents/{agent_id}/threat-intel"
    headers  = capability_mgr._auth_headers()

    try:
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code != 200 or not resp.json():
            return
        broadcasts = resp.json()
        logger.warning("Received %d IoC broadcast(s) from correlation engine", len(broadcasts))

        ar_cap = capability_mgr.capability_instances.get("autonomous_response")

        for broadcast in broadcasts:
            iocs = broadcast.get("iocs", {})

            # Block malicious IPs via autonomous_response capability
            for ip in iocs.get("ips", []):
                if ar_cap and hasattr(ar_cap, "block_ip"):
                    try:
                        ar_cap.block_ip(ip)
                        logger.warning("IoC: Blocked IP %s", ip)
                    except Exception as e:
                        logger.error("IoC: Failed to block IP %s: %s", ip, e)

            # Quarantine known-bad file hashes (if FIM found matching files)
            for file_hash in iocs.get("hashes", []):
                logger.warning("IoC: Alerting on known-bad hash %s", file_hash)

            # Log domain IOCs for DNS-level blocking awareness
            for domain in iocs.get("domains", []):
                logger.warning("IoC: Malicious domain flagged %s", domain)

    except Exception as e:
        logger.debug("IoC broadcast poll error: %s", e)


# ─────────────────────────────────────────────
# Playbook Polling
# ─────────────────────────────────────────────
def poll_pending_playbooks(cfg, capability_mgr):
    """
    Poll the backend for playbooks assigned to this agent or triggered by
    agent-side events (on_agent_start, on_heartbeat, on_threat_detected).
    Each playbook step maps to an existing execute_single_instruction handler.
    """
    agent_id = capability_mgr.agent_id
    base_url = cfg.get("api_base_url", "http://localhost:5000").rstrip("/")
    url      = f"{base_url}/api/agents/{agent_id}/pending-playbooks"
    headers  = capability_mgr._auth_headers()

    try:
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code != 200 or not resp.json():
            return
        playbooks = resp.json()
        logger.info("Received %d pending playbook(s) to execute", len(playbooks))

        for pb in playbooks:
            pb_id   = pb.get("id")
            pb_name = pb.get("name", pb_id)
            steps   = pb.get("steps", [])
            status  = "executed"

            logger.info("Executing playbook '%s' (%d steps)", pb_name, len(steps))
            for step in steps:
                action      = step.get("action", "")
                step_params = step.get("params", {})
                if not action:
                    continue
                try:
                    result = capability_mgr.execute_single_instruction(action, payload=step_params)
                    if result.get("status") == "error":
                        status = "failed"
                        logger.error("Playbook '%s' step '%s' failed: %s", pb_name, action, result)
                    else:
                        logger.info("Playbook '%s' step '%s' → %s", pb_name, action, result.get("status"))
                except Exception as se:
                    status = "failed"
                    logger.error("Playbook '%s' step '%s' exception: %s", pb_name, action, se)

            # Acknowledge back to backend so it isn't re-delivered
            try:
                ack_url = f"{base_url}/api/agents/{agent_id}/playbook-ack"
                requests.post(
                    ack_url,
                    json={"playbook_id": pb_id, "status": status},
                    headers=headers,
                    timeout=5,
                )
            except Exception as ae:
                logger.warning("Playbook ack failed for '%s': %s", pb_name, ae)

    except Exception as e:
        logger.debug("Playbook poll error: %s", e)


# ─────────────────────────────────────────────
# Approval Decision Polling
# ─────────────────────────────────────────────

# In-memory store: {request_id: action_callback}
_pending_approvals: dict = {}


def register_approval_request(request_id: str, action_callback):
    """Called before an action is gated for human approval."""
    _pending_approvals[request_id] = action_callback


def poll_pending_approvals(cfg, capability_mgr):
    """
    Poll the backend for each outstanding approval request.
    When the backend returns status='approved', execute the stored callback.
    Clears approved/rejected requests from the local store.
    """
    if not _pending_approvals:
        return

    agent_id = capability_mgr.agent_id
    base_url = cfg.get("api_base_url", "http://localhost:5000").rstrip("/")
    headers  = capability_mgr._auth_headers()
    resolved = []

    for request_id, callback in list(_pending_approvals.items()):
        try:
            url  = f"{base_url}/api/agents/{agent_id}/approvals/{request_id}"
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code != 200:
                continue
            data   = resp.json()
            status = data.get("status", "pending")

            if status in ("approved", "auto_approved"):
                logger.info("Approval %s granted — executing deferred action", request_id)
                try:
                    extra_params = data.get("params", {})
                    callback(extra_params)
                except Exception as cb_err:
                    logger.error("Approved action for %s failed: %s", request_id, cb_err)
                resolved.append(request_id)

            elif status in ("rejected", "escalated", "skipped"):
                logger.warning("Approval %s %s — action cancelled", request_id, status)
                resolved.append(request_id)

        except Exception as e:
            logger.debug("Approval poll error for %s: %s", request_id, e)

    for rid in resolved:
        _pending_approvals.pop(rid, None)


# ─────────────────────────────────────────────
# Proactive Threat Hunting (scheduled, no instruction needed)
# ─────────────────────────────────────────────
def run_proactive_threat_hunt(cfg, capability_mgr):
    """
    Autonomously run a lightweight threat hunt every N heartbeats.
    Covers persistence, shadow AI, and process anomalies — the three
    most likely early-stage indicators that don't need a backend trigger.
    Results are posted to the backend and stored in agent memory.
    """
    logger.warning("🔍 Proactive threat hunt starting (autonomous schedule)…")
    results = {}
    scan_caps = ("persistence_detection", "shadow_ai", "process_monitor")

    for cap_id in scan_caps:
        cap = capability_mgr.capability_instances.get(cap_id)
        if not cap:
            continue
        try:
            results[cap_id] = cap.collect() if hasattr(cap, "collect") else cap.execute()
        except Exception as e:
            results[cap_id] = {"error": str(e)}

    # Post results to backend
    try:
        url = cfg.get("api_base_url", "").rstrip("/") + f"/api/agents/{capability_mgr.agent_id}/threat-hunt-results"
        requests.post(
            url,
            json={
                "results": results,
                "triggered_by": "proactive_schedule",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
            headers=capability_mgr._auth_headers(),
            timeout=15,
        )
    except Exception as e:
        logger.error("Proactive hunt report failed: %s", e)

    # Learn from this hunt — store experience so future ReAct decisions can reference it
    if capability_mgr.memory:
        try:
            any_findings = any(
                isinstance(v, dict) and v.get("status") not in ("error", None)
                for v in results.values()
            )
            capability_mgr.memory.store_experience(
                context={"action": "proactive_threat_hunt", "caps_run": list(results.keys())},
                action="proactive_threat_hunt",
                outcome={"success": True, "findings": any_findings, "score": 1.0},
            )
        except Exception:
            pass

    # Raise backend alerts for any confirmed suspicious findings
    ar_cap = capability_mgr.capability_instances.get("autonomous_response")
    if ar_cap and hasattr(ar_cap, "raise_alert"):
        backend_url = cfg.get("api_base_url", "http://localhost:5000")
        api_key     = cfg.get("agent_token", "")
        agent_id    = capability_mgr.agent_id
        for cap_id, result in results.items():
            if not isinstance(result, dict):
                continue
            # Treat any non-error result with actual data as a potential finding
            suspicious = result.get("threats_detected") or result.get("anomalies") or result.get("items")
            if suspicious:
                ar_cap.raise_alert(
                    alert_type=f"PROACTIVE_HUNT_{cap_id.upper()}",
                    description=f"Proactive threat hunt ({cap_id}) found suspicious activity: {str(suspicious)[:200]}",
                    severity="High",
                    backend_url=backend_url,
                    api_key=api_key,
                    agent_id=agent_id,
                )

    logger.warning("🔍 Proactive threat hunt complete — capabilities run: %s", list(results.keys()))


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

    # ── Start system tray icon (desktop endpoints only) ───────────────────
    try:
        from tray_icon import AgentTrayIcon
        tray = AgentTrayIcon(cfg, lambda: capability_mgr.agent_id)
        tray.start()
    except Exception as _tray_err:
        logger.debug("Tray icon not started: %s", _tray_err)

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

            # IoC broadcast check every 5 heartbeats
            if heartbeat_count % 5 == 0:
                poll_threat_intel(cfg, capability_mgr)

            # Playbook polling every 12 heartbeats (~1 min at 5s interval)
            if heartbeat_count % 12 == 0 and heartbeat_count > 0:
                poll_pending_playbooks(cfg, capability_mgr)

            # Approval decision polling every 6 heartbeats (~30s at 5s interval)
            if heartbeat_count % 6 == 0 and heartbeat_count > 0:
                poll_pending_approvals(cfg, capability_mgr)

            # Proactive autonomous threat hunt every 60 heartbeats (~5 min at 5s interval)
            if heartbeat_count % 60 == 0 and heartbeat_count > 0:
                run_proactive_threat_hunt(cfg, capability_mgr)

            # Refresh dynamic safety rules from backend every 60 heartbeats
            if heartbeat_count % 60 == 0 and capability_mgr.safety:
                try:
                    capability_mgr.safety.load_remote_rules(
                        api_base_url=cfg.get("api_base_url", ""),
                        api_key=cfg.get("agent_token", ""),
                        agent_id=capability_mgr.agent_id,
                    )
                except Exception as _sr:
                    logger.debug("Safety rule refresh failed: %s", _sr)

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
