"""
Standalone HTTP API for the RepoAgent fleet.

Runs as its own process on the central server, independent of dashboard.py
(the Streamlit UI). All dev-side HTTP traffic targets this process on port 5000:
  - POST /register         heartbeats from each dev's agent
  - POST /upload-report    report uploads from each dev's agent
  - POST /project-config   lead-side push of per-project config (e.g. purpose.md)
  - GET  /                 returns agents.json (for legacy callers)
  - GET  /env              returns server's .env (subnet-restricted)
  - GET  /project-config   dev-side fetch of per-project config

Shares the same on-disk state as dashboard.py (agents.json, reports/,
project_configs/) so the Streamlit UI can read those files for display
without going through this API.

Run: nohup ./venv/bin/python central_api.py > central_api.log 2>&1 & disown
"""

import json
import os
import re
import sys
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PORT = 5000
HERE = os.path.dirname(os.path.abspath(__file__))
AGENT_FILE = os.path.join(HERE, "agents.json")
REPORTS_DIR = os.path.join(HERE, "reports")
PROJECT_CONFIGS_DIR = os.path.join(HERE, "project_configs")
ENV_FILE = os.path.join(HERE, ".env")

# Whitelist of project-config files that may be pushed/fetched.
PROJECT_CONFIG_ALLOWED_FILES = {
    "purpose.md",
    "rules.yaml",
    "config.yaml",
    "standards.md",
}


def _safe_path_part(s):
    """Sanitize a string to be safe as a filesystem path component.
    Identical to dashboard.py's helper — kept here so this module is standalone.
    """
    return re.sub(r'[^A-Za-z0-9._-]', '_', (s or "unknown"))[:80]


def load_agents():
    if os.path.exists(AGENT_FILE):
        try:
            with open(AGENT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_agents(agents):
    with open(AGENT_FILE, "w", encoding="utf-8") as f:
        json.dump(agents, f, indent=2)


def log(msg):
    """Single-line stderr log so nohup captures it in central_api.log."""
    sys.stderr.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    sys.stderr.flush()


class Handler(BaseHTTPRequestHandler):
    # ---- POST ----------------------------------------------------------
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw)
        except Exception:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid JSON")
            return

        # Per-project config upload — lead-side edit of purpose.md / etc.
        if self.path == "/project-config":
            try:
                project_name = body.get("project_name", "")
                file_name = body.get("file_name", "")
                content = body.get("content", "")
                if not project_name or file_name not in PROJECT_CONFIG_ALLOWED_FILES:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Missing project_name or invalid file_name")
                    return
                proj_dir = os.path.join(PROJECT_CONFIGS_DIR, _safe_path_part(project_name))
                os.makedirs(proj_dir, exist_ok=True)
                with open(os.path.join(proj_dir, file_name), "w", encoding="utf-8") as f:
                    f.write(content)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")
            except Exception as e:
                log(f"/project-config error: {e}")
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Error: {e}".encode())
            return

        # Report upload — mirrors dashboard.py exactly.
        if self.path == "/upload-report":
            try:
                dev = _safe_path_part(body.get("dev_name", ""))
                proj = _safe_path_part(body.get("project_name", ""))
                machine = _safe_path_part(body.get("machine", ""))
                ts = _safe_path_part(body.get("timestamp", datetime.now().strftime("%Y-%m-%d_%H-%M-%S")))
                from_d = body.get("from_date") or ""
                to_d = body.get("to_date") or ""
                content = body.get("content", "")
                report_type = body.get("type", "report")

                folder = os.path.join(REPORTS_DIR, f"{dev}__{machine}__{proj}")
                os.makedirs(folder, exist_ok=True)

                if report_type == "architecture":
                    filename = f"architecture_{ts}.md"
                else:
                    range_suffix = ""
                    if from_d or to_d:
                        range_suffix = f"_{_safe_path_part(from_d)}_to_{_safe_path_part(to_d)}"
                    filename = f"report_{ts}{range_suffix}.md"

                with open(os.path.join(folder, filename), "w", encoding="utf-8") as f:
                    f.write(content)

                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")
            except Exception as e:
                log(f"/upload-report error: {e}")
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Error: {e}".encode())
            return

        # Default path = /register. Mirrors dashboard.py's logic.
        blocked = ['.agent-monitor', '.Trash', '.trash', 'untitled', 'pycharm_agent_test',
                   'test-project_port_collision', '.agent']
        project_name = body.get("project_name", "")
        if project_name in blocked or project_name.startswith("."):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"SKIP")
            return

        agents = load_agents()
        key = (body.get("dev_name", "").lower(), body.get("project_name", "").lower())
        agents = [a for a in agents if (a.get("dev_name", "").lower(), a.get("project_name", "").lower()) != key]
        body["registered_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        agents.append(body)
        save_agents(agents)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    # ---- GET -----------------------------------------------------------
    def do_GET(self):
        # Per-project config fetch — dev-side pull of purpose.md / etc.
        if self.path.startswith("/project-config"):
            try:
                qs = parse_qs(urlparse(self.path).query)
                project_name = qs.get("project", [""])[0]
                file_name = qs.get("file", [""])[0]
                if not project_name or file_name not in PROJECT_CONFIG_ALLOWED_FILES:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Missing project or invalid file")
                    return
                path = os.path.join(PROJECT_CONFIGS_DIR, _safe_path_part(project_name), file_name)
                if not os.path.exists(path):
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b"Not found")
                    return
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                mtime = int(os.path.getmtime(path))
                resp = json.dumps({"content": content, "mtime": mtime}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                log(f"GET /project-config error: {e}")
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Error: {e}".encode())
            return

        # /env — subnet-restricted, mirrors dashboard.py exactly
        if self.path == "/env":
            client_ip = self.client_address[0]
            if not (client_ip.startswith("10.0.") or client_ip.startswith("172.16.") or client_ip == "127.0.0.1"):
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b"Forbidden")
                return
            if os.path.exists(ENV_FILE):
                with open(ENV_FILE, "r") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(content.encode())
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"No .env found")
            return

        # Default / — return the full agents.json (legacy callers depend on this)
        agents = load_agents()
        body = json.dumps(agents).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Quieter — we have our own log() above for things that matter
        return


def main():
    os.makedirs(REPORTS_DIR, exist_ok=True)
    os.makedirs(PROJECT_CONFIGS_DIR, exist_ok=True)
    log(f"central_api.py starting on 0.0.0.0:{PORT}")
    log(f"agents file: {AGENT_FILE}")
    log(f"reports dir: {REPORTS_DIR}")
    log(f"project_configs dir: {PROJECT_CONFIGS_DIR}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
