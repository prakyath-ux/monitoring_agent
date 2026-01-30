# Local Directory Monitoring Agent

> **Status: Phase 2 Complete & Demoed**
> **Last Updated: 30 January 2026**

## Project Vision

An **autonomous local AI agent** that runs on developer machines, monitors all file activity in a working directory, logs everything as context (memory), and generates intelligent reports on demand.

```
Dev works normally → Agent watches silently → Logs everything → Generate report anytime
```

---

## Phase 2 Completed (30 Jan 2026)

### Initial Requirements (All Complete)

| # | Requirement | Status |
|---|-------------|--------|
| 1 | **purpose.md** - Define repo intent for deviation detection | ✅ Done |
| 2 | **rules.yaml** - Machine-checkable coding rules | ✅ Done |
| 3 | **scan command** - Build context from existing codebase | ✅ Done |
| 4 | **check command** - Real-time rule validation on file changes | ✅ Done |
| 5 | **AI source detection** - Identify if changes came from AI tools | ✅ Done |
| 6 | **Log source tracking** - Store AI detection info in logs | ✅ Done |

### Demo Completed (30 Jan 2026)

Successfully demonstrated:
- Claude Code AI detection working in real-time
- Diff logging capturing full code changes
- SOURCE field correctly identifying `Claude Code (AI)` vs `VS Code`
- Bulk change heuristic (>10 lines) triggering AI classification

### Key Features Working

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

**3. Log Entry Format**
```
[timestamp] FILE_MODIFIED | FILE_RENAMED | FILE_CREATED | FILE_DELETED
PATH: /path/to/file
SOURCE: Claude Code (AI) | VS Code | Cursor | Manual Edit
DIFF: (unified diff of changes)
```

### Known Behavior

- **Atomic writes**: Claude Code (and many editors) use atomic writes (write temp → rename over original)
- This triggers `FILE_RENAMED` + `FILE_DELETED` events instead of `FILE_MODIFIED`
- The agent correctly captures the diff and source in `on_moved()` handler

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

| Feature | Purpose | Priority |
|---------|---------|----------|
| **Report integration** | Include AI vs manual breakdown in reports | High |
| **Conflict detection** | Identify when changes conflict with existing code | High |
| **Solution suggestions** | Propose fixes for detected issues (via LLM) | Medium |
| **Auto-fix mode** | Automatically apply safe fixes with approval | Medium |
| **Normalize event types** | Map FILE_RENAMED → FILE_MODIFIED for atomic writes | Low |

### Phase 3 Discussion Topics

1. **Report AI/Manual Breakdown**
   - Parse logs for SOURCE field
   - Calculate: X% AI-generated, Y% manual edits
   - List which files were AI-modified

2. **Conflict Detection**
   - Compare changes against `purpose.md` intent
   - Flag when AI introduces patterns that conflict with existing code
   - Detect when AI duplicates existing functionality

3. **Solution Suggestions**
   - When violations detected, use LLM to suggest fixes
   - Show diff preview before applying
   - Respect rules.yaml constraints
