import streamlit as st
import subprocess
import platform
import requests
import socket
import time
from datetime import datetime

# ----- Page Config --------#
st.set_page_config(
    page_title= "RepoAgent Central Montior",
    page_icon = "",
    layout="wide",
    initial_sidebar_state="collapsed"
)


#-----Google sheet URL (Same one our UI.py POST to)-----#
#-----We change it to our app's GET endpoint--------#
GSHEET_READ_URL = "https://script.google.com/macros/s/AKfycbxkE9Ab8WK85U5RYUJ7HbxZSTPNkZV0J13eMuocOaRj1mDlUeBaRB6UGuDEOclWh40KAg/exec"


# ------ helper Functions---------#
def fetch_registered_agents():
    """Fetch all registered agents from Google Sheet"""
    try:
        response = requests.get(GSHEET_READ_URL, timeout=15, allow_redirects=True)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                # Map Google Sheet headers to our expected keys
                normalized = []
                for row in data:
                    normalized.append({
                        "dev_name": row.get("Dev Name", ""),
                        "project_name": row.get("Project Name", ""),
                        "network_url": row.get("Network URL", ""),
                        "machine": row.get("Machine", ""),
                    })
                return normalized
            st.warning(f"Unexpected response format: {type(data)}")
        else:
            st.warning(f"Google Sheet returned status {response.status_code}")
    except Exception as e:
        st.warning(f"Failed to fetch from Google Sheet: {e}")
    return []



def ping_host(ip, timeout=1):
    """Ping an IP address, return (alive, latency_ms)"""
    flag = "-n" if platform.system() == "Windows" else "-c"
    timeout_flag = "-w" if platform.system() == "Windows" else "W"
    try:
        result = subprocess.run(
            ["ping", flag, "1", timeout_flag, str(timeout), ip],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode==0:
            # Extract latency from output
            output = result.stdout
            if "time" in output:
                time_str = output.split("time")[-1].split()[0]
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
with st.spinner("Fetching regsitered agents..."):
    agents = fetch_registered_agents()

if not agents:
    st.warning("No registered agents found. Make sure your Google Apps Script supports GET requests.")
    st.info("Agents register themselves when the Streamlit dashboard starts on each developer machine.")

#Manual entry fallback
st.markdown("---")
st.subheader("Manual Fleet Configuration")
st.caption("Add known machines manually unti; Google Sheet integration is ready")

if "manual_agents" not in st.session_state:
    st.session_state.manual_agents = [
            {"dev_name": "infra", "project_name": "idocx-service", "network_url": "http://10.0.3.135:8502/idocx-service", "machine": "ubuntu-server"}
    ]

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

# Combine Google Sheet agents + manual agents
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

        # Dashboard check
        dashboard_alive = check_dashboard(url) if url and is_online else False

        results.append({
            "developer": agent.get("dev_name", "Unknown"),
            "project": agent.get("project_name", "—"),
            "machine": agent.get("machine", "—"),
            "ip": ip or "—",
            "online": is_online,
            "latency": latency,
            "dashboard": dashboard_alive,
            "url": url
        })

        progress.progress((i + 1) / len(agents), text=f"Checking {agent.get('dev_name', '')}...")

    progress.empty()

    # ── Summary Metrics ──
    total = len(results)
    online = sum(1 for r in results if r["online"])
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

    for r in results:
        col_dev, col_proj, col_machine, col_ip, col_ping, col_agent, col_link = st.columns([2, 2, 2, 2, 2, 2, 1])

        with col_dev:
            st.markdown(f"**{r['developer']}**")
        with col_proj:
            st.markdown(r["project"])
        with col_machine:
            st.markdown(r["machine"])
        with col_ip:
            st.markdown(f"`{r['ip']}`")
        with col_ping:
            if r["online"]:
                st.markdown(f'<span class="status-online">Online ({r["latency"]:.0f}ms)</span>', unsafe_allow_html=True)
            else:
                st.markdown('<span class="status-offline">Offline</span>', unsafe_allow_html=True)
        with col_agent:
            if r["dashboard"]:
                st.markdown('<span class="status-online">Running</span>', unsafe_allow_html=True)
            elif r["online"]:
                st.markdown('<span class="status-unknown">Stopped</span>', unsafe_allow_html=True)
            else:
                st.markdown('<span class="status-offline">—</span>', unsafe_allow_html=True)
        with col_link:
            if r["dashboard"] and r["url"]:
                st.markdown(f"[Open]({r['url']})")

    # ── Auto Refresh ──
    st.markdown("---")
    auto_refresh = st.checkbox("Auto-refresh every 30 seconds", value=True)
    if auto_refresh:
        time.sleep(30)
        st.rerun()

