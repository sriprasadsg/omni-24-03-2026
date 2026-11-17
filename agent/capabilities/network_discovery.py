"""
Network Discovery Capability
Scans the local network to identify active devices using ARP and Ping.
"""
from .base import BaseCapability
import socket
import threading
from typing import Dict, Any, List
import logging
import platform
import subprocess
import re

SCAPY_AVAILABLE = False
ARP = Ether = srp = ICMP = IP = sr1 = None

def _import_scapy():
    global SCAPY_AVAILABLE, ARP, Ether, srp, ICMP, IP, sr1
    if SCAPY_AVAILABLE:
        return True
    import sys, os, io, logging as _logging, warnings as _warnings

    # Suppress Scapy startup noise (WinPcap deprecated, pcap service not running, etc.)
    # — both its logging calls and any direct stderr writes.
    for name in ("scapy", "scapy.runtime", "scapy.loading", "scapy.interactive"):
        _logging.getLogger(name).setLevel(_logging.CRITICAL)

    _old_stderr = sys.stderr
    sys.stderr = io.StringIO()
    try:
        with _warnings.catch_warnings():
            _warnings.simplefilter("ignore")
            from scapy.all import ARP as _ARP, Ether as _Ether, srp as _srp, ICMP as _ICMP, IP as _IP, sr1 as _sr1
        ARP, Ether, srp, ICMP, IP, sr1 = _ARP, _Ether, _srp, _ICMP, _IP, _sr1
        SCAPY_AVAILABLE = True
        return True
    except (ImportError, Exception, BaseException) as e:
        _logging.getLogger(__name__).warning(
            "Scapy import failed (%s). Network discovery will use ping-sweep fallback.", e
        )
        SCAPY_AVAILABLE = False
        return False
    finally:
        sys.stderr = _old_stderr

# Attempt import at module load; failures are handled gracefully inside the function
_import_scapy()

# How often the route to the platform server is traced again (one trace takes up to ~30 s).
ROUTE_EVERY_SECONDS = 15 * 60
MAX_HOPS = 20
# Ports checked on each scanned host; the open ones are reported with the device.
PROBE_PORTS = (22, 53, 80, 135, 139, 443, 445, 631, 3389, 8080, 8443)


def _ip(text):
    import ipaddress
    try:
        return str(ipaddress.ip_address(str(text).strip("[]()")))
    except ValueError:
        return None


def _average(times):
    return round(sum(times) / len(times), 1) if times else None


def parse_tracepath(text: str) -> List[Dict[str, Any]]:
    """`tracepath -n`: " 1:  192.168.0.1   0.512ms", " 2:  no reply"; a hop may print twice."""
    hops: Dict[int, Dict[str, Any]] = {}
    for line in text.splitlines():
        t = line.split()
        if not t or not t[0].rstrip(":?").isdigit() or (len(t) > 1 and t[1] == "[LOCALHOST]"):
            continue
        n = int(t[0].rstrip(":?"))
        ip = _ip(t[1]) if len(t) > 1 else None
        rtt = next((float(x[:-2]) for x in t if x.endswith("ms") and x[:-2].replace(".", "", 1).isdigit()), None)
        if n not in hops or (hops[n]["ip"] is None and ip):
            hops[n] = {"hop": n, "ip": ip, "rtt_ms": rtt}
    return [hops[n] for n in sorted(hops)]


def parse_traceroute(text: str) -> List[Dict[str, Any]]:
    """`traceroute -n` (unix) or `tracert -d` (Windows): a hop number, probe times ("5 ms", "<1 ms",
    "*"), then the address."""
    hops = []
    for line in text.splitlines():
        t = line.split()
        if not t or not t[0].isdigit():
            continue
        times = []
        for x in t[1:]:
            v = x.lstrip("<").removesuffix("ms")
            if v.replace(".", "", 1).isdigit() and _ip(x) is None:
                times.append(float(v))
        ip = next((_ip(x) for x in reversed(t[1:]) if _ip(x)), None)
        if times or ip or "*" in t:
            hops.append({"hop": int(t[0]), "ip": ip, "rtt_ms": _average(times)})
    return hops


def device_type(open_ports: List[int]) -> str:
    """A device type guessed from its open ports."""
    has = set(open_ports).__contains__
    if has(3389):
        return "Windows (RDP)"
    if has(445):
        return "Windows (SMB)"
    if has(22):
        return "Linux/SSH"
    if has(631):
        return "Printer"
    if has(53) and (has(80) or has(443)):
        return "Router/Firewall"
    if has(80) or has(443) or has(8080) or has(8443):
        return "Web Server"
    return "Unknown"

class NetworkDiscoveryCapability(BaseCapability):
    
    @property
    def capability_id(self) -> str:
        return "network_discovery"
    
    @property
    def capability_name(self) -> str:
        return "Network Discovery"
    
    def collect(self) -> Dict[str, Any]:
        """Return last scan results; auto-trigger a background scan if data is older than 30 min."""
        import time as _time
        last_scan = getattr(self, "_last_scan_results", [])
        last_ts = getattr(self, "_last_scan_ts", 0)

        # Trigger a fresh scan in a background thread if stale (>30 min) or first run
        if _time.time() - last_ts > 1800:
            import threading as _threading
            def _bg_scan():
                try:
                    results = self.start_scan()
                    self._last_scan_results = results
                    self._last_scan_ts = _time.time()
                except Exception as _e:
                    logging.warning("Background network scan failed: %s", _e)
            _threading.Thread(target=_bg_scan, daemon=True).start()

        out = {
            "status": "ready",
            "scapy_available": SCAPY_AVAILABLE,
            "last_scan": last_scan,
            "device_count": len(last_scan),
            "last_scan_age_seconds": int(_time.time() - last_ts) if last_ts else None,
        }
        route = self._route_to_server()
        if route:
            out["route"] = route
        return out

    def _route_to_server(self):
        """The last route traced to the platform server; starts a new trace in the background when
        one is due, so collection never waits for it."""
        import time as _time
        if _time.time() - getattr(self, "_route_started", 0) >= ROUTE_EVERY_SECONDS and not getattr(self, "_route_running", False):
            target = self._server_host()
            if target:
                self._route_started, self._route_running = _time.time(), True

                def _bg_trace():
                    try:
                        traced = self.trace(target)
                        if traced:
                            self._last_route = traced
                    except Exception as _e:
                        logging.debug("Route trace failed: %s", _e)
                    finally:
                        self._route_running = False
                threading.Thread(target=_bg_trace, daemon=True).start()
        return getattr(self, "_last_route", None)

    def _server_host(self):
        """The platform server's host from the agent config; None for an agent on the server itself."""
        from urllib.parse import urlparse
        host = urlparse(str((self.config or {}).get("api_base_url") or "")).hostname
        if not host or host == "localhost" or (_ip(host) or "").startswith(("127.", "::1")):
            return None
        return host

    def trace(self, target: str):
        import shutil
        from datetime import datetime, timezone
        if platform.system().lower() == "windows":
            cmd, parse = ["tracert", "-d", "-h", str(MAX_HOPS), "-w", "500", target], parse_traceroute
        elif shutil.which("tracepath"):
            cmd, parse = ["tracepath", "-n", "-m", str(MAX_HOPS), target], parse_tracepath
        elif shutil.which("traceroute"):
            cmd, parse = ["traceroute", "-n", "-q", "1", "-w", "1", "-m", str(MAX_HOPS), target], parse_traceroute
        else:
            return None
        text = subprocess.run(cmd, capture_output=True, text=True, timeout=90).stdout
        hops = parse(text)
        if not hops:
            return None
        try:
            target_ip = socket.gethostbyname(target)
        except OSError:
            target_ip = None
        return {"target": target, "traced_at": datetime.now(timezone.utc).isoformat(),
                "reached": bool(target_ip) and hops[-1]["ip"] == target_ip, "hops": hops}

    def start_scan(self, subnet: str = None) -> List[Dict[str, Any]]:
        """
        Perform a network scan.
        If subnet is not provided, it attempts to guess the local subnet.
        """
        _import_scapy() # Attempt import before scanning
        
        if not subnet:
            subnet = self._get_local_subnet()
            
        logging.info(f"Starting network scan on {subnet}...")
        results = []

        if SCAPY_AVAILABLE:
            try:
                results = self._scan_arp(subnet)
                if not results:
                    logging.debug("ARP scan returned no results; falling back to ping sweep.")
                    results = self._scan_ping_sweep(subnet)
            except Exception as e:
                logging.debug("ARP scan failed (%s); falling back to ping sweep.", e)
                results = self._scan_ping_sweep(subnet)
        else:
            logging.warning("Scapy not available. Falling back to multi-threaded ping sweep.")
            results = self._scan_ping_sweep(subnet)

        self._last_scan_results = results
        return results

    def _get_local_subnet(self) -> str:
        """Get local IP and assume /24 subnet for simplicity"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            # Assume /24
            base_ip = ".".join(local_ip.split(".")[:3]) + ".0/24"
            return base_ip
        except Exception:
            return "192.168.1.0/24"

    def _scan_arp(self, subnet: str) -> List[Dict[str, Any]]:
        """
        Use Scapy to send ARP requests.
        Returns list of discovered devices.
        """
        devices = []
        try:
            # Explicitly resolve the outbound interface so Scapy doesn't pick a
            # loopback or virtual adapter (e.g. 'Microsoft KM-TEST Loopback Adapter').
            try:
                from scapy.config import conf as _scapy_conf
                iface, _, _ = _scapy_conf.route.route("8.8.8.8")
            except Exception:
                iface = None

            # Create ARP request packet
            arp_req = ARP(pdst=subnet)
            ether = Ether(dst="ff:ff:ff:ff:ff:ff")
            packet = ether/arp_req

            # Send and receive — pass iface only when we resolved one
            srp_kwargs = {"timeout": 2, "verbose": 0}
            if iface:
                srp_kwargs["iface"] = iface
            result = srp(packet, **srp_kwargs)[0]

            for sent, received in result:
                devices.append({
                    "ip": received.psrc,
                    "mac": received.hwsrc,
                    "hostname": self._resolve_hostname(received.psrc),
                    "status": "Up",
                    **self._probe(received.psrc),
                    "last_seen": self._get_timestamp()
                })
        except Exception as e:
            logging.debug("ARP scan failed (%s); caller will fall back to ping sweep.", e)

        return devices

    def _scan_ping_sweep(self, subnet: str) -> List[Dict[str, Any]]:
        """
        Multi-threaded ping sweep for non-scapy environments or as fallback.
        """
        devices = []
        threads = []
        
        # Extract base IP (e.g., 192.168.1.)
        match = re.match(r"(\d+\.\d+\.\d+)\.", subnet)
        if not match:
            return []
        
        base_ip = match.group(1)
        
        def ping_ip(ip):
            if self._ping(ip):
                devices.append({
                    "ip": ip,
                    "hostname": self._resolve_hostname(ip),
                    "mac": "Unknown",
                    "status": "Up",
                    **self._probe(ip),
                    "last_seen": self._get_timestamp()
                })

        # Scan 1 to 254
        for i in range(1, 255):
            ip = f"{base_ip}.{i}"
            t = threading.Thread(target=ping_ip, args=(ip,))
            t.start()
            threads.append(t)
            
            # Limit concurrent threads to avoid system strain
            if len(threads) >= 50:
                for thread in threads:
                    thread.join()
                threads = []
        
        for thread in threads:
            thread.join()
            
        return devices

    def _ping(self, ip: str) -> bool:
        """Ping an IP address and return True if it responds"""
        param = "-n" if platform.system().lower() == "windows" else "-c"
        command = ["ping", param, "1", "-w", "500", ip]
        try:
            return subprocess.call(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
        except:
            return False

    def _resolve_hostname(self, ip: str) -> str:
        try:
            return socket.gethostbyaddr(ip)[0]
        except socket.herror:
            return ip

    def _probe(self, ip: str) -> Dict[str, Any]:
        """Open ports of a scanned host and the device type they suggest."""
        open_ports = [p for p in PROBE_PORTS if self._check_port(ip, p)]
        return {"open_ports": open_ports, "device_type": device_type(open_ports)}

    def _guess_device_type(self, ip: str) -> str:
        """
        Try to guess device type by checking a few ports.
        Very basic.
        """
        common_ports = {
            80: "Router/Web",
            443: "Router/Web",
            22: "Linux/Switch",
            3389: "Windows",
            631: "Printer"
        }
        
        for port, type_guess in common_ports.items():
            if self._check_port(ip, port):
                return type_guess
        
        return "Unknown"

    def _check_port(self, ip: str, port: int) -> bool:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        try:
            s.connect((ip, port))
            s.close()
            return True
        except:
            return False
            
    def _get_timestamp(self) -> str:
        from datetime import datetime
        return datetime.now().isoformat()
