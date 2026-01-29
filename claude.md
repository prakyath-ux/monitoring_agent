# Local Directory Monitoring Agent

> **Status: Phase 2 Complete**
> **Last Updated: 29 January 2026**

## Project Vision

An **autonomous local AI agent** that runs on developer machines, monitors all file activity in a working directory, logs everything as context (memory), and generates intelligent reports on demand.

```
Dev works normally → Agent watches silently → Logs everything → Generate report anytime
```

---

## Phase 2 Completed (29 Jan 2026)

### Initial Requirements (All Complete)

| # | Requirement | Status |
|---|-------------|--------|
| 1 | **purpose.md** - Define repo intent for deviation detection | Done |
| 2 | **rules.yaml** - Machine-checkable coding rules | Done |
| 3 | **scan command** - Build context from existing codebase | Done |
| 4 | **check command** - Real-time rule validation on file changes | Done |
| 5 | **AI source detection** - Identify if changes came from AI tools | Done |

### Today's Wins

**1. `check` Command System**
- Validates codebase against `rules.yaml`
- Detects: forbidden files, forbidden imports, forbidden patterns, file length, function length
- Real-time checking during file monitoring
- Clear violation output with file paths and line numbers

**2. AI Source Detection System**
- Cross-platform process detection (macOS/Linux/Windows)
- Detects Claude Code, VS Code, Cursor
- Bulk change heuristic (>10 lines = AI-generated)
- Output examples:
  - `(via VS Code)` - manual small edits
  - `(via Claude Code (AI))` - AI bulk changes
  - `(via Cursor (AI))` - Cursor AI changes

---

## Current Commands

```bash
python agent.py init       # Initialize .agent/ folder
python agent.py start      # Start monitoring (foreground)
python agent.py stop       # Stop monitoring
python agent.py status     # Check if agent is running
python agent.py report     # Generate AI report from logs
python agent.py logs       # View recent activity logs
python agent.py scan       # Scan existing codebase metadata
python agent.py check      # Check codebase against rules.yaml
```

---

## Architecture

```
my-project/
├── agent.py              ← The monitoring agent (single file)
├── .agent/               ← Agent's working directory
│   ├── config.yaml       ← Settings (extensions, model, retention)
│   ├── standards.md      ← Coding standards for reports
│   ├── purpose.md        ← Repository mission & boundaries
│   ├── rules.yaml        ← Machine-checkable rules
│   ├── ignore.yaml       ← Patterns to ignore
│   ├── scan.json         ← Codebase metadata snapshot
│   ├── logs/             ← Activity logs (agent's memory)
│   └── reports/          ← Generated reports
└── src/                  ← Your actual code
```

---

## Design Decisions (Locked In)

| Decision | Choice |
|----------|--------|
| **Environment** | Local machine (not GitHub) |
| **Mode** | Continuous background monitoring |
| **Memory** | Persistent logs of all file activity |
| **Report** | On-demand, uses full logged context |
| **Architecture** | Single file (agent.py) |
| **Rule Checking** | Real-time + on-demand |

---

## Rules System (rules.yaml)

```yaml
rules:
  max_function_lines: 60
  max_file_lines: 800
  forbidden_imports:
    - flask
    - fastapi
    - django
    - sqlite3
  forbidden_files:
    - api.py
    - server.py
    - routes.py
  forbidden_patterns:
    - pattern: "password\\s*=\\s*['\"]"
      message: "Hardcoded password detected"
```

---

## AI Detection Logic

```
if Claude running + bulk change (>10 lines):
    → "Claude Code (AI)"
elif VS Code + bulk change:
    → "VS Code (AI Tool)"
elif VS Code:
    → "VS Code"
elif Cursor + bulk change:
    → "Cursor (AI)"
elif Cursor:
    → "Cursor"
elif bulk change only:
    → "AI Tool (likely)"
else:
    → "Manual Edit"
```

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ |
| File Watching | `watchdog` library |
| LLM | OpenAI API (GPT-4o) |
| Config | YAML |
| Architecture | Single file |

---

## Phase 3 Roadmap (Future)

| Feature | Purpose |
|---------|---------|
| Conflict detection | Identify when changes conflict with existing code |
| Solution suggestions | Propose fixes for detected issues |
| Auto-fix mode | Automatically apply safe fixes with approval |
| Log source tracking | Store AI detection info in logs |
| Report integration | Include AI vs manual breakdown in reports |
