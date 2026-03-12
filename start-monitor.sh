#!/bin/bash
# ── Agent Monitor Startup Script ──
# Works with any IDE (IntelliJ, PyCharm, Sublime, Terminal)
# Same behavior as the VS Code extension

AGENT_HOME="$HOME/.agent-monitor"
PROJECT_DIR="${1:-$(pwd)}"
PROJECT_NAME="$(basename "$PROJECT_DIR")"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ── Preflight checks ──
if [ ! -d "$AGENT_HOME" ]; then
    echo -e "${RED}[ERROR] Agent not installed. Run: git clone -b agent_scaling https://github.com/prakyath-ux/monitoring_agent.git ~/.agent-monitor${NC}"
    exit 1
fi

if [ ! -f "$AGENT_HOME/venv/bin/python" ] && [ ! -f "$AGENT_HOME/venv/Scripts/python.exe" ]; then
    echo -e "${YELLOW}[SETUP] Creating virtual environment...${NC}"
    python3 -m venv "$AGENT_HOME/venv"
    "$AGENT_HOME/venv/bin/pip" install -r "$AGENT_HOME/requirements.txt"
fi

PYTHON="$AGENT_HOME/venv/bin/python"
STREAMLIT="$AGENT_HOME/venv/bin/streamlit"

# ── Initialize project if needed ──
if [ ! -d "$PROJECT_DIR/.agent" ]; then
    echo -e "${YELLOW}[INIT] Initializing monitoring for: $PROJECT_NAME${NC}"
    "$PYTHON" "$AGENT_HOME/agent.py" --project-dir "$PROJECT_DIR" init
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

# ── Check if already running for this project ──
EXISTING_PID=$(ps aux | grep "[s]treamlit.*$PROJECT_NAME" | awk '{print $2}')
if [ -n "$EXISTING_PID" ]; then
    echo -e "${GREEN}[OK] Agent already running for $PROJECT_NAME${NC}"
    echo -e "${GREEN}[OK] Dashboard: http://localhost:$PORT/$PROJECT_NAME${NC}"
    exit 0
fi

# ── Start Streamlit UI in background ──
echo -e "${GREEN}[START] Launching agent for: $PROJECT_NAME${NC}"
AGENT_PROJECT_DIR="$PROJECT_DIR" AGENT_STREAMLIT_PORT="$PORT" \
    "$STREAMLIT" run "$AGENT_HOME/UI.py" \
    --server.address 0.0.0.0 \
    --server.port "$PORT" \
    --server.baseUrlPath "$PROJECT_NAME" \
    > /dev/null 2>&1 &

STREAMLIT_PID=$!
echo $STREAMLIT_PID > "$PROJECT_DIR/.agent/.streamlit_pid"

sleep 2

if kill -0 $STREAMLIT_PID 2>/dev/null; then
    echo -e "${GREEN}[OK] Agent Monitor running${NC}"
    echo -e "${GREEN}[OK] Dashboard: http://localhost:$PORT/$PROJECT_NAME${NC}"
    echo -e "${GREEN}[OK] PID: $STREAMLIT_PID${NC}"
else
    echo -e "${RED}[ERROR] Streamlit failed to start${NC}"
    exit 1
fi
