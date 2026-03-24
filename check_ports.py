
import socket

def check_port(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        result = s.connect_ex(('127.0.0.1', port))
        return result == 0

ports = [5000, 3000]
all_open = True
for port in ports:
    is_open = check_port(port)
    print(f"Port {port}: {'OPEN' if is_open else 'CLOSED'}")
    if not is_open: all_open = False

if all_open:
    print("ALL SERVICES UP")
else:
    print("SOME SERVICES DOWN")
