#!/usr/bin/env python3
import argparse
import os
import platform
import shutil
import subprocess
import sys
import venv
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.absolute()
VENV_DIR = SCRIPT_DIR / ".venv"
DATA_DIR = SCRIPT_DIR / "data"
ENV_FILE = SCRIPT_DIR / ".env"
REQUIREMENTS_FILE = SCRIPT_DIR / "requirements.txt"


def print_status(message: str, status: str = "INFO"):
    colors = {"INFO": "\033[94m", "OK": "\033[92m", "WARN": "\033[93m", "ERROR": "\033[91m", "RESET": "\033[0m"}
    print(f"{colors.get(status, colors['INFO'])}[{status}]{colors['RESET']} {message}")


def load_env():
    if not ENV_FILE.exists():
        return {}
    
    env = {}
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    return env


def detect_linux_distro() -> str:
    try:
        with open("/etc/os-release") as f:
            content = f.read().lower()
            if "debian" in content or "ubuntu" in content:
                return "debian"
            elif "fedora" in content or "rhel" in content or "centos" in content:
                return "fedora"
            elif "arch" in content:
                return "arch"
    except FileNotFoundError:
        pass
    return "debian"


def check_system_dependencies() -> list[str]:
    missing = []
    system = platform.system().lower()
    if system == "linux":
        if not shutil.which("qemu-system-x86_64"):
            missing.append("qemu-system-x86_64")
        if not shutil.which("qemu-img"):
            missing.append("qemu-img")
    elif system == "darwin":
        if not shutil.which("qemu-system-x86_64"):
            missing.append("qemu (brew install qemu)")
    return missing


def install_system_hint():
    system = platform.system().lower()
    print_status("Missing system dependencies. Please install:", "WARN")
    if system == "linux":
        distro = detect_linux_distro()
        pkgs = {
            "debian": "sudo apt install python3-dev portaudio19-dev qemu-system-x86 qemu-utils",
            "fedora": "sudo dnf install python3-devel portaudio-devel qemu-system-x86 qemu-img",
            "arch": "sudo pacman -S python portaudio qemu-full",
        }
        print(f"  {pkgs.get(distro, pkgs['debian'])}")
    elif system == "darwin":
        print("  brew install portaudio qemu")
    else:
        print("  Please install QEMU from https://www.qemu.org/download/#windows")


def get_venv_python() -> Path:
    if platform.system() == "Windows":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def get_venv_pip() -> Path:
    if platform.system() == "Windows":
        return VENV_DIR / "Scripts" / "pip.exe"
    return VENV_DIR / "bin" / "pip"


def create_venv() -> bool:
    if VENV_DIR.exists():
        print_status(f"Virtual environment exists", "OK")
        return True
    print_status("Creating virtual environment...")
    try:
        venv.create(VENV_DIR, with_pip=True)
        print_status("Virtual environment created", "OK")
        return True
    except Exception as e:
        print_status(f"Failed to create venv: {e}", "ERROR")
        return False


def install_dependencies() -> bool:
    pip = get_venv_pip()
    if not REQUIREMENTS_FILE.exists():
        print_status(f"Requirements file not found", "ERROR")
        return False

    print_status("Upgrading pip...")
    subprocess.run([str(pip), "install", "--upgrade", "pip"], capture_output=True)

    print_status("Installing dependencies...")
    result = subprocess.run([str(pip), "install", "-r", str(REQUIREMENTS_FILE)], capture_output=True, text=True)
    if result.returncode != 0:
        print_status(f"Installation failed: {result.stderr}", "ERROR")
        return False
    print_status("Dependencies installed", "OK")
    return True


def verify_dependencies() -> tuple[bool, list[str]]:
    python = get_venv_python()
    print_status("Verifying dependencies...")
    packages = ["websockets", "dashscope", "PyQt6", "pyaudio", "PIL", "lancedb", "sentence_transformers", "vncdotool", "qasync", "OpenGL"]
    broken = []
    for pkg in packages:
        result = subprocess.run([str(python), "-c", f"import {pkg}"], capture_output=True)
        if result.returncode != 0:
            broken.append(pkg)
    if broken:
        print_status(f"Broken packages: {', '.join(broken)}", "WARN")
        return False, broken
    print_status("All dependencies verified", "OK")
    return True, []


def repair_dependencies(broken: list[str]) -> bool:
    pip = get_venv_pip()
    print_status(f"Repairing: {', '.join(broken)}")
    pkg_map = {"PIL": "Pillow", "sentence_transformers": "sentence-transformers", "lancedb": "lancedb", "OpenGL": "PyOpenGL"}
    for pkg in broken:
        actual = pkg_map.get(pkg, pkg)
        result = subprocess.run([str(pip), "install", "--force-reinstall", actual], capture_output=True)
        if result.returncode != 0:
            print_status(f"Failed to repair {actual}", "ERROR")
            return False
    print_status("Packages repaired", "OK")
    return True


def setup_data_dirs():
    for d in [DATA_DIR, DATA_DIR / "memory", DATA_DIR / "vm"]:
        d.mkdir(parents=True, exist_ok=True)
    print_status("Data directories ready", "OK")


def run_application(iso_path: str, avatar_path: str, env_vars: dict):
    python = get_venv_python()
    print_status("Starting 42Agent...")
    print_status(f"ISO: {iso_path}")
    print_status(f"Avatar: {avatar_path}")
    print()

    env = os.environ.copy()
    env["PYTHONPATH"] = str(SCRIPT_DIR)
    env.update(env_vars)

    subprocess.run(
        [str(python), "-m", "src.main", "--iso", iso_path, "--avatar", avatar_path],
        env=env,
        cwd=str(SCRIPT_DIR)
    )


def main():
    parser = argparse.ArgumentParser(description="42Agent - Autonomous AI Agent")
    parser.add_argument("--iso", help="Path to VM ISO file (overrides .env)")
    parser.add_argument("--avatar", help="Path to Live2D model file (overrides .env)")
    parser.add_argument("--check-only", action="store_true", help="Only check dependencies")
    parser.add_argument("--repair", action="store_true", help="Force repair dependencies")
    parser.add_argument("--clean", action="store_true", help="Remove venv and start fresh")
    args = parser.parse_args()

    print()
    print("=" * 50)
    print("  42Agent")
    print("=" * 50)
    print()

    env_vars = load_env()

    if args.clean:
        if VENV_DIR.exists():
            print_status("Removing virtual environment...")
            shutil.rmtree(VENV_DIR)
            print_status("Clean complete", "OK")

    missing_sys = check_system_dependencies()
    if missing_sys:
        install_system_hint()
        if not args.check_only:
            sys.exit(1)

    if not create_venv():
        sys.exit(1)

    if not install_dependencies():
        sys.exit(1)

    ok, broken = verify_dependencies()
    if not ok:
        if args.repair or not args.check_only:
            if not repair_dependencies(broken):
                sys.exit(1)
            ok, broken = verify_dependencies()
            if not ok:
                print_status("Dependencies still broken", "ERROR")
                sys.exit(1)

    setup_data_dirs()

    if args.check_only:
        print()
        print_status("All checks passed!", "OK")
        sys.exit(0)

    iso_path = args.iso or env_vars.get("ISO_PATH")
    avatar_path = args.avatar or env_vars.get("AVATAR_PATH")

    if not iso_path or not avatar_path:
        print_status("ISO and Avatar paths required", "ERROR")
        print()
        print("Set in .env file:")
        print("  ISO_PATH=./ubuntu.iso")
        print("  AVATAR_PATH=./assets/model.json")
        print()
        print("Or use command line:")
        print("  python run.py --iso ubuntu.iso --avatar model.json")
        sys.exit(1)

    iso_path = Path(iso_path)
    avatar_path = Path(avatar_path)

    if not iso_path.is_absolute():
        iso_path = SCRIPT_DIR / iso_path
    if not avatar_path.is_absolute():
        avatar_path = SCRIPT_DIR / avatar_path

    if not iso_path.exists():
        print_status(f"ISO not found: {iso_path}", "ERROR")
        sys.exit(1)
    if not avatar_path.exists():
        print_status(f"Avatar not found: {avatar_path}", "ERROR")
        sys.exit(1)

    api_key = env_vars.get("DASHSCOPE_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print_status("DASHSCOPE_API_KEY not set in .env", "ERROR")
        sys.exit(1)
    print_status("API key loaded", "OK")

    env_vars["DASHSCOPE_API_KEY"] = api_key
    print()
    run_application(str(iso_path.absolute()), str(avatar_path.absolute()), env_vars)


if __name__ == "__main__":
    main()
