#!/bin/bash
# ── Agent Monitor Startup Script (version2) ──
# Works with any IDE (IntelliJ, PyCharm, Sublime, Terminal)
# Matches VS Code extension behavior: silent, heartbeat, auto-pull

AGENT_HOME="$HOME/.agent-monitor"
REPO_URL="https://github.com/prakyath-ux/monitoring_agent.git"
BRANCH="version2"
DASHBOARD_SERVER="10.0.3.55"
DASHBOARD_PORT="5000"
PROJECT_DIR="${1:-$(pwd)}"
PROJECT_NAME="$(basename "$PROJECT_DIR")"

# ── Check and install prerequisites ──
if ! command -v git &> /dev/null; then
    echo "Installing git..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # xcode-select includes git on Mac
        xcode-select --install 2>/dev/null
        echo "Xcode tools installing. Wait for the popup to complete, then re-run this script."
        exit 0
    else
        # Linux: try apt, yum, dnf
        if command -v apt-get &> /dev/null; then
            sudo apt-get update -qq && sudo apt-get install -y -qq git
        elif command -v yum &> /dev/null; then
            sudo yum install -y git
        elif command -v dnf &> /dev/null; then
            sudo dnf install -y git
        else
            echo "Git not found. Install git manually and re-run."
            exit 1
        fi
    fi
fi

if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo "Installing Python..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        if command -v brew &> /dev/null; then
            brew install python3
        else
            echo "Python not found. Install from https://python.org or run: brew install python3"
            exit 1
        fi
    else
        # Linux: try apt, yum, dnf
        if command -v apt-get &> /dev/null; then
            sudo apt-get update -qq && sudo apt-get install -y -qq python3 python3-venv python3-pip
        elif command -v yum &> /dev/null; then
            sudo yum install -y python3 python3-pip
        elif command -v dnf &> /dev/null; then
            sudo dnf install -y python3 python3-pip
        else
            echo "Python not found. Install Python 3.9+ manually and re-run."
            exit 1
        fi
    fi
fi

# Verify installs worked
if ! command -v git &> /dev/null; then
    echo "Git installation failed. Install manually and re-run."
    exit 1
fi
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo "Python installation failed. Install manually and re-run."
    exit 1
fi

# ── Clone if not installed ──
if [ ! -d "$AGENT_HOME/.git" ]; then
    if [ -d "$AGENT_HOME" ]; then
        rm -rf "$AGENT_HOME"
    fi
    echo "Installing agent..."
    git clone -b "$BRANCH" "$REPO_URL" "$AGENT_HOME" > /dev/null 2>&1
    if [ $? -ne 0 ]; then
        echo "Clone failed."
        exit 1
    fi
fi

# ── Auto-pull latest code ──
git -C "$AGENT_HOME" pull origin "$BRANCH" > /dev/null 2>&1

# ── Run setup.py if venv or .agent missing ──
PYTHON="$AGENT_HOME/venv/bin/python"
STREAMLIT="$AGENT_HOME/venv/bin/streamlit"
SETUP_PY="$AGENT_HOME/version2/setup.py"

if [ ! -f "$PYTHON" ] || [ ! -d "$PROJECT_DIR/.agent" ]; then
    echo "Running setup..."
    if command -v python3 &> /dev/null; then
        python3 "$SETUP_PY" "$PROJECT_DIR"
    else
        python "$SETUP_PY" "$PROJECT_DIR"
    fi
    if [ $? -ne 0 ]; then
        echo "Setup failed."
        exit 1
    fi
fi

# ── Check if already running for this project ──
if [ -f "$PROJECT_DIR/.agent/.pid" ]; then
    PID=$(cat "$PROJECT_DIR/.agent/.pid")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Agent already running."
        exit 0
    fi
fi

# ── Find free port starting from 8501 ──
find_free_port() {
    local port=8501
    while lsof -i :$port >/dev/null 2>&1; do
        port=$((port + 1))
    done
    echo $port
}

PORT=$(find_free_port)

# ── Get LAN IP (prefer 10.0.3.x subnet) ──
get_lan_ip() {
    local all_ips
    # Try ifconfig (Mac) then ip addr (Linux)
    all_ips=$(ifconfig 2>/dev/null | grep "inet " | awk '{print $2}')
    if [ -z "$all_ips" ]; then
        all_ips=$(ip -4 addr show 2>/dev/null | grep "inet " | awk '{print $2}' | cut -d/ -f1)
    fi
    # Prefer 10.0.3.x
    local ip
    ip=$(echo "$all_ips" | grep "10\.0\.3\." | head -1)
    if [ -z "$ip" ]; then
        ip=$(echo "$all_ips" | grep -v "127\.0\.0\.1" | head -1)
    fi
    echo "${ip:-127.0.0.1}"
}

LAN_IP=$(get_lan_ip)

# ── Start Streamlit silently in background ──
AGENT_PROJECT_DIR="$PROJECT_DIR" AGENT_STREAMLIT_PORT="$PORT" \
    "$STREAMLIT" run "$AGENT_HOME/UI.py" \
    --server.address 0.0.0.0 \
    --server.port "$PORT" \
    --server.headless true \
    --server.baseUrlPath "$PROJECT_NAME" \
    > /dev/null 2>&1 &

STREAMLIT_PID=$!

sleep 2

if ! kill -0 $STREAMLIT_PID 2>/dev/null; then
    echo "Failed to start."
    exit 1
fi

# ── Open firewall ports on Linux (range for multiple projects) ──
if [[ "$OSTYPE" != "darwin"* ]]; then
    sudo ufw allow 8501:8510/tcp > /dev/null 2>&1
fi

# ── Start agent in background ──
"$PYTHON" "$AGENT_HOME/agent.py" --project-dir "$PROJECT_DIR" start > /dev/null 2>&1 &

# ── Register with central dashboard ──
register() {
    curl -s -X POST "http://$DASHBOARD_SERVER:$DASHBOARD_PORT" \
        -H "Content-Type: application/json" \
        -d "{\"dev_name\":\"$(whoami)\",\"project_name\":\"$PROJECT_NAME\",\"network_url\":\"http://$LAN_IP:$PORT/$PROJECT_NAME\",\"machine\":\"$(hostname)\"}" \
        > /dev/null 2>&1
}

register

# ── Heartbeat every 60s in background ──
while true; do
    sleep 60
    register
done &

HEARTBEAT_PID=$!

# ── Save PIDs for cleanup ──
echo "$STREAMLIT_PID" > "$PROJECT_DIR/.agent/.streamlit_pid"
echo "$HEARTBEAT_PID" > "$PROJECT_DIR/.agent/.heartbeat_pid"

echo "Agent started."
