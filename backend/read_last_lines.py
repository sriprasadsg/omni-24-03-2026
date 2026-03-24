
import os

def read_last_lines():
    log_file = "backend_no_auth_v2.log"
    if not os.path.exists(log_file):
        print(f"File {log_file} does not exist.")
        return

    with open(log_file, "rb") as f:
        # Seek to end
        f.seek(0, os.SEEK_END)
        file_size = f.tell()
        # Read last 4KB
        f.seek(max(0, file_size - 4096))
        content = f.read()

    # Decode and print
    print(content.decode("utf-8", errors="ignore"))

if __name__ == "__main__":
    read_last_lines()
