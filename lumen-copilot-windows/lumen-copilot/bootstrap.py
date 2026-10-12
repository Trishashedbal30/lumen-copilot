"""Portable installer; invoked by setup.bat/setup.sh. Never requires activation."""
import os
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent

def main():
    os.chdir(ROOT)
    if not (3, 11) <= sys.version_info[:2] < (3, 14):
        print("Use 64-bit Python 3.12 (supported: 3.11-3.13). Python 3.14 is not validated for this bundle.")
        return 1
    env = ROOT / ".venv"
    python = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    try:
        if not python.exists():
            print("Creating a local virtual environment...")
            venv.EnvBuilder(with_pip=True).create(env)
        subprocess.check_call([str(python), "-c", "import sys,struct; assert (3,11)<=sys.version_info[:2]<(3,14) and struct.calcsize('P')==8, 'Existing .venv must use 64-bit Python 3.11-3.13. Rename .venv and rerun setup.bat.'"])
        subprocess.check_call([str(python), "-m", "pip", "install", "--upgrade", "pip"])
        subprocess.check_call([str(python), "-m", "pip", "install", "-r", "requirements.txt"])
        subprocess.check_call([str(python), "doctor.py"])
        return subprocess.call([str(python), "run.py", *sys.argv[1:]])
    except (OSError, subprocess.CalledProcessError) as exc:
        print("Setup stopped:", exc)
        print("Check your Internet connection and Python version. Then run setup.bat again.")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
