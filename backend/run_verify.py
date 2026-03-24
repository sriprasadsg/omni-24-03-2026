
import subprocess
import os

print("Starting verification wrapper...")
try:
    with open("verify_out_py.txt", "w", encoding="utf-8") as f:
        # unexpected arguments or environmental issues might cause failure, so we capture everything
        subprocess.run(["python", "verify_network_map.py"], stdout=f, stderr=f, text=True, encoding="utf-8")
    print("Verification wrapper finished.")
except Exception as e:
    print(f"Wrapper failed: {e}")
