"""One command to run Lumen Copilot:  python run.py   (then open http://localhost:8000)"""
import os
import subprocess
import socket
import sys
import threading
import time
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)


def load_env():
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8-sig"):
            line = line.split("#", 1)[0].strip()
            if "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("\"\'"))


def ensure_data():
    if not os.path.exists(os.path.join(ROOT, "data", "lumen.duckdb")):
        print("Generating synthetic tenant data (about 10 seconds)...")
        subprocess.check_call([sys.executable, "-m", "backend.data.generate_data"])
    if not os.path.exists(os.path.join(ROOT, "data", "app_metadata.json")):
        subprocess.check_call([sys.executable, "-m", "backend.data.generate_metadata"])


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    load_env()
    ensure_data()
    port = int(os.environ.get("PORT", "8000"))
    if not 1 <= port <= 65535:
        raise SystemExit("PORT must be between 1 and 65535.")
    try:
        with socket.socket() as probe:
            probe.bind((os.environ.get("HOST", "127.0.0.1"), port))
    except OSError:
        raise SystemExit(f"Port {port} is in use. Close the other server or set PORT=8001 in .env.")
    url = f"http://localhost:{port}"
    if "--no-browser" not in sys.argv:
        threading.Thread(target=lambda: (time.sleep(2.5), webbrowser.open(url)), daemon=True).start()
    print(f"\n  Lumen Copilot running at {url}\n  Evaluation: {url}/eval   App graph: {url}/graph\n")
    import uvicorn
    uvicorn.run("backend.main:app", host=os.environ.get("HOST", "127.0.0.1"), port=port, log_level="warning")
