# Monitor Agent - Technical Documentation

**Version 1.0** | Impacto Digifin| February 2026

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [High-Level Design](#2-high-level-design)
3. [Low-Level Design](#3-low-level-design)
4. [Environment and Setup](#4-environment-and-setup)
5. [Dependencies](#5-dependencies)
6. [Deployment and Execution](#6-deployment-and-execution)
7. [Appendices](#7-appendices)

---

## 1. Project Overview

### 1.1 Purpose

Monitor Agent is an autonomous local AI agent that runs on developer machines, monitors all file activity in a working directory, logs everything as persistent context (memory), and generates intelligent reports on demand. It provides a unified Streamlit dashboard for real-time control and a VS Code extension for zero-friction activation.

The platform exists because development teams lack visibility into how code evolves day-to-day. Manual code reviews catch issues after the fact, and there is no automated way to track whether changes align with a repository's stated purpose, follow coding standards, or originate from AI tools versus human developers. Monitor Agent solves this by watching silently while developers work, building a continuous activity log, and producing LLM-powered reports that summarize activity, detect deviations, and flag rule violations.

```
Dev works normally --> Agent watches silently --> Logs everything --> Generate report anytime
```

### 1.2 Key Features

**Continuous File Monitoring**
- Background process powered by the `watchdog` library monitors all file system events (create, modify, delete, rename) in the project directory.
- Computes unified diffs for every modification by maintaining an in-memory cache of file contents.
- Respects configurable ignore patterns (`node_modules/`, `.git/`, `__pycache__/`, etc.) and watched file extensions.
- Logs every event with timestamp, file path, diff, detected source, and current git branch.

**AI Source Detection**
- Cross-platform process detection identifies which editor or AI tool made the change (Claude Code, VS Code, Cursor, IntelliJ, PyCharm).
- Bulk change heuristic: modifications adding more than 10 lines are flagged as likely AI-generated.
- Source classification examples:
  - `Claude Code (AI)` -- Claude Code process detected with bulk change.
  - `VS Code (AI Tool)` -- VS Code process detected with bulk change.
  - `VS Code` -- VS Code process detected with small edit.
  - `Manual Edit` -- No recognized editor process detected.

**Git Branch Awareness**
- A `BranchWatcher` polls `.git/HEAD` every 2 seconds to detect branch switches.
- Logs `BRANCH_SWITCHED` events with old and new branch names.
- Every file event is tagged with the current branch name.

**Pause/Resume for Branch Switches**
- Pausing the agent prevents stale diffs caused by branch switches changing files on disk while the agent's RAM cache holds old branch content.
- On resume, the agent refreshes its entire file cache from disk before processing new events, ensuring clean single-line diffs.

**Real-Time Rule Checking**
- Validates files against a `rules.yaml` configuration on every modification event.
- Detects: forbidden files, forbidden imports (via Python AST parsing), forbidden regex patterns, file length advisories, and function length advisories.
- Violations are printed to the console in real-time and displayed in the dashboard.

**On-Demand Codebase Scanning**
- The `scan` command walks the project directory and extracts metadata from every watched file: line count, function names, class names, and imports.
- Results are saved to `scan.json` and used as context for report generation.

**LLM-Powered Report Generation**
- Reads all activity logs, coding standards, repository purpose, and scan data.
- Constructs a comprehensive prompt and calls the OpenAI API (GPT-4o by default).
- Generates reports covering: activity summary, timeline, purpose alignment, issues detected, and recommendations.
- Reports are saved as Markdown files with timestamps.
- API usage (tokens and cost) is tracked per request.

**Streamlit Dashboard (UI.py)**
- Full web-based dashboard with sidebar navigation: Dashboard, Activity Logs, Rule Violations, Reports, and Settings.
- Start/Stop/Pause/Resume agent controls.
- Activity log browser with filtering by source (AI vs. Manual) and event type.
- Rule violation display with severity separation (violations vs. advisories).
- Report viewer with generation trigger and history.
- Settings editor for config, rules, purpose, and API usage tracking.
- First-run setup wizard for new projects.

**VS Code Extension (agent-monitor)**
- Activates on VS Code startup (`onStartupFinished`).
- Detects whether the opened workspace has a `.agent/` folder; if not, prompts the user to initialize.
- Auto-installs the agent from a remote Git repository on first use (clones to `~/.agent-monitor/`, creates a virtual environment, installs dependencies).
- Launches the Streamlit dashboard as a detached subprocess with the workspace path passed via environment variable.
- Provides status bar indicator (Running/Stopped) and three commands: Start, Stop, Status.
- Cross-platform support (macOS, Linux, Windows).

### 1.3 Target Audience and Use Cases

| Audience | Use Case |
|----------|----------|
| **Developers** | Work normally while the agent silently logs all file activity, diffs, and source attribution for later review. |
| **Team Leads** | Generate reports to understand what changed, who changed it (human vs. AI), and whether changes align with the repository's purpose. |
| **QA Engineers** | Review rule violations and advisories to catch forbidden patterns, oversized functions, and unauthorized imports. |
| **Project Managers** | Track AI tool adoption across the team by reviewing source attribution in activity logs. |
| **DevOps / Infra** | Deploy the VS Code extension across developer machines for zero-configuration agent activation on every project. |

---

## 2. High-Level Design

### 2.1 System Architecture

The system follows a three-tier architecture with a clear separation between the trigger layer (VS Code extension), the engine layer (central agent installation), and the data layer (per-project configuration and logs).

**Tier 1 -- VS Code Extension (Trigger Layer)**

The extension is distributed as a `.vsix` file installed by each developer. On project open, it checks for the central agent and project configuration, installs them if missing, and launches the dashboard. The extension contains approximately 242 lines of JavaScript.

**Tier 2 -- Central Agent (Engine Layer)**

The central agent lives at `~/.agent-monitor/` and is shared across all projects on a single machine. It is cloned from a private GitHub repository on first use. It contains the monitoring engine (`agent.py`, 1288 lines), the dashboard (`UI.py`, 1020 lines), a Python virtual environment, and all dependencies.

**Tier 3 -- Per-Project Configuration (Data Layer)**

Each monitored project gets its own `.agent/` directory containing project-specific settings, rules, daily log files, generated reports, and API usage tracking.

```
Developer Machine
+--------------------------------------------------------------------------+
|                                                                          |
|   VS Code Extension          Central Agent          Per-Project Data     |
|   (agent-monitor/)           (~/.agent-monitor/)    (<project>/.agent/)  |
|                                                                          |
|   extension.js ---clones-->  agent.py               config.yaml          |
|   package.json               UI.py                  rules.yaml           |
|                 ---launches-> requirements.txt       purpose.md           |
|                               venv/                  standards.md         |
|                                                      ignore.yaml         |
|                                                      scan.json           |
|                                                      logs/               |
|                                                      reports/            |
|                                                      usage/              |
|                                                                          |
+--------------------------------------------------------------------------+
|                                                                          |
|   External Services:  OpenAI API (GPT-4o)  |  Google Sheets (registry)   |
|                                                                          |
+--------------------------------------------------------------------------+
```

### 2.2 Component Interaction Diagram

```
+-----------------------------------------------------------------------+
|                        STREAMLIT DASHBOARD (UI.py)                    |
|                                                                       |
|  +------------------+  +-------------------+  +--------------------+  |
|  |   Dashboard      |  |  Activity Logs    |  |  Rule Violations   |  |
|  +------------------+  +-------------------+  +--------------------+  |
|  +------------------+  +-------------------+                          |
|  |   Reports        |  |    Settings       |                          |
|  +------------------+  +-------------------+                          |
|                                                                       |
+----------------------------+------------------------------------------+
                             |
              subprocess calls to agent.py
                             |
                             v
+----------------------------+------------------------------------------+
|                       agent.py (Engine)                               |
|                                                                       |
|  +------------------+  +-------------------+  +--------------------+  |
|  | FileEventHandler |  |  BranchWatcher    |  |  ReportEngine      |  |
|  | (watchdog)       |  |  (daemon thread)  |  |  (OpenAI API)      |  |
|  +--------+---------+  +---------+---------+  +----------+---------+  |
|           |                      |                       |            |
|           v                      v                       v            |
|  +--------+---------+  +--------+----------+  +---------+----------+ |
|  | detect_editor    |  | get_current       |  | read_all_logs()    | |
|  | _source()        |  | _branch()         |  | load_standards()   | |
|  +------------------+  +-------------------+  | load_purpose()     | |
|                                               | load_scan()        | |
|                                               +--------------------+ |
+-------------------------------+---------------------------------------+
                                |
                                v
+-------------------------------+---------------------------------------+
|                  .agent/ (Per-Project Data)                           |
|                                                                       |
|   logs/YYYY-MM-DD.log    reports/report_*.md    usage/usage.json     |
|   config.yaml            rules.yaml             purpose.md           |
|   standards.md           ignore.yaml            scan.json            |
|                                                                       |
+-----------------------------------------------------------------------+
```

### 2.3 Data Flow

The platform operates as a continuous monitoring loop with on-demand reporting.

```
Stage 1: MONITOR (Continuous)
  Developer edits files in their IDE
       |
       v
  watchdog Observer detects filesystem event
       |
       v
  FileEventHandler processes event:
    1. Filters by extension and ignore patterns
    2. Reads new content from disk
    3. Computes unified diff against in-memory cache
    4. Counts added lines for bulk change heuristic
    5. Calls detect_editor_source() for AI classification
    6. Runs real-time rule checking against rules.yaml
    7. Calls LogWriter.write() to append to daily log
       |
       v
  .agent/logs/YYYY-MM-DD.log (persistent storage)


Stage 2: BRANCH TRACKING (Continuous, parallel)
  BranchWatcher polls .git/HEAD every 2 seconds
       |
       v
  If branch name changed:
    Log BRANCH_SWITCHED event with old and new branch names


Stage 3: REPORT (On demand)
  User triggers report via CLI or dashboard
       |
       v
  ReportEngine.generate_report():
    1. read_all_logs() -- all activity within date range
    2. load_purpose() -- repository mission statement
    3. load_standards() -- coding standards
    4. load_scan() -- codebase structure metadata
    5. Build combined prompt
       |
       v
  OpenAI API (GPT-4o)
       |
       v
  Report saved to .agent/reports/report_YYYY-MM-DD_HH-MM-SS.md
  Usage logged to .agent/usage/usage.json
```

### 2.4 External Integrations

| Integration | Purpose | Protocol |
|-------------|---------|----------|
| **OpenAI API** | LLM inference for report generation (GPT-4o) | HTTPS (REST API) |
| **GitHub** | Agent source code repository for first-time clone | HTTPS (git clone) |
| **Google Apps Script** | Dashboard instance registration in shared Google Sheet | HTTPS (POST request) |

---

## 3. Low-Level Design

### 3.1 Module: agent.py (Monitoring Engine)

**File:** `agent.py`
**Lines:** 1,288
**Purpose:** Single-file architecture containing all classes, configuration loaders, utility functions, CLI commands, and the main entry point for the monitoring agent.

#### 3.1.1 Constants and Configuration

```python
IS_WINDOWS = platform.system() == "Windows"

PROJECT_DIR = os.environ.get("AGENT_PROJECT_DIR", os.getcwd())
AGENT_DIR   = os.path.join(PROJECT_DIR, ".agent")
LOGS_DIR    = os.path.join(AGENT_DIR, "logs")
CONFIG_FILE = os.path.join(AGENT_DIR, "config.yaml")
STANDARDS_FILE = os.path.join(AGENT_DIR, "standards.md")
IGNORE_FILE = os.path.join(AGENT_DIR, "ignore.yaml")
PID_FILE    = os.path.join(AGENT_DIR, ".pid")
PAUSE_FILE  = os.path.join(AGENT_DIR, ".paused")
PURPOSE_FILE = os.path.join(AGENT_DIR, "purpose.md")
SCAN_FILE   = os.path.join(AGENT_DIR, "scan.json")
REPORTS_DIR = os.path.join(AGENT_DIR, "reports")
RULES_FILE  = os.path.join(AGENT_DIR, "rules.yaml")
USAGE_DIR   = os.path.join(AGENT_DIR, "usage")
USAGE_FILE  = os.path.join(USAGE_DIR, "usage.json")

PRICING = {
    "gpt-4o":      {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}
```

All path constants support the `--project-dir` CLI flag. When provided, `main()` overrides every global path variable to point at the specified directory instead of `os.getcwd()`.

#### 3.1.2 Configuration Loader Functions

**`load_config()`**

| Attribute | Detail |
|-----------|--------|
| **Parameters** | None |
| **Returns** | `dict` with keys: `watch_extensions`, `model`, `log_retention_days` |
| **Purpose** | Loads agent configuration from `.agent/config.yaml`. Returns hardcoded defaults if the file does not exist. |

Default values:

```python
{
    "watch_extensions": [".py", ".js", ".ts", ".java", ".go"],
    "model": "gpt-4o",
    "log_retention_days": 30
}
```

**`load_ignore_patterns()`**

| Attribute | Detail |
|-----------|--------|
| **Parameters** | None |
| **Returns** | `list[str]` -- ignore pattern strings |
| **Purpose** | Loads patterns from `.agent/ignore.yaml`. Returns defaults if file does not exist. |

Default patterns: `node_modules/`, `.git/`, `__pycache__/`, `.agent/logs`, `*.pyc`, `.env`

**`load_standards()`**

| Attribute | Detail |
|-----------|--------|
| **Parameters** | None |
| **Returns** | `str` -- content of `standards.md` |
| **Purpose** | Loads company coding standards. Returns `"No company standards defined"` if file does not exist. |

**`load_purpose()`**

| Attribute | Detail |
|-----------|--------|
| **Parameters** | None |
| **Returns** | `str` -- content of `purpose.md` |
| **Purpose** | Loads repository purpose. Returns `"No repository purpose defined"` if file does not exist. |

**`load_rules()`**

| Attribute | Detail |
|-----------|--------|
| **Parameters** | None |
| **Returns** | `dict` or `None` |
| **Purpose** | Loads validation rules from `.agent/rules.yaml`. Returns `None` if file does not exist. |

**`load_usage()`**

| Attribute | Detail |
|-----------|--------|
| **Parameters** | None |
| **Returns** | `dict` with keys: `total_input_tokens`, `total_output_tokens`, `total_cost_usd`, `requests` |
| **Purpose** | Loads API usage data from `.agent/usage/usage.json`. Returns zeroed defaults if file does not exist. |

**`load_scan()`**

| Attribute | Detail |
|-----------|--------|
| **Parameters** | None |
| **Returns** | `dict` or `None` |
| **Purpose** | Loads codebase scan data from `.agent/scan.json`. |

#### 3.1.3 Utility Functions

**`is_pid_alive(pid)`**

| Attribute | Detail |
|-----------|--------|
| **Parameters** | `pid: int` -- process ID to check |
| **Returns** | `bool` |
| **Purpose** | Cross-platform check for whether a process is running. |

Logic:
- Windows: Runs `tasklist /FI "PID eq {pid}"` and checks if the PID appears in stdout.
- Unix/macOS: Calls `os.kill(pid, 0)` which succeeds without sending a signal if the process exists.

**`detect_editor_source(file_path, diff_lines_added=0)`**

| Attribute | Detail |
|-----------|--------|
| **Parameters** | `file_path: str` -- path to modified file; `diff_lines_added: int` -- number of added lines (default 0) |
| **Returns** | `str` -- source identifier string |
| **Purpose** | Detects which editor or AI tool made the change by combining process detection with a bulk change heuristic. |

Uses a nested `process_running(name)` function:
- Unix/macOS: `pgrep -f {name}` -- searches all running process names.
- Windows: `tasklist /FI "IMAGENAME eq {name}*"` -- filters by image name.

Detection priority (evaluated in order):

| Priority | Condition | Returns |
|----------|-----------|---------|
| 1 | Claude running + >10 lines added | `"Claude Code (AI)"` |
| 2 | VS Code running + >10 lines added | `"VS Code (AI Tool)"` |
| 3 | VS Code running | `"VS Code"` |
| 4 | Cursor running + >10 lines added | `"Cursor (AI)"` |
| 5 | Cursor running | `"Cursor"` |
| 6 | IntelliJ running + >10 lines added | `"IntelliJ (AI Tool)"` |
| 7 | PyCharm running + >10 lines added | `"PyCharm (AI Tool)"` |
| 8 | IntelliJ running | `"IntelliJ"` |
| 9 | PyCharm running | `"PyCharm"` |
| 10 | >10 lines added only | `"AI Tool (likely)"` |
| 11 | Default | `"Manual Edit"` |

**`get_current_branch()`**

| Attribute | Detail |
|-----------|--------|
| **Parameters** | None |
| **Returns** | `str` or `None` |
| **Purpose** | Reads `.git/HEAD` directly as a file. If content starts with `ref: refs/heads/`, extracts the branch name. For detached HEAD, returns the first 8 characters of the commit hash. Returns `None` if not in a git repo. |

**`is_paused()`**

| Attribute | Detail |
|-----------|--------|
| **Parameters** | None |
| **Returns** | `bool` |
| **Purpose** | Returns `True` if the `.agent/.paused` flag file exists. |

**`should_ignore(path, ignore_patterns)`**

| Attribute | Detail |
|-----------|--------|
| **Parameters** | `path: str`; `ignore_patterns: list[str]` |
| **Returns** | `bool` |
| **Purpose** | Checks if a file path matches any ignore pattern. |

Three pattern types:

| Pattern Type | Example | Match Method |
|-------------|---------|-------------|
| Directory (ends with `/`) | `node_modules/` | Substring match on path |
| Extension (starts with `*`) | `*.pyc` | Suffix match on filename |
| Exact string | `.env` | Substring match on path |

**`scan_file(file_path)`**

| Attribute | Detail |
|-----------|--------|
| **Parameters** | `file_path: str` |
| **Returns** | `dict` with keys: `path`, `lines`, `functions`, `classes`, `imports`; or `None` on error |
| **Purpose** | Reads a file and extracts metadata by scanning for `def `, `class `, `import`/`from` line prefixes. |

**`log_usage(model, input_tokens, output_tokens, purpose="report")`**

| Attribute | Detail |
|-----------|--------|
| **Parameters** | `model: str`; `input_tokens: int`; `output_tokens: int`; `purpose: str` (default `"report"`) |
| **Returns** | `float` -- total cost in USD for this request |
| **Purpose** | Calculates cost from the `PRICING` dictionary (per-million-token rates), appends a timestamped entry to `usage.json`, and updates running totals. |

**`check_file(file_path, rules)`**

| Attribute | Detail |
|-----------|--------|
| **Parameters** | `file_path: str`; `rules: dict` -- rules from `rules.yaml` |
| **Returns** | `list[dict]` -- each dict has keys: `type`, `severity`, `message` |
| **Purpose** | Validates a single file against the configured rules. |

Performs five checks in order:

| Check | Type | Severity | Logic |
|-------|------|----------|-------|
| Forbidden file names | `FORBIDDEN_FILE` | violation | Filename matches an entry in `forbidden_files` list |
| File length | `FILE_TOO_LONG` | advisory | Line count exceeds `max_file_lines` threshold |
| Forbidden patterns | `FORBIDDEN_PATTERN` | violation | A line matches a regex in `forbidden_patterns` (e.g., hardcoded passwords) |
| Forbidden imports | `FORBIDDEN_IMPORT` | violation | Python-only. Uses `ast.parse()` to walk `Import` and `ImportFrom` nodes |
| Function length | `FUNCTION_TOO_LONG` | advisory | Python-only. Uses `ast` to walk `FunctionDef` and `AsyncFunctionDef` nodes |

Result example:

```python
{
    "type": "FORBIDDEN_IMPORT",
    "severity": "violation",
    "message": "'flask' import not allowed (line 5)"
}
```

---

### 3.2 Class: LogWriter

**File:** `agent.py`, lines 310--363
**Purpose:** Writes structured log entries to daily log files in `.agent/logs/`.

#### Methods

**`__init__(self)`**

Creates the `logs/` directory if it does not exist.

**`get_log_file(self)`**

| Attribute | Detail |
|-----------|--------|
| **Returns** | `Path` -- path to today's log file (`YYYY-MM-DD.log`) |

**`write(self, event_type, path, content=None, diff=None, source=None, branch=None)`**

| Attribute | Detail |
|-----------|--------|
| **Parameters** | `event_type: str` -- one of `FILE_CREATED`, `FILE_MODIFIED`, `FILE_DELETED`, `FILE_RENAMED`, `BRANCH_SWITCHED`; `path: str` -- absolute file path; `content: str` (optional) -- full file content for created files; `diff: str` (optional) -- unified diff; `source: str` (optional) -- editor/AI tool identifier; `branch: str` (optional) -- current git branch |
| **Returns** | `None` |
| **Purpose** | Formats a timestamped entry delimited by 80 `=` characters and appends it to the daily log file. |

Log entry format:

```
================================================================================
[2026-02-10 14:30:00] FILE_MODIFIED
PATH: /Users/dev/project/src/main.py
SOURCE: Claude Code (AI)
BRANCH: dev
DIFF:
---
+++
@@ -10,3 +10,5 @@
 existing line
+new line added
+another new line
================================================================================
```

---

### 3.3 Class: FileEventHandler

**File:** `agent.py`, lines 371--553
**Inherits:** `watchdog.events.FileSystemEventHandler`
**Purpose:** Processes filesystem events, computes diffs against an in-memory cache, detects the editor source, runs real-time rule checking, and logs the results.

#### Instance Variables

| Variable | Type | Purpose |
|----------|------|---------|
| `log_writer` | `LogWriter` | Reference to the log writer instance |
| `config` | `dict` | Agent configuration (watched extensions, model) |
| `ignore_pattterns` | `list` | Ignore patterns list |
| `file_contents` | `dict[str, str]` | In-memory cache mapping absolute file paths to their content |
| `_was_paused` | `bool` | Flag indicating the agent was paused; triggers cache refresh |

#### Methods

**`__init__(self, log_writer, config, ignore_patterns)`**

Stores references and calls `_preload_file_contents()` to populate the RAM cache.

**`_preload_file_contents(self)`**

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Walks the project directory tree and reads all files matching watched extensions into `self.file_contents`. Respects ignore patterns. Used on startup and after pause/resume. |

**`_refresh_cache_if_resumed(self)`**

| Attribute | Detail |
|-----------|--------|
| **Purpose** | If `_was_paused` is `True`, re-runs `_preload_file_contents()` and resets the flag. This prevents stale diffs after a branch switch during pause. |

**`should_process(self, path)`**

| Attribute | Detail |
|-----------|--------|
| **Parameters** | `path: str` |
| **Returns** | `bool` |
| **Logic** | Returns `True` only if the file extension is in the watched list and the path does not match any ignore pattern. |

**`get_file_content(self, path)`**

| Attribute | Detail |
|-----------|--------|
| **Parameters** | `path: str` |
| **Returns** | `str` or `None` |
| **Logic** | Safely reads file content via `Path(path).read_text()`. Returns `None` on any exception. |

**`on_created(self, event)`**

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Handles file creation events. Skips directories and paused state. Refreshes cache if recently resumed. Reads content, updates cache, and logs `FILE_CREATED` with branch info. |

**`on_modified(self, event)`**

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Core event handler. Computes unified diff between cached content and new disk content, counts added lines, detects editor source, updates cache, logs `FILE_MODIFIED`, and runs real-time rule checking. |

Logic flow:

```python
new_content = self.get_file_content(path)
old_content = self.file_contents.get(path, "")

if old_content and new_content:
    diff = "\n".join(difflib.unified_diff(
        old_content.splitlines(),
        new_content.splitlines(),
        lineterm=""
    ))

lines_added = sum(1 for line in diff.split('\n')
                  if line.startswith('+') and not line.startswith('+++'))
source = detect_editor_source(path, lines_added)

self.file_contents[path] = new_content
self.log_writer.write("FILE_MODIFIED", path, diff=diff,
                       source=source, branch=get_current_branch())

# Real-time rule checking
rules_data = load_rules()
if rules_data and "rules" in rules_data:
    results = check_file(path, rules_data["rules"])
    violations = [r for r in results if r.get("severity") == "violation"]
    if violations:
        for v in violations:
            print(f"   {v['type']}: {v['message']}")
```

**`on_deleted(self, event)`**

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Logs `FILE_DELETED`, removes file from cache. |

**`on_moved(self, event)`**

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Handles file rename/move events, which are commonly triggered by atomic writes (editors write to a temp file, then rename over the original). Computes diff using the destination path, detects source, logs `FILE_RENAMED`, and runs rule checking. |

---

### 3.4 Class: BranchWatcher

**File:** `agent.py`, lines 556--593
**Purpose:** Polls `.git/HEAD` on a daemon thread to detect branch switches.

#### Instance Variables

| Variable | Type | Purpose |
|----------|------|---------|
| `log_writer` | `LogWriter` | Reference to log writer |
| `poll_interval` | `int` | Seconds between polls (default: 2) |
| `current_branch` | `str` | Currently tracked branch name |
| `_running` | `bool` | Flag controlling the poll loop |
| `_thread` | `Thread` | Daemon thread reference |

#### Methods

**`__init__(self, log_writer, poll_interval=2)`**

Reads the initial branch name from `.git/HEAD` and stores references.

**`start(self)`**

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Spawns a daemon thread running `_poll_loop`. Returns early if not in a git repo. |

**`stop(self)`**

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Sets `_running` to `False` and joins the thread with a 5-second timeout. |

**`_poll_loop(self)`**

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Sleeps for `poll_interval` seconds, reads current branch. If the branch name changed, logs a `BRANCH_SWITCHED` event with the old and new branch names. |

Implementation detail: Reads `.git/HEAD` directly as a file rather than running git commands, avoiding subprocess overhead.

---

### 3.5 Class: ReportEngine

**File:** `agent.py`, lines 597--692
**Purpose:** Reads all activity logs, combines them with project context, and sends the combined prompt to the OpenAI API for report generation.

#### Methods

**`__init__(self, config)`**

Stores config and creates an `openai.OpenAI()` client (reads `OPENAI_API_KEY` from environment).

**`read_all_logs(self, from_date=None, to_date=None)`**

| Attribute | Detail |
|-----------|--------|
| **Parameters** | `from_date: str` (YYYY-MM-DD, optional); `to_date: str` (YYYY-MM-DD, optional) |
| **Returns** | `str` -- concatenated log text |
| **Purpose** | Reads all `.log` files in `.agent/logs/` in chronological order, optionally filtering by date range. |

**`generate_report(self, from_date=None, to_date=None)`**

| Attribute | Detail |
|-----------|--------|
| **Parameters** | `from_date: str` (optional); `to_date: str` (optional) |
| **Returns** | `str` -- report in Markdown format, or `None` if no logs found |
| **Purpose** | Builds a comprehensive prompt from five sources and calls the OpenAI API. |

Prompt construction:

1. Repository purpose (from `purpose.md`)
2. Codebase structure (from `scan.json` -- file, function, class counts)
3. Coding standards (from `standards.md`)
4. Full activity logs
5. Task instructions: produce Summary, Timeline, Alignment Check, Issues, Recommendations

API call:

```python
response = self.client.chat.completions.create(
    model=self.config.get("model", "gpt-4o"),
    max_tokens=4096,
    messages=[{'role': 'user', 'content': prompt}]
)
```

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `model` | `gpt-4o` (default) | Configurable via `config.yaml` |
| `max_tokens` | `4096` | Sufficient for detailed multi-section reports |

After the API call, logs token usage and cost via `log_usage()`.

---

### 3.6 CLI Commands

All commands are implemented as standalone functions and registered via `argparse` subparsers in `main()`. All support the `--project-dir` flag for central install mode.

**`cmd_init()`** (lines 697--803)

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Initialize `.agent/` folder in the current directory. Creates directories and default configuration files. |

Creates the following if they do not already exist:

| File | Content |
|------|---------|
| `.agent/` | Root directory |
| `.agent/logs/` | Log storage directory |
| `.agent/reports/` | Report storage directory |
| `config.yaml` | Default extensions (`.py`, `.js`, `.ts`, `.java`, `.go`), model `gpt-4o`, retention 30 days |
| `standards.md` | Default naming conventions, best practices, security rules |
| `ignore.yaml` | Default ignore patterns (`node_modules/`, `.git/`, `__pycache__/`, etc.) |
| `purpose.md` | Template with Mission, Direction, and Deviation Signals sections |
| `rules.yaml` | Default rules: max 60 function lines, max 800 file lines, forbidden imports/files/patterns |

**`cmd_start()`** (lines 805--855)

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Start the file watcher in foreground mode. |
| **Logic** | 1. Check if already running via PID file. 2. Load config and ignore patterns. 3. Create `LogWriter`, `FileEventHandler`, `Observer`. 4. Create `BranchWatcher`. 5. Save PID to `.agent/.pid`. 6. Register `SIGINT` and `SIGTERM` (Unix only) signal handlers. 7. Start observer and branch watcher. 8. Enter `while True: time.sleep(1)` loop. |

**`cmd_stop()`** (lines 858--877)

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Stop the running agent. Reads PID from file, sends `SIGTERM` (Unix) or runs `taskkill /PID /T /F` (Windows). Removes PID and pause files. |

**`cmd_pause()`** (lines 880--890)

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Creates `.agent/.paused` flag file with ISO timestamp. The agent process stays alive but ignores all file events. |

**`cmd_resume()`** (lines 893--899)

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Removes `.agent/.paused` flag file. Cache refresh happens on the next file event via `_refresh_cache_if_resumed()`. |

**`cmd_status()`** (lines 902--913)

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Reads PID from file, checks if process is alive via `is_pid_alive()`. Cleans up stale PID files. |

**`cmd_report(from_date=None, to_date=None)`** (lines 916--933)

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Creates `ReportEngine`, generates report, prints to console, saves to `reports/report_YYYY-MM-DD_HH-MM-SS.md`. |

**`cmd_logs(date=None)`** (lines 936--956)

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Prints most recent log file, or log for a specific date if `--date` is provided. |

**`cmd_scan()`** (lines 959--1016)

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Walks project directory, calls `scan_file()` for each watched file, aggregates metadata (total files, lines, functions, classes), saves to `scan.json`. |

**`cmd_check()`** (lines 1107--1188)

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Validates all watched files against `rules.yaml`. Walks directory tree, calls `check_file()` for each, separates results into violations and advisories, prints summary with counts. |

---

### 3.7 Main Entry Point

**`main()`** (lines 1196--1283)

Parses CLI arguments via `argparse`:

| Argument | Type | Description |
|----------|------|-------------|
| `--project-dir` | Optional | Target project directory (overrides all global path constants) |
| `command` | Subcommand | One of: `init`, `start`, `stop`, `status`, `report`, `logs`, `scan`, `check`, `pause`, `resume` |
| `--from` (report) | Optional | Start date (YYYY-MM-DD) |
| `--to` (report) | Optional | End date (YYYY-MM-DD) |
| `--date` (logs) | Optional | Specific date (YYYY-MM-DD) |

When `--project-dir` is provided, all global path constants (`AGENT_DIR`, `LOGS_DIR`, `CONFIG_FILE`, etc.) are reassigned to point at the specified directory.

---

### 3.8 Module: UI.py (Streamlit Dashboard)

**File:** `UI.py`
**Lines:** 1,020
**Purpose:** Full web-based dashboard for controlling the agent, viewing logs, managing rules, generating reports, and editing settings.

#### 3.8.1 Constants

```python
PROJECT_DIR  = os.environ.get("AGENT_PROJECT_DIR", os.getcwd())
AGENT_DIR    = os.path.join(PROJECT_DIR, ".agent")
LOGS_DIR     = os.path.join(AGENT_DIR, "logs")
REPORTS_DIR  = os.path.join(AGENT_DIR, "reports")
USAGE_FILE   = os.path.join(AGENT_DIR, "usage", "usage.json")
PURPOSE_FILE = os.path.join(AGENT_DIR, "purpose.md")
RULES_FILE   = os.path.join(AGENT_DIR, "rules.yaml")
CONFIG_FILE  = os.path.join(AGENT_DIR, "config.yaml")
```

#### 3.8.2 Custom CSS

Lines 30--158 define custom CSS classes injected via `st.markdown(unsafe_allow_html=True)`:

| Class | Purpose |
|-------|---------|
| `.metric-card` | Dashboard metrics display (dark background, rounded corners) |
| `.violation-card` | Rule violation display (red left border) |
| `.deviation-card` | Deviation alerts (orange left border) |
| `.success-card` | Success messages (green left border) |
| `.log-entry` | Activity log entry formatting |
| `.activity-row` | Activity timeline row formatting |
| `.source-ai` / `.source-manual` | Color-coded source labels (red for AI, green for manual) |

#### 3.8.3 Helper Functions

**`run_agent_command(command)`**

| Attribute | Detail |
|-----------|--------|
| **Parameters** | `command: str` -- agent subcommand |
| **Returns** | `str` -- combined stdout and stderr output |
| **Purpose** | Runs `python agent.py --project-dir {PROJECT_DIR} {command}` as a subprocess. |

**`is_agent_running()`**

| Attribute | Detail |
|-----------|--------|
| **Returns** | `bool` |
| **Purpose** | Reads `.pid` file, checks process existence via `os.kill(pid, 0)` (Unix) or `tasklist` (Windows). |

**`parse_log_entries(log_text)`**

| Attribute | Detail |
|-----------|--------|
| **Parameters** | `log_text: str` -- raw log file content |
| **Returns** | `list[dict]` -- each dict has keys: `timestamp`, `event`, `path`, `source`, `branch`, `diff`, `content` |
| **Purpose** | Splits log text on 80-character `=` separators and applies regex to extract each field. |

Regex patterns used:

| Field | Pattern |
|-------|---------|
| Timestamp + Event | `\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (\S+)` |
| Path | `PATH: (.+)` |
| Source | `SOURCE: (.+)` |
| Branch | `BRANCH: (.+)` |
| Diff | `DIFF:\n(.*)` (with `re.DOTALL`) |
| Content | `CONTENT:\n(.*)` (with `re.DOTALL`) |

**`get_all_log_entries()`**

| Attribute | Detail |
|-----------|--------|
| **Returns** | `list[dict]` |
| **Purpose** | Reads all `.log` files in reverse date order, parses each. |

**`get_log_dates()`**

| Attribute | Detail |
|-----------|--------|
| **Returns** | `list[str]` -- sorted YYYY-MM-DD strings (most recent first) |

**`parse_check_output(output)`**

| Attribute | Detail |
|-----------|--------|
| **Parameters** | `output: str` -- raw check command output |
| **Returns** | `tuple[list, list]` -- (violations, advisories) |
| **Purpose** | Parses file headers (`[path]`) and tree-formatted entries (`|--`) into structured lists. |

**`get_violation_count()`**

| Attribute | Detail |
|-----------|--------|
| **Returns** | `int` |
| **Purpose** | Runs check command and extracts violation count from `VIOLATIONS FOUND: {n}` output. |

#### 3.8.4 Auto-Start Logic (lines 350--362)

On first render, if `.agent/` exists and the agent is not running, spawns `agent.py start` as a background subprocess via `subprocess.Popen`. Waits 1.5 seconds for the process to start before rendering the dashboard.

#### 3.8.5 First-Run Setup Wizard (lines 364--471)

Detects a fresh `.agent/` by checking if `purpose.md` contains placeholder text or is under 20 characters. Displays a three-step wizard:

1. **Project Purpose** -- Text area for describing the repository mission.
2. **Coding Rules** -- Number inputs for max function/file lines, text areas for forbidden imports and files.
3. **Monitoring Config** -- Comma-separated list of watched file extensions.

Saves wizard inputs to `purpose.md`, `rules.yaml`, and `config.yaml`. Blocks the rest of the UI via `st.stop()` until setup is complete.

#### 3.8.6 Google Sheets Registration (lines 473--501)

On every launch, posts a JSON payload to a Google Apps Script endpoint:

```python
requests.post(GSHEET_URL, json={
    "dev_name": dev_name,
    "project_name": project_name,
    "network_url": f"http://{local_ip}:8501/{project_name}",
    "machine": hostname
}, timeout=5)
```

Fails silently to avoid blocking the dashboard.

#### 3.8.7 Sidebar (lines 508--574)

| Element | Description |
|---------|-------------|
| Status indicator | Green `"Agent Running"` or red `"Agent Stopped"` |
| Start / Stop buttons | Enable/disable based on current state |
| Pause / Resume buttons | Visible only when agent is running |
| Paused warning | Yellow banner during paused state |
| Scan Codebase button | Triggers `scan` command with spinner |
| Navigation radio | Dashboard, Activity Logs, Rule Violations, Reports, Settings |
| Footer | Current working directory and timestamp |

#### 3.8.8 Dashboard Page (lines 581--641)

| Section | Content |
|---------|---------|
| Violations Alert | Runs `check` command, displays violation count and expandable details |
| Recent Activity | Last 10 log entries with color-coded source labels (red=AI, green=manual) and branch tags |
| Repository Purpose | Expandable section showing `purpose.md` content |

#### 3.8.9 Activity Logs Page (lines 648--732)

| Feature | Description |
|---------|-------------|
| Source filter | Selectbox: All, AI Only, Manual Only |
| Event filter | Selectbox: All, FILE_MODIFIED, FILE_CREATED, FILE_DELETED, FILE_RENAMED, BRANCH_SWITCHED |
| Date grouping | Entries grouped by date in expandable sections (most recent expanded by default) |
| Entry display | Timestamp, event type, source label, branch tag, file path |
| Diff viewer | Expandable code block for each entry's diff or content |
| Summary | Total entries across all displayed days |

#### 3.8.10 Rule Violations Page (lines 739--857)

| Section | Content |
|---------|---------|
| Summary metrics | Four columns: Files Checked, Passed, Failed, Advisories |
| Violations section | Grouped by violation type (FORBIDDEN_FILE, FORBIDDEN_IMPORT, FORBIDDEN_PATTERN) with colored severity indicators |
| Advisories section | Grouped by advisory type (FILE_TOO_LONG, FUNCTION_TOO_LONG) with blue indicators |
| Run Check button | Manually triggers a fresh check |

#### 3.8.11 Reports Page (lines 864--907)

| Feature | Description |
|---------|-------------|
| Generate button | Triggers `report` command with spinner ("Generating report via OpenAI...") |
| Current report | Rendered as Markdown |
| Past reports list | Lists all `*.md` files in `reports/` with View buttons |
| Report viewer | Displays selected past report content |

#### 3.8.12 Settings Page (lines 914--1020)

Four tabs:

| Tab | Content |
|-----|---------|
| Config | View/edit `config.yaml` with Save/Cancel buttons |
| Rules | View/edit `rules.yaml` with Save/Cancel buttons |
| Purpose | View/edit `purpose.md` with Save/Cancel buttons |
| API Usage | Input/output token totals, request history list (timestamp, model, purpose, token counts) |

---

### 3.9 Module: extension.js (VS Code Extension)

**File:** `agent-monitor/extension.js`
**Lines:** 242
**Purpose:** VS Code extension that auto-installs the agent, initializes projects, launches the Streamlit dashboard, and provides status bar controls.

#### 3.9.1 Constants

```javascript
const AGENT_HOME = path.join(os.homedir(), '.agent-monitor');
const REPO_URL   = 'https://github.com/prakyath-ux/monitoring_agent.git';
const IS_WIN     = process.platform === 'win32';
const VENV_BIN   = IS_WIN ? 'Scripts' : 'bin';
const PYTHON_CMD = IS_WIN ? 'python' : 'python3';
```

**MIN_ENV Pattern:**

The extension passes a minimal environment to child processes to prevent `ENOBUFS` errors on systems with large environment blocks:

```javascript
// Unix
{ PATH, HOME, USER, LANG }

// Windows
{ PATH, USERPROFILE, HOME, SYSTEMROOT, TEMP, PATHEXT, COMSPEC }
```

#### 3.9.2 Functions

**`activate(context)`**

| Attribute | Detail |
|-----------|--------|
| **Parameters** | `context: vscode.ExtensionContext` |
| **Purpose** | Entry point. Creates a status bar item (left-aligned, priority 100), registers three commands (`agentMonitor.start`, `agentMonitor.stop`, `agentMonitor.status`), and calls `startAgent()` automatically on activation. |

**`deactivate()`**

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Kills the Streamlit process on extension unload. Uses `process.kill(-pid)` (Unix, kills process group) or `taskkill /PID /T /F` (Windows). |

**`getWorkspacePath()`**

| Attribute | Detail |
|-----------|--------|
| **Returns** | `string` or `null` |
| **Purpose** | Returns the first workspace folder's filesystem path, or `null` if no workspace is open. |

**`updateStatusBar(state)`**

| Attribute | Detail |
|-----------|--------|
| **Parameters** | `state: string` -- one of `'running'`, `'stopped'`, `'installing'`, `'starting'` |
| **Purpose** | Updates the status bar icon and color. |

| State | Text | Color |
|-------|------|-------|
| `running` | `$(eye) Agent: Running` | Green (`#4EC9B0`) |
| `stopped` | `$(circle-slash) Agent: Stopped` | Red (`#F44747`) |
| `installing` | `$(sync~spin) Agent: Installing...` | Yellow (`#DCDCAA`) |
| `starting` | `$(loading~spin) Agent: Starting...` | Yellow (`#DCDCAA`) |

**`ensureAgentInstalled()`**

| Attribute | Detail |
|-----------|--------|
| **Returns** | `bool` |
| **Purpose** | Checks if `~/.agent-monitor/agent.py` exists. If not: clones the repository via `execSync`, creates a Python virtual environment via `execFileSync`, and installs pip dependencies. |

Steps:
1. `git clone -b agent_scaling {REPO_URL} "{AGENT_HOME}"` (60s timeout)
2. `python3 -m venv {AGENT_HOME}/venv` (60s timeout)
3. `pip install -r {AGENT_HOME}/requirements.txt` (120s timeout)

**`ensureProjectInit(cwd)`**

| Attribute | Detail |
|-----------|--------|
| **Parameters** | `cwd: string` -- workspace path |
| **Returns** | `bool` |
| **Purpose** | Skips if the directory contains `extension.js` (the extension repo itself). Otherwise, runs `agent.py --project-dir {cwd} init` to create `.agent/`. |

**`startAgent()`**

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Async function. Gets workspace path, skips extension repos. If `.agent/` exists, installs agent and launches dashboard. If `.agent/` does not exist, prompts the user with "Initialize monitoring for this project?" dialog. |

**`launchStreamlit(cwd)`**

| Attribute | Detail |
|-----------|--------|
| **Parameters** | `cwd: string` -- workspace path |
| **Purpose** | Spawns `streamlit run UI.py` as a detached, unreferenced subprocess. Passes `AGENT_PROJECT_DIR` in the environment and sets the base URL path to the project folder name. |

```javascript
streamlitProcess = spawn(streamlitCmd, [
    'run', uiPy,
    '--server.address', '0.0.0.0',
    '--server.baseUrlPath', projectName
], {
    cwd: cwd,
    detached: true,
    stdio: 'ignore',
    env: { ...MIN_ENV, AGENT_PROJECT_DIR: cwd }
});
streamlitProcess.unref();
```

Dashboard URL pattern: `http://localhost:8501/{projectName}`

**`stopAgent()`**

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Kills the Streamlit process (`process.kill(-pid)` on Unix, `taskkill` on Windows) and runs `agent.py --project-dir {cwd} stop` to stop the monitoring agent. |

**`checkStatus()`**

| Attribute | Detail |
|-----------|--------|
| **Purpose** | Runs `agent.py --project-dir {cwd} status` via `execFile`. Displays result in an information notification and updates the status bar accordingly. |

#### 3.9.3 package.json

```json
{
    "name": "agent-monitor",
    "displayName": "Agent Monitor",
    "description": "Auto-starts the directory monitoring agent when .agent/ folder is detected",
    "version": "1.0.0",
    "publisher": "impacto-infra",
    "engines": { "vscode": "^1.85.0" },
    "activationEvents": [ "onStartupFinished" ],
    "main": "./extension.js",
    "contributes": {
        "commands": [
            { "command": "agentMonitor.start",  "title": "Agent: Start" },
            { "command": "agentMonitor.stop",   "title": "Agent: Stop" },
            { "command": "agentMonitor.status", "title": "Agent: Status" }
        ]
    }
}
```

| Field | Value | Purpose |
|-------|-------|---------|
| `activationEvents` | `onStartupFinished` | Extension activates after VS Code has fully started |
| `engines.vscode` | `^1.85.0` | Minimum VS Code version required |
| `contributes.commands` | 3 commands | Registered in the Command Palette |

---

## 4. Environment and Setup

### 4.1 Python Version

The project requires **Python 3.11 or higher**. Python 3.11 is the minimum due to:
- `Path.unlink(missing_ok=True)` parameter (available from Python 3.8, but the project targets 3.11+ per CLAUDE.md).
- `ast.FunctionDef.end_lineno` attribute for function length calculation (available from Python 3.8).
- Broad `except:` clauses used throughout assume modern exception handling behavior.

### 4.2 Operating System Compatibility

| OS | Status | Notes |
|----|--------|-------|
| **macOS** | Fully supported | Primary development platform. Uses `pgrep`, `os.kill()`, `SIGTERM`. FSEvents for file watching. |
| **Linux** | Fully supported | Uses `pgrep`, `os.kill()`, `SIGTERM`. inotify for file watching. |
| **Windows** | Supported | Uses `tasklist`, `taskkill`. `SIGTERM` handler not registered (only `SIGINT`). ReadDirectoryChangesW for file watching. |

### 4.3 Automated Setup (Recommended)

1. Install the `agent-monitor-1.0.0.vsix` extension in VS Code.
2. Open any project folder.
3. Accept the "Initialize monitoring?" prompt.
4. The extension automatically:
   - Clones the agent repository to `~/.agent-monitor/`
   - Creates a Python virtual environment
   - Installs all pip dependencies
   - Initializes `.agent/` in the project
   - Launches the Streamlit dashboard

### 4.4 Manual Setup

```bash
# Step 1: Clone the agent repository
git clone -b agent_scaling https://github.com/prakyath-ux/monitoring_agent.git ~/.agent-monitor

# Step 2: Create virtual environment
cd ~/.agent-monitor
python3 -m venv venv

# Step 3: Activate virtual environment
source venv/bin/activate          # macOS / Linux
# venv\Scripts\activate           # Windows

# Step 4: Install dependencies
pip install -r requirements.txt

# Step 5: Initialize a project
cd /path/to/your/project
python ~/.agent-monitor/agent.py init

# Step 6: Configure the project (edit files in .agent/)
#   .agent/purpose.md    -- describe your project mission
#   .agent/rules.yaml    -- set coding rules
#   .agent/config.yaml   -- set watched file extensions

# Step 7: Start the agent
python ~/.agent-monitor/agent.py --project-dir /path/to/your/project start
```

### 4.5 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | For reports | OpenAI API key. Set in a `.env` file in the project root or export in shell. Loaded via `python-dotenv`. |
| `AGENT_PROJECT_DIR` | No | Overrides the project directory. Used internally by the extension and dashboard. |

### 4.6 Cross-Platform Notes

**Signal handling:**
- macOS / Linux: Registers both `SIGINT` and `SIGTERM` handlers.
- Windows: Only `SIGINT` is registered. Process termination uses `taskkill /PID {pid} /T /F`.

**Process detection:**
- macOS / Linux: `pgrep -f {name}` searches all running process command lines.
- Windows: `tasklist /FI "IMAGENAME eq {name}*"` filters by image name.

**Virtual environment paths:**
- macOS / Linux: `venv/bin/python`, `venv/bin/pip`, `venv/bin/streamlit`
- Windows: `venv\Scripts\python.exe`, `venv\Scripts\pip.exe`, `venv\Scripts\streamlit.exe`

---

## 5. Dependencies

### 5.1 Python Packages

| Package | Version | Purpose |
|---------|---------|---------|
| `watchdog` | >= 3.0.0 | Cross-platform filesystem event monitoring (FSEvents, inotify, ReadDirectoryChangesW) |
| `openai` | Latest | OpenAI API client for GPT-4o report generation |
| `anthropic` | >= 0.18.0 | Anthropic API client (reserved for future use) |
| `pyyaml` | >= 6.0 | YAML configuration file parsing |
| `python-dotenv` | >= 1.0.0 | Loads environment variables from `.env` files |
| `streamlit` | Latest | Web dashboard framework |
| `requests` | Latest | HTTP client for Google Sheets registration (transitive dependency) |

### 5.2 Python Standard Library Modules Used

| Module | Purpose |
|--------|---------|
| `os` | File paths, environment variables, process signals |
| `sys` | System exit, executable path |
| `time` | Sleep intervals for polling loops |
| `signal` | SIGINT and SIGTERM handler registration |
| `argparse` | CLI argument and subcommand parsing |
| `threading` | Daemon thread for BranchWatcher |
| `platform` | OS detection for cross-platform logic |
| `datetime` | Timestamps for log entries and filenames |
| `pathlib` | File existence checks and content reading |
| `difflib` | Unified diff computation between file versions |
| `json` | Serialization for scan.json, usage.json |
| `ast` | Python source parsing for import and function length checks |
| `re` | Regex matching for forbidden patterns and log parsing |
| `subprocess` | Process detection and external command execution |
| `socket` | Hostname and IP resolution for Google Sheets registration |

### 5.3 VS Code Extension Dependencies

- **Runtime:** Node.js built-in modules only (`child_process`, `path`, `fs`, `os`). No npm runtime dependencies.
- **Development:** `@types/vscode` ^1.85.0 (type definitions only).

### 5.4 Installation

```bash
pip install -r requirements.txt
```

Contents of `requirements.txt`:

```
# File system monitoring
watchdog>=3.0.0

# Claude API client
anthropic>=0.18.0

# YAML config parsing
pyyaml>=6.0

# Load .env files
python-dotenv>=1.0.0

# OpenAI
openai

# Streamlit
streamlit
```

---

## 6. Deployment and Execution

### 6.1 Running the Agent (CLI)

```bash
# Initialize project (creates .agent/ with default configs)
python agent.py init

# Start monitoring in foreground
python agent.py start

# Stop monitoring
python agent.py stop

# Check status
python agent.py status

# Central install mode (used by the VS Code extension)
python agent.py --project-dir /path/to/project start
```

### 6.2 Branch Switch Workflow

```bash
# Before switching branches -- pause the agent
python agent.py pause

# Commit your work and switch
git add . && git commit -m "message"
git checkout other-branch

# After switching -- resume the agent
python agent.py resume
```

The pause prevents logging of massive diffs caused by branch file differences. The resume triggers a cache refresh on the next file event, ensuring subsequent diffs are accurate.

### 6.3 Report Generation

```bash
# Generate report from all logs
python agent.py report

# Generate report for a specific date range
python agent.py report --from 2026-02-01 --to 2026-02-10
```

### 6.4 Rule Checking and Scanning

```bash
# Validate code against rules.yaml
python agent.py check

# Scan codebase and save metadata to scan.json
python agent.py scan

# View most recent log
python agent.py logs

# View log for a specific date
python agent.py logs --date 2026-02-10
```

### 6.5 Launching the Dashboard

```bash
# Standard launch
streamlit run UI.py

# With project directory override
AGENT_PROJECT_DIR=/path/to/project streamlit run UI.py
```

Default URL: `http://localhost:8501/`

When launched by the VS Code extension, the URL includes the project name: `http://localhost:8501/{projectName}`

### 6.6 Configuration Files

All configuration lives in the `.agent/` directory inside each project.

**config.yaml** -- Controls monitoring behavior (As per use-case):

```yaml
watch_extensions:
  - ".py"
  - ".js"
  - ".ts"
  - ".java"
  - ".go"
model: gpt-4o
log_retention_days: 30
```

**rules.yaml** -- Defines coding rules for validation (As per use-case):

```yaml
rules:
  max_function_lines: 60
  max_file_lines: 800
  forbidden_imports:
    - flask
    - fastapi
    - django
    - sqlite3
    - sqlalchemy
    - pymongo
  forbidden_files:
    - api.py
    - server.py
    - routes.py
    - models.py
    - auth.py
  forbidden_patterns:
    - pattern: "password\\s*=\\s*['\"]"
      message: "Hardcoded password detected"
    - pattern: "api_key\\s*=\\s*['\"]"
      message: "Hardcoded API key detected"
    - pattern: "secret\\s*=\\s*['\"]"
      message: "Hardcoded secret detected"
```

**ignore.yaml** -- Paths and patterns excluded from monitoring (As per use-case):

```yaml
- node_modules/
- .git/
- __pycache__/
- .agent/logs/
- "*.pyc"
- .env
- "*.log"
```

**purpose.md** -- Free-form Markdown describing the project mission, direction, and deviation signals. Used by the report engine to assess whether changes align with project intent.

**standards.md** -- Free-form Markdown containing company coding standards (naming conventions, best practices, security rules). Used as context for report generation.

### 6.7 Updating the Agent

```bash
cd ~/.agent-monitor
git pull origin agent_scaling
source venv/bin/activate
pip install -r requirements.txt
```

### 6.8 Common Troubleshooting

| Symptom | Cause | Resolution |
|---------|-------|------------|
| "Agent is not running" | No PID file or stale PID | Run `python agent.py start` |
| "Agent already running" | Previous instance still active | Run `python agent.py stop` first |
| ".agent/ folder not found" | Project not initialized | Run `python agent.py init` |
| No diffs appearing in logs | Agent started after files already existed | Run `python agent.py scan` to build the initial cache |
| Large diffs after branch switch | Stale RAM cache from old branch | Use `pause` before switching branches and `resume` after |
| "Failed to clone agent repo" | Network issue or git not installed | Check internet connection and git installation |
| "Failed to set up venv" | Python version too old or missing | Ensure Python 3.11+ is installed and on PATH |
| Report generation fails | Missing `OPENAI_API_KEY` | Set the key in a `.env` file or shell environment |
| Dashboard not loading | Streamlit not installed or port 8501 in use | Run `pip install streamlit` and check that port 8501 is free |
| Extension not activating | VS Code version below 1.85.0 | Update VS Code to the latest version |

---

## 7. Appendices

### 7.1 Glossary

| Term | Definition |
|------|------------|
| **Agent** | The background Python process that monitors filesystem events and logs activity. |
| **Atomic write** | A write strategy where the editor writes to a temporary file, then renames it over the original to prevent data corruption. Triggers `FILE_RENAMED` instead of `FILE_MODIFIED`. |
| **Branch Watcher** | A daemon thread that polls `.git/HEAD` every 2 seconds to detect branch switches. |
| **Bulk change heuristic** | A rule classifying changes with more than 10 added lines as likely AI-generated. |
| **Cache refresh** | The process of re-reading all watched files from disk into RAM after a pause/resume cycle. |
| **Central install** | The `~/.agent-monitor/` directory containing the shared agent code, virtual environment, and dependencies. |
| **FileEventHandler** | The watchdog event handler class that processes file create, modify, delete, and rename events. |
| **LogWriter** | The class that appends structured entries to daily log files in `.agent/logs/`. |
| **MIN_ENV** | The minimal environment variable set passed to child processes by the VS Code extension to prevent `ENOBUFS` errors. |
| **Observer** | The watchdog `Observer` class that monitors a directory tree for filesystem events using OS-native APIs. |
| **PID file** | A file (`.agent/.pid`) containing the running agent's process ID for lifecycle management. |
| **RAM cache** | The in-memory dictionary (`self.file_contents`) storing file contents for diff computation. |
| **ReportEngine** | The class that generates AI analysis reports by sending logs and context to the OpenAI API. |
| **SIGTERM** | A termination signal sent to a process for graceful shutdown. Used on Unix/macOS; not available on Windows. |
| **Source detection** | The process of identifying whether a file change came from an AI tool or manual editing. |
| **Unified diff** | A diff format showing line-by-line changes with `+` for additions and `-` for removals. |
| **Watchdog** | A Python library for monitoring filesystem events using OS-native APIs (FSEvents on macOS, inotify on Linux, ReadDirectoryChangesW on Windows). |

### 7.2 Data Structures Reference

**Log Entry**

```
================================================================================
[2026-02-13 14:30:45] FILE_MODIFIED
PATH: /Users/dev/project/src/main.py
SOURCE: Claude Code (AI)
BRANCH: dev
DIFF:
---
+++
@@ -10,3 +10,5 @@
 existing line
+new line added
+another new line
================================================================================
```

**Scan Data (scan.json)**

```json
{
    "scanned_at": "2026-02-13T14:30:45.123456",
    "files": {
        "src/main.py": {
            "path": "src/main.py",
            "lines": 150,
            "functions": ["main", "helper"],
            "classes": ["MyClass"],
            "imports": ["import os", "from pathlib import Path"]
        }
    },
    "summary": {
        "total_files": 5,
        "total_lines": 750,
        "total_functions": 12,
        "total_classes": 3
    }
}
```

**Usage Data (usage.json)**

```json
{
    "total_input_tokens": 50000,
    "total_output_tokens": 15000,
    "total_cost_usd": 0.15,
    "requests": [
        {
            "timestamp": "2026-02-13T14:30:45.123456",
            "model": "gpt-4o",
            "purpose": "report",
            "input_tokens": 10000,
            "output_tokens": 3000,
            "cost_usd": 0.035
        }
    ]
}
```

**Check File Result**

```json
{
    "type": "FORBIDDEN_IMPORT",
    "severity": "violation",
    "message": "'flask' import not allowed (line 5)"
}
```

### 7.3 File Inventory

| File | Lines | Module | Role |
|------|-------|--------|------|
| `agent.py` | 1,288 | Engine | Monitoring agent, CLI commands, all core classes |
| `UI.py` | 1,020 | Dashboard | Streamlit web interface (5 pages) |
| `extension.js` | 242 | Extension | VS Code extension for auto-setup and launch |
| `package.json` | 27 | Extension | VS Code extension manifest |
| `requirements.txt` | 19 | Config | Python package dependencies |
| **Total** | **~2,596** | | |

### 7.4 External References

| Resource | URL |
|----------|-----|
| Watchdog Documentation | https://python-watchdog.readthedocs.io/ |
| OpenAI API Reference | https://platform.openai.com/docs/api-reference |
| Streamlit Documentation | https://docs.streamlit.io/ |
| VS Code Extension API | https://code.visualstudio.com/api |
| Python difflib | https://docs.python.org/3/library/difflib.html |
| Python ast Module | https://docs.python.org/3/library/ast.html |
| PyYAML Documentation | https://pyyaml.org/wiki/PyYAMLDocumentation |
| python-dotenv | https://pypi.org/project/python-dotenv/ |

---

*Monitor Agent v1.0 -- Impacto Digifin*
