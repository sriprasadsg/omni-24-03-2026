import socket

def get_ip_current():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # doesn't even have to be reachable
        s.connect(('8.8.8.8', 1)) 
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def get_ip_hostname():
    try:
        return socket.gethostbyname(socket.gethostname())
    except:
        return "Error"

def get_all_ips():
    try:
        hostname = socket.gethostname()
        return socket.gethostbyname_ex(hostname)[2]
    except:
        return []

print(f"Current Logic (8.8.8.8): {get_ip_current()}")
print(f"Hostname Logic: {get_ip_hostname()}")
print(f"All IPs: {get_all_ips()}")
