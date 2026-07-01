import subprocess
import sys
import os

FILES_TO_DEPLOY = [
    "boot.py",
    "main.py",
    "config.py",
    "crc8.py",
    "lad_controller.py",
    "web_server.py",
    "mqtt_client.py"
]

def deploy():
    print("[Deploy] Starting file synchronization to W5500-EVB-Pico board using uv...")

    for file in FILES_TO_DEPLOY:
        local_path = os.path.join("src", file)
        if not os.path.exists(local_path):
            print(f"[Deploy] Error: Local file {local_path} not found. Aborting.")
            sys.exit(1)

        print(f"[Deploy] Transferring {local_path} -> MicroPython filesystem as :{file}...")
        try:
            # Leverage uv to run mpremote in an isolated virtual environment on the fly
            subprocess.run(
                ["uv", "run", "--with", "mpremote", "mpremote", "fs", "cp", local_path, f":{file}"],
                check=True
            )
        except subprocess.SubprocessError as e:
            print(f"[Deploy] Error transferring {file}: {e}")
            print("[Deploy] Troubleshooting Checklist:")
            print("  1. Is the Pico board plugged in via USB?")
            print("  2. Is another program (like Thonny, screen, or minicom) occupying the serial port?")
            sys.exit(1)

    print("[Deploy] All files successfully transferred.")
    print("[Deploy] Issuing hardware board reset command...")
    try:
        subprocess.run(["uv", "run", "--with", "mpremote", "mpremote", "reset"], check=True)
        print("[Deploy] Board reset completed. Application execution running.")
    except subprocess.SubprocessError as e:
        print(f"[Deploy] Warning: Reset command failed ({e}). Please manually power-cycle the board.")

if __name__ == "__main__":
    deploy()
