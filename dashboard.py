import streamlit as st
import subprocess
import platform
import requests
import socket
import time
from datetime import datetime
import json
import os 
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# ----- Page Config --------#
st.set_page_config(
    page_title= "RepoAgent Central Monitor",
    page_icon = "",
    layout="wide",
    initial_sidebar_state="collapsed"
)


#-----Google sheet URL (Same one our UI.py POST to)-----#
#-----We change it to our app's GET endpoint--------#
#GSHEET_READ_URL = "https://script.google.com/macros/s/AKfycbxkE9Ab8WK85U5RYUJ7HbxZSTPNkZV0J13eMuocOaRj1mDlUeBaRB6UGuDEOclWh40KAg/exec"

AGENT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agents.json")
REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
API_PORT = 5000

import re as _re_for_safe
def _safe_path_part(s):
    """Sanitize a string to be safe as a filesystem path component."""
    return _re_for_safe.sub(r'[^A-Za-z0-9._-]', '_', (s or "unknown"))[:80]


# ---- Mermaid renderer for architecture reports ----
import streamlit.components.v1 as _arch_components
import json as _arch_json
import uuid as _arch_uuid

_MERMAID_FENCED = _re_for_safe.compile(r'```mermaid\s*\n(.*?)```', _re_for_safe.DOTALL)
_MERMAID_BARE = _re_for_safe.compile(
    r'^(flowchart\s+[A-Z]+|graph\s+[A-Z]+)\s*\n((?:[ \t]+.*\n)+)',
    _re_for_safe.MULTILINE,
)
_MERMAID_SUBGRAPH = _re_for_safe.compile(r'^(\s*subgraph\s+)([^\n]+)$', _re_for_safe.MULTILINE)

def _sanitize_mermaid(content):
    """Quote subgraph names containing hyphens/dots/spaces so Mermaid can parse."""
    def _fix(m):
        prefix = m.group(1)
        name = m.group(2).strip()
        if not name or name.startswith('"') or name.startswith("'"):
            return m.group(0)
        if _re_for_safe.search(r'[-.\s]', name):
            return f'{prefix}"{name}"'
        return m.group(0)
    return _MERMAID_SUBGRAPH.sub(_fix, content)

def _render_mermaid_via_api(content):
    """Render a Mermaid block by calling mermaid.render() programmatically.
    On parse error, the iframe shows the actual error + source for debugging.
    Also always shows a 'DEBUG: source' pre block so we can see what was passed.
    """
    container_id = f"mm-{_arch_uuid.uuid4().hex[:8]}"
    src_js = _arch_json.dumps(content)
    html = f"""
    <div id="{container_id}" style="background:white;padding:20px;border-radius:8px;min-height:300px;overflow:auto;"></div>
    <details style="margin-top:8px;font-family:system-ui;font-size:12px;">
      <summary style="cursor:pointer;color:#555;">DEBUG: show diagram source passed to Mermaid</summary>
      <pre id="dbg-{container_id}" style="background:#f4f4f4;padding:10px;border-radius:4px;white-space:pre-wrap;border:1px solid #ddd;"></pre>
    </details>
    <script type="module">
      import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
      mermaid.initialize({{ startOnLoad: false, theme: 'default', securityLevel: 'loose' }});
      const src = {src_js};
      document.getElementById('dbg-{container_id}').textContent =
        '[length=' + src.length + ']\\n' + src;
      try {{
        const {{ svg }} = await mermaid.render('g-{container_id}', src);
        document.getElementById('{container_id}').innerHTML = svg;
      }} catch (e) {{
        const msg = (e && e.message) ? e.message : String(e);
        document.getElementById('{container_id}').innerHTML =
          '<div style="color:#c00;font-family:system-ui;margin-bottom:10px;"><b>Mermaid render failed:</b><br>' +
          msg.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') +
          '</div>';
      }}
    </script>
    """
    _arch_components.html(html, height=620, scrolling=True)

def render_architecture_markdown(md_text):
    """Render markdown, converting mermaid blocks into actual rendered diagrams.

    Handles both fenced ```mermaid blocks and bare flowchart/graph blocks
    (some LLM outputs forget the fence). Bare-wrap only runs when no fenced
    block is already present — otherwise it double-fences and breaks the
    lazy regex below.
    """
    if not _MERMAID_FENCED.search(md_text):
        def _wrap_bare(m):
            return f"```mermaid\n{m.group(1)}\n{m.group(2)}```\n"
        md_text = _MERMAID_BARE.sub(_wrap_bare, md_text)

    parts = []
    last = 0
    for m in _MERMAID_FENCED.finditer(md_text):
        if m.start() > last:
            parts.append(("md", md_text[last:m.start()]))
        parts.append(("mermaid", m.group(1).strip()))
        last = m.end()
    if last < len(md_text):
        parts.append(("md", md_text[last:]))

    for kind, content in parts:
        if kind == "md":
            st.markdown(content)
        else:
            _render_mermaid_via_api(_sanitize_mermaid(content))

# ------ Authentication ---------#
DASHBOARD_USERS = {
    "frontend": "access123",
    "backend": "access123",
    "mobile": "access123",
    "AI": "access123",
    "development": "access1234",
}

LOGIN_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "login_log.json")

def log_login(username):
    logs = []
    if os.path.exists(LOGIN_LOG):
        with open(LOGIN_LOG, "r") as f:
            logs = json.load(f)
    logs.append({
        "user": username,
        "time": (datetime.utcnow() + __import__('datetime').timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M:%S IST")
    })
    with open(LOGIN_LOG, "w") as f:
        json.dump(logs[-100:], f, indent=2)

import hashlib

AUTH_SECRET = "repoagent2026"

def make_token(username):
    return hashlib.sha256(f"{username}:{AUTH_SECRET}".encode()).hexdigest()[:16]

def check_login():
    # Check URL token first (persists across browser refresh)
    params = st.query_params
    token = params.get("t")
    token_user = params.get("u")
    if token and token_user and token_user in DASHBOARD_USERS:
        if make_token(token_user) == token:
            st.session_state.authenticated = True
            st.session_state.logged_in_user = token_user
            return

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.markdown("<h2 style='text-align:center;'>RepoAgent Central Monitor</h2>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.button("Login", use_container_width=True):
                if username in DASHBOARD_USERS and password == DASHBOARD_USERS[username]:
                    st.session_state.authenticated = True
                    st.session_state.logged_in_user = username
                    st.query_params["u"] = username
                    st.query_params["t"] = make_token(username)
                    log_login(username)
                    st.rerun()
                else:
                    st.error("Invalid credentials")
        st.stop()

check_login()

TEAMS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "teams.json")

# ------ helper Functions---------#
def load_agents():
    """Load registered agents from local JSON file"""
    if os.path.exists(AGENT_FILE):
        with open(AGENT_FILE, "r") as f:
            return json.load(f)
    return []

def load_teams():
    """Load team definitions"""
    if os.path.exists(TEAMS_FILE):
        with open(TEAMS_FILE, "r") as f:
            return json.load(f)
    return {}

def get_team_for_agent(agent, teams):
    """Find which team an agent belongs to based on machine/dev_name matching"""
    machine = agent.get("machine", "")
    dev_name = agent.get("dev_name", "")
    for team_name, members in teams.items():
        for member in members:
            if "match_machine" in member and "match_dev_name" in member:
                if machine == member["match_machine"] and dev_name == member["match_dev_name"]:
                    return team_name, member.get("display_name", dev_name)
            elif "match_machine" in member:
                if machine == member["match_machine"]:
                    return team_name, member.get("display_name", dev_name)
            elif "match_dev_name" in member:
                if dev_name == member["match_dev_name"]:
                    return team_name, member.get("display_name", dev_name)
    return "Unassigned", dev_name

def list_reports_for(dev_name, machine, project_name, prefix="report_"):
    """List reports stored for a given (dev, machine, project) combo.

    prefix: filter by filename prefix — "report_" for activity reports,
            "architecture_" for architecture critiques.
    """
    dev = _safe_path_part(dev_name)
    proj = _safe_path_part(project_name)
    machine_safe = _safe_path_part(machine)
    folder = os.path.join(REPORTS_DIR, f"{dev}__{machine_safe}__{proj}")
    if not os.path.exists(folder):
        return []
    files = []
    for fname in os.listdir(folder):
        if fname.endswith(".md") and fname.startswith(prefix):
            full = os.path.join(folder, fname)
            files.append({
                "filename": fname,
                "path": full,
                "size": os.path.getsize(full),
                "mtime": os.path.getmtime(full),
            })
    files.sort(key=lambda x: x["mtime"], reverse=True)
    return files


def save_agents(agents):
    """Save agents list to JSON file"""
    with open(AGENT_FILE, "w") as f:
        json.dump(agents, f, indent=2)

class RegisterHandler(BaseHTTPRequestHandler):
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

        # Report upload — separate path
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

                # Architecture reports are stand-alone snapshots — no date range needed
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
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Error: {e}".encode())
            return

        # Reject junk project names
        blocked = ['.agent-monitor', '.Trash', '.trash', 'untitled', 'pycharm_agent_test',
                   'test-project_port_collision', '.agent']
        project_name = body.get("project_name", "")
        if project_name in blocked or project_name.startswith("."):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"SKIP")
            return

        agents = load_agents()
        # Deduplicate by dev_name + project_name
        key = (body.get("dev_name", "").lower(), body.get("project_name", "").lower())
        agents = [a for a in agents if (a.get("dev_name", "").lower(), a.get("project_name", "").lower()) != key]
        body["registered_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        agents.append(body)
        save_agents(agents)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def do_GET(self):
        # Serve .env keys at /env path — only to local network
        if self.path == "/env":
            client_ip = self.client_address[0]
            if not (client_ip.startswith("10.0.") or client_ip.startswith("172.16.") or client_ip == "127.0.0.1"):
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b"Forbidden")
                return
            env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
            if os.path.exists(env_file):
                with open(env_file, "r") as f:
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

        agents = load_agents()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(agents).encode())

    def log_message(self, format, *args):
        pass # Suppress console logs

def start_api():
    server = HTTPServer(("0.0.0.0", API_PORT), RegisterHandler)
    server.serve_forever()

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0

if not is_port_in_use(API_PORT):
    threading.Thread(target=start_api, daemon=True).start()

def ping_host(ip, timeout=1):
    """Ping an IP address, return (alive, latency_ms)"""
    flag = "-n" if platform.system() == "Windows" else "-c"
    timeout_flag = "-w" if platform.system() == "Windows" else "-W"
    try:
        result = subprocess.run(
            ["ping", flag, "1", timeout_flag, str(timeout), ip],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode==0:
            # Extract latency from output
            output = result.stdout
            if "time=" in output:
                time_str = output.split("time=")[-1].split()[0]
                latency = float(time_str.replace("ms", ""))
                return True, latency
            return True, 0
        return False, 0
    except Exception:
        return False, 0
    
def check_dashboard(url, timeout=2):
    """Check if a streamlit dashboard is reachable"""
    try:
        r = requests.get(url, timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False
    

def extract_ip(network_url):
    """Extract IP from a network URL like http://10.0.3.135:8501/project"""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(network_url)
        return parsed.hostname
    except Exception:
        return None
    
def extract_port(network_url):
    """Extract port from network URL"""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(network_url)
        return parsed.port or 8501
    except Exception:
        return 8501
    

# ── Custom CSS ──
st.markdown("""
<style>
    /* Clean light background */
    .stApp {
        background: #f8f9fb;
    }

    /* Status indicators - clean, no glow */
    .status-online { color: #16a34a; font-weight: 600; }
    .status-offline { color: #dc2626; font-weight: 600; }
    .status-unknown { color: #d97706; font-weight: 600; }

    /* Metric cards */
    [data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 14px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    [data-testid="stMetricValue"] {
        color: #1e293b;
    }
    [data-testid="stMetricLabel"] {
        color: #64748b;
    }

    /* Headers */
    h1, h2, h3 {
        color: #1e293b !important;
    }

    /* Buttons */
    .stButton > button {
        background: #4f46e5;
        color: white;
        border: none;
        border-radius: 6px;
        font-weight: 600;
    }
    .stButton > button:hover {
        background: #4338ca;
    }

    /* Links */
    a {
        color: #4f46e5 !important;
        text-decoration: none;
        font-weight: 600;
    }
    a:hover {
        color: #3730a3 !important;
    }

    /* Expander */
    [data-testid="stExpander"] {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
    }

    /* Table text */
    .stMarkdown code {
        color: #4f46e5;
        background: #eef2ff;
    }

    /* Progress bar — thicker */
    .stProgress > div > div > div {
        height: 20px !important;
    }
    .stProgress p {
        font-size: 1.1rem !important;
        font-weight: 600 !important;
        color: #1e293b !important;
    }
</style>
""", unsafe_allow_html=True)



#--------Main Dashboard ---------#
col_banner, col_user = st.columns([5, 1])
with col_banner:
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #e0f2fe, #bae6fd, #dbeafe); padding: 28px 32px; border-radius: 12px; border: 1px solid #93c5fd;">
        <h1 style="color: #1e3a5f !important; margin: 0; font-size: 1.8rem;">RepoAgent - Central Monitor</h1>
        <p style="color: #475569; margin: 6px 0 0 0; font-size: 0.85rem;">Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
    """, unsafe_allow_html=True)
with col_user:
    logged_user = st.session_state.get("logged_in_user", "")
    st.markdown(f'<p style="text-align:right; color:#64748b; margin-top:28px; font-size:0.85rem;">Logged in as <b>{logged_user}</b></p>', unsafe_allow_html=True)
    if st.button("Logout", key="logout_btn", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.logged_in_user = None
        st.query_params.clear()
        st.rerun()
st.markdown("---")

#Fetch data from google sheet
with st.spinner("Connecting to agent network..."):
    agents = load_agents()

if not agents:
    st.info("No registered agents yet. agents register when a developer opens a project with .agent/")

if "manual_agents" not in st.session_state:
    st.session_state.manual_agents = []

# Add new agent form
with st.expander("Add Machine"):
    col1, col2 = st.columns(2)
    with col1:
        new_name = st.text_input("Developer Name")
        new_project = st.text_input("Project Name")
    with col2:
        new_url = st.text_input("Dashboard URL", placeholder="http://10.0.3.135:8501/project")
        new_machine = st.text_input("Machine Name")

    if st.button("Add", use_container_width=True):
        if new_name and new_url:
            st.session_state.manual_agents.append({
                "dev_name": new_name,
                "project_name": new_project,
                "network_url": new_url,
                "machine": new_machine
            })
            st.rerun()

all_agents = list(agents) + st.session_state.get("manual_agents", [])

# Deduplicate by dev_name + project_name, keeping the LAST entry (most recent)
seen = {}
for a in all_agents:
    key = (a.get("dev_name", "").lower(), a.get("project_name", "").lower())
    seen[key] = a  # later entries overwrite earlier ones
agents = list(seen.values())

if agents:
    # Load team definitions
    teams = load_teams()

    # Filter agents by team before loading (so leads only see their team loading)
    logged_in_user = st.session_state.get("logged_in_user", "development")
    user_team_map = {
        "frontend": "Frontend",
        "backend": "Backend",
        "mobile": "Mobile",
        "AI": "AI",
    }
    if logged_in_user != "development":
        user_team = user_team_map.get(logged_in_user, "")
        if user_team:
            agents = [a for a in agents if get_team_for_agent(a, teams)[0] == user_team]

    # ── Run checks ──
    results = []
    progress = st.progress(0, text="Collecting data from developer machines...")

    for i, agent in enumerate(agents):
        ip = extract_ip(agent.get("network_url", ""))
        url = agent.get("network_url", "")

        # Ping
        is_online, latency = ping_host(ip) if ip else (False, 0)

        # Dashboard check — try even if ping fails (firewall may block ping)
        dashboard_alive = check_dashboard(url) if url else False

        # Determine network status
        if is_online:
            net_status = "online"
        elif dashboard_alive:
            net_status = "firewall"  # ping blocked but dashboard reachable
        else:
            net_status = "offline"

        team_name, display_name = get_team_for_agent(agent, teams)
        results.append({
            "developer": display_name,
            "dev_name_raw": agent.get("dev_name", ""),
            "project": agent.get("project_name", "—"),
            "machine": agent.get("machine", "—"),
            "ip": ip or "—",
            "online": is_online,
            "net_status": net_status,
            "latency": latency,
            "dashboard": dashboard_alive,
            "url": url,
            "team": team_name
        })

        pct = int(((i + 1) / len(agents)) * 100)
        progress.progress((i + 1) / len(agents), text=f"Collecting data: {agent.get('machine', '')} - {agent.get('project_name', '')}  ({pct}%)")

    progress.empty()

    st.markdown("---")

    # ── Fleet Table ──
    st.subheader("Fleet Status")

    # Team filter — auto-filter by logged-in user's team
    logged_in_user = st.session_state.get("logged_in_user", "development")
    user_team_map = {
        "frontend": "Frontend",
        "backend": "Backend",
        "mobile": "Mobile",
        "AI": "AI",
    }

    if logged_in_user == "development":
        # Development sees all teams with filter
        all_teams = ["All"] + list(teams.keys()) + ["Unassigned"]
        selected_team = st.selectbox("Filter by Team", all_teams, index=0)
        if selected_team != "All":
            results = [r for r in results if r["team"] == selected_team]
    else:
        # Other leads see only their team
        team_name = user_team_map.get(logged_in_user, "Unassigned")
        st.markdown(f"**Team: {team_name}**")
        results = [r for r in results if r["team"] == team_name]

    # ── Summary Metrics (after filter) ──
    unique_machines = len(set(r["ip"] for r in results if r["ip"] != "—"))
    total_projects = len(results)
    online_machines = len(set(r["ip"] for r in results if r["net_status"] in ("online", "firewall") and r["ip"] != "—"))
    dashboards_up = sum(1 for r in results if r["dashboard"])
    offline_machines = unique_machines - online_machines

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Machines", unique_machines)
    with col2:
        st.metric("Projects", total_projects)
    with col3:
        st.metric("Online", online_machines)
    with col4:
        st.metric("Running", dashboards_up)
    with col5:
        st.metric("Offline", offline_machines)

    st.markdown("---")

    # Sort: Running first, then Stopped, then Offline
    def sort_key(r):
        if r["dashboard"]:
            return 0
        elif r["net_status"] != "offline":
            return 1
        else:
            return 2
    results.sort(key=sort_key)

    # Group by machine (dev_name + machine combo to avoid merging different devs with same username)
    from collections import OrderedDict
    grouped = OrderedDict()
    for r in results:
        key = f"{r['developer']}|{r['machine']}|{r['ip']}"
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(r)

    # Column headers
    h_dev, h_proj, h_machine, h_ip, h_ping, h_agent, h_link, h_hist, h_arch = st.columns([2, 2, 2, 2, 2, 2, 1, 1, 1])
    with h_dev:
        st.markdown("**Developer**")
    with h_proj:
        st.markdown("**Project**")
    with h_machine:
        st.markdown("**Machine**")
    with h_ip:
        st.markdown("**IP Address**")
    with h_ping:
        st.markdown("**Network**")
    with h_agent:
        st.markdown("**Dashboard**")
    with h_link:
        st.markdown("**Link**")
    with h_hist:
        st.markdown("**History**")
    with h_arch:
        st.markdown("**Architecture**")
    st.markdown("---")

    @st.dialog("Report History", width="large")
    def report_history_dialog(dev_raw, machine, project, display_name):
        st.caption(f"{display_name} / {project}")
        reports = list_reports_for(dev_raw, machine, project)
        if not reports:
            st.info("No reports yet for this project.")
            return
        options = {datetime.fromtimestamp(r["mtime"]).strftime("%Y-%m-%d %H:%M"): r["path"] for r in reports}
        labels = list(options.keys())
        pick = st.selectbox("Select report", labels, index=0, key=f"pick_rep_{dev_raw}_{project}")
        sel_path = options[pick]
        if os.path.exists(sel_path):
            with open(sel_path, "r", encoding="utf-8") as f:
                st.markdown(f.read())

    @st.dialog("Architecture", width="large")
    def architecture_dialog(dev_raw, machine, project, display_name):
        st.caption(f"{display_name} / {project}")
        archs = list_reports_for(dev_raw, machine, project, prefix="architecture_")
        if not archs:
            st.info("No architecture reports yet for this project.")
            return
        options = {datetime.fromtimestamp(r["mtime"]).strftime("%Y-%m-%d %H:%M"): r["path"] for r in archs}
        labels = list(options.keys())
        pick = st.selectbox("Select snapshot", labels, index=0, key=f"pick_arch_{dev_raw}_{project}")
        sel_path = options[pick]
        if os.path.exists(sel_path):
            with open(sel_path, "r", encoding="utf-8") as f:
                render_architecture_markdown(f.read())

    for group_key, dev_results in grouped.items():
      for idx, r in enumerate(dev_results):
        col_dev, col_proj, col_machine, col_ip, col_ping, col_agent, col_link, col_hist, col_arch = st.columns([2, 2, 2, 2, 2, 2, 1, 1, 1])

        with col_dev:
            if idx == 0:
                st.markdown(f"**{r['developer']}**")
            else:
                st.markdown("")
        with col_proj:
            st.markdown(r["project"])
        with col_machine:
            if idx == 0:
                st.markdown(r["machine"])
            else:
                st.markdown("")
        with col_ip:
            if idx == 0:
                st.markdown(f"`{r['ip']}`")
            else:
                st.markdown("")
        with col_ping:
            if r["net_status"] == "online":
                st.markdown(f'<span class="status-online">Online ({r["latency"]:.0f}ms)</span>', unsafe_allow_html=True)
            elif r["net_status"] == "firewall":
                st.markdown('<span class="status-unknown">Firewall Blocked</span>', unsafe_allow_html=True)
            else:
                st.markdown('<span class="status-offline">Offline</span>', unsafe_allow_html=True)
        with col_agent:
            if r["dashboard"]:
                st.markdown('<span class="status-online">Running</span>', unsafe_allow_html=True)
            elif r["net_status"] != "offline":
                st.markdown('<span class="status-unknown">Stopped</span>', unsafe_allow_html=True)
            else:
                st.markdown('<span class="status-offline">—</span>', unsafe_allow_html=True)
        with col_link:
            if r["dashboard"] and r["url"]:
                st.markdown(f"[Open]({r['url']})")
        with col_hist:
            reports = list_reports_for(r["dev_name_raw"], r["machine"], r["project"])
            if reports:
                btn_key = f"hist_{group_key}_{r['project']}_{idx}"
                if st.button(f"View ({len(reports)})", key=btn_key, use_container_width=True):
                    report_history_dialog(r["dev_name_raw"], r["machine"], r["project"], r["developer"])
            else:
                st.markdown("—")
        with col_arch:
            archs = list_reports_for(r["dev_name_raw"], r["machine"], r["project"], prefix="architecture_")
            if archs:
                arch_key = f"arch_{group_key}_{r['project']}_{idx}"
                if st.button(f"Arch ({len(archs)})", key=arch_key, use_container_width=True):
                    architecture_dialog(r["dev_name_raw"], r["machine"], r["project"], r["developer"])
            else:
                st.markdown("—")
      st.markdown("---")


    # ── Auto Refresh ──
    st.markdown("---")
    auto_refresh = st.checkbox("Auto-refresh every 30 seconds", value=False)
    if auto_refresh:
        time.sleep(30)
        st.rerun()

