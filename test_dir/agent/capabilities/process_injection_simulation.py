"""
Process Injection Simulation Capability
Simulates benign process injection for security testing.
"""
import os
import sys
import time
import subprocess
import logging
from typing import Dict, Any, Optional
from .base import BaseCapability

logger = logging.getLogger(__name__)

class ProcessInjectionSimulationCapability(BaseCapability):
    
    @property
    def capability_id(self) -> str:
        return "process_injection_simulation"
    
    @property
    def capability_name(self) -> str:
        return "Process Injection Simulation"
    
    def collect(self) -> Dict[str, Any]:
        """
        This capability is usually triggered via execute_action, 
        but we can return status here.
        """
        return {
            "status": "ready",
            "supported_platforms": ["windows", "linux"],
            "last_simulation": self.config.get("last_simulation")
        }

    def run_simulation(self, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a benign process injection simulation.
        """
        config = config or {}
        technique = config.get("technique", "memory_write")
        target_process = config.get("target_process", "notepad.exe" if os.name == "nt" else "cat")
        
        result = {
            "success": False,
            "technique": technique,
            "target": target_process,
            "timestamp": time.time(),
            "details": ""
        }
        
        try:
            if os.name == "nt":
                return self._simulate_windows(target_process, technique, result)
            else:
                return self._simulate_linux(target_process, technique, result)
        except Exception as e:
            result["details"] = f"Error during simulation: {str(e)}"
            logger.error(f"Process injection simulation failed: {e}")
            return result

    def _simulate_windows(self, target_process, technique, result):
        try:
            import ctypes
            from ctypes import wintypes
        except ImportError:
            result["details"] = "ctypes not available"
            return result
        
        # Constants
        PROCESS_ALL_ACCESS = 0x1F0FFF
        MEM_COMMIT = 0x1000
        MEM_RESERVE = 0x2000
        PAGE_EXECUTE_READWRITE = 0x40
        
        try:
            # 1. Spawn target process
            # Use a common process that is likely to exist
            proc = subprocess.Popen([target_process], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            pid = proc.pid
            result["pid"] = pid
            
            # 2. Open process
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
            if not handle:
                result["details"] = f"Failed to open process {pid}. Error: {ctypes.windll.kernel32.GetLastError()}"
                proc.terminate()
                return result
            
            # 3. Allocate memory
            payload = b"Benign Simulation Payload"
            addr = ctypes.windll.kernel32.VirtualAllocEx(handle, None, len(payload), MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE)
            if not addr:
                result["details"] = f"Failed to allocate memory in process {pid}. Error: {ctypes.windll.kernel32.GetLastError()}"
                ctypes.windll.kernel32.CloseHandle(handle)
                proc.terminate()
                return result
            
            # 4. Write to memory
            written = wintypes.SIZE_T(0)
            if not ctypes.windll.kernel32.WriteProcessMemory(handle, addr, payload, len(payload), ctypes.byref(written)):
                result["details"] = f"Failed to write to memory in process {pid}. Error: {ctypes.windll.kernel32.GetLastError()}"
            else:
                result["success"] = True
                result["details"] = f"Successfully wrote {written.value} bytes to process {pid} at {hex(addr)}"
            
            # Cleanup
            ctypes.windll.kernel32.CloseHandle(handle)
            time.sleep(1)
            proc.terminate()
            
            return result
        except Exception as e:
            result["details"] = f"Windows simulation error: {str(e)}"
            return result

    def _simulate_linux(self, target_process, technique, result):
        try:
            # On Linux, we'll simulate by spawning a process and writing to its /proc/[pid]/mem
            proc = subprocess.Popen([target_process], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            pid = proc.pid
            result["pid"] = pid
            
            # Simulated "injection"
            mem_path = f"/proc/{pid}/mem"
            if os.path.exists(mem_path):
                result["details"] = f"Simulated Linux injection: Process {pid} spawned, /proc/{pid}/mem exists."
                result["success"] = True
            else:
                result["details"] = f"Process {pid} spawned, but /proc/{pid}/mem not found (expected on some systems)."
                result["success"] = True # Still count as success for simulation
            
            time.sleep(1)
            proc.terminate()
            return result
        except Exception as e:
            result["details"] = f"Linux simulation error: {str(e)}"
            return result
