import streamlit as st
import subprocess
import sys
import os
import re
import json
from pathlib import Path
from datetime import datetime

# ── Page Configuration ──
st.set_page_config(
    page_title="RepoAgent",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Constants ──
AGENT_DIR = ".agent"
LOGS_DIR = f"{AGENT_DIR}/logs"
REPORTS_DIR = f"{AGENT_DIR}/reports"
USAGE_FILE = f"{AGENT_DIR}/usage/usage.json"
PURPOSE_FILE = f"{AGENT_DIR}/purpose.md"
RULES_FILE = f"{AGENT_DIR}/rules.yaml"
CONFIG_FILE = f"{AGENT_DIR}/config.yaml"

# ── Custom CSS ──
st.markdown("""
<style>
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
    .violation-card {
        background: #2d1b1b;
        border-left: 4px solid #f85149;
        padding: 14px 18px;
        border-radius: 0 8px 8px 0;
        margin-bottom: 10px;
        color: #f0f0f0;
        font-size: 1rem;
        line-height: 1.6;
    }
    .violation-card strong {
        color: #ff6b6b;
        font-size: 1.05rem;
    }
    .deviation-card {
        background: #2d2b1b;
        border-left: 4px solid #d29922;
        padding: 14px 18px;
        border-radius: 0 8px 8px 0;
        margin-bottom: 10px;
        color: #f0f0f0;
        font-size: 1rem;
        line-height: 1.6;
    }
    .success-card {
        background: #1b2d1b;
        border-left: 4px solid #3fb950;
        padding: 14px 18px;
        border-radius: 0 8px 8px 0;
        margin-bottom: 10px;
        color: #f0f0f0;
        font-size: 1.05rem;
        font-weight: 500;
    }
    .log-entry {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 12px;
        color: #e6edf3;
        font-size: 1rem;
        line-height: 1.6;
    }
    .log-entry strong {
        color: #58a6ff;
    }
    .log-entry code {
        color: #79c0ff;
        background: #0d1117;
        padding: 2px 6px;
        border-radius: 4px;
    }
    .activity-row {
        padding: 10px 0;
        border-bottom: 1px solid #21262d;
        font-size: 1rem;
        color: #e6edf3;
    }
    .activity-time {
        color: #8b949e;
        font-weight: 500;
    }
    .activity-event {
        font-weight: 600;
        color: #e6edf3;
    }
    .activity-file {
        color: #79c0ff;
        font-weight: 500;
    }
    .activity-source-ai {
        color: #f85149;
        font-weight: 600;
    }
    .activity-source-manual {
        color: #3fb950;
        font-weight: 600;
    }
    .source-ai {
        color: #f85149;
        font-weight: bold;
    }
    .source-manual {
        color: #3fb950;
        font-weight: bold;
    }
    div[data-testid="stSidebar"] {
        background: #0d1117;
    }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════
#  HELPER FUNCTIONS
# ══════════════════════════════════════════════════

def run_agent_command(command):
    """Run agent.py command and return output"""
    try:
        result = subprocess.run(
            [sys.executable, "agent.py", command],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent
        )
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr
        return output.strip() if output else "Command completed."
    except Exception as e:
        return f"Error: {str(e)}"


def is_agent_running():
    """Check if agent is currently running"""
    pid_file = Path(f"{AGENT_DIR}/.pid")
    if pid_file.exists():
        pid = pid_file.read_text().strip()
        try:
            os.kill(int(pid), 0)
            return True
        except (ProcessLookupError, ValueError, OSError):
            return False
    return False


def parse_log_entries(log_text):
    """Parse log file text into structured entries"""
    entries = []
    blocks = log_text.split("=" * 80)

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        entry = {}

        # Parse timestamp and event type
        ts_match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (\S+)', block)
        if ts_match:
            entry["timestamp"] = ts_match.group(1)
            entry["event"] = ts_match.group(2)

        # Parse path
        path_match = re.search(r'PATH: (.+)', block)
        if path_match:
            entry["path"] = path_match.group(1).strip()

        # Parse source
        source_match = re.search(r'SOURCE: (.+)', block)
        if source_match:
            entry["source"] = source_match.group(1).strip()
        else:
            entry["source"] = "Unknown"

        # Parse diff
        diff_match = re.search(r'DIFF:\n(.*)', block, re.DOTALL)
        if diff_match:
            entry["diff"] = diff_match.group(1).strip()

        # Parse content
        content_match = re.search(r'CONTENT:\n(.*)', block, re.DOTALL)
        if content_match:
            entry["content"] = content_match.group(1).strip()

        if "timestamp" in entry and "path" in entry:
            entries.append(entry)

    return entries


def get_all_log_entries():
    """Read and parse all log files"""
    logs_path = Path(LOGS_DIR)
    if not logs_path.exists():
        return []

    all_entries = []
    for log_file in sorted(logs_path.glob("*.log"), reverse=True):
        text = log_file.read_text()
        entries = parse_log_entries(text)
        all_entries.extend(entries)

    return all_entries


def get_log_dates():
    """Get list of available log dates"""
    logs_path = Path(LOGS_DIR)
    if not logs_path.exists():
        return []
    return sorted([f.stem for f in logs_path.glob("*.log")], reverse=True)


def load_purpose():
    """Load purpose.md content"""
    path = Path(PURPOSE_FILE)
    if path.exists():
        return path.read_text()
    return "No purpose.md found. Run `python agent.py init` first."


def load_usage():
    """Load usage data"""
    path = Path(USAGE_FILE)
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {"total_input_tokens": 0, "total_output_tokens": 0, "total_cost_usd": 0.0, "requests": []}


def get_violation_count():
    """Run check and count violations"""
    output = run_agent_command("check")
    match = re.search(r'VIOLATIONS FOUND: (\d+)', output)
    if match:
        return int(match.group(1))
    return 0


def parse_check_output(output):
    """Parse check command output into violations and advisories"""
    violations = []
    advisories = []
    current_file = None
    current_section = None

    for line in output.split("\n"):
        stripped = line.strip()

        # Detect section headers
        if "VIOLATIONS FOUND:" in stripped:
            current_section = "violation"
            continue
        elif "ADVISORIES:" in stripped:
            current_section = "advisory"
            continue
        elif stripped.startswith("Files checked:") or stripped.startswith("Passed:") or stripped.startswith("Failed:"):
            continue

        # Parse file headers and entries
        if stripped.startswith("[") and stripped.endswith("]"):
            current_file = stripped[1:-1]
        elif "├──" in stripped or "└──" in stripped:
            v_text = stripped.split("── ", 1)[-1] if "── " in stripped else stripped
            parts = v_text.split(": ", 1)
            if len(parts) == 2:
                entry = {
                    "file": current_file,
                    "type": parts[0].strip(),
                    "message": parts[1].strip()
                }
                if current_section == "advisory":
                    advisories.append(entry)
                else:
                    violations.append(entry)

    return violations, advisories


def parse_violations(output):
    """Backwards-compatible wrapper"""
    violations, _ = parse_check_output(output)
    return violations


# ══════════════════════════════════════════════════
#  SIDEBAR
# ══════════════════════════════════════════════════

with st.sidebar:
    st.markdown("## 🛡️ RepoAgent")
    st.caption("Local Directory Code Monitor")
    st.markdown("---")

    # Agent status
    running = is_agent_running()
    if running:
        st.success("● Agent Running")
    else:
        st.error("○ Agent Stopped")

    # Start / Stop buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("▶ Start", use_container_width=True, disabled=running):
            subprocess.Popen(
                [sys.executable, "agent.py", "start"],
                cwd=Path(__file__).parent,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            import time
            time.sleep(1)
            st.rerun()
    with col2:
        if st.button("⏹ Stop", use_container_width=True, disabled=not running):
            run_agent_command("stop")
            st.rerun()

    st.markdown("---")

    # Navigation
    page = st.radio(
        "Navigation",
        ["📊 Dashboard", "📜 Activity Logs", "📋 Rule Violations", "📄 Reports", "⚙️ Settings"],
        label_visibility="collapsed"
    )

    st.markdown("---")
    st.caption(f"📁 {os.getcwd()}")
    st.caption(f"🕐 {datetime.now().strftime('%H:%M:%S')}")


# ══════════════════════════════════════════════════
#  PAGE 1: DASHBOARD
# ══════════════════════════════════════════════════

if page == "📊 Dashboard":
    st.header("📊 Dashboard")
    st.markdown("---")

    # ── Metrics Row ──
    entries = get_all_log_entries()

    # Filter out .pid entries for meaningful stats
    real_entries = [e for e in entries if ".pid" not in e.get("path", "")]

    # Count stats
    total_events = len(real_entries)
    ai_entries = [e for e in real_entries if "AI" in e.get("source", "")]
    manual_entries = [e for e in real_entries if "AI" not in e.get("source", "")]
    ai_percent = round((len(ai_entries) / total_events * 100) if total_events > 0 else 0)

    # Unique files
    unique_files = set(e.get("path", "") for e in real_entries)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("📂 Files Tracked", len(unique_files))
    with col2:
        st.metric("📝 Total Events", total_events)
    with col3:
        st.metric("🤖 AI Edits", f"{ai_percent}%")
    with col4:
        st.metric("👤 Manual Edits", f"{100 - ai_percent}%")

    st.markdown("---")

    # ── Two Column Layout ──
    left_col, right_col = st.columns([1, 1])

    # ── Purpose / Motivation ──
    with left_col:
        st.subheader("🎯 Repository Purpose")
        purpose = load_purpose()

        # Extract just the mission statement for a cleaner look
        mission_match = re.search(r'## Mission Statement\n\n(.+?)(?=\n---|\n##)', purpose, re.DOTALL)
        if mission_match:
            st.info(mission_match.group(1).strip())
        else:
            st.info(purpose[:500])

        with st.expander("View Full Purpose Document"):
            st.markdown(purpose)

    # ── Deviation Alerts ──
    with right_col:
        st.subheader("⚠️ Alerts")

        # Run rule check
        check_output = run_agent_command("check")

        if "VIOLATIONS FOUND" in check_output:
            violations = parse_violations(check_output)
            st.warning(f"{len(violations)} violation(s) detected")
            with st.expander(f"View All Alerts ({len(violations)})", expanded=False):
                for v in violations:
                    st.markdown(
                        f'<div class="violation-card">🔴 <strong>{v["type"]}</strong><br>'
                        f'{v["file"]}: {v["message"]}</div>',
                        unsafe_allow_html=True
                    )
        else:
            st.markdown(
                '<div class="success-card">✅ No rule violations detected</div>',
                unsafe_allow_html=True
            )

    st.markdown("---")

    # ── Recent Activity Feed ──
    st.subheader("📌 Recent Activity")

    recent = real_entries[:10]
    if recent:
        # Table header
        st.markdown(
            '<div class="activity-row" style="border-bottom: 2px solid #30363d; padding-bottom: 8px;">'
            '<strong style="color: #8b949e;">TIME</strong> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; '
            '<strong style="color: #8b949e;">EVENT</strong> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; '
            '<strong style="color: #8b949e;">FILE</strong> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; '
            '<strong style="color: #8b949e;">SOURCE</strong>'
            '</div>',
            unsafe_allow_html=True
        )

        for entry in recent:
            source = entry.get("source", "Unknown")
            if "AI" in source:
                source_html = f'<span class="activity-source-ai">🤖 {source}</span>'
            else:
                source_html = f'<span class="activity-source-manual">👤 {source}</span>'

            event_icon = {
                "FILE_MODIFIED": "✏️",
                "FILE_CREATED": "🆕",
                "FILE_DELETED": "🗑️",
                "FILE_RENAMED": "📝"
            }.get(entry.get("event", ""), "📄")

            short_path = entry.get("path", "").replace(os.getcwd() + "/", "")
            ts = entry.get("timestamp", "")
            time_str = ts.split(" ")[-1] if " " in ts else ts

            st.markdown(
                f'<div class="activity-row">'
                f'<span class="activity-time">{time_str}</span> &nbsp;&nbsp;&nbsp; '
                f'<span class="activity-event">{event_icon} {entry.get("event", "")}</span> &nbsp;&nbsp;&nbsp; '
                f'<span class="activity-file">{short_path}</span> &nbsp;&nbsp;&nbsp; '
                f'{source_html}'
                f'</div>',
                unsafe_allow_html=True
            )
    else:
        st.info("No activity logged yet. Start the agent and make some file changes.")


# ══════════════════════════════════════════════════
#  PAGE 2: ACTIVITY LOGS
# ══════════════════════════════════════════════════

elif page == "📜 Activity Logs":
    st.header("📜 Activity Logs")
    st.markdown("---")

    # Filters row
    col_source, col_event = st.columns(2)

    with col_source:
        source_filter = st.selectbox("🔍 Filter by Source", ["All", "AI Only", "Manual Only"])

    with col_event:
        event_filter = st.selectbox("📂 Filter by Event", ["All", "FILE_MODIFIED", "FILE_CREATED", "FILE_DELETED", "FILE_RENAMED"])

    st.markdown("---")

    # Load all entries grouped by date
    available_dates = get_log_dates()

    if not available_dates:
        st.info("No activity logs found. Start the agent and make some file changes.")
    else:
        total_shown = 0

        for date in available_dates:
            log_file = Path(LOGS_DIR) / f"{date}.log"
            if not log_file.exists():
                continue

            entries = parse_log_entries(log_file.read_text())

            # Filter out .pid entries
            entries = [e for e in entries if ".pid" not in e.get("path", "")]

            # Apply source filter
            if source_filter == "AI Only":
                entries = [e for e in entries if "AI" in e.get("source", "")]
            elif source_filter == "Manual Only":
                entries = [e for e in entries if "AI" not in e.get("source", "")]

            # Apply event filter
            if event_filter != "All":
                entries = [e for e in entries if e.get("event") == event_filter]

            if not entries:
                continue

            total_shown += len(entries)

            # Clickable date header
            with st.expander(f"📅 {date}  —  {len(entries)} event(s)", expanded=(date == available_dates[0])):
                for entry in entries:
                    source = entry.get("source", "Unknown")
                    if "AI" in source:
                        source_html = f'<span class="activity-source-ai">🤖 {source}</span>'
                    else:
                        source_html = f'<span class="activity-source-manual">👤 {source}</span>'

                    event_icon = {
                        "FILE_MODIFIED": "✏️",
                        "FILE_CREATED": "🆕",
                        "FILE_DELETED": "🗑️",
                        "FILE_RENAMED": "📝"
                    }.get(entry.get("event", ""), "📄")

                    short_path = entry.get("path", "").replace(os.getcwd() + "/", "")
                    ts = entry.get("timestamp", "")
                    time_str = ts.split(" ")[-1] if " " in ts else ts

                    # Entry header
                    st.markdown(
                        f'<div class="log-entry">'
                        f'<strong>{time_str}</strong> &nbsp; | &nbsp; '
                        f'<span class="activity-event">{event_icon} {entry.get("event", "")}</span> &nbsp; | &nbsp; '
                        f'{source_html}<br>'
                        f'📄 <code>{short_path}</code>'
                        f'</div>',
                        unsafe_allow_html=True
                    )

                    # Show diff if available
                    if entry.get("diff"):
                        with st.expander(f"View Diff — {short_path}", expanded=False):
                            st.code(entry["diff"], language="diff")

                    # Show content if available (for FILE_CREATED)
                    elif entry.get("content"):
                        with st.expander(f"View Content — {short_path}", expanded=False):
                            st.code(entry["content"], language="python")

        st.caption(f"Total: {total_shown} entries across {len(available_dates)} day(s)")


# ══════════════════════════════════════════════════
#  PAGE 3: RULE VIOLATIONS
# ══════════════════════════════════════════════════

elif page == "📋 Rule Violations":
    st.markdown("#### Rule Violations")
    st.caption("Validate codebase against rules.yaml")
    st.markdown("---")

    # Run check
    col_btn, col_spacer = st.columns([1, 4])
    with col_btn:
        run_check = st.button("Run Check", use_container_width=True)

    if run_check or "check_output" not in st.session_state:
        st.session_state.check_output = run_agent_command("check")

    output = st.session_state.check_output

    # Parse summary numbers
    checked_match = re.search(r'Files checked: (\d+)', output)
    passed_match = re.search(r'Passed: (\d+)', output)
    failed_match = re.search(r'Failed: (\d+)', output)

    files_checked = int(checked_match.group(1)) if checked_match else 0
    files_passed = int(passed_match.group(1)) if passed_match else 0
    files_failed = int(failed_match.group(1)) if failed_match else 0

    # Parse both violations and advisories
    violations, advisories = parse_check_output(output)

    # Summary bar
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Files Checked", files_checked)
    with col2:
        st.metric("Passed", files_passed)
    with col3:
        st.metric("Failed", files_failed)
    with col4:
        st.metric("Advisories", len(advisories))

    st.markdown("---")

    # ── VIOLATIONS SECTION ──
    st.markdown("**Violations**")
    st.caption("Rule-breaking issues that must be addressed")

    if violations:
        # Group violations by type
        v_by_type = {}
        for v in violations:
            vtype = v["type"]
            if vtype not in v_by_type:
                v_by_type[vtype] = []
            v_by_type[vtype].append(v)

        for vtype, items in v_by_type.items():
            severity_color = {
                "FORBIDDEN_FILE": "#f85149",
                "FORBIDDEN_IMPORT": "#d29922",
                "FORBIDDEN_PATTERN": "#f85149",
            }.get(vtype, "#f85149")

            with st.expander(f"{vtype.replace('_', ' ').title()}  —  {len(items)} issue(s)", expanded=False):
                for item in items:
                    short_file = item["file"].replace("./", "") if item["file"] else "-"
                    st.markdown(
                        f'<div style="padding: 10px 14px; margin-bottom: 6px; '
                        f'border-left: 3px solid {severity_color}; '
                        f'background: rgba(0,0,0,0.02); border-radius: 0 6px 6px 0;">'
                        f'<span style="color: #111; font-weight: 700;">{short_file}</span><br>'
                        f'<span style="color: #222; font-size: 0.95rem; font-weight: 500;">{item["message"]}</span>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
    else:
        st.markdown(
            '<div style="padding: 14px 18px; border-left: 3px solid #3fb950; '
            'background: rgba(63, 185, 80, 0.05); border-radius: 0 6px 6px 0; '
            'color: #111; font-size: 0.95rem; font-weight: 600;">'
            'No violations found.'
            '</div>',
            unsafe_allow_html=True
        )

    st.markdown("---")

    # ── ADVISORIES SECTION ──
    st.markdown("**Advisories**")
    st.caption("Suggestions for improvement — not blocking")

    if advisories:
        # Group advisories by type
        a_by_type = {}
        for a in advisories:
            atype = a["type"]
            if atype not in a_by_type:
                a_by_type[atype] = []
            a_by_type[atype].append(a)

        for atype, items in a_by_type.items():
            with st.expander(f"{atype.replace('_', ' ').title()}  —  {len(items)} suggestion(s)", expanded=False):
                for item in items:
                    short_file = item["file"].replace("./", "") if item["file"] else "-"
                    st.markdown(
                        f'<div style="padding: 10px 14px; margin-bottom: 6px; '
                        f'border-left: 3px solid #58a6ff; '
                        f'background: rgba(0,0,0,0.02); border-radius: 0 6px 6px 0;">'
                        f'<span style="color: #111; font-weight: 700;">{short_file}</span><br>'
                        f'<span style="color: #222; font-size: 0.95rem; font-weight: 500;">{item["message"]}</span>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
    else:
        st.markdown(
            '<div style="padding: 14px 18px; border-left: 3px solid #58a6ff; '
            'background: rgba(88, 166, 255, 0.05); border-radius: 0 6px 6px 0; '
            'color: #111; font-size: 0.95rem; font-weight: 600;">'
            'No advisories.'
            '</div>',
            unsafe_allow_html=True
        )


# ══════════════════════════════════════════════════
#  PAGE 4: REPORTS
# ══════════════════════════════════════════════════

elif page == "📄 Reports":
    st.header("📄 Reports")
    st.markdown("---")

    col_btn, col_spacer = st.columns([1, 3])
    with col_btn:
        generate = st.button("📊 Generate New Report", use_container_width=True)

    if generate:
        with st.spinner("Generating report via OpenAI... This may take a moment."):
            output = run_agent_command("report")
            st.session_state.report_output = output

    if "report_output" in st.session_state:
        st.success("Report generated!")
        st.markdown(st.session_state.report_output)

    st.markdown("---")
    st.subheader("📁 Past Reports")

    reports_path = Path(REPORTS_DIR)
    if reports_path.exists():
        report_files = sorted(reports_path.glob("*.md"), reverse=True)

        if report_files:
            for report_file in report_files:
                col_name, col_view = st.columns([3, 1])
                with col_name:
                    st.caption(f"📄 {report_file.name}")
                with col_view:
                    if st.button("View", key=report_file.name, use_container_width=True):
                        st.session_state.viewing_report = report_file.name

            # Display selected report
            if "viewing_report" in st.session_state:
                st.markdown("---")
                report_path = reports_path / st.session_state.viewing_report
                if report_path.exists():
                    st.subheader(f"📄 {st.session_state.viewing_report}")
                    st.markdown(report_path.read_text())
        else:
            st.info("No reports generated yet.")
    else:
        st.info("No reports directory found. Generate your first report.")


# ══════════════════════════════════════════════════
#  PAGE 5: SETTINGS
# ══════════════════════════════════════════════════

elif page == "⚙️ Settings":
    st.header("⚙️ Settings")
    st.markdown("---")

    tab1, tab2, tab3, tab4 = st.tabs(["📋 Config", "📏 Rules", "🎯 Purpose", "💰 API Usage"])

    # Config tab
    with tab1:
        config_path = Path(CONFIG_FILE)
        if config_path.exists():
            st.code(config_path.read_text(), language="yaml")
        else:
            st.warning("config.yaml not found. Run `python agent.py init`")

    # Rules tab
    with tab2:
        rules_path = Path(RULES_FILE)
        if rules_path.exists():
            st.code(rules_path.read_text(), language="yaml")
        else:
            st.warning("rules.yaml not found. Run `python agent.py init`")

    # Purpose tab
    with tab3:
        st.markdown(load_purpose())

    # Usage tab
    with tab4:
        usage = load_usage()

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("📥 Input Tokens", f"{usage['total_input_tokens']:,}")
        with col2:
            st.metric("📤 Output Tokens", f"{usage['total_output_tokens']:,}")
        with col3:
            st.metric("💰 Total Cost", f"${usage['total_cost_usd']:.4f}")

        if usage["requests"]:
            st.markdown("---")
            st.subheader("Request History")
            for req in reversed(usage["requests"]):
                st.markdown(
                    f'<div class="log-entry">'
                    f'<strong>{req["timestamp"][:19]}</strong> &nbsp; | &nbsp; '
                    f'{req["model"]} &nbsp; | &nbsp; '
                    f'{req["purpose"]}<br>'
                    f'📥 {req["input_tokens"]:,} in &nbsp; 📤 {req["output_tokens"]:,} out &nbsp; '
                    f'💰 ${req["cost_usd"]:.6f}'
                    f'</div>',
                    unsafe_allow_html=True
                )
        else:
            st.info("No API requests logged yet.")
