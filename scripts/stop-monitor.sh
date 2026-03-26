#!/bin/bash
# ── Stop Agent Monitor ──

AGENT_HOME="$HOME/.agent-monitor"
PROJECT_DIR="${1:-$(pwd)}"
PYTHON="$AGENT_HOME/venv/bin/python"

# Stop agent
"$PYTHON" "$AGENT_HOME/agent.py" --project-dir "$PROJECT_DIR" stop > /dev/null 2>&1

# Stop Streamlit
if [ -f "$PROJECT_DIR/.agent/.streamlit_pid" ]; then
    kill $(cat "$PROJECT_DIR/.agent/.streamlit_pid") 2>/dev/null
    rm -f "$PROJECT_DIR/.agent/.streamlit_pid"
fi

# Stop heartbeat
if [ -f "$PROJECT_DIR/.agent/.heartbeat_pid" ]; then
    kill $(cat "$PROJECT_DIR/.agent/.heartbeat_pid") 2>/dev/null
    rm -f "$PROJECT_DIR/.agent/.heartbeat_pid"
fi

echo "Agent stopped."
