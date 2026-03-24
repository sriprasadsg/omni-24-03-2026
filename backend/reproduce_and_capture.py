
import subprocess
import time
import requests
import sys
import os
import signal

def reproduce():
    # Start server
    print("Starting server...")
    env = os.environ.copy()
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "5002"],
        cwd=r"d:\Downloads\enterprise-omni-agent-ai-platform\backend",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env
    )

    try:
        # Wait for startup
        time.sleep(10)
        
        print("Sending request...")
        try:
            response = requests.post("http://localhost:5002/api/jobs", json={
                "type": "test_job",
                "details": {"foo": "bar"}
            })
            print(f"Response: {response.status_code}")
            print(f"Content: {response.text}")
        except Exception as e:
            print(f"Request failed: {e}")

        # Wait a bit for logs to flush
        time.sleep(2)
        
    finally:
        print("Stopping server...")
        process.terminate()
        try:
            outs, errs = process.communicate(timeout=5)
            with open("captured_output.txt", "w", encoding="utf-8") as f:
                f.write(outs)
            print("Output written to captured_output.txt (Success path)")
        except subprocess.TimeoutExpired:
            process.kill()
            outs, errs = process.communicate()
            with open("captured_output.txt", "w", encoding="utf-8") as f:
                f.write(outs)
            print("Output written to captured_output.txt (Timeout path)")

if __name__ == "__main__":
    reproduce()
