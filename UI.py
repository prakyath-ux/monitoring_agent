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
    page_icon="",
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
        background: #fafafa;
        border-left: 3px solid #c0392b;
        padding: 12px 16px;
        border-radius: 0 6px 6px 0;
        margin-bottom: 8px;
        color: #333;
        font-size: 0.95rem;
        line-height: 1.5;
    }
    .violation-card strong {
        color: #222;
        font-size: 0.95rem;
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
        border-bottom: 1px solid #e0e0e0;
        padding: 10px 4px;
        margin-bottom: 0;
        color: #222;
        font-size: 0.92rem;
        line-height: 1.5;
    }
    .log-entry strong {
        color: #333;
        font-weight: 600;
    }
    .log-entry code {
        color: #333;
        background: #f0f0f0;
        padding: 2px 6px;
        border-radius: 3px;
        font-size: 0.88rem;
    }
    .log-entry .log-source-ai {
        color: #c0392b;
        font-weight: 600;
    }
    .log-entry .log-source-manual {
        color: #27864a;
        font-weight: 600;
    }
    .log-entry .log-event {
        color: #555;
        font-weight: 600;
    }
    .log-entry .log-time {
        color: #888;
        font-weight: 500;
        font-size: 0.88rem;
    }
    .activity-row {
        padding: 10px 0;
        border-bottom: 1px solid #21262d;
        font-size: 1rem;
        color: #111;
    }
    .activity-time {
        color: #111;
        font-weight: 700;
    }
    .activity-event {
        font-weight: 700;
        color: #111;
    }
    .activity-file {
        color: #111;
        font-weight: 700;
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

        # Parse branch
        branch_match = re.search(r'BRANCH: (.+)', block)
        if branch_match:
            entry["branch"] = branch_match.group(1).strip()

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


# ── Auto-Start Agent ──
if "auto_start_attempted" not in st.session_state:
    st.session_state.auto_start_attempted = True
    if not is_agent_running() and Path(AGENT_DIR).exists():
        subprocess.Popen(
            [sys.executable, "agent.py", "start"],
            cwd=Path(__file__).parent,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        import time
        time.sleep(1.5)


# ══════════════════════════════════════════════════
#  SIDEBAR
# ══════════════════════════════════════════════════

with st.sidebar:
    st.markdown("## RepoAgent")
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
        ["Dashboard", "Activity Logs", "Rule Violations", "Reports", "Settings"],
        label_visibility="collapsed"
    )

    st.markdown("---")
    st.caption(f"{os.getcwd()}")
    st.caption(f"{datetime.now().strftime('%H:%M:%S')}")


# ══════════════════════════════════════════════════
#  PAGE 1: DASHBOARD
# ══════════════════════════════════════════════════

if page == "Dashboard":
    st.header("Dashboard")
    st.markdown("---")

    # ── Alerts ──
    check_output = run_agent_command("check")

    if "VIOLATIONS FOUND" in check_output:
        violations = parse_violations(check_output)
        st.warning(f"⚠️ {len(violations)} violation(s) detected")
        with st.expander(f"View Violations ({len(violations)})"):
            for v in violations:
                st.markdown(
                    f'<div class="violation-card"><strong>{v["type"]}</strong><br>'
                    f'{v["file"]}: {v["message"]}</div>',
                    unsafe_allow_html=True
                )
    else:
        st.success("No rule violations detected")

    st.markdown("---")

    # ── Recent Activity ──
    st.subheader("Recent Activity")

    entries = get_all_log_entries()
    real_entries = [e for e in entries if ".pid" not in e.get("path", "")]
    recent = real_entries[:10]

    if recent:
        for entry in recent:
            source = entry.get("source", "Unknown")
            if "AI" in source:
                source_html = f'<span class="activity-source-ai">{source}</span>'
            else:
                source_html = f'<span class="activity-source-manual">{source}</span>'

            short_path = entry.get("path", "").replace(os.getcwd() + "/", "")
            ts = entry.get("timestamp", "")
            time_str = ts.split(" ")[-1] if " " in ts else ts
            event = entry.get("event", "")
            branch = entry.get("branch", "")
            branch_html = f' &nbsp; <span style="color: #58a6ff; font-weight: 500;">({branch})</span>' if branch else ""

            st.markdown(
                f'<div class="activity-row">'
                f'<span class="activity-time">{time_str}</span> &nbsp;&nbsp; '
                f'<span class="activity-event">{event}</span> &nbsp;&nbsp; '
                f'<span class="activity-file">{short_path}</span> &nbsp;&nbsp; '
                f'{source_html}{branch_html}'
                f'</div>',
                unsafe_allow_html=True
            )
    else:
        st.info("No activity logged yet. Start the agent and make some file changes.")

    st.markdown("---")

    # ── Purpose ──
    with st.expander("Repository Purpose"):
        st.markdown(load_purpose())


# ══════════════════════════════════════════════════
#  PAGE 2: ACTIVITY LOGS
# ══════════════════════════════════════════════════

elif page == "Activity Logs":
    st.header("Activity Logs")
    st.markdown("---")

    # Filters row
    col_source, col_event = st.columns(2)

    with col_source:
        source_filter = st.selectbox("Filter by Source", ["All", "AI Only", "Manual Only"])

    with col_event:
        event_filter = st.selectbox("Filter by Event", ["All", "FILE_MODIFIED", "FILE_CREATED", "FILE_DELETED", "FILE_RENAMED", "BRANCH_SWITCHED"])

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
            with st.expander(f"{date}  —  {len(entries)} event(s)", expanded=(date == available_dates[0])):
                for entry in entries:
                    source = entry.get("source", "Unknown")
                    if "AI" in source:
                        source_html = f'<span class="log-source-ai">{source}</span>'
                    else:
                        source_html = f'<span class="log-source-manual">{source}</span>'

                    short_path = entry.get("path", "").replace(os.getcwd() + "/", "")
                    ts = entry.get("timestamp", "")
                    time_str = ts.split(" ")[-1] if " " in ts else ts
                    branch = entry.get("branch", "")
                    branch_html = f' &nbsp; <span style="color: #58a6ff; font-weight: 500;">({branch})</span>' if branch else ""

                    # Entry row
                    st.markdown(
                        f'<div class="log-entry">'
                        f'<span class="log-time">{time_str}</span> &nbsp;&nbsp; '
                        f'<span class="log-event">{entry.get("event", "")}</span> &nbsp;&nbsp; '
                        f'{source_html}{branch_html}<br>'
                        f'<code>{short_path}</code>'
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

elif page == "Rule Violations":
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

elif page == "Reports":
    st.header("Reports")
    st.markdown("---")

    col_btn, col_spacer = st.columns([1, 3])
    with col_btn:
        generate = st.button("Generate New Report", use_container_width=True)

    if generate:
        with st.spinner("Generating report via OpenAI... This may take a moment."):
            output = run_agent_command("report")
            st.session_state.report_output = output

    if "report_output" in st.session_state:
        st.success("Report generated!")
        st.markdown(st.session_state.report_output)

    st.markdown("---")
    st.subheader("Past Reports")

    reports_path = Path(REPORTS_DIR)
    if reports_path.exists():
        report_files = sorted(reports_path.glob("*.md"), reverse=True)

        if report_files:
            for report_file in report_files:
                col_name, col_view = st.columns([3, 1])
                with col_name:
                    st.caption(f"{report_file.name}")
                with col_view:
                    if st.button("View", key=report_file.name, use_container_width=True):
                        st.session_state.viewing_report = report_file.name

            # Display selected report
            if "viewing_report" in st.session_state:
                st.markdown("---")
                report_path = reports_path / st.session_state.viewing_report
                if report_path.exists():
                    st.subheader(f"{st.session_state.viewing_report}")
                    st.markdown(report_path.read_text())
        else:
            st.info("No reports generated yet.")
    else:
        st.info("No reports directory found. Generate your first report.")


# ══════════════════════════════════════════════════
#  PAGE 5: SETTINGS
# ══════════════════════════════════════════════════

elif page == "Settings":
    st.header("Settings")
    st.markdown("---")

    tab1, tab2, tab3, tab4 = st.tabs(["Config", "Rules", "Purpose", "API Usage"])

    # Config tab
    with tab1:
        config_path = Path(CONFIG_FILE)
        if config_path.exists():
            if st.session_state.get("edit_config"):
                config_content = st.text_area("config.yaml", config_path.read_text(), height=300, key="config_editor")
                col_save, col_cancel, _ = st.columns([1, 1, 4])
                with col_save:
                    if st.button("Save", key="save_config", use_container_width=True):
                        config_path.write_text(config_content)
                        st.session_state.edit_config = False
                        st.success("Config saved")
                        st.rerun()
                with col_cancel:
                    if st.button("Cancel", key="cancel_config", use_container_width=True):
                        st.session_state.edit_config = False
                        st.rerun()
            else:
                st.code(config_path.read_text(), language="yaml")
                if st.button("Edit", key="edit_config_btn"):
                    st.session_state.edit_config = True
                    st.rerun()
        else:
            st.warning("config.yaml not found. Run `python agent.py init`")

    # Rules tab
    with tab2:
        rules_path = Path(RULES_FILE)
        if rules_path.exists():
            if st.session_state.get("edit_rules"):
                rules_content = st.text_area("rules.yaml", rules_path.read_text(), height=400, key="rules_editor")
                col_save, col_cancel, _ = st.columns([1, 1, 4])
                with col_save:
                    if st.button("Save", key="save_rules", use_container_width=True):
                        rules_path.write_text(rules_content)
                        st.session_state.edit_rules = False
                        st.success("Rules saved")
                        st.rerun()
                with col_cancel:
                    if st.button("Cancel", key="cancel_rules", use_container_width=True):
                        st.session_state.edit_rules = False
                        st.rerun()
            else:
                st.code(rules_path.read_text(), language="yaml")
                if st.button("Edit", key="edit_rules_btn"):
                    st.session_state.edit_rules = True
                    st.rerun()
        else:
            st.warning("rules.yaml not found. Run `python agent.py init`")

    # Purpose tab
    with tab3:
        purpose_path = Path(PURPOSE_FILE)
        if purpose_path.exists():
            if st.session_state.get("edit_purpose"):
                purpose_content = st.text_area("purpose.md", purpose_path.read_text(), height=400, key="purpose_editor")
                col_save, col_cancel, _ = st.columns([1, 1, 4])
                with col_save:
                    if st.button("Save", key="save_purpose", use_container_width=True):
                        purpose_path.write_text(purpose_content)
                        st.session_state.edit_purpose = False
                        st.success("Purpose saved")
                        st.rerun()
                with col_cancel:
                    if st.button("Cancel", key="cancel_purpose", use_container_width=True):
                        st.session_state.edit_purpose = False
                        st.rerun()
            else:
                st.markdown(load_purpose())
                if st.button("Edit", key="edit_purpose_btn"):
                    st.session_state.edit_purpose = True
                    st.rerun()
        else:
            st.warning("purpose.md not found. Run `python agent.py init`")

    # Usage tab
    with tab4:
        usage = load_usage()

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Input Tokens", f"{usage['total_input_tokens']:,}")
        with col2:
            st.metric("Output Tokens", f"{usage['total_output_tokens']:,}")

        if usage["requests"]:
            st.markdown("---")
            st.subheader("Request History")
            for req in reversed(usage["requests"]):
                st.markdown(
                    f'<div class="log-entry">'
                    f'<strong>{req["timestamp"][:19]}</strong> &nbsp; | &nbsp; '
                    f'{req["model"]} &nbsp; | &nbsp; '
                    f'{req["purpose"]}<br>'
                    f'{req["input_tokens"]:,} in &nbsp; {req["output_tokens"]:,} out'
                    f'</div>',
                    unsafe_allow_html=True
                )
        else:
            st.info("No API requests logged yet.")
