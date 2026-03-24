"""
eBPF Tracing Capability
Provides deep kernel-level visibility and tracing (Linux only).
Leverages bcc (BPF Compiler Collection) to intercept syscalls.
"""
from .base import BaseCapability
import platform
import threading
import time
from typing import Dict, Any, List

try:
    from bcc import BPF
    BCC_AVAILABLE = True
except ImportError:
    BCC_AVAILABLE = False

# Simple BPF program to trace process clones (forks/execs)
bpf_program = """
#include <uapi/linux/ptrace.h>
#include <linux/sched.h>

struct data_t {
    u32 pid;
    u32 tgid;
    char comm[TASK_COMM_LEN];
};

BPF_PERF_OUTPUT(clones);

int trace_sys_clone(struct pt_regs *ctx) {
    struct data_t data = {};
    data.pid = bpf_get_current_pid_tgid();
    data.tgid = bpf_get_current_pid_tgid() >> 32;
    bpf_get_current_comm(&data.comm, sizeof(data.comm));
    clones.perf_submit(ctx, &data, sizeof(data));
    return 0;
}
"""

class eBPFTracingCapability(BaseCapability):
    
    def __init__(self, config=None):
        super().__init__(config)
        self.os_type = platform.system().lower()
        self.bpf = None
        self.events = []
        self._thread = None
        self._running = False
        
        if self.os_type == 'linux' and BCC_AVAILABLE:
            self._init_bpf()

    @property
    def capability_id(self) -> str:
        return "ebpf_tracing"
    
    @property
    def capability_name(self) -> str:
        return "eBPF Tracing"
        
    def _init_bpf(self):
        try:
            self.bpf = BPF(text=bpf_program)
            # Find the syscall prefix for the current kernel architecture
            clone_fnname = self.bpf.get_syscall_prefix().decode() + 'clone'
            self.bpf.attach_kprobe(event=clone_fnname, fn_name="trace_sys_clone")
            
            self.bpf["clones"].open_perf_buffer(self._print_event)
            
            self._running = True
            self._thread = threading.Thread(target=self._poll_perf, daemon=True)
            self._thread.start()
        except Exception as e:
            print(f"[eBPF] Failed to initialize BPF program: {e}")
            self.bpf = None

    def _print_event(self, cpu, data, size):
        try:
            event = self.bpf["clones"].event(data)
            self.events.append({
                "pid": event.pid,
                "tgid": event.tgid,
                "comm": event.comm.decode('utf-8', 'replace'),
                "timestamp": time.time()
            })
            # Keep array bounded
            if len(self.events) > 100:
                self.events.pop(0)
        except Exception:
            pass

    def _poll_perf(self):
        while self._running:
            try:
                self.bpf.perf_buffer_poll()
            except Exception:
                pass
            time.sleep(0.1)

    def collect(self) -> Dict[str, Any]:
        if self.os_type != "linux":
            return {
                "status": "Not Supported",
                "reason": f"eBPF is only available on Linux (current: {self.os_type})",
                "metrics": {}
            }
            
        if not BCC_AVAILABLE:
             return {
                "status": "Inactive",
                "reason": "python3-bpfcc / bcc library is not installed or requires root",
                "metrics": {}
            }
            
        if not self.bpf:
            return {
                "status": "Failed",
                "reason": "Failed to compile/load BPF program",
                "metrics": {}
            }

        # Return captured events
        captured = list(self.events)
        self.events.clear()
        
        return {
            "status": "Active",
            "reason": "Tracking kernel events via bcc",
            "metrics": {
                "clones_traced": len(captured),
                "recent_process_creations": captured
            }
        }

