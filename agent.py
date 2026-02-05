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
from datetime import datetime
from pathlib import Path
import difflib
import yaml
import json

# Load .env file
from dotenv import load_dotenv
load_dotenv()

#File watching
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

#Openai API
import openai

# ================================= CONFIGURATION ===================================

AGENT_DIR = ".agent"
LOGS_DIR = f"{AGENT_DIR}/logs"
CONFIG_FILE = f"{AGENT_DIR}/config.yaml"
STANDARDS_FILE = f"{AGENT_DIR}/standards.md"
IGNORE_FILE = f"{AGENT_DIR}/ignore.yaml"
PID_FILE = f"{AGENT_DIR}/.pid"
PAUSE_FILE = f"{AGENT_DIR}/.paused"
PURPOSE_FILE = f"{AGENT_DIR}/purpose.md"
SCAN_FILE = f"{AGENT_DIR}/scan.json"
REPORTS_DIR = f"{AGENT_DIR}/reports"
RULES_FILE = f"{AGENT_DIR}/rules.yaml"
USAGE_DIR = f"{AGENT_DIR}/usage"
USAGE_FILE = f"{USAGE_DIR}/usage.json"

#GPT-4o models pricing
PRICING = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}

def load_config():
    """ Load agent configuration form .agents/config.yaml """

    if Path(CONFIG_FILE).exists():
        with open(CONFIG_FILE) as f:
            return yaml.safe_load(f)
    return {
        "watch_extensions": [".py", ".js", ".ts", ".java", ".go"],
        "model": "gpt-4o",
        "log_retention_days": 30
    }


def load_ignore_patterns():
    """ Load patterns to ignore from .agent/ignore.yaml """

    if Path(IGNORE_FILE).exists():
        with open(IGNORE_FILE) as f:
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
        return Path(STANDARDS_FILE).read_text()
    return "No company standards defined"

def load_purpose():
    """ Load repository purpose from .agent/purpose.md """

    if Path(PURPOSE_FILE).exists():
        return Path(PURPOSE_FILE).read_text()
    return "No repository purpose defined"

def load_rules():
    """ Load rules from .agent/rules.yaml """
    if Path(RULES_FILE).exists():
        with open(RULES_FILE) as f:
            return yaml.safe_load(f)
    return None

def load_usage():
    """Load usage data from .agent/usage/usage.json"""
    if Path(USAGE_FILE).exists():
        with open(USAGE_FILE) as f:
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
    with open(USAGE_FILE, "w") as f:
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
                    capture_output=True, text=True, timeout=2
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
    elif is_bulk_change:
        return "AI Tool (likely)"
    else:
        return "Manual Edit"


def get_current_branch():
    """Get the current git branch name, or None if not a git repo"""
    git_head = Path(".git/HEAD")
    if not git_head.exists():
        return None
    try:
        content = git_head.read_text().strip()
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
        content = Path(file_path).read_text()
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
        with open(SCAN_FILE) as f:
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

        with open(log_file, "a") as f:
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
        self._preload_file_contents()

    def _preload_file_contents(self):
        """Load existing file contents so first edits have diffs"""
        extensions = self.config.get("watch_extensions", [])
        for root, dirs, files in os.walk("."):
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
        """ Safely read file content """
        try:
            return Path(path).read_text()
        except:
            return None 
        
    def on_created(self, event):
        """ Handle file creation """
        if event.is_directory:
            return
        if is_paused():
            return

        if not self.should_process(event.src_path):
            return
        
        content = self.get_file_content(event.src_path)
        self.file_contents[event.src_path] = content
        self.log_writer.write("FILE_CREATED", event.src_path, content=content, branch=get_current_branch())

    def on_modified(self, event):
        """ Handle file modification """
        if event.is_directory:
            return
        if is_paused():
            return

        if not self.should_process(event.src_path):
            return
        
        new_content = self.get_file_content(event.src_path)
        old_content = self.file_contents.get(event.src_path, "")
        

        # generate diff
        if old_content and new_content:
            diff = "\n".join(difflib.unified_diff(
                old_content.splitlines(),
                new_content.splitlines(),
                lineterm=""
            ))
        else:
            diff = None
        
                # Count lines added and detect source
        lines_added = 0
        if diff:
            lines_added = sum(1 for line in diff.split('\n') if line.startswith('+') and not line.startswith('+++'))
        source = detect_editor_source(event.src_path, lines_added)


        self.file_contents[event.src_path] = new_content
        self.log_writer.write("FILE_MODIFIED", event.src_path, diff=diff, source=source, branch=get_current_branch())
        print(f"  [{datetime.now().strftime('%H:%M:%S')}] FILE_MODIFIED: {event.src_path} (via {source})")

        # Real-time rule checking (silent on success)
        rules_data = load_rules()
        if rules_data and "rules" in rules_data:
            results = check_file(event.src_path, rules_data["rules"])
            violations = [r for r in results if r.get("severity") == "violation"]
            if violations:
                print(f"\n⚠️  VIOLATIONS in {event.src_path}:")
                for v in violations:
                    print(f"   └── {v['type']}: {v['message']}")


    def on_deleted(self, event):
        """ handle file deletion """
        if event.is_directory:
            return
        if is_paused():
            return

        if not self.should_process(event.src_path):
            return
        
        self.file_contents.pop(event.src_path, None)
        self.log_writer.write("FILE_DELETED", event.src_path, branch=get_current_branch())

    def on_moved(self, event):
        """ Handle file rename/move """
        if event.is_directory:
            return
        if is_paused():
            return

        if not self.should_process(event.dest_path):
            return

        # Get old and new content for diff
        old_content = self.file_contents.get(event.dest_path, "")
        new_content = self.get_file_content(event.dest_path)

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
        source = detect_editor_source(event.dest_path, lines_added)

        self.file_contents[event.dest_path] = new_content
        self.log_writer.write("FILE_RENAMED", event.dest_path, diff=diff, source=source, branch=get_current_branch())
        print(f"  [{datetime.now().strftime('%H:%M:%S')}] FILE_RENAMED: {event.dest_path} (via {source})")

        # Real-time rule checking for renamed files
        rules_data = load_rules()
        if rules_data and "rules" in rules_data:
            results = check_file(event.dest_path, rules_data["rules"])
            violations = [r for r in results if r.get("severity") == "violation"]
            if violations:
                print(f"\n⚠️  VIOLATIONS in {event.dest_path}:")
                for v in violations:
                    print(f"   └── {v['type']}: {v['message']}")



class BranchWatcher:
    """Polls .git/HEAD for branch switches and logs them"""

    def __init__(self, log_writer, poll_interval=2):
        self.log_writer = log_writer
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
            all_logs.append(log_file.read_text())

        return "\n".join(all_logs)

    def generate_report(self, from_date = None, to_date = None):
        """ Generate report from logs using Openai """
        logs = self.read_all_logs(from_date, to_date)
        standards = load_standards()

        if not logs.strip():
            print("No activity logs found.")
            return None
        
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

        prompt = f"""You are a code review agent analyzing a developer's activity.

## Repository Purpose
{purpose}
{scan_context}
## Company Coding Standards
{standards}

## Activity Logs (What the developer did)
{logs}

## Your Task
Analyze the developer's activity and generate a report with:

1. **Summary**: Overview of what was worked on
2. **Activity Timeline**: Key actions in chronological order
3. **Alignment Check**: Do the changes align with the repository purpose? Flag any deviations.
4. **Issues Detected**: Any problems, bugs, or standards violations you notice
5. **Recommendations**: Suggestions for improvement

Be specific, reference actual file names and code from the logs.
Format the report in clean markdown.
"""

        print("Generate report with openai API...")

        response = self.client.chat.completions.create(
            model=self.config.get("model", "gpt-4o"),
            max_tokens=4096,
            messages = [{'role': 'user', 'content': prompt}]
        )

        # Log usage
        model = self.config.get("model", "gpt-4o")
        cost = log_usage(
            model=model,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            purpose="report"
        )
        print(f"  Tokens: {response.usage.prompt_tokens} in / {response.usage.completion_tokens} out")
        print(f"  Cost: ${cost:.4f}")

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
        with open(CONFIG_FILE, "w") as f:
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
        Path(STANDARDS_FILE).write_text(default_standards)
    
    # Create default ignore.yaml
    if not Path(IGNORE_FILE).exists():
        default_ignore = [
            "node_modules/",
            ".git/",
            "__pycache__/",
            ".agent/logs/",
            "*.pyc",
            ".env",
            "*.log"
        ]
        with open(IGNORE_FILE, "w") as f:
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
        Path(PURPOSE_FILE).write_text(default_purpose)
    
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
        with open(RULES_FILE, "w") as f:
            yaml.dump(default_rules, f, default_flow_style=False, sort_keys=False)


def cmd_start():
    """Start the file watcher in background"""
    # Check if already running
    if Path(PID_FILE).exists():
        pid = int(Path(PID_FILE).read_text())
        try:
            os.kill(pid, 0)  # Check if process exists
            print(f"Agent already running (PID: {pid})")
            return
        except OSError:
            pass  # Process not running, clean up
    
    # Check if .agent/ exists
    if not Path(AGENT_DIR).exists():
        print("Error: .agent/ folder not found. Run 'python agent.py init' first.")
        return
    
    config = load_config()
    ignore_patterns = load_ignore_patterns()
    log_writer = LogWriter()
    
    event_handler = FileEventHandler(log_writer, config, ignore_patterns)
    observer = Observer()
    observer.schedule(event_handler, ".", recursive=True)

    # Start branch watcher
    branch_watcher = BranchWatcher(log_writer)

    # Save PID
    Path(PID_FILE).write_text(str(os.getpid()))

    # Handle shutdown
    def shutdown(signum, frame):
        print("\nStopping agent...")
        observer.stop()
        branch_watcher.stop()
        Path(PID_FILE).unlink(missing_ok=True)
        Path(PAUSE_FILE).unlink(missing_ok=True)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    observer.start()
    branch_watcher.start()
    print(f"Agent started. Watching: {os.getcwd()}")
    print("Press Ctrl+C to stop.")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown(None, None)


def cmd_stop():
    """Stop the running agent"""
    if not Path(PID_FILE).exists():
        print("Agent is not running.")
        return
    
    pid = int(Path(PID_FILE).read_text())
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"Agent stopped (PID: {pid})")
    except OSError:
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
    Path(PAUSE_FILE).write_text(datetime.now().isoformat())
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
    
    pid = int(Path(PID_FILE).read_text())
    try:
        os.kill(pid, 0)
        print(f"Agent is running (PID: {pid})")
    except OSError:
        print("Agent is not running (stale PID file).")
        Path(PID_FILE).unlink(missing_ok=True)


def cmd_report(from_date=None, to_date=None):
    """Generate a report from logged activity"""
    config = load_config()
    engine = ReportEngine(config)
    report = engine.generate_report(from_date, to_date)
    
    if report:
        #Print to console
        print("\n" + "="*80)
        print(report)
        print("="*80 + "\n")

        #save to file
        Path(REPORTS_DIR).mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        report_file = Path(REPORTS_DIR) / f"report_{timestamp}.md"
        report_file.write_text(report)
        print(f"Report savd to: {report_file}")


def cmd_logs(date=None):
    """View recent logs"""
    logs_path = Path(LOGS_DIR)
    if not logs_path.exists():
        print("No logs found.")
        return
    
    if date:
        log_file = logs_path / f"{date}.log"
        if log_file.exists():
            print(log_file.read_text())
        else:
            print(f"No logs for {date}")
    else:
        # Show most recent log
        log_files = sorted(logs_path.glob("*.log"), reverse=True)
        if log_files:
            print(f"--- {log_files[0].name} ---")
            print(log_files[0].read_text())
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

    for root, dirs, files in os.walk("."):
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
    with open(SCAN_FILE, "w") as f:
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
        with open(file_path, 'r') as f:
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

    for root, dirs, files in os.walk("."):
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
                print(f"  ├── {v['type']}: {v['message']}")
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
                print(f"  ├── {a['type']}: {a['message']}")
            print()

    print(f"Files checked: {files_checked}")
    print(f"Passed: {files_passed}")
    print(f"Failed: {files_failed}")






# ===================================== MAIN ========================================

def main():
    parser = argparse.ArgumentParser(description="Local Directory Monitoring Agent")
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

    
    args = parser.parse_args()
    
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
    else:
        parser.print_help()


if __name__ == "__main__":
    main()




