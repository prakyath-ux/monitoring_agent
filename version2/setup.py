"""
Agent Monitor - Setup Script
One-time installer for dev machines. Works on Mac, Linux, Windows.
Usage: python3 setup.py /path/to/project
"""

import os
import sys
import platform
import subprocess
import shutil
import logging
from pathlib import Path


# ----- Config ------
AGENT_HOME = Path.home() / ".agent-monitor"
REPO_URL = "https://github.com/prakyath-ux/monitoring_agent.git"
BRANCH = "version2"
SERVICE_NAME = "agent-monitor"
LOG_FILE = AGENT_HOME / "install.log"


# -------- OS Detection ---------
def detect_os():
    system = platform.system()
    if system == "Darwin":
        return "mac"
    elif system == "Linux":
        return "linux"
    elif system == "Windows":
        return "windows"
    else:
        return None
    

# -------- Logging ------------
def setup_logging():
    AGENT_HOME.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level = logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )

# ----- Prerequisite checks --------
def check_python():
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 9):
        logging.error(f"Python 3.9+ required. Found {version.major}.{version.minor}")
        return False
    logging.info(f"Python {version.major}.{version.minor}.{version.micro} - OK")
    return True

def check_git():
    if not shutil.which("git"):
        logging.error("git not found. Install git first.")
        return False
    logging.info("git - OK")
    return True

def check_venv(current_os):
    """Check if venv is available (Linux often needs seperate package)"""
    try:
        subprocess.run(
            [sys.executable, "-m", "venv", "--help"],
            capture_output=True, timeout=10
        )
        logging.info("venv module - OK")
        return True
    except Exception:
        if current_os == "linux":
            logging.error("python3-venv not installd. Run: sudo apt install python3-venv")
        else:
            logging.error("venv module not available")
        return False
    

#------ Installation Steps------------
def clone_repo():
    git_dir = AGENT_HOME / ".git"

    # Case 1: Valid clone exists — just pull latest
    if git_dir.exists() and (AGENT_HOME / "agent.py").exists():
        logging.info("Agent code already exists. Pulling latest...")
        subprocess.run(
            ["git", "pull", "origin", BRANCH],
            cwd=str(AGENT_HOME), capture_output=True, timeout=60
        )
        return True

    # Case 2: Directory exists but not a valid clone — remove and re-clone
    if AGENT_HOME.exists():
        logging.warning(f"{AGENT_HOME} exists but is not a valid agent install. Removing...")
        shutil.rmtree(str(AGENT_HOME))
        logging.info("Old directory removed.")

    # Case 3: Fresh clone
    logging.info("Cloning agent repository...")
    try:
        subprocess.run(
            ["git", "clone", "-b", BRANCH, REPO_URL, str(AGENT_HOME)],
            capture_output=True, timeout=120, check=True
        )
        logging.info("Clone Complete.")
        return True

    except subprocess.CalledProcessError as e:
        logging.error(f"Clone failed: {e.stderr}")
        return False
    

def create_venv():
    venv_path = AGENT_HOME / "venv"
    if detect_os() == "windows":
        pip_path = venv_path / "Scripts" / "pip.exe"
    else:
        pip_path = venv_path / "bin" / "pip"

    # If venv exists but pip is missing, delete and recreate
    if venv_path.exists() and not pip_path.exists():
        logging.warning("Broken venv (no pip). Recreating...")
        import shutil
        shutil.rmtree(str(venv_path), ignore_errors=True)

    if venv_path.exists():
        logging.info("Virtual environment already exists.")
        return True

    # On Linux, ensure python3-venv and python3-pip are installed
    if detect_os() == "linux":
        try:
            subprocess.run(
                ["sudo", "apt-get", "install", "-y", "-qq", "python3-venv", "python3-pip"],
                capture_output=True, timeout=60
            )
        except Exception:
            pass

    logging.info("Creating Virtual Environment...")
    try:
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_path)],
            check=True, timeout=60
        )
        # Ensure pip is available in the venv
        if detect_os() == "windows":
            python_in_venv = str(venv_path / "Scripts" / "python.exe")
        else:
            python_in_venv = str(venv_path / "bin" / "python")
        subprocess.run(
            [python_in_venv, "-m", "ensurepip", "--upgrade"],
            capture_output=True, timeout=60
        )
        logging.info("Virtual Environment Created.")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to create venv: {e}")
        return False

def get_pip_path():
    current_os = detect_os()
    if current_os == "windows":
        return str(AGENT_HOME / "venv" / "Scripts" / "pip.exe")
    return str(AGENT_HOME / "venv" / "bin" / "pip")


def get_python_path():
    current_os = detect_os()
    if current_os == "windows":
        return str(AGENT_HOME / "venv" / "Scripts" / "python.exe")
    return str(AGENT_HOME / "venv" / "bin" / "python")

def install_dependencies():
    pip_path = get_pip_path()
    req_file = str(AGENT_HOME / "requirements.txt")

    logging.info("Installing Dependencies...")
    for attempt in range(3):
        try:
            subprocess.run(
                [pip_path, "install", "-r", req_file],
                check=True, capture_output=True, timeout=300 
            )
            logging.info("Dependencies Installed.")
            return True
        except subprocess.CalledProcessError as e:
            logging.warning(f"Attempt {attempt + 1} failed. Retrying...")
    logging.error("Failed to install dependencies after 3 attempts.")
    return False

#----- Project Setup---------
def validate_project_path(project_path):
    path = Path(project_path).resolve()

    if not path.exists():
        logging.error(f"Path does not exist: {path}")
        return None
    if not path.is_dir():
        logging.error(f"Not a directory: {path}")
        return None
    if not os.access(str(path), os.W_OK):
        logging.error(f"No write permission: {path}")
        return None

    logging.info(f"Project path valid: {path}")
    return path



def init_project(project_path):
    agent_dir = project_path / ".agent"
    if agent_dir.exists():
        logging.info(".agent/ already exists. Skipping init")
        return True
    
    python_path = get_python_path()
    agent_script = str(AGENT_HOME / "agent.py")

    logging.info("Initializing .agent/ in project...")
    try:
        subprocess.run(
            [python_path, agent_script, "--project-dir", str(project_path), "init"],
            check=True, capture_output=True, timeout=30
        )
        logging.info("Project initialization")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Init failed. {e.stderr}")
        return False
    

# ----- OS Service Registration -------------
def register_service_mac(project_path):
    plist_name = f"com.{SERVICE_NAME}.plist"
    plist_path = Path.home() / "Library" / "LaunchAgents" / plist_name
    python_path = get_python_path()
    agent_script = str(AGENT_HOME / "agent.py")

    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.{SERVICE_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>{agent_script}</string>
        <string>--project-dir</string>
        <string>{project_path}</string>
        <string>start</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{AGENT_HOME}/service.log</string>
    <key>StandardErrorPath</key>
    <string>{AGENT_HOME}/service_error.log</string>
</dict>
</plist>"""

    plist_path.write_text(plist_content, encoding="utf-8")
    subprocess.run(["launchctl", "load", str(plist_path)], capture_output=True)
    logging.info(f"macOS service registered: {plist_path}")
    return True

def register_service_linux(project_path):
    service_dir = Path.home() / ".config" / "systemd" / "user"
    service_dir.mkdir(parents=True, exist_ok=True)
    service_path = service_dir / f"{SERVICE_NAME}.service"
    python_path = get_python_path()
    agent_script = str(AGENT_HOME / "agent.py")

    service_content = f"""[Unit]
Description=Agent Monitor - File Watcher
After=network.target

[Service]
Type=simple
ExecStart={python_path} {agent_script} --project-dir "{project_path}" start
Restart=on-failure
RestartSec=10
StandardOutput=append:{AGENT_HOME}/service.log
StandardError=append:{AGENT_HOME}/service_error.log

[Install]
WantedBy=default.target
"""
    service_path.write_text(service_content, encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    subprocess.run(["systemctl", "--user", "enable", SERVICE_NAME], capture_output=True)
    subprocess.run(["systemctl", "--user", "start", SERVICE_NAME], capture_output=True)
    logging.info(f"Linux service registered; {service_path}")
    return True


def register_service_windows(project_path):
    python_path = get_python_path()
    agent_script = str(AGENT_HOME / "agent.py")
    task_name = SERVICE_NAME

    cmd = (
        f'schtasks /create /tn "{task_name}" /tr '
        f'"\"{python_path}\" \"{agent_script}\" --project-dir \"{project_path}\" start" '
        f'/sc onlogon /rl limited /f'
    )
    try:
        subprocess.run(cmd, shell=True, check=True, capture_output=True)
        logging.info(f"Windows task registered: {task_name}")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to register Windows task: {e}")
        return False
    

def register_service(current_os, project_path):
    logging.info(f"Registering OS Service ({current_os})...")
    if current_os == "mac":
        return register_service_mac(project_path)
    elif current_os == "linux":
        return register_service_linux(project_path)
    elif current_os == "windows":
        return register_service_windows(project_path)
    return False


# ------ Main ----------
def main():
    # get project path from args
    if len(sys.argv) < 2:
        print("Usage: python3 setup.py /path/to/project")
        sys.exit(1)

    project_arg = sys.argv[1]

    setup_logging()
    logging.info("=" * 50)
    logging.info("Agent Monitor - Setup")
    logging.info("=" * 50)

    #Step1: Detect OS
    current_os = detect_os()
    if not current_os:
        logging.error("Unsupported operating system.")
        sys.exit(1)

    logging.info(f"OS detected: {current_os}")


    #Step2: Check prerequisites
    logging.info("Checking Prerequisites...")
    if not check_python():
        sys.exit(1)
    if not check_git():
        sys.exit(1)
    if not check_venv(current_os):
        sys.exit(1)

    #step3 Clone or pull request
    if not clone_repo():
        sys.exit(1)

    #step4 Create virtual environment
    if not create_venv():
        sys.exit(1)

    # Step 5: Install dependencies
    if not install_dependencies():
        sys.exit(1)

    #step 6: Validate Project path
    project_path = validate_project_path(project_arg)
    if not project_path:
        sys.exit(1)

    #step 7: Initialize project
    if not init_project(project_path):
        sys.exit(1)

    # Step 8: Register as OS service
    if not register_service(current_os, project_path):
        logging.warning("Service registration failed. Agent will need manual start.")

    # Step 9: Open firewall ports on Linux (range for multiple projects)
    if current_os == "linux":
        try:
            subprocess.run(["sudo", "ufw", "allow", "8501:8510/tcp"], capture_output=True, timeout=10)
            logging.info("Firewall ports 8501-8510 opened.")
        except Exception:
            logging.warning("Could not open firewall ports. Run: sudo ufw allow 8501:8510/tcp")

    # Step 10: Summary
    logging.info("=" * 50)
    logging.info("Setup Complete!")
    logging.info(f" OS:         {current_os}")
    logging.info(f" Agent:      {AGENT_HOME}")
    logging.info(f" Project:    {project_path}")
    logging.info(f" Logs:       {LOG_FILE}")
    logging.info("=" * 50)

if __name__ == "__main__":
    main()  

