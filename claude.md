# Local Directory Monitoring Agent

> **Status: Research & Design Phase**

## Project Vision

An **autonomous local AI agent** that runs on developer machines, monitors all file activity in a working directory, logs everything as context (memory), and generates intelligent reports on demand.

```
Dev works normally → Agent watches silently → Logs everything → Generate report anytime
```

## Design Decisions (Locked In)

| Decision | Choice |
|----------|--------|
| **Environment** | Local machine (not GitHub) |
| **Mode** | Continuous background monitoring |
| **Memory** | Persistent logs of all file activity |
| **Report** | On-demand, uses full logged context |
| **Autonomy** | Auto-fix + meaningful report |

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                     DEV'S WORKING DIRECTORY                     │
│                                                                 │
│   my-project/                                                   │
│   ├── agent.py              ← The monitoring agent              │
│   ├── .agent/                                                   │
│   │   ├── config.yaml       ← Settings                          │
│   │   ├── standards.md      ← Company coding rules              │
│   │   ├── ignore.yaml       ← Files/patterns to skip            │
│   │   └── logs/             ← Activity logs (agent's memory)    │
│   │       └── 2024-01-28.log                                    │
│   └── src/                  ← Dev's actual code                 │
│       └── ...                                                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Agent Workflow

```
1. START AGENT
   └── python agent.py start
   └── Agent begins watching directory silently

2. DEV WORKS NORMALLY
   └── Creates files, writes code, deletes files
   └── Agent logs EVERYTHING in background

3. GENERATE REPORT (when ready)
   └── python agent.py report
   └── Agent reads all logs (memory)
   └── Sends context to Claude API
   └── Generates comprehensive report

4. STOP AGENT (optional)
   └── python agent.py stop
```

---

## What Gets Logged (Agent Memory)

The agent records:
- File created / deleted / renamed
- Content added / modified
- Code diffs (before/after)
- Timestamps for all actions
- Error detections (syntax errors, etc.)

Example log entry:
```
[10:25:42] FILE_MODIFIED: src/app.py
           DIFF:
           - print("hello")
           + print("Hello, World!")
```

---

## Agent Components

| Component | Purpose |
|-----------|---------|
| **File Watcher** | Monitors directory for all changes |
| **Log Writer** | Records events with timestamps and diffs |
| **Log Storage** | Persistent memory in `.agent/logs/` |
| **Report Engine** | Reads logs + standards, calls Claude, generates report |

---

## Commands

```bash
python agent.py start      # Start monitoring (background)
python agent.py stop       # Stop monitoring
python agent.py status     # Check if agent is running
python agent.py report     # Generate report using logged context
python agent.py logs       # View recent activity logs
```

---

## Report Generation

When `python agent.py report` is triggered:

1. Agent reads all logs from `.agent/logs/`
2. Agent reads `.agent/standards.md` (company rules)
3. Sends everything to Claude API as context
4. Claude analyzes:
   - What the dev has been working on
   - Patterns in the code changes
   - Potential issues or bugs
   - Suggestions based on company standards
5. Returns formatted report

---

## Configuration Files

### `.agent/config.yaml`
```yaml
# Agent settings
watch_extensions:
  - .py
  - .js
  - .ts
  - .java

log_retention_days: 30
model: claude-sonnet
auto_start: false
```

### `.agent/standards.md`
```markdown
# Company Coding Standards

## Naming Conventions
- Use camelCase for variables
- Use PascalCase for classes

## Security
- Never hardcode secrets
- Sanitize all user input

## Best Practices
- Add error handling for async operations
- Write docstrings for public functions
```

### `.agent/ignore.yaml`
```yaml
# Don't monitor these
- node_modules/
- .git/
- __pycache__/
- .env
- "*.log"
- .agent/logs/   # Don't watch our own logs
```

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ |
| File Watching | `watchdog` library |
| LLM | Claude API (Anthropic) |
| Config | YAML |
| Logging | Custom + Python logging |

---

## Next Steps (Research Phase)

1. [ ] Build basic file watcher prototype
2. [ ] Implement logging system
3. [ ] Test Claude API integration for report generation
4. [ ] Create CLI commands (start, stop, report)
5. [ ] Test with real project directory
