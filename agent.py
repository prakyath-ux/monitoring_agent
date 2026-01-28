"""
Local Directory Monitoring Agent
Watches file changes, logs activity, generates reports via Openai API
"""

import os
import sys
import time
import signal
import argparse
from datetime import datetime
from pathlib import Path
import difflib
import yaml

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

    def write(self, event_type, path, content=None, diff=None):
        """ Write a log entry """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file = self.get_log_file()

        entry = f"\n{'='*80}\n"
        entry += f"[{timestamp}] {event_type}\n"
        entry += f"PATH: {path}\n"

        if diff:
            entry += f"DIFF:\n{diff}\n"
        elif content:
            entry += f"CONTENT:\n{content}\n"

        entry += f"{'='*80}\n"

        with open(log_file, "a") as f:
            f.write(entry)
        
        print(f"[{timestamp} {event_type}: {path}]")



# ======================================= FILE WATCHER ==============================================

# File changes → watchdog detects → on_*() method called → log_writer.write()
class FileEventHandler(FileSystemEventHandler):
    """ Handles file system events and logs """

    def __init__(self, log_writer, config, ignore_patterns):
        self.log_writer = log_writer
        self.config = config
        self.ignore_pattterns = ignore_patterns
        self.file_contents = {}

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
        
        if not self.should_process(event.src_path):
            return
        
        content = self.get_file_content(event.src_path)
        self.file_contents[event.src_path] = content
        self.log_writer.write("FILE_CREATED", event.src_path, content = content)

    def on_modified(self, event):
        """ Handle file modification """
        if event.is_directory:
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

        self.file_contents[event.src_path] = new_content
        self.log_writer.write("FILE_MODIFIED", event.src_path, diff=diff)


    def on_deleted(self, event):
        """ handle file deletion """
        if event.is_directory:
            return
        
        if not self.should_process(event.src_path):
            return
        
        self.file_contents.pop(event.src_path, None)
        self.log_writer.write("FILE_DELETED", event.src_path)

    def on_moved(self, event):
        """ Handle file rename/move """
        if event.is_directory:
            return
        
        if not self.should_process(event.dest_path):
            return 
        
        self.log_writer.write(
            "FILE_RENAMED",
            f"{event.src_path} -> {event.dest_path}"
        )


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

        prompt = f"""You are a code review agent analyzing a developer's activity.

## Company Coding Standards
{standards}

## Activity Logs (What the developer did)
{logs}

## Your Task
Analyze the developer's activity and generate a report with:

1. **Summary**: Overview of what was worked on
2. **Activity Timeline**: Key actions in chronological order
3. **Issues Detected**: Any problems, bugs, or standards violations you notice
4. **Recommendations**: Suggestions for improvement

Be specific, reference actual file names and code from the logs.
Format the report in clean markdown.
"""

        print("Generate report with openai API...")

        response = self.client.chat.completions.create(
            model=self.config.get("model", "gpt-4o"),
            max_tokens=4096,
            messages = [{'role': 'user', 'content': prompt}]
        )

        return response.choices[0].message.content
    

# ================================ CLI COMMANDS ============================================

def cmd_init():
    """Initialize .agent/ folder in current directory"""
    # Create directories
    Path(AGENT_DIR).mkdir(exist_ok=True)
    Path(LOGS_DIR).mkdir(exist_ok=True)
    
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
    
    print(f"Initialized agent in {os.getcwd()}")
    print(f"  Created: {AGENT_DIR}/")
    print(f"  Created: {CONFIG_FILE}")
    print(f"  Created: {STANDARDS_FILE}")
    print(f"  Created: {IGNORE_FILE}")

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
    
    # Save PID
    Path(PID_FILE).write_text(str(os.getpid()))
    
    # Handle shutdown
    def shutdown(signum, frame):
        print("\nStopping agent...")
        observer.stop()
        Path(PID_FILE).unlink(missing_ok=True)
        sys.exit(0)
    
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    observer.start()
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
        print("\n" + "="*80)
        print(report)
        print("="*80 + "\n")


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
    else:
        parser.print_help()


if __name__ == "__main__":
    main()




