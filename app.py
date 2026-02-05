import streamlit as st
import subprocess
import sys
from pathlib import Path

#Page configuration
st.set_page_config(
    page_title = "Monitoring Agent",
    page_icon = "📁",
    layout= "wide",
)

#Helper fucntion to run agent commands
def run_agent_command(command):
    """Run agent.py command and return output"""
    try:
        result = subprocess.run(
            [sys.executable, "agent.py", command],
            capture_output=True,
            text=True,
            cwd = Path(__file__).parent
        )
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr
        return output if output else "Command completed."
    except Exception as e:
        return f"Error: {str(e)}"
    

# Title and Header
st.title("📁 Monitoring Agent")
st.markdown("---")

# Status section
col_status, col_info = st.columns([1,2])

with col_status:
    st.subheader("Agent Status")
    if st.button("🔄 Check Status", use_container_width=True):
        status_output = run_agent_command("sttus")
        if "running" in status_output.lower():
            st.success("● Agent is running")
        else:
            st.error("○ Agent is not running")
        st.code(status_output)


# Main controls
st.markdown("---")
st.subheader("Controls")

col1, col2, col3, col4 = st.columns(4)

with col1:
    if st.button("▶️ Start Agent", use_container_width=True):
        st.session_state.output = run_agent_command("start")
        st.session_state.last_command = "start"

with col2:
    if st.button("⏹️ Stop Agent", use_container_width=True):
        st.session_state.output = run_agent_command("stop")
        st.session_state.last_command = "stop"

with col3:
    if st.button("🔧 Initialize", use_container_width=True):
        st.session_state.output = run_agent_command("init")
        st.session_state.last_command = "init"

with col4:
    if st.button("🔍 Scan Codebase", use_container_width=True):
        st.session_state.output = run_agent_command("scan")
        st.session_state.last_command = "scan"


# Analysis tools
st.markdown("---")
st.subheader("Analysis Tools")

col5, col6, col7 = st.columns(3)

with col5:
    if st.button("📋 Check Rules", use_container_width=True):
        st.session_state.output = run_agent_command("check")
        st.session_state.last_command = "check"

with col6:
    if st.button("📊 Generate Report", use_container_width=True):
        st.session_state.output = run_agent_command("report")
        st.session_state.last_command = "report"

with col7:
    if st.button("📜 View Logs", use_container_width=True):
        st.session_state.output = run_agent_command("logs")
        st.session_state.last_command = "logs"


# output display
st.markdown("---")
st.subheader("Output")

if "output" in st.session_state:
    st.code(st.session_state.output, language="text")
else:
    st.info("Click a button above to run a command")

#Footer
st.markdown("---")
st.caption("Local Directory Monitoring Agent")
