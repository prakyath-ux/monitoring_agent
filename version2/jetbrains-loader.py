"""
JetBrains IDE Loader - auto-updates via git pull
Equivalent of extension-loader.js for VS Code
Called by the thin Kotlin plugin bootstrap
"""

import sys
import os
import json
import time
import socket
import signal
import subprocess
import platform
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

IS_WINDOWS = platform.system() == "Windows"
AGENT_HOME = Path.home() / ".agent-monitor"
DASHBOARD_SERVER = "172.16.0.146"
DASHBOARD_PORT = 5000


def get_python_path():
    vbin = "Scripts" if IS_WINDOWS else "bin"
    ext = ".exe" if IS_WINDOWS else ""
    return str(AGENT_HOME / "venv" / vbin / f"python{ext}")


def get_streamlit_path():
    vbin = "Scripts" if IS_WINDOWS else "bin"
    ext = ".exe" if IS_WINDOWS else ""
    return str(AGENT_HOME / "venv" / vbin / f"streamlit{ext}")


def find_free_port(start=8501):
    for port in range(start, start + 100):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("0.0.0.0", port))
                return port
        except OSError:
            continue
    return start


def get_local_ip():
    fallback = "127.0.0.1"

    # Method 1: UDP connect trick — most reliable cross-platform
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("172.16.0.146", 5000))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass

    # Method 2: Parse subprocess output (Linux/Mac)
    try:
        if not IS_WINDOWS:
            result = subprocess.run(
                ["ip", "-4", "addr", "show"], capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                result = subprocess.run(
                    ["ifconfig"], capture_output=True, text=True, timeout=5
                )
            for line in result.stdout.splitlines():
                line = line.strip()
                if "inet " in line:
                    parts = line.split()
                    idx = parts.index("inet") + 1 if "inet" in parts else -1
                    if idx > 0:
                        ip = parts[idx].split("/")[0]
                        if ip.startswith("10.0.3."):
                            return ip
                        if fallback == "127.0.0.1" and not ip.startswith("127."):
                            fallback = ip
        else:
            result = subprocess.run(
                ["ipconfig"], capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            for line in result.stdout.splitlines():
                if "IPv4" in line and ":" in line:
                    ip = line.split(":")[-1].strip()
                    if ip.startswith("10.0.3."):
                        return ip
                    if fallback == "127.0.0.1" and not ip.startswith("127."):
                        fallback = ip
    except Exception:
        pass

    # Method 3: getaddrinfo fallback
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith("10.0.3."):
                return ip
            if fallback == "127.0.0.1" and not ip.startswith("127."):
                fallback = ip
    except Exception:
        pass

    return fallback


def fetch_env_keys():
    """Fetch .env from central dashboard and save to ~/.agent-monitor/.env"""
    env_file = AGENT_HOME / ".env"
    if env_file.exists():
        return  # Already have keys
    try:
        req = Request(f"http://{DASHBOARD_SERVER}:{DASHBOARD_PORT}/env", method="GET")
        response = urlopen(req, timeout=5)
        content = response.read().decode("utf-8")
        if content and "OPENAI_API_KEY" in content:
            env_file.write_text(content, encoding="utf-8")
    except Exception:
        pass


def ensure_setup(project_dir):
    python_path = get_python_path()
    agent_dir = Path(project_dir) / ".agent"
    setup_py = AGENT_HOME / "version2" / "setup.py"

    if Path(python_path).exists() and agent_dir.exists():
        fetch_env_keys()
        return True

    if not setup_py.exists():
        print("ERROR: setup.py not found")
        return False

    system_python = "python" if IS_WINDOWS else "python3"
    try:
        kwargs = {"timeout": 300}
        if IS_WINDOWS:
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(
            [system_python, str(setup_py), project_dir],
            **kwargs
        )
        return result.returncode == 0
    except Exception as e:
        print(f"ERROR: Setup failed: {e}")
        return False


def launch_streamlit(project_dir):
    project_name = os.path.basename(project_dir)
    port = find_free_port(8501)
    streamlit_path = get_streamlit_path()
    ui_py = str(AGENT_HOME / "UI.py")

    env = os.environ.copy()
    env["AGENT_PROJECT_DIR"] = project_dir
    env["AGENT_STREAMLIT_PORT"] = str(port)

    kwargs = {
        "cwd": project_dir,
        "env": env,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if IS_WINDOWS:
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        proc = subprocess.Popen(
            [streamlit_path, "run", ui_py,
             "--server.address", "0.0.0.0",
             "--server.port", str(port),
             "--server.headless", "true",
             "--server.baseUrlPath", project_name],
            **kwargs
        )
        # Save Streamlit PID
        pid_file = Path(project_dir) / ".agent" / ".streamlit_pid"
        pid_file.write_text(str(proc.pid), encoding="utf-8")
    except Exception as e:
        print(f"ERROR: Streamlit failed: {e}")
        return 0

    # Wait and detect actual port from Streamlit
    time.sleep(3)
    actual_port = detect_actual_port(project_dir, port)
    return actual_port


def detect_actual_port(project_dir, default_port):
    """Check which port Streamlit actually started on"""
    for port in range(8501, 8510):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                s.connect(("127.0.0.1", port))
                return port
        except (OSError, socket.timeout):
            continue
    return default_port


def start_agent(project_dir):
    python_path = get_python_path()
    agent_py = str(AGENT_HOME / "agent.py")

    kwargs = {
        "cwd": project_dir,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if IS_WINDOWS:
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        proc = subprocess.Popen(
            [python_path, agent_py, "--project-dir", project_dir, "start"],
            **kwargs
        )
    except Exception as e:
        print(f"ERROR: Agent start failed: {e}")


def stop_agent(project_dir):
    python_path = get_python_path()
    agent_py = str(AGENT_HOME / "agent.py")

    # Stop agent
    try:
        subprocess.run(
            [python_path, agent_py, "--project-dir", project_dir, "stop"],
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
        )
    except Exception:
        pass

    # Stop Streamlit
    pid_file = Path(project_dir) / ".agent" / ".streamlit_pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            if IS_WINDOWS:
                subprocess.run(["taskkill", "/F", "/PID", str(pid), "/T"],
                               capture_output=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                os.kill(pid, signal.SIGTERM)
            pid_file.unlink(missing_ok=True)
        except Exception:
            pass

    # Stop heartbeat
    hb_pid_file = AGENT_HOME / ".heartbeat_pid"
    if hb_pid_file.exists():
        try:
            pid = int(hb_pid_file.read_text(encoding="utf-8").strip())
            if IS_WINDOWS:
                subprocess.run(["taskkill", "/F", "/PID", str(pid), "/T"],
                               capture_output=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                os.kill(pid, signal.SIGTERM)
            hb_pid_file.unlink(missing_ok=True)
        except Exception:
            pass


def register_with_dashboard(project_dir, port):
    project_name = os.path.basename(project_dir)
    ip = get_local_ip()
    dev_name = os.environ.get("USER", os.environ.get("USERNAME", "unknown"))
    machine = socket.gethostname()

    data = json.dumps({
        "dev_name": dev_name,
        "project_name": project_name,
        "network_url": f"http://{ip}:{port}/{project_name}",
        "machine": machine
    }).encode("utf-8")

    try:
        req = Request(
            f"http://{DASHBOARD_SERVER}:{DASHBOARD_PORT}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        urlopen(req, timeout=5)
    except Exception:
        pass


def start_heartbeat(project_dir, port):
    """Start heartbeat as a background process"""
    # Write a small heartbeat script and run it
    hb_script = AGENT_HOME / ".heartbeat.py"
    hb_script.write_text(f"""
import time, json, socket, os
from urllib.request import urlopen, Request
from urllib.error import URLError

project_dir = {repr(project_dir)}
port = {port}
server = "{DASHBOARD_SERVER}"
server_port = {DASHBOARD_PORT}

def get_local_ip():
    fallback = "127.0.0.1"
    import subprocess as sp
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("{DASHBOARD_SERVER}", {DASHBOARD_PORT}))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."): return ip
    except: pass
    try:
        r = sp.run(["ip", "-4", "addr", "show"], capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            r = sp.run(["ifconfig"], capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines():
            if "inet " in line:
                parts = line.strip().split()
                idx = parts.index("inet") + 1 if "inet" in parts else -1
                if idx > 0:
                    ip = parts[idx].split("/")[0]
                    if ip.startswith("10.0.3."): return ip
                    if fallback == "127.0.0.1" and not ip.startswith("127."): fallback = ip
    except: pass
    return fallback

def register():
    ip = get_local_ip()
    if ip == "127.0.0.1": return  # Heartbeat skip — don't overwrite good IP
    dev_name = os.environ.get("USER", os.environ.get("USERNAME", "unknown"))
    machine = socket.gethostname()
    project_name = os.path.basename(project_dir)
    data = json.dumps({{"dev_name": dev_name, "project_name": project_name,
        "network_url": f"http://{{ip}}:{{port}}/{{project_name}}", "machine": machine}}).encode("utf-8")
    try:
        req = Request(f"http://{{server}}:{{server_port}}", data=data,
            headers={{"Content-Type": "application/json"}}, method="POST")
        urlopen(req, timeout=5)
    except: pass

while True:
    time.sleep(60)
    register()
""", encoding="utf-8")

    python_path = get_python_path()
    kwargs = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if IS_WINDOWS:
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        proc = subprocess.Popen([python_path, str(hb_script)], **kwargs)
        hb_pid_file = AGENT_HOME / ".heartbeat_pid"
        hb_pid_file.write_text(str(proc.pid), encoding="utf-8")
    except Exception:
        pass


def register_project_locally(project_dir):
    """Save this project to the list of registered projects for system heartbeat"""
    reg_file = AGENT_HOME / ".registered_projects.json"
    projects = []
    if reg_file.exists():
        try:
            projects = json.loads(reg_file.read_text(encoding="utf-8"))
        except Exception:
            projects = []
    if project_dir not in projects:
        projects.append(project_dir)
        reg_file.write_text(json.dumps(projects, indent=2), encoding="utf-8")


def start_system_heartbeat():
    """Start system-level heartbeat that runs independent of IDE"""
    pid_file = AGENT_HOME / ".system_heartbeat_pid"

    # Check if already running
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            if IS_WINDOWS:
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}"],
                    capture_output=True, text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                if str(pid) in result.stdout:
                    return  # Already running
            else:
                os.kill(pid, 0)
                return  # Already running
        except (ProcessLookupError, OSError, ValueError):
            pass

    heartbeat_script = AGENT_HOME / "scripts" / "heartbeat.py"
    if not heartbeat_script.exists():
        return

    python_path = get_python_path()
    kwargs = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if IS_WINDOWS:
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        proc = subprocess.Popen([python_path, str(heartbeat_script)], **kwargs)
        pid_file.write_text(str(proc.pid), encoding="utf-8")
    except Exception:
        pass


def check_status(project_dir):
    pid_file = Path(project_dir) / ".agent" / ".pid"
    if not pid_file.exists():
        return "stopped"
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        if pid > 0:
            return "running"
    except Exception:
        pass
    return "stopped"


def cmd_start(project_dir):
    """Full startup sequence — called by JetBrains plugin"""
    # Register this project for system heartbeat
    register_project_locally(project_dir)

    # Setup if needed
    if not ensure_setup(project_dir):
        print("STATUS:error")
        return

    # Check if already running
    if check_status(project_dir) == "running":
        print("STATUS:running")
        return

    # Launch Streamlit
    port = launch_streamlit(project_dir)

    # Start agent
    time.sleep(2)
    start_agent(project_dir)

    # Register with dashboard
    register_with_dashboard(project_dir, port)

    # Start per-project heartbeat
    start_heartbeat(project_dir, port)

    # Start system-level heartbeat (survives IDE close, updates IP for all projects)
    start_system_heartbeat()

    # Wait for agent to start
    time.sleep(5)
    status = check_status(project_dir)
    print(f"STATUS:{status}")


def cmd_stop(project_dir):
    """Stop everything — called by JetBrains plugin"""
    stop_agent(project_dir)
    print("STATUS:stopped")


def cmd_status(project_dir):
    """Check status — called by JetBrains plugin"""
    status = check_status(project_dir)
    print(f"STATUS:{status}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: jetbrains-loader.py <start|stop|status> <project_dir>")
        sys.exit(1)

    command = sys.argv[1]
    project_dir = sys.argv[2]

    if command == "start":
        cmd_start(project_dir)
    elif command == "stop":
        cmd_stop(project_dir)
    elif command == "status":
        cmd_status(project_dir)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
