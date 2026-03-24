import sys
import os
import logging

logging.basicConfig(level=logging.INFO)

print("Attempting to import Scapy...")
try:
    from scapy.all import ARP, Ether, srp
    print("Scapy imported successfully.")
except ImportError as e:
    print(f"Failed to import Scapy: {e}")
    sys.exit(1)
except Exception as e:
    print(f"Error during import: {e}")
    sys.exit(1)

print("Attempting simple ARP scan on localhost...")
try:
    # Try a single IP first to test interface binding
    # We'll try to find the gateway or just broadcast
    target_ip = "192.168.90.1/32" # Guessing gateway or just a safe IP
    
    arp = ARP(pdst=target_ip)
    ether = Ether(dst="ff:ff:ff:ff:ff:ff")
    packet = ether/arp
    
    print("Sending packet...")
    result = srp(packet, timeout=2, verbose=1)[0]
    
    print(f"Scan finished. Got {len(result)} responses.")
    for sent, received in result:
        print(f"Device: {received.psrc} | MAC: {received.hwsrc}")

except Exception as e:
    print(f"Scapy Execution Failed: {e}")
    import traceback
    traceback.print_exc()
