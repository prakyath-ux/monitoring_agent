"""
Local Directory Monitoring Agent
Watches file changes, logs activity, generates reports via Openai API
"""

import os
import sys
import time
import signal
import argparse
import threading
import platform
import subprocess

IS_WINDOWS = platform.system() == "Windows"


def is_pid_alive(pid):
    """Check if a process is running (cross-platform)"""
    if IS_WINDOWS:
        import subprocess
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, text=True, timeout=3,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            return str(pid) in result.stdout
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
from datetime import datetime
from pathlib import Path
import difflib
import yaml
import json

#File watching
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

#Openai API
import openai

# ================================= CONFIGURATION ===================================

# Support --project-dir for central install mode
PROJECT_DIR = os.environ.get("AGENT_PROJECT_DIR", os.getcwd())

# Load .env — check ~/.agent-monitor/.env first (shared key), then project dir
from dotenv import load_dotenv
_agent_env = os.path.join(os.path.expanduser("~"), '.agent-monitor', '.env')
_project_env = os.path.join(PROJECT_DIR, '.env')
if os.path.exists(_agent_env):
    load_dotenv(_agent_env, override=True)
if os.path.exists(_project_env):
    load_dotenv(_project_env, override=True)

AGENT_DIR = os.path.join(PROJECT_DIR, ".agent")
LOGS_DIR = os.path.join(AGENT_DIR, "logs")
CONFIG_FILE = os.path.join(AGENT_DIR, "config.yaml")
STANDARDS_FILE = os.path.join(AGENT_DIR, "standards.md")
IGNORE_FILE = os.path.join(AGENT_DIR, "ignore.yaml")
PID_FILE = os.path.join(AGENT_DIR, ".pid")
PAUSE_FILE = os.path.join(AGENT_DIR, ".paused")
PURPOSE_FILE = os.path.join(AGENT_DIR, "purpose.md")
SCAN_FILE = os.path.join(AGENT_DIR, "scan.json")
REPORTS_DIR = os.path.join(AGENT_DIR, "reports")
RULES_FILE = os.path.join(AGENT_DIR, "rules.yaml")
USAGE_DIR = os.path.join(AGENT_DIR, "usage")
USAGE_FILE = os.path.join(USAGE_DIR, "usage.json")

#GPT-4o models pricing
PRICING = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}

def load_config():
    """ Load agent configuration form .agents/config.yaml """

    if Path(CONFIG_FILE).exists():
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {
        "watch_extensions": [".py", ".js", ".ts", ".java", ".go"],
        "model": "gpt-4o",
        "log_retention_days": 30
    }


def load_ignore_patterns():
    """ Load patterns to ignore from .agent/ignore.yaml """

    if Path(IGNORE_FILE).exists():
        with open(IGNORE_FILE, encoding="utf-8") as f:
            return yaml.safe_load(f) or []
        
    return [
        "node_modules/",
        ".git/",
        "__pycache__/",
        ".agent/logs",
        "*.pyc",
        ".env"
    ]


def load_standards():
    """ Load company code standards from .agent/standards.md """

    if Path(STANDARDS_FILE).exists():
        return Path(STANDARDS_FILE).read_text(encoding="utf-8", errors="replace")
    return "No company standards defined"

def load_purpose():
    """ Load repository purpose from .agent/purpose.md """

    if Path(PURPOSE_FILE).exists():
        return Path(PURPOSE_FILE).read_text(encoding="utf-8", errors="replace")
    return "No repository purpose defined"

def load_rules():
    """ Load rules from .agent/rules.yaml.

    Returns None on missing file OR corrupted YAML — never raises.
    Reports should still generate even if a dev's rules.yaml is broken.
    """
    if not Path(RULES_FILE).exists():
        return None
    try:
        with open(RULES_FILE, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"  Warning: rules.yaml could not be parsed ({e}). Continuing without rules.")
        return None

def load_usage():
    """Load usage data from .agent/usage/usage.json"""
    if Path(USAGE_FILE).exists():
        with open(USAGE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cost_usd": 0.0,
        "requests": []
    }

def log_usage(model, input_tokens, output_tokens,  purpose="report"):
    """Log a single API request to usage file"""
    Path(USAGE_DIR).mkdir(parents=True, exist_ok = True)
    data = load_usage()

    #Calculate Cost
    pricing = PRICING.get(model, PRICING["gpt-4o"])
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    total_cost = input_cost + output_cost

    #update totals
    data["total_input_tokens"] += input_tokens
    data["total_output_tokens"] += output_tokens
    data["total_cost_usd"] += total_cost

    # Add request entry
    data["requests"].append({
        "timestamp": datetime.now().isoformat(),
        "model": model,
        "purpose": purpose,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(total_cost, 6)
    })

    #save
    with open(USAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return total_cost


def detect_editor_source(file_path, diff_lines_added=0):
    """Detect if change came from AI tool or manual edit (cross-platform)"""
    import subprocess
    import platform
    
    system = platform.system()
    
    def process_running(name):
        try:
            if system == "Windows":
                result = subprocess.run(
                    ['tasklist', '/FI', f'IMAGENAME eq {name}*'],
                    capture_output=True, text=True, timeout=2,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                return name.lower() in result.stdout.lower()
            else:
                result = subprocess.run(
                    ['pgrep', '-f', name],
                    capture_output=True, text=True, timeout=2
                )
                return bool(result.stdout.strip())
        except:
            return False
    
    claude_running = process_running('claude')
    cursor_running = process_running('Cursor')
    vscode_running = process_running('Code')
    intellij_running = process_running('idea')
    pycharm_running = process_running('pycharm')
    is_bulk_change = diff_lines_added > 10
    
    if claude_running and is_bulk_change:
        return "Claude Code (AI)"
    elif vscode_running and is_bulk_change:
        return "VS Code (AI Tool)"
    elif vscode_running:
        return "VS Code"
    elif cursor_running and is_bulk_change:
        return "Cursor (AI)"
    elif cursor_running:
        return "Cursor"
    elif intellij_running and is_bulk_change:
        return "IntelliJ (AI Tool)"
    elif pycharm_running and is_bulk_change:
        return "PyCharm (AI Tool)"
    elif intellij_running:
        return "IntelliJ"
    elif pycharm_running:
        return "PyCharm"
    elif is_bulk_change:
        return "AI Tool (likely)"
    else:
        return "Manual Edit"


def get_current_branch():
    """Get the current git branch name, or None if not a git repo"""
    git_head = Path(PROJECT_DIR) / ".git" / "HEAD"
    if not git_head.exists():
        return None
    try:
        content = git_head.read_text(encoding="utf-8", errors="replace").strip()
        if content.startswith("ref: refs/heads/"):
            return content[len("ref: refs/heads/"):]
        return content[:8]
    except Exception:
        return None


def is_paused():
    """Check if the agent is paused (flag file exists)"""
    return Path(PAUSE_FILE).exists()


def scan_file(file_path):
    """ Extract metadata from a single file """
    try:
        content = Path(file_path).read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()

        metadata = {
            "path": str(file_path),
            "lines": len(lines),
            "functions": [],
            "classes": [],
            "imports": []
        }

        for line in lines:
            stripped = line.strip()
            # Detect functions
            if stripped.startswith("def "):
                func_name = stripped[4:stripped.find("(")]
                metadata["functions"].append(func_name)
            #Detcet classes
            elif stripped.startswith("class "):
                class_name = stripped[6:stripped.find("(") if "(" in stripped else stripped.find(":")]
                metadata["classes"].append(class_name)
            #Detect imports
            elif stripped.startswith("import ") or stripped.startswith("from "):
                metadata["imports"].append(stripped)

        return metadata
    except:
        return None

def load_scan():
    """ Load scan data from .agent/scan.json """
    if Path(SCAN_FILE).exists():
        with open(SCAN_FILE, encoding="utf-8") as f:
            return json.load(f)
    return None

def should_ignore(path, ignore_patterns):
    """ Check if a path should be ignored """

    path_str = str(path)
    for pattern in ignore_patterns:
        if pattern.endswith("/"):
            # Directory pattern
            if pattern[:-1] in path_str:
                return True
        elif pattern.startswith("*"):
            # Extension patterns
            if path_str.endswith(pattern[1:]):
                return True
        else:
            # exact match
            if pattern in path_str:
                return True

    return False



# ====================================== LOG WRITER ===============================================

class LogWriter:
    """ Writes user activity logs to .agent/logs"""

    def __init__(self):
        Path(LOGS_DIR).mkdir(parents=True, exist_ok=True)

    def get_log_file(self):
        """ Get today's log file path """
        today = datetime.now().strftime("%Y-%m-%d")
        return Path(LOGS_DIR) / f"{today}.log"

    # def write(self, event_type, path, content=None, diff=None):
    #     """ Write a log entry """
    #     timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    #     log_file = self.get_log_file()

    #     entry = f"\n{'='*80}\n"
    #     entry += f"[{timestamp}] {event_type}\n"
    #     entry += f"PATH: {path}\n"

    #     if diff:
    #         entry += f"DIFF:\n{diff}\n"
    #     elif content:
    #         entry += f"CONTENT:\n{content}\n"

    #     entry += f"{'='*80}\n"

    #     with open(log_file, "a") as f:
    #         f.write(entry)
        
    #     print(f"[{timestamp} {event_type}: {path}]")

    def write(self, event_type, path, content=None, diff=None, source=None, branch=None):
        """ Write a log entry """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file = self.get_log_file()

        entry = f"\n{'='*80}\n"
        entry += f"[{timestamp}] {event_type}\n"
        entry += f"PATH: {path}\n"
        if source:
            entry += f"SOURCE: {source}\n"
        if branch:
            entry += f"BRANCH: {branch}\n"

        if diff:
            entry += f"DIFF:\n{diff}\n"
        elif content:
            entry += f"CONTENT:\n{content}\n"

        entry += f"{'='*80}\n"

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(entry)




# ======================================= FILE WATCHER ==============================================

# File changes → watchdog detects → on_*() method called → log_writer.write()
class FileEventHandler(FileSystemEventHandler):
    """ Handles file system events and logs """

    def __init__(self, log_writer, config, ignore_patterns):
        self.log_writer = log_writer
        self.config = config
        self.ignore_pattterns = ignore_patterns
        self.file_contents = {}
        self._was_paused = False
        self._last_event_time = {}  # path -> timestamp for debounce
        self._pending_changes = {}  # path -> {"first_change": timestamp, "timer": Timer}
        self._batch_silence = 30  # seconds of silence before logging
        self._batch_max_wait = 300  # max 5 minutes before forced log
        self._branch_switching = False  # True during branch switch cooldown
        self._branch_switch_time = 0
        self._branch_switch_cooldown = 5  # seconds to suppress events after branch switch
        self._bulk_events = []  # timestamps of recent events for bulk detection
        self._bulk_threshold = 50  # events within 2 seconds = branch switch
        self._bulk_window = 2  # seconds
        self._preload_file_contents()

    def on_branch_switch(self):
        """Called by BranchWatcher when branch changes — suppress events and refresh cache"""
        self._branch_switching = True
        self._branch_switch_time = time.time()
        # Cancel all pending batched changes (they're from the old branch)
        for path, pending in list(self._pending_changes.items()):
            if pending.get("timer"):
                pending["timer"].cancel()
        self._pending_changes.clear()
        # Refresh RAM cache from disk (new branch files)
        self._preload_file_contents()

    def _detect_bulk_events(self):
        """Detect branch switch by volume — if 50+ events in 2 seconds, it's a switch"""
        now = time.time()
        self._bulk_events.append(now)
        # Remove old events outside the window
        self._bulk_events = [t for t in self._bulk_events if now - t <= self._bulk_window]
        if len(self._bulk_events) >= self._bulk_threshold:
            # Bulk detected — treat as branch switch
            self._bulk_events.clear()
            self.on_branch_switch()
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] Bulk events detected — suppressing (likely branch switch)")
            return True
        return False

    def _is_branch_switching(self):
        """Check if we're in the branch switch cooldown period"""
        if not self._branch_switching:
            return False
        if time.time() - self._branch_switch_time > self._branch_switch_cooldown:
            self._branch_switching = False
            return False
        return True

    def _preload_file_contents(self):
        """Load existing file contents so first edits have diffs"""
        extensions = self.config.get("watch_extensions", [])
        for root, dirs, files in os.walk(PROJECT_DIR):
            dirs[:] = [d for d in dirs if not should_ignore(os.path.join(root, d), self.ignore_pattterns)]
            for f in files:
                fpath = os.path.join(root, f)
                if should_ignore(fpath, self.ignore_pattterns):
                    continue
                if Path(fpath).suffix not in extensions:
                    continue
                abs_path = os.path.abspath(fpath)
                content = self.get_file_content(abs_path)
                if content:
                    self.file_contents[abs_path] = content

    def should_process(self, path):
        """ Check if file should be processed """

        if should_ignore(path, self.ignore_pattterns):
            return False

        # check extensions
        ext = Path(path).suffix
        if ext and ext not in self.config.get("watch_extensions", []):
            return False

        return True

    def get_file_content(self, path):
        """ Safely read file content with retry for Windows file locking """
        for _ in range(3):
            try:
                return Path(path).read_text(encoding="utf-8", errors="replace")
            except (PermissionError, OSError):
                import time
                time.sleep(0.1)
            except Exception:
                return None
        return None
        
    def _refresh_cache_if_resumed(self):
        """After resume from pause, refresh cache to avoid stale diffs from branch switches"""
        if self._was_paused:
            self._was_paused = False
            self._preload_file_contents()
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] Cache refreshed after resume")

    def on_created(self, event):
        """ Handle file creation """
        if event.is_directory:
            return
        if is_paused():
            self._was_paused = True
            return
        if self._is_branch_switching() or self._detect_bulk_events():
            return
        self._refresh_cache_if_resumed()

        path = os.path.abspath(event.src_path)
        if not self.should_process(path):
            return

        content = self.get_file_content(path)
        self.file_contents[path] = content
        self.log_writer.write("FILE_CREATED", path, content=content, branch=get_current_branch())

    def _flush_pending(self, path):
        """Log the batched changes for a file"""
        if path not in self._pending_changes:
            return

        # Remove from pending
        pending = self._pending_changes.pop(path, None)
        if pending and pending.get("timer"):
            pending["timer"].cancel()

        # Get current content from disk vs original cached content
        new_content = self.get_file_content(path)
        old_content = pending.get("original_content", "") if pending else ""

        if old_content and new_content:
            diff = "\n".join(difflib.unified_diff(
                old_content.splitlines(),
                new_content.splitlines(),
                lineterm=""
            ))
        else:
            diff = None

        if not diff:
            self.file_contents[path] = new_content
            return

        lines_added = sum(1 for line in diff.split('\n') if line.startswith('+') and not line.startswith('+++'))
        source = detect_editor_source(path, lines_added)

        self.file_contents[path] = new_content
        self.log_writer.write("FILE_MODIFIED", path, diff=diff, source=source, branch=get_current_branch())
        print(f"  [{datetime.now().strftime('%H:%M:%S')}] FILE_MODIFIED: {path} (via {source})")

    def on_modified(self, event):
        """ Handle file modification — batches rapid changes """
        if event.is_directory:
            return
        if is_paused():
            self._was_paused = True
            return
        if self._is_branch_switching() or self._detect_bulk_events():
            return
        self._refresh_cache_if_resumed()

        path = os.path.abspath(event.src_path)
        if not self.should_process(path):
            return

        now = time.time()

        if path in self._pending_changes:
            # Already tracking this file — reset the silence timer
            pending = self._pending_changes[path]
            if pending.get("timer"):
                pending["timer"].cancel()

            # Check if max wait exceeded — force log
            if now - pending["first_change"] >= self._batch_max_wait:
                self._flush_pending(path)
                # Start fresh tracking
                self._pending_changes[path] = {
                    "first_change": now,
                    "original_content": self.file_contents.get(path, ""),
                    "timer": threading.Timer(self._batch_silence, self._flush_pending, args=[path])
                }
                self._pending_changes[path]["timer"].start()
                return

            # Reset silence timer
            pending["timer"] = threading.Timer(self._batch_silence, self._flush_pending, args=[path])
            pending["timer"].start()
        else:
            # First change to this file — start tracking
            self._pending_changes[path] = {
                "first_change": now,
                "original_content": self.file_contents.get(path, ""),
                "timer": threading.Timer(self._batch_silence, self._flush_pending, args=[path])
            }
            self._pending_changes[path]["timer"].start()

        # Real-time rule checking (silent on success)
        rules_data = load_rules()
        if rules_data and "rules" in rules_data:
            results = check_file(path, rules_data["rules"])
            violations = [r for r in results if r.get("severity") == "violation"]
            if violations:
                print(f"\n[!] VIOLATIONS in {path}:")
                for v in violations:
                    print(f"   - {v['type']}: {v['message']}")


    def on_deleted(self, event):
        """ handle file deletion """
        if event.is_directory:
            return
        if is_paused():
            self._was_paused = True
            return
        if self._is_branch_switching() or self._detect_bulk_events():
            return
        self._refresh_cache_if_resumed()

        path = os.path.abspath(event.src_path)
        if not self.should_process(path):
            return

        # Atomic writes (temp→rename) trigger a ghost DELETE — file still exists on disk
        # Skip logging if the file wasn't actually deleted
        if os.path.exists(path):
            return

        # Keep cache for atomic writes — DELETE may fire before MOVE
        # Preserves old content so on_moved() can produce a proper diff
        self._pending_deletes = getattr(self, '_pending_deletes', {})
        self._pending_deletes[path] = self.file_contents.get(path, "")
        self.file_contents.pop(path, None)
        self.log_writer.write("FILE_DELETED", path, branch=get_current_branch())

    def on_moved(self, event):
        """ Handle file rename/move """
        if event.is_directory:
            return
        if is_paused():
            self._was_paused = True
            return
        if self._is_branch_switching() or self._detect_bulk_events():
            return
        self._refresh_cache_if_resumed()

        dest_path = os.path.abspath(event.dest_path)
        if not self.should_process(dest_path):
            return

        # Debounce: skip if same file was logged within 2 seconds
        now = time.time()
        last = self._last_event_time.get(dest_path, 0)
        if now - last < 2.0:
            return

        # Get old content — check pending deletes first (atomic write pattern)
        self._pending_deletes = getattr(self, '_pending_deletes', {})
        old_content = self.file_contents.get(dest_path, "") or self._pending_deletes.pop(dest_path, "")
        new_content = self.get_file_content(dest_path)

        # Generate diff
        diff = None
        if old_content and new_content:
            diff = "\n".join(difflib.unified_diff(
                old_content.splitlines(),
                new_content.splitlines(),
                lineterm=""
            ))
        elif new_content and not old_content:
            # New file via rename - log full content as diff
            diff = "\n".join(f"+{line}" for line in new_content.splitlines())

        # Count lines added for source detection
        lines_added = 0
        if diff:
            lines_added = sum(1 for line in diff.split('\n') if line.startswith('+') and not line.startswith('+++'))
        source = detect_editor_source(dest_path, lines_added)

        self._last_event_time[dest_path] = now
        self.file_contents[dest_path] = new_content
        self.log_writer.write("FILE_RENAMED", dest_path, diff=diff, source=source, branch=get_current_branch())
        print(f"  [{datetime.now().strftime('%H:%M:%S')}] FILE_RENAMED: {dest_path} (via {source})")

        # Real-time rule checking for renamed files
        rules_data = load_rules()
        if rules_data and "rules" in rules_data:
            results = check_file(dest_path, rules_data["rules"])
            violations = [r for r in results if r.get("severity") == "violation"]
            if violations:
                print(f"\n[!] VIOLATIONS in {dest_path}:")
                for v in violations:
                    print(f"   - {v['type']}: {v['message']}")



class BranchWatcher:
    """Polls .git/HEAD for branch switches and logs them"""

    def __init__(self, log_writer, event_handler=None, poll_interval=2):
        self.log_writer = log_writer
        self.event_handler = event_handler
        self.poll_interval = poll_interval
        self.current_branch = get_current_branch()
        self._running = False
        self._thread = None

    def start(self):
        if self.current_branch is None:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        print(f"  Branch watcher started (current: {self.current_branch})")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _poll_loop(self):
        while self._running:
            time.sleep(self.poll_interval)
            new_branch = get_current_branch()
            if new_branch and new_branch != self.current_branch:
                old_branch = self.current_branch
                self.current_branch = new_branch
                # Suppress file events during branch switch and refresh cache
                if self.event_handler:
                    self.event_handler.on_branch_switch()
                self.log_writer.write(
                    "BRANCH_SWITCHED",
                    ".git/HEAD",
                    content=f"Switched from '{old_branch}' to '{new_branch}'",
                    branch=new_branch
                )
                print(f"  [{datetime.now().strftime('%H:%M:%S')}] BRANCH_SWITCHED: {old_branch} -> {new_branch}")


# ====================================== REPORT ENGINE ======================================
# read_all_logs() → load_standards() → build prompt → OpenAI API → return report
class ReportEngine:
    """ Generate report using Openai API """

    def __init__(self,config):
        self.config = config
        self.client = openai.OpenAI()

    def read_all_logs(self, from_date=None, to_date=None):
        """ Read all log files within date range """

        logs_path = Path(LOGS_DIR)
        if not logs_path.exists():
            return ""
    
        all_logs = []
        for log_file in sorted(logs_path.glob("*.log")):
            # Filter by date if specified
            file_date = log_file.stem  #YYYY-MM-DD
            if from_date and file_date < from_date:
                continue

            all_logs.append(f"\n--- {log_file.name} ---\n")
            all_logs.append(log_file.read_text(encoding="utf-8", errors="replace"))

        return "\n".join(all_logs)

    def generate_report(self, from_date = None, to_date = None):
        """ Generate report from logs using Openai """
        logs = self.read_all_logs(from_date, to_date)
        standards = load_standards()

        if not logs.strip():
            print("No activity logs found.")
            return None

        # Truncate logs if too large for the model's token limits
        # ~4 chars per token, cap logs at ~60K tokens to leave room for prompt + response
        max_log_chars = 240000
        if len(logs) > max_log_chars:
            original_len = len(logs)
            logs = logs[-max_log_chars:]
            # Cut to next complete log entry to avoid partial entries
            first_entry = logs.find("\n[")
            if first_entry > 0:
                logs = logs[first_entry + 1:]
            print(f"  Logs truncated: {original_len:,} -> {len(logs):,} chars (keeping most recent)")
        
        purpose = load_purpose()

        scan_data = load_scan()
        scan_context = ""
        if scan_data:
            scan_context = f"""
## Codebase Structure (from scan)
Total files: {scan_data['summary']['total_files']}
Total lines: {scan_data['summary']['total_lines']}
Functions: {scan_data['summary']['total_functions']}
Classes: {scan_data['summary']['total_classes']}

Files: 
"""

            for path, meta in scan_data['files'].items():
                scan_context += f"- {path}: {meta['lines']} lines, {len(meta['functions'])} functions, {len(meta['classes'])} classes\n"

        rules_data = load_rules()
        rules_context = ""
        if rules_data and "rules" in rules_data:
            r = rules_data["rules"]
            rules_context = f"""
## Rules & Constraints
- Max function lines: {r.get('max_function_lines', 'not set')}
- Max file lines: {r.get('max_file_lines', 'not set')}
- Forbidden imports: {', '.join(r.get('forbidden_imports', [])) or 'none'}
- Forbidden files: {', '.join(r.get('forbidden_files', [])) or 'none'}
"""

        system_prompt = """You are RepoAgent — an autonomous code intelligence system that protects, evaluates, and guides software projects.

You generate reports through five distinct personas. Each persona writes its own section independently, in its own voice. Do NOT repeat the same finding across multiple sections — each persona owns its domain.

**Guardian**: You enforce the project's boundaries. Every change is evaluated against the purpose document. Deviations are verdicts, not suggestions. You classify changes as ALIGNED, DRIFTING, or VIOLATION. You are firm but fair.

**Architect**: You assess the project's structural blueprint — its patterns, component responsibilities, and design philosophy. You detect when new code breaks established patterns, duplicates existing functionality, or adds unnecessary complexity. You speak in terms of structure and design.

**Strategist**: You evaluate the project's trajectory. You assess whether effort is focused on the right areas, detect accumulating technical debt, and identify decisions that need to be made now. You think in terms of priorities and direction.

**Mentor**: You are the constructive voice. You acknowledge good work first, then guide improvement. You explain WHY something matters and HOW to fix it. You reference existing code that shows the right approach. Your tone is encouraging and educational.

**Investigator**: You analyze the source of changes — AI-generated vs manual. You assess whether AI contributions were reviewed and whether they helped or introduced risk. You frame this as quality assurance, never surveillance.

RULES:
- Each persona writes ONLY about its domain. No overlap.
- Be specific — reference actual file names, function names, and code from the logs.
- Every observation must be traceable to evidence in the logs. No generic statements.
- You exist to protect the project's integrity and help teams build better software."""

        prompt = f"""## Project Purpose (Source of Truth)
{purpose}
{scan_context}
{rules_context}
## Coding Standards
{standards}

## Activity Logs
{logs}

---

Generate a deviation report with EXACTLY 5 sections, one per persona. Use these EXACT section headers (they are used for parsing):

## GUARDIAN REPORT
Evaluate every significant change against the purpose document.
- For each change, give a verdict: **ALIGNED** / **DRIFTING** / **VIOLATION**
- If DRIFTING or VIOLATION, specify which boundary or principle is at risk
- Overall project health: On Track / Drifting / At Risk
- Start with a 2-3 sentence executive summary of purpose alignment

## ARCHITECT REPORT
Assess the structural health of the codebase.
- Are new changes consistent with existing patterns?
- Is any functionality being duplicated?
- Is complexity growing beyond what the task requires?
- Architecture health: Stable / Degrading / Improving
- Reference specific files, functions, and patterns

## STRATEGIST REPORT
Evaluate the project's trajectory and priorities.
- Where is the team's effort concentrated? Is it the right area?
- What technical debt is accumulating?
- Are priorities aligned with the roadmap?
- Top 3 priorities for the next development session
- Decisions that need to be made now to prevent future problems

## MENTOR REPORT
Provide constructive guidance for each issue found.
- What was done well (acknowledge good work first)
- For each issue: what it is, why it matters, how to fix it
- Point to existing code that shows the right approach
- Teach the principle behind the fix, not just the fix itself
- Keep the tone encouraging and constructive

## SOURCE ANALYSIS
Analyze the source and quality of changes.
- Breakdown of AI-generated vs manual changes (with file names)
- Any AI-generated code that appears unreviewed (bulk changes with no follow-up edits)
- Quality assessment: are AI contributions helping or introducing risk?
- Frame as quality assurance, not surveillance

Be specific. Reference actual file names, function names, and code from the logs. Do not make generic observations — every point should be traceable to evidence in the logs.
Format in clean markdown."""

        print("Generate report with openai API...")

        response = self.client.chat.completions.create(
            model=self.config.get("model", "gpt-4o"),
            max_tokens=4096,
            messages = [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': prompt}
            ]
        )

        # Log usage
        model = self.config.get("model", "gpt-4o")
        log_usage(
            model=model,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            purpose="report"
        )
        print(f"  Tokens: {response.usage.prompt_tokens} in / {response.usage.completion_tokens} out")

        return response.choices[0].message.content
        

# ================================ CLI COMMANDS ============================================

def cmd_init():
    """Initialize .agent/ folder in current directory"""
    # Create directories
    Path(AGENT_DIR).mkdir(exist_ok=True)
    Path(LOGS_DIR).mkdir(exist_ok=True)
    Path(REPORTS_DIR).mkdir(exist_ok=True)
    
    # Create default config.yaml
    if not Path(CONFIG_FILE).exists():
        default_config = {
            "watch_extensions": [".py", ".js", ".ts", ".java", ".go"],
            "model": "gpt-4o",
            "log_retention_days": 30
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            yaml.dump(default_config, f, default_flow_style=False)
    
    # Create default standards.md
    if not Path(STANDARDS_FILE).exists():
        default_standards = """# Company Coding Standards

## Naming Conventions
- Use camelCase for variables and functions
- Use PascalCase for classes
- Use UPPER_SNAKE_CASE for constants

## Best Practices
- Add error handling for all async operations
- Write docstrings for public functions
- Keep functions under 50 lines, if it is ot possible, mention it in the report 

## Security
- Never hardcode secrets or API keys
- Sanitize all user input
- Use parameterized queries for databases
"""
        Path(STANDARDS_FILE).write_text(default_standards, encoding="utf-8")
    
    # Create default ignore.yaml
    if not Path(IGNORE_FILE).exists():
        default_ignore = [
            "node_modules/", ".git/", "__pycache__/", ".agent/",
            "*.pyc", ".env", "*.log",
            "venv/", ".venv/", "env/",
            ".next/", "dist/", "build/", "target/",
            ".gradle/", ".idea/", ".vscode/",
            "out/", "bin/", ".cache/", ".nuxt/", ".turbo/",
            "coverage/", ".nyc_output/", ".pytest_cache/", ".mypy_cache/",
            "*.min.js", "*.map", "*.class", "*.jar", "*.war",
            ".dart_tool/", ".flutter-plugins", "ios/Pods/",
            "android/.gradle/", "android/build/", "*.apk", "*.ipa",
            ".expo/", "__MACOSX/", ".DS_Store", "Thumbs.db",
            "*.egg-info/", ".tox/", "htmlcov/",
            ".chrome_profile/", ".playwright/", "test-results/",
            "playwright-report/", ".wrangler/", "*.sqlite", "*.db"
        ]
        with open(IGNORE_FILE, "w", encoding="utf-8") as f:
            yaml.dump(default_ignore, f, default_flow_style=False)

    # Create default purpose.md
    if not Path(PURPOSE_FILE).exists():
        default_purpose = """# Repository Purpose

## Mission
[What is this project? One paragraph describing core intent]

## Direction
[Where is this project heading? List current and planned phases]

## Deviation Signals
[What changes would indicate scope creep or wrong direction?]
"""
        Path(PURPOSE_FILE).write_text(default_purpose, encoding="utf-8")
    
    print(f"Initialized agent in {os.getcwd()}")
    print(f"  Created: {AGENT_DIR}/")
    print(f"  Created: {CONFIG_FILE}")
    print(f"  Created: {STANDARDS_FILE}")
    print(f"  Created: {IGNORE_FILE}")
    print(f"  Created: {PURPOSE_FILE} ")

    # Create default rules.yaml file
    if not Path(RULES_FILE).exists():
        default_rules = {
            "rules": {
                "max_function_lines": 60,
                "max_file_lines": 800,
                "forbidden_imports": [
                    "flask",
                    "fastapi",
                    "django",
                    "sqlite3",
                    "sqlalchemy",
                    "pymongo"
                ],

                "forbidden_files": [
                    "api.py",
                    "server.py",
                    "routes.py",
                    "models.py",
                    "auth.py"
                ],

                "forbidden_patterns": [
                    {"pattern": "password\\s*=\\s*['\"]", "message": "Hardcoded password detected"},
                    {"pattern": "api_key\\s*=\\s*['\"]", "message": "Hardcoded API key detected"},
                    {"pattern": "secret\\s*=\\s*['\"]", "message": "Hardcoded secret detected"}
                ]
            }
        }
        with open(RULES_FILE, "w", encoding="utf-8") as f:
            yaml.dump(default_rules, f, default_flow_style=False, sort_keys=False)

    # Ensure .agent/ is in project's .gitignore
    add_agent_to_gitignore()


def add_agent_to_gitignore():
    """Add .agent/ to project's .gitignore and .dockerignore if missing"""
    for ignore_file in [".gitignore", ".dockerignore"]:
        try:
            ignore_path = Path(PROJECT_DIR) / ignore_file
            if ignore_path.exists():
                content = ignore_path.read_text(encoding="utf-8")
                if ".agent/" not in content and ".agent" not in content.splitlines():
                    with open(str(ignore_path), "a", encoding="utf-8") as f:
                        f.write("\n# Agent Monitor\n.agent/\n")
            elif ignore_file == ".gitignore":
                # Only create .gitignore if missing, don't create .dockerignore
                ignore_path.write_text("# Agent Monitor\n.agent/\n", encoding="utf-8")
        except Exception:
            pass


def ensure_agent_files():
    """Self-heal: recreate missing config files if .agent/ exists"""
    if not Path(AGENT_DIR).exists():
        return
    if not Path(CONFIG_FILE).exists():
        default_config = {
            "watch_extensions": [".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt", ".kts",
                                 ".go", ".json", ".xml", ".yaml", ".yml", ".properties",
                                 ".gradle", ".sql", ".html", ".css", ".scss"],
            "model": "gpt-4o",
            "log_retention_days": 30
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            yaml.dump(default_config, f, default_flow_style=False)
    if not Path(RULES_FILE).exists():
        default_rules = {
            "rules": {
                "max_function_lines": 60,
                "max_file_lines": 800,
                "forbidden_imports": [],
                "forbidden_files": [],
                "forbidden_patterns": [
                    {"pattern": "password\\s*=\\s*['\"]", "message": "Hardcoded password detected"},
                    {"pattern": "api_key\\s*=\\s*['\"]", "message": "Hardcoded API key detected"},
                    {"pattern": "secret\\s*=\\s*['\"]", "message": "Hardcoded secret detected"}
                ]
            }
        }
        with open(RULES_FILE, "w", encoding="utf-8") as f:
            yaml.dump(default_rules, f, default_flow_style=False, sort_keys=False)
    if not Path(PURPOSE_FILE).exists():
        Path(PURPOSE_FILE).write_text("# Repository Purpose\n\n## Mission\n[What is this project?]\n\n## Direction\n[Where is this project heading?]\n", encoding="utf-8")
    if not Path(STANDARDS_FILE).exists():
        Path(STANDARDS_FILE).write_text("# Company Coding Standards\n\n## Best Practices\n- Add error handling for all async operations\n- Write docstrings for public functions\n- Keep functions under 50 lines\n", encoding="utf-8")

    # Always merge required ignore patterns into ignore.yaml
    try:
        ignore_file = Path(IGNORE_FILE)
        if ignore_file.exists():
            ignore_data = yaml.safe_load(ignore_file.read_text(encoding="utf-8")) or []
        else:
            ignore_data = []
        required_ignores = [
            ".agent/", "node_modules/", "venv/", ".venv/", "env/", ".git/", "__pycache__/",
            ".next/", "dist/", "build/", "target/", ".gradle/", ".idea/",
            "out/", "bin/", ".cache/", ".nuxt/", ".turbo/", ".vscode/",
            "coverage/", ".nyc_output/", ".pytest_cache/", ".mypy_cache/",
            "*.min.js", "*.map", "*.class", "*.jar", "*.war",
            ".dart_tool/", ".flutter-plugins", "ios/Pods/",
            "android/.gradle/", "android/build/", "*.apk", "*.ipa",
            ".expo/", "__MACOSX/", ".DS_Store", "Thumbs.db",
            "*.egg-info/", ".tox/", "htmlcov/",
            ".chrome_profile/", ".playwright/", "test-results/",
            "playwright-report/", ".wrangler/", "*.sqlite", "*.db",
            "surefire-reports/", "**/target/**"
        ]
        changed = False
        for pattern in required_ignores:
            if pattern not in ignore_data:
                ignore_data.append(pattern)
                changed = True
        if changed:
            with open(str(ignore_file), "w", encoding="utf-8") as f:
                yaml.dump(ignore_data, f, default_flow_style=False)
    except Exception:
        pass


def _kill_pid_file(pid_file):
    """Kill the process recorded in pid_file and remove the file. Best-effort."""
    if not pid_file.exists():
        return
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        if IS_WINDOWS:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            os.kill(pid, 9)
    except Exception:
        pass
    try:
        pid_file.unlink(missing_ok=True)
    except Exception:
        pass


def start_system_heartbeat():
    """Start system-level heartbeat, kill old one first to ensure latest code.

    Also kills the legacy per-IDE .heartbeat.py (inline-generated by older
    JetBrains loaders) — it shipped with a hardcoded port that never
    re-verified, so it raced with the correct system heartbeat and flipped
    the dashboard between right and wrong URLs. System heartbeat is now the
    sole writer.
    """
    agent_home = Path(__file__).resolve().parent
    pid_file = agent_home / ".system_heartbeat_pid"
    legacy_pid_file = agent_home / ".heartbeat_pid"
    heartbeat_script = agent_home / "scripts" / "heartbeat.py"
    if not heartbeat_script.exists():
        return
    # Kill the legacy per-IDE heartbeat (stale code, broken port logic)
    _kill_pid_file(legacy_pid_file)
    # Also clear the script file so the loader writes a fresh one on next IDE open
    legacy_script = agent_home / ".heartbeat.py"
    try:
        legacy_script.unlink(missing_ok=True)
    except Exception:
        pass
    # Kill old system heartbeat so the new one runs with the latest code
    _kill_pid_file(pid_file)
    try:
        kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL}
        if IS_WINDOWS:
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        python_path = agent_home / "venv" / ("Scripts" if IS_WINDOWS else "bin") / ("python.exe" if IS_WINDOWS else "python")
        proc = subprocess.Popen([str(python_path), str(heartbeat_script)], **kwargs)
        pid_file.write_text(str(proc.pid), encoding="utf-8")
    except Exception:
        pass


def _pid_is_alive(pid):
    """Return True if the given PID is still a running process."""
    try:
        if IS_WINDOWS:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            return str(pid) in result.stdout
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False


def ensure_system_heartbeat_alive():
    """Watchdog: if the system heartbeat process has died, respawn it.

    Called from the main loop. Only acts when the heartbeat is actually dead —
    a healthy heartbeat is never touched. Idempotent and safe.
    """
    agent_home = Path(__file__).resolve().parent
    pid_file = agent_home / ".system_heartbeat_pid"
    heartbeat_script = agent_home / "scripts" / "heartbeat.py"
    if not heartbeat_script.exists():
        return
    # If PID file exists and process is alive, do nothing
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            if _pid_is_alive(pid):
                return
        except Exception:
            pass
    # Heartbeat is dead — respawn (use the kill-and-spawn helper for safety)
    start_system_heartbeat()


def ensure_linger_enabled():
    """On Linux, enable systemd user `linger` so the agent service survives logout/reboot.

    Idempotent: checks first, only acts if not already enabled. Silently fails if
    no passwordless sudo — that's the best we can do without admin help.
    """
    if IS_WINDOWS:
        return
    if sys.platform == "darwin":
        return
    try:
        user = os.environ.get("USER") or os.environ.get("USERNAME") or ""
        if not user:
            return
        # Check if linger already enabled
        result = subprocess.run(
            ["loginctl", "show-user", user, "-p", "Linger"],
            capture_output=True, text=True, timeout=5
        )
        if "Linger=yes" in (result.stdout or ""):
            return  # already configured
        # Try to enable. -n means non-interactive; if no passwordless sudo, fails silently.
        subprocess.run(
            ["sudo", "-n", "loginctl", "enable-linger", user],
            capture_output=True, timeout=10
        )
    except Exception:
        pass


PROJECT_CONFIG_FETCH_URL = "http://172.16.0.146:5000/project-config"
# Map of config file basename -> local absolute path. Kept in sync with the
# server-side whitelist in dashboard.py (PROJECT_CONFIG_ALLOWED_FILES).
_PROJECT_CONFIG_FILES = {
    "purpose.md": PURPOSE_FILE,
    "rules.yaml": RULES_FILE,
    "config.yaml": CONFIG_FILE,
    "standards.md": STANDARDS_FILE,
}


def fetch_project_configs():
    """Pull the team-authoritative copy of purpose.md / rules.yaml / etc. for
    THIS project from the central server. Overwrites local file only if the
    server's version is newer (by mtime) than the local one. Silent on network
    failure — server may be down or unreachable.

    Triggered on agent start and during the periodic auto-pull cycle so that
    teammates working on the same project_name converge to a single
    source-of-truth set of config files within a few minutes of any edit.
    """
    from urllib.request import urlopen
    from urllib.parse import quote
    project_name = os.path.basename(PROJECT_DIR)
    if not project_name:
        return
    for file_name, local_path in _PROJECT_CONFIG_FILES.items():
        try:
            url = (
                f"{PROJECT_CONFIG_FETCH_URL}"
                f"?project={quote(project_name)}&file={quote(file_name)}"
            )
            with urlopen(url, timeout=5) as resp:
                if resp.status != 200:
                    continue
                data = json.loads(resp.read().decode("utf-8"))
            server_content = data.get("content", "")
            server_mtime = int(data.get("mtime", 0))
            local_p = Path(local_path)
            local_mtime = int(local_p.stat().st_mtime) if local_p.exists() else 0
            # Only overwrite if server is strictly newer than local
            if server_mtime > local_mtime:
                local_p.parent.mkdir(parents=True, exist_ok=True)
                local_p.write_text(server_content, encoding="utf-8")
        except Exception:
            # Server unreachable, file not on server (404), or any other
            # transient issue — silently move on. Periodic retry handles it.
            continue


def cmd_start():
    """Start the file watcher in background"""
    # Self-heal missing config files
    ensure_agent_files()

    # Pull team-authoritative configs (purpose.md, rules.yaml, etc.) from
    # central server so all devs on this project converge to the same intent
    fetch_project_configs()

    # Best-effort: enable systemd user linger on Linux so service survives logout
    ensure_linger_enabled()

    # Start system heartbeat (independent of IDE)
    start_system_heartbeat()

    # Auto-pull latest code (works for all startup methods: extension, script, OS service)
    agent_home = Path(__file__).resolve().parent
    if (agent_home / ".git").exists():
        try:
            subprocess.run(
                ["git", "-C", str(agent_home), "pull", "origin", "version2"],
                capture_output=True, timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
            )
        except Exception:
            pass

    # Check if already running
    if Path(PID_FILE).exists():
        pid = int(Path(PID_FILE).read_text(encoding="utf-8", errors="replace"))
        if is_pid_alive(pid):
            print(f"Agent already running (PID: {pid})")
            return
    
    # Check if .agent/ exists
    if not Path(AGENT_DIR).exists():
        print("Error: .agent/ folder not found. Run 'python agent.py init' first.")
        return
    
    config = load_config()
    ignore_patterns = load_ignore_patterns()
    log_writer = LogWriter()
    
    event_handler = FileEventHandler(log_writer, config, ignore_patterns)
    # Use PollingObserver on WSL (native file events don't work across WSL boundary)
    is_wsl = os.path.exists("/proc/version") and "microsoft" in open("/proc/version", encoding="utf-8").read().lower()
    if is_wsl:
        from watchdog.observers.polling import PollingObserver
        observer = PollingObserver(timeout=3)
    else:
        observer = Observer()
    observer.schedule(event_handler, PROJECT_DIR, recursive=True)

    # Start branch watcher — connected to event handler for branch switch suppression
    branch_watcher = BranchWatcher(log_writer, event_handler=event_handler)

    # Save PID
    Path(PID_FILE).write_text(str(os.getpid()), encoding="utf-8")

    # Handle shutdown
    def shutdown(signum, frame):
        print("\nStopping agent...")
        observer.stop()
        branch_watcher.stop()
        Path(PID_FILE).unlink(missing_ok=True)
        Path(PAUSE_FILE).unlink(missing_ok=True)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    if not IS_WINDOWS:
        signal.signal(signal.SIGTERM, shutdown)

    observer.start()
    branch_watcher.start()
    print(f"Agent started. Watching: {os.getcwd()}")
    print("Press Ctrl+C to stop.")

    # Periodic auto-pull and self-restart every 4 hours
    last_pull = time.time()
    pull_interval = 2 * 60  # 2 minutes (faster propagation during active development)
    last_pid_touch = time.time()
    pid_touch_interval = 60  # touch PID file every minute as a heartbeat
    last_hb_check = time.time()
    hb_check_interval = 60  # watchdog: revive system heartbeat if it dies

    try:
        while True:
            time.sleep(1)
            # Touch PID file so the IDE extension knows the agent is alive
            if time.time() - last_pid_touch >= pid_touch_interval:
                last_pid_touch = time.time()
                try:
                    Path(PID_FILE).write_text(str(os.getpid()), encoding="utf-8")
                except Exception:
                    pass
            # Watchdog: revive system heartbeat if its process has died
            if time.time() - last_hb_check >= hb_check_interval:
                last_hb_check = time.time()
                try:
                    ensure_system_heartbeat_alive()
                except Exception:
                    pass
            if time.time() - last_pull >= pull_interval:
                last_pull = time.time()
                # Pull team-authoritative project configs from central server
                # so any lead-side edit reaches all devs on the same project
                try:
                    fetch_project_configs()
                except Exception:
                    pass
                agent_home = Path(__file__).resolve().parent
                if (agent_home / ".git").exists():
                    try:
                        result = subprocess.run(
                            ["git", "-C", str(agent_home), "pull", "origin", "version2"],
                            capture_output=True, text=True, timeout=30,
                            creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
                        )
                        # One-time fix: ensure .agent/ is in ignore.yaml (remove after 2026-04-01)
                        # One-time fix: ensure essential patterns in ignore.yaml (remove after 2026-04-01)
                        try:
                            ignore_file = Path(IGNORE_FILE)
                            if ignore_file.exists():
                                ignore_data = yaml.safe_load(ignore_file.read_text(encoding="utf-8")) or []
                                required = [".agent/", "node_modules/", "venv/", ".venv/", "env/", ".git/", "__pycache__/",
                                            ".next/", "dist/", "build/", "target/", ".gradle/", ".idea/",
                                            "out/", "bin/", ".cache/", ".nuxt/", ".turbo/", ".vscode/",
                                            "coverage/", ".nyc_output/", ".pytest_cache/", ".mypy_cache/",
                                            "*.min.js", "*.map", "*.class", "*.jar", "*.war",
                                            ".dart_tool/", ".flutter-plugins", "ios/Pods/",
                                            "android/.gradle/", "android/build/", "*.apk", "*.ipa",
                                            ".expo/", "__MACOSX/", ".DS_Store", "Thumbs.db",
                                            "*.egg-info/", ".tox/", "htmlcov/",
                                            ".chrome_profile/", ".playwright/", "test-results/",
                                            "playwright-report/", ".wrangler/", "*.sqlite", "*.db"]
                                changed = False
                                for pattern in required:
                                    if pattern not in ignore_data:
                                        ignore_data.append(pattern)
                                        changed = True
                                # Remove old partial .agent entries
                                old_agent = [p for p in ignore_data if p.startswith(".agent/") and p != ".agent/"]
                                if old_agent:
                                    ignore_data = [p for p in ignore_data if p not in old_agent]
                                    changed = True
                                if changed:
                                    with open(str(ignore_file), "w", encoding="utf-8") as f:
                                        yaml.dump(ignore_data, f, default_flow_style=False)
                        except Exception:
                            pass

                        # One-time fix: ensure .agent/ in project .gitignore (remove after 2026-04-01)
                        try:
                            add_agent_to_gitignore()
                        except Exception:
                            pass

                        # If new code was pulled, restart the agent
                        if result.returncode == 0 and "Already up to date" not in result.stdout:
                            print("New code detected. Restarting agent...")
                            observer.stop()
                            branch_watcher.stop()
                            Path(PID_FILE).unlink(missing_ok=True)
                            if IS_WINDOWS:
                                subprocess.Popen(
                                    [sys.executable] + sys.argv,
                                    creationflags=subprocess.CREATE_NO_WINDOW
                                )
                                sys.exit(0)
                            else:
                                os.execv(sys.executable, [sys.executable] + sys.argv)
                    except Exception:
                        pass
    except KeyboardInterrupt:
        shutdown(None, None)


def cmd_stop():
    """Stop the running agent"""
    if not Path(PID_FILE).exists():
        print("Agent is not running.")
        return

    pid = int(Path(PID_FILE).read_text(encoding="utf-8", errors="replace"))
    try:
        if IS_WINDOWS:
            import subprocess
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True, timeout=5,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            os.kill(pid, signal.SIGTERM)
        print(f"Agent stopped (PID: {pid})")
    except Exception:
        print("Agent process not found.")

    Path(PID_FILE).unlink(missing_ok=True)
    Path(PAUSE_FILE).unlink(missing_ok=True)


def cmd_pause():
    """Pause the agent's file event logging (process stays alive)"""
    if not Path(PID_FILE).exists():
        print("Agent is not running.")
        return
    if Path(PAUSE_FILE).exists():
        print("Agent is already paused.")
        return
    Path(PAUSE_FILE).write_text(datetime.now().isoformat(), encoding="utf-8")
    print("Agent paused. File events will be ignored.")
    print("Run 'python agent.py resume' to resume logging.")


def cmd_resume():
    """Resume the agent's file event logging"""
    if not Path(PAUSE_FILE).exists():
        print("Agent is not paused.")
        return
    Path(PAUSE_FILE).unlink()
    print("Agent resumed. File events will be logged again.")


def cmd_status():
    """Check if agent is running"""
    if not Path(PID_FILE).exists():
        print("Agent is not running.")
        return

    pid = int(Path(PID_FILE).read_text(encoding="utf-8", errors="replace"))
    if is_pid_alive(pid):
        print(f"Agent is running (PID: {pid})")
    else:
        print("Agent is not running (stale PID file).")
        Path(PID_FILE).unlink(missing_ok=True)


def cmd_report(from_date=None, to_date=None):
    """Generate a report from logged activity"""
    config = load_config()
    engine = ReportEngine(config)
    report = engine.generate_report(from_date, to_date)

    if report:
        #Print report (clean, no separators — stdout is captured by UI)
        print(report)

        #save to file
        Path(REPORTS_DIR).mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        report_file = Path(REPORTS_DIR) / f"report_{timestamp}.md"
        report_file.write_text(report, encoding="utf-8")
        print(f"Report savd to: {report_file}")

        # Upload to central dashboard so leads can access history even when dev is offline
        try:
            upload_report_to_server(report, from_date, to_date, timestamp)
        except Exception as e:
            print(f"  Report upload skipped: {e}")


def upload_report_to_server(report_content, from_date, to_date, timestamp, report_type="report"):
    """POST the generated report to the central dashboard for history archival.

    report_type: "report" for activity-log reports, "architecture" for architecture critiques.
    """
    from urllib.request import Request, urlopen

    DASHBOARD_SERVER = "172.16.0.146"
    DASHBOARD_PORT = 5000

    project_name = os.path.basename(PROJECT_DIR)
    dev_name = os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"
    machine = os.uname().nodename if hasattr(os, "uname") else os.environ.get("COMPUTERNAME", "unknown")

    payload = {
        "type": report_type,
        "dev_name": dev_name,
        "project_name": project_name,
        "machine": machine,
        "from_date": from_date or "",
        "to_date": to_date or "",
        "timestamp": timestamp,
        "content": report_content,
    }

    data = json.dumps(payload).encode("utf-8")
    req = Request(
        f"http://{DASHBOARD_SERVER}:{DASHBOARD_PORT}/upload-report",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=10) as resp:
        if resp.status == 200:
            print(f"  Report uploaded to dashboard history")


# ====================================== ARCHITECTURE ENGINE ======================================
# walk project → build structure summary → load purpose → OpenAI → architecture critique

ARCH_ENTRY_POINTS = {
    "main.py", "app.py", "server.py", "manage.py", "wsgi.py", "asgi.py", "run.py", "__main__.py",
    "index.js", "index.ts", "index.tsx", "main.js", "main.ts", "App.tsx", "App.jsx", "server.js",
    "Main.java", "Application.java", "main.go", "main.rs", "Program.cs",
}
ARCH_MANIFESTS = {
    "requirements.txt", "pyproject.toml", "Pipfile", "setup.py", "setup.cfg",
    "package.json", "tsconfig.json", "pom.xml", "build.gradle", "build.gradle.kts",
    "Cargo.toml", "go.mod", "Gemfile", "composer.json", "Dockerfile", "docker-compose.yml",
    ".env.example", "Makefile",
}
# Folders where real business logic typically lives — sampled aggressively
ARCH_CORE_CODE_DIRS = {
    "src", "lib", "app", "core", "internal", "pkg", "api",
    "services", "service", "controllers", "controller", "models", "model",
    "routes", "router", "handlers", "handler", "views", "view",
    "components", "modules", "domain", "repository", "repositories",
    "backend", "server",
    "main",  # Java: src/main/java
}
ARCH_SOURCE_EXTS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".kt", ".kts", ".go",
    ".rs", ".rb", ".cs", ".cpp", ".c", ".h", ".php", ".scala", ".swift",
}
ARCH_DOC_FILES = {"readme.md", "readme.rst", "readme.txt", "readme"}

def _path_contains_core_dir(rel_path):
    """Return True if any segment of rel_path is a known core-code dir name."""
    parts = rel_path.replace("\\", "/").lower().split("/")
    return any(p in ARCH_CORE_CODE_DIRS for p in parts)


def _extract_py_signatures(source):
    """Best-effort: pull top-level class + function signatures from Python source.
    Returns a list of one-line strings. Empty list if parse fails."""
    try:
        import ast
        tree = ast.parse(source)
    except Exception:
        return []
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = ", ".join(a.arg for a in node.args.args)
            out.append(f"def {node.name}({args})")
        elif isinstance(node, ast.ClassDef):
            bases = ", ".join(getattr(b, "id", "?") for b in node.bases)
            out.append(f"class {node.name}({bases})" if bases else f"class {node.name}")
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = ", ".join(a.arg for a in child.args.args)
                    out.append(f"  - {child.name}({args})")
    return out[:30]  # cap output


def build_architecture_summary(max_depth=10, max_files_per_dir=20,
                                manifest_chars=2000,
                                code_sample_lines=80,
                                code_max_files=30,
                                code_max_file_bytes=100_000,
                                readme_chars=1500):
    """Walk the project and build a code-focused architecture summary for the LLM.

    Returns a string with:
      - directory tree
      - language breakdown
      - entry points (with sampled code)
      - CORE CODE SAMPLES from src/ services/ controllers/ etc. (the primary subject)
      - manifests
      - supplementary readme content
    """
    ignore_patterns = load_ignore_patterns()

    tree_lines = []
    ext_counts = {}
    entry_points = []          # list of (relpath, sampled_code, signatures)
    manifests = {}
    core_code_candidates = []  # list of (size, relpath, abspath) — files in core dirs, source ext
    readmes = {}
    largest_files = []
    total_files = 0

    project_root = os.path.abspath(PROJECT_DIR)

    for root, dirs, files in os.walk(project_root):
        # Compute depth relative to project root
        rel_root = os.path.relpath(root, project_root)
        depth = 0 if rel_root == "." else rel_root.count(os.sep) + 1

        # Filter ignored dirs in place so os.walk skips them
        dirs[:] = sorted([d for d in dirs if not should_ignore(os.path.join(root, d), ignore_patterns)])

        if depth > max_depth:
            dirs[:] = []  # don't descend further
            continue

        # Add this directory to tree
        if rel_root == ".":
            tree_lines.append(f"{os.path.basename(project_root)}/")
        else:
            indent = "  " * depth
            tree_lines.append(f"{indent}{os.path.basename(root)}/")

        # Process files
        kept_files = []
        for fname in sorted(files):
            fpath = os.path.join(root, fname)
            if should_ignore(fpath, ignore_patterns):
                continue
            kept_files.append(fname)

            ext = Path(fname).suffix.lower() or "<no-ext>"
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
            total_files += 1

            relpath = os.path.relpath(fpath, project_root)

            # Entry point detection — store path for later sampling
            if fname in ARCH_ENTRY_POINTS:
                entry_points.append(relpath)

            # Manifest detection (read truncated content)
            if fname in ARCH_MANIFESTS and len(manifests) < 12:
                try:
                    content = Path(fpath).read_text(encoding="utf-8", errors="replace")
                    if len(content) > manifest_chars:
                        content = content[:manifest_chars] + "\n... (truncated)"
                    manifests[relpath] = content
                except Exception:
                    pass

            # README detection — supplementary context only
            if fname.lower() in ARCH_DOC_FILES and len(readmes) < 4:
                try:
                    content = Path(fpath).read_text(encoding="utf-8", errors="replace")
                    if len(content) > readme_chars:
                        content = content[:readme_chars] + "\n... (truncated)"
                    readmes[relpath] = content
                except Exception:
                    pass

            # Track size for largest files
            try:
                size = os.path.getsize(fpath)
                largest_files.append((size, relpath))
            except Exception:
                size = 0

            # Core-code candidate detection: source file inside a core dir
            if (ext in ARCH_SOURCE_EXTS
                    and _path_contains_core_dir(relpath)
                    and size < code_max_file_bytes):
                core_code_candidates.append((size, relpath, fpath))

        # Show only first N files per directory in tree
        for fname in kept_files[:max_files_per_dir]:
            indent = "  " * (depth + 1)
            tree_lines.append(f"{indent}{fname}")
        if len(kept_files) > max_files_per_dir:
            indent = "  " * (depth + 1)
            tree_lines.append(f"{indent}... ({len(kept_files) - max_files_per_dir} more files)")

    # Top largest source files overall (used if no core-dir files found)
    largest_files = [(s, p) for s, p in largest_files if Path(p).suffix.lower() in ARCH_SOURCE_EXTS]
    largest_files.sort(reverse=True)
    top_largest = largest_files[:10]

    # Pick code samples — prefer core-dir files (largest first)
    core_code_candidates.sort(reverse=True)
    chosen_for_sampling = core_code_candidates[:code_max_files]

    # Fallback: if no core-dir source files found, sample the project's largest
    # source files instead (handles flat-layout projects like single-file agents,
    # CLI tools, scripts at root, etc.)
    fallback_used = False
    if not chosen_for_sampling and largest_files:
        fallback_used = True
        for size, relpath in largest_files[:code_max_files]:
            if size >= code_max_file_bytes:
                continue
            abs_p = os.path.join(project_root, relpath)
            chosen_for_sampling.append((size, relpath, abs_p))

    # Always sample entry points too (different list, no overlap by path)
    chosen_paths = {p for _, p, _ in chosen_for_sampling}
    entry_point_samples = []
    for ep in entry_points[:5]:
        if ep in chosen_paths:
            continue
        try:
            abs_p = os.path.join(project_root, ep)
            text = Path(abs_p).read_text(encoding="utf-8", errors="replace")
            head = "\n".join(text.splitlines()[:code_sample_lines])
            sigs = _extract_py_signatures(text) if ep.endswith(".py") else []
            entry_point_samples.append((ep, head, sigs))
        except Exception:
            pass

    # Read code samples for chosen core-dir files
    code_samples = []  # list of (relpath, size, head, signatures)
    for size, relpath, fpath in chosen_for_sampling:
        try:
            text = Path(fpath).read_text(encoding="utf-8", errors="replace")
            head = "\n".join(text.splitlines()[:code_sample_lines])
            sigs = _extract_py_signatures(text) if relpath.endswith(".py") else []
            code_samples.append((relpath, size, head, sigs))
        except Exception:
            continue

    # Language breakdown (sorted by count)
    lang_lines = []
    for ext, count in sorted(ext_counts.items(), key=lambda x: -x[1])[:20]:
        lang_lines.append(f"  {ext}: {count} files")

    parts = []
    parts.append(f"# Project: {os.path.basename(project_root)}")
    parts.append(f"Total tracked files: {total_files}")
    parts.append("")
    parts.append("## Directory Tree")
    parts.append("```")
    parts.extend(tree_lines[:400])  # cap tree to avoid huge prompts
    if len(tree_lines) > 400:
        parts.append(f"... ({len(tree_lines) - 400} more lines truncated)")
    parts.append("```")
    parts.append("")
    parts.append("## Language / File-Type Breakdown")
    parts.extend(lang_lines)
    parts.append("")
    parts.append("## Entry Points Detected")
    if entry_points:
        for ep in entry_points[:20]:
            parts.append(f"  - {ep}")
    else:
        parts.append("  (none detected)")
    parts.append("")

    # Entry point code samples
    if entry_point_samples:
        parts.append("## Entry Point Code (first lines)")
        for ep, head, sigs in entry_point_samples:
            parts.append(f"### {ep}")
            if sigs:
                parts.append("Top-level definitions:")
                for s in sigs:
                    parts.append(f"  {s}")
                parts.append("")
            parts.append("```")
            parts.append(head)
            parts.append("```")
            parts.append("")

    # PRIMARY SUBJECT: core code samples
    parts.append("## CORE CODE SAMPLES (primary subject of analysis)")
    if fallback_used:
        parts.append("This project keeps its source files at the project root (no conventional "
                     "src/ or services/ folder). Sampling the largest source files as the primary "
                     "subject — these represent the actual application logic.")
    else:
        parts.append("These are source files in conventional logic folders (src/, services/, "
                     "controllers/, models/, routes/, handlers/, core/, etc.). "
                     "These represent the actual application logic and should be the focus.")
    parts.append("")
    if code_samples:
        for relpath, size, head, sigs in code_samples:
            parts.append(f"### {relpath} ({size:,} bytes)")
            if sigs:
                parts.append("Top-level definitions:")
                for s in sigs:
                    parts.append(f"  {s}")
                parts.append("")
            parts.append("```")
            parts.append(head)
            parts.append("```")
            parts.append("")
    else:
        parts.append("(No source code files found in this project — analysis will be limited to structure.)")
        parts.append("")

    parts.append("## Largest Source Files (overall, for reference)")
    for size, path in top_largest:
        parts.append(f"  - {path} ({size:,} bytes)")
    parts.append("")

    parts.append("## Manifest / Config Files")
    for path, content in manifests.items():
        parts.append(f"### {path}")
        parts.append("```")
        parts.append(content)
        parts.append("```")
        parts.append("")

    # SUPPLEMENTARY: README/docs — NOT the primary subject
    if readmes:
        parts.append("## Supplementary: README / docs (background context only)")
        parts.append("These are documentation files. They provide context about INTENT but should NOT be the focus of the critique.")
        parts.append("")
        for path, content in readmes.items():
            parts.append(f"### {path}")
            parts.append("```")
            parts.append(content)
            parts.append("```")
            parts.append("")

    return "\n".join(parts)


class ArchitectureEngine:
    """Generate an architecture critique report using OpenAI."""

    def __init__(self, config):
        self.config = config
        self.client = openai.OpenAI()

    def generate(self):
        summary = build_architecture_summary()
        purpose = load_purpose()
        rules_data = load_rules() or {}
        rules = rules_data.get("rules", {})

        # Hard cap on summary length to leave room for response
        max_summary_chars = 200000
        if len(summary) > max_summary_chars:
            summary = summary[:max_summary_chars] + "\n... (summary truncated)"

        system_prompt = """You are RepoAgent's Principal Architecture Analyst.

You are given a project snapshot containing: directory tree, language breakdown, entry points, **actual source code samples from the project's logic folders (src/, services/, controllers/, models/, routes/, handlers/, core/, etc.)**, manifests, and supplementary README content.

Your job is to produce a single architecture-critique report that explains HOW the project is structured, WHAT each piece does, WHY it looks this way, whether it ALIGNS with the stated purpose, and where the architectural leaks/flaws/misalignments are.

**WHAT TO FOCUS ON (in priority order):**
1. **The CORE CODE SAMPLES section** — this is the primary subject. The class/function signatures, imports, and code patterns here tell you what the application actually does. Reason about responsibilities, coupling, layering, naming, and design patterns from these samples.
2. **The entry points and their first lines** — these tell you the runtime shape (web server, CLI, worker, etc.) and the wiring.
3. **Manifests** — for dependency truth and tech stack inference.
4. **Directory tree / language breakdown** — for the overall shape and scale.
5. **README / docs (supplementary)** — context about intent only. **Do NOT make the critique about README quality.** Do not pad strengths with documentation observations. Documentation comments belong only if they're structurally significant (e.g. a misleading README that contradicts code).

**WHAT TO COMMENT ON IN THE CRITIQUE:**
- Specific class and function names from the code samples — e.g. "the `OrderService.process()` method in `src/services/order_service.py` directly calls the database, bypassing the repository layer."
- Architectural patterns observed: MVC, layered, hexagonal, microservice, event-driven — be specific about evidence.
- Coupling between modules: which services call which, where dependencies are tight.
- Separation of concerns: are routes/controllers/services/repositories actually separated, or is logic leaking across layers?
- Error handling, logging, dependency injection — but only where visible in the samples.
- DO NOT critique what you cannot see. If a sample is a partial file (first 80 lines), don't claim a function is missing — say "based on the visible portion".

Tone: a senior architect reviewing a colleague's project. Honest, specific, constructive. Applaud what is genuinely good in the **code**; critique what is genuinely off in the **code**. Never invent files, classes, or functions that aren't visible in the snapshot.

Output strict Markdown with these EXACT section headers (used for parsing):

## OVERVIEW
A 3-5 sentence plain-English description of what this project does, **based on what the actual code samples reveal** (not just the README). State the inferred tech stack from imports/manifests. If the inference is uncertain, say so.

## ARCHITECTURE FLOW
A Mermaid diagram showing the runtime/logical architecture — the major components and HOW THEY CALL OR FLOW INTO EACH OTHER. This is NOT a folder tree. Reason about the code first, then draw the diagram.

How to reason before drawing:
1. From the manifest files and entry points, identify the tech stack and runtime shape (web service, batch job, library, CLI, etc.).
2. Identify the main components: entry point(s), controllers/routes, services/business logic, data access / repositories, external dependencies (DBs, queues, identity providers, third-party APIs).
3. Determine the call direction. In a typical service: client → controller → service → repository → database. In an event-driven system: producer → queue → consumer → store. Use evidence from the manifests; if direction is genuinely ambiguous, fall back to the standard pattern for that stack.

REQUIREMENTS for the diagram (any of these failing means the diagram is unacceptable):
- **Every node MUST have at least one edge (incoming or outgoing).** Disconnected nodes are forbidden. If you cannot connect a node, drop it.
- **Use directed arrows `-->` to show direction of calls / data flow / dependencies.** Label edges when the relationship is non-obvious, e.g. `Service -->|reads/writes| DB`.
- **Hard maximum 12 nodes.** Sweet spot 6–10. A readable diagram beats a complete one.
- **Group by ARCHITECTURAL LAYER, not by folder.** Use these layer subgraphs when applicable: `subgraph Presentation` (controllers, routes, UI), `subgraph Business` (services, use cases, domain logic), `subgraph Data` (repositories, ORM, DAOs), `subgraph External` (DBs, queues, third-party APIs, auth providers).
- **Aggressively collapse similar items into ONE labeled node.** Instead of drawing 5 separate controllers, draw ONE node labeled `OrderControllers [Order, Cart, Payment, Shipping, Status]`. Instead of 8 service classes, draw one `Order Services [several services]` node.
- **Prefer top-down hierarchical flow.** Direction `TB` (top-to-bottom). A typical flow: top layer (entry) → middle layer (services) → bottom layer (data + external).
- **No layer-skipping shortcuts.** A Controller should not have an arrow directly to a DB. The path goes Controller → Service → Repository → DB.
- **Aim for clarity, not completeness.** Drop nodes that don't show in the architectural story. Junior engineers should be able to read this diagram in 30 seconds.

CRITICAL FORMAT — the diagram MUST be wrapped in a fenced code block tagged `mermaid`:

```mermaid
flowchart TB
    subgraph App
        Controller --> Service
        Service --> Repository
    end
    subgraph External
        DB[("PostgreSQL")]
        Auth[("Keycloak")]
    end
    Repository --> DB
    Controller --> Auth
```

MERMAID SYNTAX RULES (failing these breaks rendering):
- Node IDs must be alphanumeric only (A, B, Node1, ServiceA). NO hyphens, dots, slashes, or spaces in IDs.
- Subgraph names with hyphens, dots, slashes, or spaces MUST be wrapped in double quotes. Correct: `subgraph "iform-service"`. Wrong: `subgraph iform-service`.
- **If a node label contains parentheses, commas, slashes, or angle brackets, wrap the ENTIRE label in double quotes.** Mermaid treats unquoted parens as a different node shape. Correct: `Service["Order Service (handles orders, returns)"]`. Wrong: `Service[Order Service (handles orders, returns)]`. Wrong: `App[App.jsx (Next.js app shell)]`.
- For multi-line labels, use `\n` inside the quoted label: `A["Line one\nLine two"]`.
- **Do NOT use `classDef` or `class` styling directives.** The renderer applies its own visual theme. Adding `classDef` is unnecessary and often introduces parse errors.

Do NOT include an ASCII tree version. Do NOT just list folders. The system renders the Mermaid block as an actual visual diagram.

## ALIGNMENT WITH PURPOSE
Quote 1-2 lines from purpose.md, then give a verdict: ALIGNED / PARTIALLY ALIGNED / DRIFTING / VIOLATION. Justify the verdict with specific file/module evidence.

## STRENGTHS
Bullet list. Each item: a specific architectural strength **with concrete code evidence — cite class names, function names, or specific files from the CORE CODE SAMPLES**. Not generic ("good naming"); concrete ("clear separation: `OrderController` in `src/controllers/order_controller.py` only handles HTTP concerns, delegates business logic to `OrderService`"). 3-6 items. **No items about README/docs quality.**

## CONCERNS, FLAWS & LEAKS
Bullet list. Each item formatted as:
- **<Issue>** — <one-line description grounded in actual code evidence>
  - WHERE: <specific file, class, or function from the samples>
  - WHY IT MATTERS: <one sentence about real-world impact>
  - HOW TO FIX: <one concrete refactor suggestion referencing the code>
3-8 items. Prioritize structural / code-level issues (coupling, layering violations, missing abstractions, fat controllers, etc.) over style. **No items about README/docs unless documentation actively misleads about the code.**

## RECOMMENDATIONS
A short prioritized list (P0 / P1 / P2). Each item: one sentence on the change + one sentence on the expected benefit. Maximum 6 items.

Rules:
- Be specific. Reference actual **class names, function names, and file paths from the CORE CODE SAMPLES**.
- Never fabricate. If a sample is only a partial file, say "based on visible portion".
- No hedging fluff. No corporate speak.
- Do NOT critique README or documentation quality unless docs actively contradict the code.
- The report goes to the developer who built this project AND their lead. They want to understand their CODE, not their README.
"""

        user_content = f"""## Stated Purpose
{purpose}

## Coding Rules / Constraints
- Max function lines: {rules.get('max_function_lines', 'not set')}
- Max file lines: {rules.get('max_file_lines', 'not set')}
- Forbidden imports: {', '.join(rules.get('forbidden_imports', [])) or 'none'}
- Forbidden files: {', '.join(rules.get('forbidden_files', [])) or 'none'}

## Project Structure Snapshot
{summary}
"""

        # Architecture analysis always uses a stronger model than regular reports.
        # Hardcoded here so every dev gets the same quality regardless of local config.yaml.
        model = "gpt-5.1"
        print(f"  Calling {model} for architecture analysis...")
        resp = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
        )
        log_usage(model, resp.usage.prompt_tokens, resp.usage.completion_tokens, "architecture")
        print(f"  Tokens: {resp.usage.prompt_tokens} in / {resp.usage.completion_tokens} out")
        return resp.choices[0].message.content


def cmd_architecture():
    """Generate an architecture critique report for the current project."""
    if not Path(AGENT_DIR).exists():
        print("Error: .agent/ folder not found. Run 'python agent.py init'")
        return

    config = load_config()
    engine = ArchitectureEngine(config)
    report = engine.generate()

    if not report:
        print("Architecture analysis returned empty.")
        return

    print(report)

    Path(REPORTS_DIR).mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    report_file = Path(REPORTS_DIR) / f"architecture_{timestamp}.md"
    report_file.write_text(report, encoding="utf-8")
    print(f"Architecture report saved to: {report_file}")

    try:
        upload_report_to_server(report, None, None, timestamp, report_type="architecture")
    except Exception as e:
        print(f"  Architecture upload skipped: {e}")


def cmd_logs(date=None):
    """View recent logs"""
    logs_path = Path(LOGS_DIR)
    if not logs_path.exists():
        print("No logs found.")
        return
    
    if date:
        log_file = logs_path / f"{date}.log"
        if log_file.exists():
            print(log_file.read_text(encoding="utf-8", errors="replace"))
        else:
            print(f"No logs for {date}")
    else:
        # Show most recent log
        log_files = sorted(logs_path.glob("*.log"), reverse=True)
        if log_files:
            print(f"--- {log_files[0].name} ---")
            print(log_files[0].read_text(encoding="utf-8", errors="replace"))
        else:
            print("No logs found.")


def cmd_scan():
    """ Scan existing codebase and build index """
    if not Path(AGENT_DIR).exists():
        print("Error: .agent/ folder not found. Run 'python agent.py init' ")
        return 

    config = load_config()
    ignore_patterns = load_ignore_patterns()
    extensions = config.get("watch_extensions", [])

    scan_data = {
        "scanned_at": datetime.now().isoformat(),
        "files": {},
        "summary": {
            "total_files": 0,
            "total_lines": 0,
            "total_functions": 0,
            "total_classes": 0
        }
    }

    print("Scanning codebase...")

    for root, dirs, files in os.walk(PROJECT_DIR):
        # Skip ignored directories
        dirs[:] = [d for d in dirs if not should_ignore(os.path.join(root, d), ignore_patterns)]

        for file in files:
            file_path = os.path.join(root, file)

            #Skip ignored files
            if should_ignore(file_path, ignore_patterns):
                    continue

            #check extension
            ext = Path(file_path).suffix
            if ext not in extensions:
                continue

            metadata = scan_file(file_path)
            if metadata:
                scan_data["files"][file_path] = metadata
                scan_data["summary"]["total_files"] += 1
                scan_data["summary"]["total_lines"] += metadata["lines"]
                scan_data["summary"]["total_functions"] += len(metadata["functions"])
                scan_data["summary"]["total_classes"] += len(metadata["classes"])
                print(f"  Scanned: {file_path} ")

        # save scan data
    with open(SCAN_FILE, "w", encoding="utf-8") as f:
        json.dump(scan_data, f, indent=2)

    print(f"\n Scan Complete! ")
    print(f" Files: {scan_data['summary']['total_files']}")
    print(f" Lines: {scan_data['summary']['total_lines']}")
    print(f"  Functions: {scan_data['summary']['total_functions']}")
    print(f"  Classes: {scan_data['summary']['total_classes']}")
    print(f"  Saved to: {SCAN_FILE}")


def check_file(file_path, rules):
    """Check a single file against rules, return list of violations and advisories"""
    import ast
    import re

    results = []
    file_name = os.path.basename(file_path)

    #check forbidden file names
    forbidden_files = rules.get("forbidden_files", [])
    if file_name in forbidden_files:
        results.append({
            "type": "FORBIDDEN_FILE",
            "severity": "violation",
            "message": f"File name '{file_name}' is not allowed"
        })

    # Read file content
    try:
        with open(file_path, 'r', encoding="utf-8") as f:
            content = f.read()
            lines = content.split('\n')
    except Exception as e:
        return [{"type": "ERROR", "severity": "violation", "message": f"Could not read file {e}"}]

    # Check file lines (advisory, not violation)
    max_file_lines = rules.get("max_file_lines", 800)
    if len(lines) > max_file_lines:
        results.append({
            "type": "FILE_TOO_LONG",
            "severity": "advisory",
            "message": f"File has {len(lines)} lines (threshold: {max_file_lines}) — consider reviewing"
        })

    #check forbidden patterns
    forbidden_patterns = rules.get("forbidden_patterns", [])
    for pattern_rule in forbidden_patterns:
        pattern = pattern_rule.get("pattern", "")
        message = pattern_rule.get("message", "Forbidden pattern found")
        for i, line in enumerate(lines, 1):
            if re.search(pattern, line):
                results.append({
                    "type": "FORBIDDEN_PATTERN",
                    "severity": "violation",
                    "message": f"{message} (line {i})"
                })

    # Python specific checks
    if file_path.endswith('.py'):
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return results

        # Check forbidden imports
        forbidden_imports = rules.get("forbidden_imports", [])
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in forbidden_imports:
                        results.append({
                            "type": "FORBIDDEN_IMPORT",
                            "severity": "violation",
                            "message": f"'{alias.name}' import not allowed (line {node.lineno})"
                        })
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split('.')[0] in forbidden_imports:
                    results.append({
                        "type": "FORBIDDEN_IMPORT",
                        "severity": "violation",
                        "message": f"'{node.module}' import not allowed (line {node.lineno})"
                    })

        # Check function line counts (advisory, not violation)
        max_func_lines = rules.get("max_function_lines", 50)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_lines = node.end_lineno - node.lineno + 1
                if func_lines > max_func_lines:
                    results.append({
                        "type": "FUNCTION_TOO_LONG",
                        "severity": "advisory",
                        "message": f"'{node.name}' has {func_lines} lines (threshold: {max_func_lines}) — consider refactoring"
                    })

    return results


def cmd_check():
    """Check codebase against rules.yaml"""
    if not Path(AGENT_DIR).exists():
        print("Agent not initialized. Run 'python agent.py init' first.")
        return

    rules_data = load_rules()
    if not rules_data or "rules" not in rules_data:
        print("No rules.yaml found or empty. Run 'python agent.py init' to create default rules.")
        return

    rules = rules_data["rules"]
    config = load_config()
    extensions = config.get("watch_extensions", [".py"])
    ignore_patterns = load_ignore_patterns()

    print("Checking codebase against rules...\n")

    all_violations = {}
    all_advisories = {}
    files_checked = 0
    files_passed = 0
    files_failed = 0

    for root, dirs, files in os.walk(PROJECT_DIR):
        dirs[:] = [d for d in dirs if not should_ignore(os.path.join(root, d), ignore_patterns)]

        for file in files:
            file_path = os.path.join(root, file)

            if should_ignore(file_path, ignore_patterns):
                continue

            ext = Path(file_path).suffix
            if ext not in extensions:
                continue

            files_checked += 1
            results = check_file(file_path, rules)

            violations = [r for r in results if r.get("severity") == "violation"]
            advisories = [r for r in results if r.get("severity") == "advisory"]

            if violations:
                all_violations[file_path] = violations
                files_failed += 1
            elif advisories:
                files_passed += 1
            else:
                files_passed += 1

            if advisories:
                all_advisories[file_path] = advisories

    # Print violations
    if all_violations:
        total_violations = sum(len(v) for v in all_violations.values())
        print(f"VIOLATIONS FOUND: {total_violations}\n")

        for file_path, violations in all_violations.items():
            print(f"[{file_path}]")
            for v in violations:
                print(f"  - {v['type']}: {v['message']}")
            print()
    else:
        print("No violations found.\n")

    # Print advisories
    if all_advisories:
        total_advisories = sum(len(a) for a in all_advisories.values())
        print(f"ADVISORIES: {total_advisories}\n")

        for file_path, advisories in all_advisories.items():
            print(f"[{file_path}]")
            for a in advisories:
                print(f"  - {a['type']}: {a['message']}")
            print()

    print(f"Files checked: {files_checked}")
    print(f"Passed: {files_passed}")
    print(f"Failed: {files_failed}")






# ===================================== MAIN ========================================

def main():
    parser = argparse.ArgumentParser(description="Local Directory Monitoring Agent")
    parser.add_argument("--project-dir", help="Target project directory (default: current directory)")
    subparsers = parser.add_subparsers(dest="command", help = "Commands")

    #init
    subparsers.add_parser("init", help="Initialize .agent/ folder")

    # start
    subparsers.add_parser("start", help="Start monitoring")
    
    # stop
    subparsers.add_parser("stop", help="Stop monitoring")
    
    # status
    subparsers.add_parser("status", help="Check agent status")
    
    # report
    report_parser = subparsers.add_parser("report", help="Generate report")
    report_parser.add_argument("--from", dest="from_date", help="Start date (YYYY-MM-DD)")
    report_parser.add_argument("--to", dest="to_date", help="End date (YYYY-MM-DD)")
    
    # logs
    logs_parser = subparsers.add_parser("logs", help="View logs")
    logs_parser.add_argument("--date", help="Specific date (YYYY-MM-DD)")

    # scan
    subparsers.add_parser("scan", help="Scan existing codebase")

    #check
    subparsers.add_parser("check", help="Check code against rules")

    # pause
    subparsers.add_parser("pause", help="Pause event logging (agent stays alive)")

    # resume
    subparsers.add_parser("resume", help="Resume event logging")

    # architecture
    subparsers.add_parser("architecture", help="Generate architecture critique report for this project")

    
    args = parser.parse_args()

        # Override PROJECT_DIR if --project-dir is provided
    if args.project_dir:
        global PROJECT_DIR, AGENT_DIR, LOGS_DIR, CONFIG_FILE, STANDARDS_FILE
        global IGNORE_FILE, PID_FILE, PAUSE_FILE, PURPOSE_FILE, SCAN_FILE
        global REPORTS_DIR, RULES_FILE, USAGE_DIR, USAGE_FILE
        PROJECT_DIR = os.path.abspath(args.project_dir)
        AGENT_DIR = os.path.join(PROJECT_DIR, ".agent")
        LOGS_DIR = os.path.join(AGENT_DIR, "logs")
        CONFIG_FILE = os.path.join(AGENT_DIR, "config.yaml")
        STANDARDS_FILE = os.path.join(AGENT_DIR, "standards.md")
        IGNORE_FILE = os.path.join(AGENT_DIR, "ignore.yaml")
        PID_FILE = os.path.join(AGENT_DIR, ".pid")
        PAUSE_FILE = os.path.join(AGENT_DIR, ".paused")
        PURPOSE_FILE = os.path.join(AGENT_DIR, "purpose.md")
        SCAN_FILE = os.path.join(AGENT_DIR, "scan.json")
        REPORTS_DIR = os.path.join(AGENT_DIR, "reports")
        RULES_FILE = os.path.join(AGENT_DIR, "rules.yaml")
        USAGE_DIR = os.path.join(AGENT_DIR, "usage")
        USAGE_FILE = os.path.join(USAGE_DIR, "usage.json")

    
    if args.command == "init":
        cmd_init()
    elif args.command == "start":
        cmd_start()
    elif args.command == "stop":
        cmd_stop()
    elif args.command == "status":
        cmd_status()
    elif args.command == "report":
        cmd_report(args.from_date, args.to_date)
    elif args.command == "logs":
        cmd_logs(args.date)
    elif args.command == "scan":
        cmd_scan()
    elif args.command == "check":
        cmd_check()
    elif args.command == "pause":
        cmd_pause()
    elif args.command == "resume":
        cmd_resume()
    elif args.command == "architecture":
        cmd_architecture()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()




