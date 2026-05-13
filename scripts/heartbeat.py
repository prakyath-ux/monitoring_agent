"""
System-level watchdog + heartbeat.

Two jobs, both run from a single 60-second loop:

  1) WATCHDOG
     - Pull fresh code from GitHub into ~/.agent-monitor/ when remote has changes
       (cheap ls-remote SHA check first; only pulls when needed).
     - If our own source file changed, self-restart via os.execv so the new
       watchdog code takes over.
     - For each registered project, supervise its agent.py:
        * if .pid is missing/stale (>5 min old), respawn agent.py
        * if agent.py source was updated this cycle, kill the running agent
          and respawn so the new code takes effect.

  2) HEARTBEAT (unchanged behaviour)
     - For each registered project, POST /register to central_api with the
       current IP, port (probed against /<project>/_stcore/health), and
       machine name.

Designed to be the ONLY process on the dev machine that pulls fresh code
from GitHub. agent.py no longer pulls. If this watchdog itself dies, the
OS service (registered by setup.py — systemd / launchd / Task Scheduler)
should restart it.
"""

import json
import os
import socket
import subprocess
import platform
import sys
import time
from urllib.request import urlopen, Request

IS_WINDOWS = platform.system() == "Windows"
DASHBOARD_SERVER = "172.16.0.146"
DASHBOARD_PORT = 5000
AGENT_HOME = os.path.join(os.path.expanduser("~"), ".agent-monitor")
LOOP_INTERVAL_SEC = 60
PID_STALE_SEC = 5 * 60  # 5 minutes: agent touches .pid every 60s, so 5 min = clearly dead


# ============================================================================
# IP detection (existing, unchanged)
# ============================================================================

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


# ============================================================================
# Project discovery (existing, unchanged)
# ============================================================================

def get_registered_projects():
    """Find all projects on this machine that have .agent/ initialized."""
    projects = []
    agents_json = os.path.join(AGENT_HOME, ".registered_projects.json")
    if os.path.exists(agents_json):
        try:
            with open(agents_json, "r", encoding="utf-8") as f:
                projects = json.load(f)
        except Exception:
            pass
    return projects


def find_streamlit_port_for_project(project_name, port_lo=8501, port_hi=8520):
    """Probe ports for /<project_name>/_stcore/health. Returns the port serving
    THIS project, or None if not running anywhere in the range."""
    for p in range(port_lo, port_hi + 1):
        try:
            req = Request(
                "http://127.0.0.1:{}/{}/_stcore/health".format(p, project_name),
                method="GET",
            )
            with urlopen(req, timeout=1) as r:
                if r.status == 200:
                    return p
        except Exception:
            continue
    return None


# ============================================================================
# Heartbeat / registration (existing, unchanged)
# ============================================================================

def register_project(project_dir, ip):
    project_name = os.path.basename(project_dir)
    dev_name = os.environ.get("USER", os.environ.get("USERNAME", "unknown"))
    machine = socket.gethostname()

    port = find_streamlit_port_for_project(project_name)
    if port is None:
        # No Streamlit currently serving this project — skip the heartbeat
        # so we don't push a wrong URL onto the dashboard.
        return

    data = json.dumps({
        "dev_name": dev_name,
        "project_name": project_name,
        "network_url": "http://{}:{}/{}".format(ip, port, project_name),
        "machine": machine
    }).encode("utf-8")

    try:
        req = Request(
            "http://{}:{}/register".format(DASHBOARD_SERVER, DASHBOARD_PORT),
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        urlopen(req, timeout=5)
    except Exception:
        pass


# ============================================================================
# NEW — git pull (smart, with ls-remote pre-check)
# ============================================================================

def _git(args, timeout=15):
    """Run a git command in AGENT_HOME with Windows console hidden."""
    kwargs = {
        "capture_output": True,
        "text": True,
        "timeout": timeout,
    }
    if IS_WINDOWS:
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.run(["git", "-C", AGENT_HOME] + args, **kwargs)


def remote_has_new_commits():
    """Cheap check: compare local HEAD SHA to remote origin/version2 SHA.
    Returns True only when they differ. ~100 bytes over the wire when no
    new commits — much lighter than a full pull."""
    if not os.path.isdir(os.path.join(AGENT_HOME, ".git")):
        return False
    try:
        local = _git(["rev-parse", "HEAD"], timeout=5)
        if local.returncode != 0:
            return False
        local_sha = local.stdout.strip()

        remote = _git(["ls-remote", "origin", "version2"], timeout=10)
        if remote.returncode != 0 or not remote.stdout.strip():
            return False
        remote_sha = remote.stdout.split()[0]

        return bool(local_sha and remote_sha and local_sha != remote_sha)
    except Exception:
        return False


def pull_latest():
    """Run the actual git pull. Silent on failure (next cycle will retry)."""
    try:
        _git(["pull", "origin", "version2"], timeout=30)
    except Exception:
        pass


# ============================================================================
# NEW — agent supervision
# ============================================================================

def _pid_alive(pid):
    """Cross-platform check that a PID is currently a running process."""
    try:
        if IS_WINDOWS:
            result = subprocess.run(
                ["tasklist", "/FI", "PID eq {}".format(pid), "/NH"],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return str(pid) in result.stdout
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False


def agent_pid_is_stale(pid_file):
    """A .pid is stale if it's missing, can't be parsed, points to a dead
    process, OR was last touched more than PID_STALE_SEC ago."""
    if not os.path.exists(pid_file):
        return True
    try:
        if (time.time() - os.path.getmtime(pid_file)) > PID_STALE_SEC:
            return True
        pid = int(open(pid_file, encoding="utf-8", errors="replace").read().strip())
        if not _pid_alive(pid):
            return True
    except Exception:
        return True
    return False


def kill_agent_for_project(project_dir):
    """Kill the running agent.py for this project (if any) and remove .pid."""
    pid_file = os.path.join(project_dir, ".agent", ".pid")
    if not os.path.exists(pid_file):
        return
    try:
        pid = int(open(pid_file, encoding="utf-8", errors="replace").read().strip())
        if IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            try:
                os.kill(pid, 15)  # SIGTERM — agent.py's shutdown handler removes .pid
                time.sleep(0.5)
                # If still alive, hard kill
                if _pid_alive(pid):
                    os.kill(pid, 9)
            except ProcessLookupError:
                pass
    except Exception:
        pass
    try:
        os.remove(pid_file)
    except Exception:
        pass


def _venv_python():
    """Return path to the venv python interpreter, falling back to current."""
    sub = "Scripts" if IS_WINDOWS else "bin"
    exe = "python.exe" if IS_WINDOWS else "python"
    candidate = os.path.join(AGENT_HOME, "venv", sub, exe)
    if os.path.exists(candidate):
        return candidate
    return sys.executable


def spawn_agent_for_project(project_dir):
    """Spawn a fresh agent.py for this project. Fire-and-forget."""
    agent_py = os.path.join(AGENT_HOME, "agent.py")
    if not os.path.exists(agent_py):
        return
    if not os.path.isdir(project_dir):
        return  # project folder deleted by dev — silently skip

    kwargs = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if IS_WINDOWS:
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        subprocess.Popen(
            [_venv_python(), agent_py, "--project-dir", project_dir, "start"],
            **kwargs,
        )
    except Exception:
        pass


# ============================================================================
# NEW — self-restart on own source change
# ============================================================================

def maybe_self_restart(initial_mtime):
    """If our own source file's mtime increased (because git pull brought new
    watchdog code), re-exec the current process so the new code takes over.
    Returns True if we triggered a restart (caller should not run further
    work on this cycle — process is gone after os.execv)."""
    own_path = os.path.abspath(__file__)
    try:
        current = os.path.getmtime(own_path)
    except Exception:
        return False
    if current > initial_mtime:
        # IS_WINDOWS doesn't support os.execv reliably for re-exec; use Popen+exit pattern.
        try:
            if IS_WINDOWS:
                subprocess.Popen(
                    [_venv_python(), own_path],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                sys.exit(0)
            else:
                os.execv(_venv_python(), [_venv_python(), own_path])
        except Exception:
            return False
    return False


def _file_mtime(path):
    try:
        return os.path.getmtime(path)
    except Exception:
        return 0


# ============================================================================
# Main loop
# ============================================================================

def heartbeat_loop():
    own_path = os.path.abspath(__file__)
    initial_own_mtime = _file_mtime(own_path)
    agent_py_path = os.path.join(AGENT_HOME, "agent.py")
    last_agent_mtime = _file_mtime(agent_py_path)

    while True:
        try:
            # ----- 1. Smart-pull GitHub if remote has new commits -----
            try:
                if remote_has_new_commits():
                    pull_latest()
            except Exception:
                pass

            # ----- 2. If our own code changed, self-restart -----
            maybe_self_restart(initial_own_mtime)
            # If maybe_self_restart didn't exit, we keep running with old code
            # until the next cycle (which is fine — at most LOOP_INTERVAL_SEC of lag).

            # ----- 3. Detect if agent.py changed this pull -----
            current_agent_mtime = _file_mtime(agent_py_path)
            agent_code_updated = current_agent_mtime > last_agent_mtime
            if agent_code_updated:
                last_agent_mtime = current_agent_mtime

            # ----- 4. Supervise agents per project -----
            ip = get_local_ip()
            projects = get_registered_projects()
            for project_dir in projects:
                agent_dir = os.path.join(project_dir, ".agent")
                if not os.path.exists(agent_dir):
                    continue  # not initialized for this project — skip

                pid_file = os.path.join(agent_dir, ".pid")
                needs_respawn = False

                if agent_pid_is_stale(pid_file):
                    needs_respawn = True
                elif agent_code_updated:
                    # Agent code was updated this cycle — kill the running
                    # instance so the next iteration sees a stale pid and
                    # respawns with the new code.
                    kill_agent_for_project(project_dir)
                    needs_respawn = True

                if needs_respawn:
                    spawn_agent_for_project(project_dir)

            # ----- 5. Heartbeat registration (existing behaviour) -----
            if ip != "127.0.0.1":
                for project_dir in projects:
                    if os.path.exists(os.path.join(project_dir, ".agent")):
                        register_project(project_dir, ip)

        except Exception:
            # Never let the watchdog crash the loop — sleep and retry.
            pass

        time.sleep(LOOP_INTERVAL_SEC)


if __name__ == "__main__":
    heartbeat_loop()
