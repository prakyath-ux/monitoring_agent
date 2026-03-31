"""
System-level heartbeat — runs on boot, independent of IDE.
Sends machine IP to central dashboard every 60 seconds.
Updates all registered projects for this machine with the current IP.
"""

import json
import os
import socket
import subprocess
import platform
import time
from urllib.request import urlopen, Request

IS_WINDOWS = platform.system() == "Windows"
DASHBOARD_SERVER = "10.0.3.55"
DASHBOARD_PORT = 5000
AGENT_HOME = os.path.join(os.path.expanduser("~"), ".agent-monitor")


def get_local_ip():
    fallback = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((DASHBOARD_SERVER, DASHBOARD_PORT))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
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
                if "inet " in line:
                    parts = line.strip().split()
                    idx = parts.index("inet") + 1 if "inet" in parts else -1
                    if idx > 0:
                        ip = parts[idx].split("/")[0]
                        if ip.startswith("10.0.3."):
                            return ip
                        if fallback == "127.0.0.1" and not ip.startswith("127."):
                            fallback = ip
        else:
            kwargs = {"capture_output": True, "text": True, "timeout": 5}
            if IS_WINDOWS:
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            result = subprocess.run(["ipconfig"], **kwargs)
            for line in result.stdout.splitlines():
                if "IPv4" in line and ":" in line:
                    ip = line.split(":")[-1].strip()
                    if ip.startswith("10.0.3."):
                        return ip
                    if fallback == "127.0.0.1" and not ip.startswith("127."):
                        fallback = ip
    except Exception:
        pass
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


def get_registered_projects():
    """Find all projects on this machine that have .agent/ initialized"""
    projects = []
    agents_json = os.path.join(AGENT_HOME, ".registered_projects.json")
    if os.path.exists(agents_json):
        try:
            with open(agents_json, "r", encoding="utf-8") as f:
                projects = json.load(f)
        except Exception:
            pass
    return projects


def register_project(project_dir, ip):
    project_name = os.path.basename(project_dir)
    dev_name = os.environ.get("USER", os.environ.get("USERNAME", "unknown"))
    machine = socket.gethostname()

    # Detect which port Streamlit might be on
    port = 8501
    pid_file = os.path.join(project_dir, ".agent", ".streamlit_pid")
    if os.path.exists(pid_file):
        # Streamlit is running, find its port
        for p in range(8501, 8510):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.5)
                s.connect(("127.0.0.1", p))
                s.close()
                port = p
                break
            except Exception:
                continue

    data = json.dumps({
        "dev_name": dev_name,
        "project_name": project_name,
        "network_url": "http://{}:{}/{}".format(ip, port, project_name),
        "machine": machine
    }).encode("utf-8")

    try:
        req = Request(
            "http://{}:{}".format(DASHBOARD_SERVER, DASHBOARD_PORT),
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        urlopen(req, timeout=5)
    except Exception:
        pass


def heartbeat_loop():
    while True:
        ip = get_local_ip()
        if ip == "127.0.0.1":
            time.sleep(60)
            continue

        projects = get_registered_projects()

        for project_dir in projects:
            if os.path.exists(os.path.join(project_dir, ".agent")):
                register_project(project_dir, ip)

        time.sleep(60)


if __name__ == "__main__":
    heartbeat_loop()
