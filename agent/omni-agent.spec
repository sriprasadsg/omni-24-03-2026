# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for omni-agent.exe
Produces a single self-contained Windows executable with UAC elevation,
Windows version info, and all capability dependencies bundled.

Build with:
    cd agent && pyinstaller omni-agent.spec
or use:
    python build_windows.py
"""

import sys
import os

BASE = os.path.dirname(os.path.abspath(SPEC))

# ── Data files to bundle inside the exe ──────────────────────────────────────
datas = [
    # YARA malware detection rules
    (os.path.join(BASE, 'capabilities', 'yara_rules'), 'capabilities/yara_rules'),
    # Default config template (user edits this after install)
    (os.path.join(BASE, 'config.yaml'), '.'),
]

# ── Hidden imports PyInstaller cannot auto-detect ─────────────────────────────
hidden_imports = [
    # ── pywin32 / Windows Service framework ──────────────────────────────────
    'win32api',
    'win32con',
    'win32event',
    'win32evtlog',
    'win32evtlogutil',
    'win32process',
    'win32security',
    'win32service',
    'win32serviceutil',
    'win32transaction',
    'win32ts',
    'winerror',
    'pywintypes',
    'win32timezone',
    'servicemanager',
    'win32crypt',
    # ── psutil Windows internals ──────────────────────────────────────────────
    'psutil._pswindows',
    'psutil._psutil_windows',
    # ── cryptography ─────────────────────────────────────────────────────────
    'cryptography.hazmat.backends.openssl',
    'cryptography.hazmat.primitives.kdf.pbkdf2',
    'cryptography.fernet',
    # ── requests / urllib3 ───────────────────────────────────────────────────
    'requests.packages.urllib3',
    'requests.packages.urllib3.util.retry',
    'urllib3',
    'charset_normalizer',
    'certifi',
    'idna',
    # ── httpx ────────────────────────────────────────────────────────────────
    'httpx._transports.default',
    'anyio',
    'anyio._backends._asyncio',
    'sniffio',
    # ── websockets / socket.io ────────────────────────────────────────────────
    'websockets',
    'websockets.legacy.client',
    'websocket',
    'socketio',
    'socketio.async_client',
    'engineio',
    'engineio.async_client',
    'engineio.async_drivers.aiohttp',
    'engineio.async_drivers.threading',
    # ── watchdog (FIM) ────────────────────────────────────────────────────────
    'watchdog.observers',
    'watchdog.observers.winapi',
    'watchdog.observers.read_directory_changes',
    'watchdog.events',
    # ── scapy (network discovery) ─────────────────────────────────────────────
    'scapy.all',
    'scapy.layers.inet',
    'scapy.layers.l2',
    'scapy.layers.dns',
    'scapy.sendrecv',
    # ── PIL / mss (remote access / screenshots) ───────────────────────────────
    'PIL._imaging',
    'PIL.Image',
    'PIL.ImageGrab',
    'mss',
    'mss.windows',
    # ── yaml / sqlite ────────────────────────────────────────────────────────
    'yaml',
    '_yaml',
    'sqlite3',
    # ── yara-python (malware scanning) ───────────────────────────────────────
    'yara',
    # ── agent internal modules ────────────────────────────────────────────────
    'capabilities',
    'capabilities.metrics',
    'capabilities.process_monitor',
    'capabilities.fim',
    'capabilities.real_fim',
    'capabilities.network_discovery',
    'capabilities.log_shipper',
    'capabilities.vulnerability_scanner',
    'capabilities.real_scan',
    'capabilities.runtime_security',
    'capabilities.compliance',
    'capabilities.persistence_detection',
    'capabilities.shadow_ai',
    'capabilities.software_management',
    'capabilities.predictive_health',
    'capabilities.autonomous_response',
    'capabilities.sbom',
    'capabilities.edr_realtime',
    'capabilities.yara_scanner',
    'capabilities.ueba',
    'capabilities.pii_scanner',
    'capabilities.patch_installer',
    'capabilities.system_patching',
    'capabilities.vss_manager',
    'capabilities.deception_monitor',
    'capabilities.web_monitor',
    'capabilities.remote_access',
    'capabilities.backup_verifier',
    'capabilities.vendor_risk',
    'capabilities.k8s_monitor',
    'capabilities.cloud_metadata',
    'agentic_core.llm_engine',
    'agentic_core.reasoning',
    'agentic_core.safety',
    'agentic_core.tool_registry',
    'agentic_core.security_tools',
    'autonomous_actions.remediation',
    'autonomous_actions.rollback',
    'goal_system.manager',
    'knowledge_base.memory',
    'swarm.coordinator',
    'security',
    'platform_utils',
    'secure_logs',
    'service_manager',
    'fim',
]

a = Analysis(
    [os.path.join(BASE, 'agent.py')],
    pathex=[BASE],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'pandas', 'scipy',
        'IPython', 'jupyter', 'notebook',
        'pytest', 'unittest', 'doctest',
        'distutils', 'setuptools', 'wheel',
        # Linux/macOS only
        'bcc', '_posixsubprocess', 'curses',
        'readline', 'termios', 'grp', 'pty',
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='omni-agent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[
        # Do NOT compress pywin32 service DLLs — breaks SCM dispatcher
        'win32api.pyd',
        'win32service.pyd',
        'win32serviceutil.pyd',
        'win32event.pyd',
        'servicemanager.pyd',
        'pywintypes*.dll',
    ],
    runtime_tmpdir=None,
    console=True,      # Must be True for Windows Service stderr/stdout logging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=os.path.join(BASE, 'agent_version_info.txt'),
    manifest=os.path.join(BASE, 'agent.manifest'),
    uac_admin=True,
)
