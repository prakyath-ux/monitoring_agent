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
    page_title= "RepoAgent Central Montior",
    page_icon = "",
    layout="wide",
    initial_sidebar_state="collapsed"
)


#-----Google sheet URL (Same one our UI.py POST to)-----#
#-----We change it to our app's GET endpoint--------#
#GSHEET_READ_URL = "https://script.google.com/macros/s/AKfycbxkE9Ab8WK85U5RYUJ7HbxZSTPNkZV0J13eMuocOaRj1mDlUeBaRB6UGuDEOclWh40KAg/exec"

AGENT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agents.json")
API_PORT = 5000

# ------ Authentication ---------#
DASHBOARD_USERS = {
    "frontend": "access123",
    "backend": "access123",
    "mobile": "access123",
    "AI": "access123",
    "development": "access123",
}

LOGIN_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "login_log.json")

def log_login(username):
    logs = []
    if os.path.exists(LOGIN_LOG):
        with open(LOGIN_LOG, "r") as f:
            logs = json.load(f)
    logs.append({
        "user": username,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    with open(LOGIN_LOG, "w") as f:
        json.dump(logs[-100:], f, indent=2)

def check_login():
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
                    log_login(username)
                    st.rerun()
                else:
                    st.error("Invalid credentials")
        st.stop()

check_login()

# ------ helper Functions---------#
def load_agents():
    """Load registered agents from local JSON file"""
    if os.path.exists(AGENT_FILE):
        with open(AGENT_FILE, "r") as f:
            return json.load(f)
    return []

def save_agents(agents):
    """Save agents list to JSON file"""
    with open(AGENT_FILE, "w") as f:
        json.dump(agents, f, indent=2)

class RegisterHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))

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
        # Serve .env keys at /env path
        if self.path == "/env":
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
    .status-online { color: #3fb950; font-weight: 700; }
    .status-offline { color: #f85149; font-weight: 700; }
    .status-unknown { color: #d29922; font-weight: 700; }
    .metric-card {
        background: #1e1e2e;
        border-radius: 10px;
        padding: 20px;
        text-align: center;
        border: 1px solid #333;
    }
    .metric-value {
        font-size: 2.5rem;
        font-weight: bold;
        color: #58a6ff;
    }
    .metric-label {
        font-size: 0.9rem;
        color: #8b949e;
        margin-top: 5px;
    }
    .agent-row {
        padding: 12px 16px;
        border-bottom: 1px solid #21262d;
        font-size: 0.95rem;
    }
</style>
""", unsafe_allow_html=True)



#--------Main Dashboard ---------#
st.title("RepoAgent - Central Monitor")
st.caption(f"Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
st.markdown("---")

#Fetch data from google sheet
with st.spinner("Loading registered agents..."):
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
    # ── Run checks ──
    results = []
    progress = st.progress(0, text="Checking fleet status...")

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

        results.append({
            "developer": agent.get("dev_name", "Unknown"),
            "project": agent.get("project_name", "—"),
            "machine": agent.get("machine", "—"),
            "ip": ip or "—",
            "online": is_online,
            "net_status": net_status,
            "latency": latency,
            "dashboard": dashboard_alive,
            "url": url
        })

        progress.progress((i + 1) / len(agents), text=f"Checking {agent.get('dev_name', '')}...")

    progress.empty()

    # ── Summary Metrics ──
    total = len(results)
    online = sum(1 for r in results if r["net_status"] in ("online", "firewall"))
    dashboards_up = sum(1 for r in results if r["dashboard"])
    offline = total - online

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Machines", total)
    with col2:
        st.metric("Online", online)
    with col3:
        st.metric("Agents Running", dashboards_up)
    with col4:
        st.metric("Offline", offline)

    st.markdown("---")

    # ── Fleet Table ──
    st.subheader("Fleet Status")

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
    h_dev, h_proj, h_machine, h_ip, h_ping, h_agent, h_link = st.columns([2, 2, 2, 2, 2, 2, 1])
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
    st.markdown("---")

    for group_key, dev_results in grouped.items():
      for idx, r in enumerate(dev_results):
        col_dev, col_proj, col_machine, col_ip, col_ping, col_agent, col_link = st.columns([2, 2, 2, 2, 2, 2, 1])

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
      st.markdown("---")

    # ── Auto Refresh ──
    st.markdown("---")
    auto_refresh = st.checkbox("Auto-refresh every 30 seconds", value=False)
    if auto_refresh:
        time.sleep(30)
        st.rerun()

