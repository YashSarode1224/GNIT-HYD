"""
Setup and generate GNITC district topology.

This script automates obtaining the exact SHIFT commit (995004c84c16df7c8ebfd3ddddf3e723a0938a99)
and building the isolated .venv-city environment. It then regenerates the topology deterministically.
"""
import os
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHIFT_REPO = "https://github.com/NLR-Distribution-Suite/shift.git"
SHIFT_COMMIT = "995004c84c16df7c8ebfd3ddddf3e723a0938a99"
VENV_DIR = ROOT / ".venv-city"
SOURCES_DIR = ROOT / "sources"
SHIFT_DIR = SOURCES_DIR / "shift"

def main():
    SOURCES_DIR.mkdir(exist_ok=True)
    
    # 1. Clone SHIFT
    if not SHIFT_DIR.exists():
        print(f"Cloning SHIFT repository from {SHIFT_REPO}...")
        subprocess.run(["git", "clone", SHIFT_REPO, str(SHIFT_DIR)], check=True)
    else:
        print("SHIFT repository already cloned.")
        
    # 2. Checkout pinned commit
    print(f"Checking out SHIFT commit {SHIFT_COMMIT}...")
    subprocess.run(["git", "-C", str(SHIFT_DIR), "fetch", "origin", SHIFT_COMMIT], check=True)
    subprocess.run(["git", "-C", str(SHIFT_DIR), "checkout", SHIFT_COMMIT], check=True)
    
    # 3. Create virtual environment
    if not VENV_DIR.exists():
        print(f"Creating virtual environment at {VENV_DIR}...")
        subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
    else:
        print("Virtual environment already exists.")
        
    # 4. Determine pip and python paths
    if os.name == "nt":
        pip = VENV_DIR / "Scripts" / "pip.exe"
        python = VENV_DIR / "Scripts" / "python.exe"
    else:
        pip = VENV_DIR / "bin" / "pip"
        python = VENV_DIR / "bin" / "python"
        
    # 5. Install SHIFT
    print("Installing SHIFT into virtual environment...")
    subprocess.run([str(pip), "install", "-e", str(SHIFT_DIR)], check=True)
    
    # 6. Generate topology
    print("Generating GNITC district topology...")
    script = ROOT / "backend" / "scripts" / "generate_district_topology.py"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "backend")
    subprocess.run([str(python), str(script)], check=True, cwd=ROOT, env=env)
    
    print("\nSuccess! The topology has been regenerated.")

if __name__ == "__main__":
    main()
