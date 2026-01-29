# Local Directory Monitoring Agent - Technical Manual

> **Version**: 2.0
> **Status**: Phase 2 complete
> **Last Updated**: 29 January 2026

---

## Executive Summary

The **Local Directory Monitoring Agent** is an autonomous AI-powered tool that runs silently on developer machines, monitors all file activity, maintains persistent memory through logs, and generates intelligent reports on demand.

**Key Value**: Catch code quality issues, standard violations, and architectural drift in real-time - before they reach code review.

---

## Table of Contents

1. [The Problem We Solve](#the-problem-we-solve)
2. [How It Works](#how-it-works)
3. [System Architecture](#system-architecture)
4. [Data Flow](#data-flow)
5. [Directory Structure](#directory-structure)
6. [Commands Reference](#commands-reference)
7. [Use Cases](#use-cases)
8. [Demo Walkthrough](#demo-walkthrough)

---

## The Problem We Solve

### Pain Points in Modern Development

| Problem | Impact | Our Solution |
|---------|--------|--------------|
| **Lost Context** | Developers forget why changes were made | Persistent logs with timestamps capture everything |
| **No Activity Trail** | No visibility into what happened during development | File watcher records all create/modify/delete/rename events |
| **Delayed Code Review** | Issues caught too late, context is lost | On-demand reports analyze activity immediately |
| **Standard Drift** | Codebases drift from established standards over time | Reports check code against defined standards |
| **AI Tool Blindness** | No record when AI assistants (Copilot, Claude, Cursor) make changes | Watchdog captures ALL file changes regardless of source |

### The Hidden Cost

```
Developer makes changes → Days pass → Code review happens → "Why did you do this?"
                                                            ↓
                                                     "I don't remember"
```

**With our agent:**

```
Developer makes changes → Agent logs everything → Report on demand → Full context preserved
```

---

## How It Works

### The Core Concept

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│   Developer works normally                                          │
│        ↓                                                            │
│   Agent watches SILENTLY (never interrupts)                         │
│        ↓                                                            │
│   Every file change is logged with:                                 │
│   • Timestamp                                                       │
│   • Event type (created/modified/deleted/renamed)                   │
│   • Full code diff (before/after)                                   │
│        ↓                                                            │
│   Developer runs "report" when ready                                │
│        ↓                                                            │
│   AI analyzes logs against standards & purpose                      │
│        ↓                                                            │
│   Actionable report generated                                       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Design Principles

| Principle | Implementation |
|-----------|----------------|
| **Local-First** | Everything runs on developer's machine. Only external call is to LLM API for reports. |
| **Non-Intrusive** | Agent runs silently in background. Never blocks or interrupts workflow. |
| **Memory-Persistent** | All activity logged to disk. Survives restarts. Logs are the agent's memory. |
| **On-Demand Intelligence** | LLM only called when developer requests report. Keeps costs minimal. |
| **Configuration over Code** | Behavior controlled through YAML configs, not code changes. |

---

## System Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         AGENT COMPONENTS                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌─────────────────┐    ┌─────────────────┐    ┌────────────────┐  │
│   │  File Watcher   │    │   Log Writer    │    │ Report Engine  │  │
│   │  (watchdog)     │───▶│   (LogWriter)   │───▶│ (ReportEngine) │  │
│   │                 │    │                 │    │                │  │
│   │ Detects changes │    │ Persists events │    │ Reads logs     │  │
│   │ in real-time    │    │ with diffs      │    │ Calls LLM API  │  │
│   └─────────────────┘    └─────────────────┘    └────────────────┘  │
│                                                                     │
│   ┌─────────────────┐    ┌─────────────────┐    ┌────────────────┐  │
│   │  Scanner        │    │  Config Loader  │    │  CLI Parser    │  │
│   │  (cmd_scan)     │    │  (YAML files)   │    │  (argparse)    │  │
│   │                 │    │                 │    │                │  │
│   │ Indexes codebase│    │ Loads settings  │    │ User interface │  │
│   │ metadata        │    │ & rules         │    │ for commands   │  │
│   └─────────────────┘    └─────────────────┘    └────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Technology Stack

| Component | Technology | Why |
|-----------|------------|-----|
| Language | Python 3.11+ | Rapid development, rich ecosystem |
| File Watching | `watchdog` library | Cross-platform, reliable, event-driven |
| LLM Integration | OpenAI API | GPT-4o for intelligent analysis |
| Configuration | YAML | Human-readable, easy to edit |
| Architecture | Single file (`agent.py`) | Simple to understand, deploy, debug |

---

## Data Flow

### Complete Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DATA FLOW                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  SETUP PHASE (One-time)                                                     │
│  ══════════════════════                                                     │
│                                                                             │
│  python agent.py init                                                       │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────┐                │
│  │  Creates .agent/ folder structure:                      │                │
│  │  ├── config.yaml      (settings)                        │                │
│  │  ├── standards.md     (coding rules)                    │                │
│  │  ├── purpose.md       (project mission)                 │                │
│  │  ├── ignore.yaml      (files to skip)                   │                │
│  │  ├── logs/            (activity logs)                   │                │
│  │  └── reports/         (generated reports)               │                │
│  └─────────────────────────────────────────────────────────┘                │
│                                                                             │
│  python agent.py scan                                                       │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────┐                │
│  │  Creates scan.json:                                     │                │
│  │  • Maps all existing files                              │                │
│  │  • Extracts: functions, classes, imports, line counts   │                │
│  │  • Provides baseline context for LLM                    │                │
│  └─────────────────────────────────────────────────────────┘                │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  MONITORING PHASE (Continuous)                                              │
│  ═════════════════════════════                                              │
│                                                                             │
│  python agent.py start                                                      │
│         │                                                                   │
│         ▼                                                                   │
│  ┌───────────────┐     ┌───────────────┐     ┌───────────────┐              │
│  │   Developer   │     │   Watchdog    │     │   Log File    │              │
│  │   edits code  │────▶│   detects     │────▶│   records     │              │
│  │               │     │   change      │     │   event       │              │
│  └───────────────┘     └───────────────┘     └───────────────┘              │
│                                                                             │
│  Log entry format:                                                          │
│  ┌─────────────────────────────────────────────────────────┐                │
│  │  [2026-01-29 11:30:45] FILE_MODIFIED: src/app.py        │                │
│  │  DIFF:                                                  │                │
│  │  - old_function_code()                                  │                │
│  │  + new_function_code()                                  │                │
│  └─────────────────────────────────────────────────────────┘                │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  REPORT PHASE (On-Demand)                                                   │
│  ════════════════════════                                                   │
│                                                                             │
│  python agent.py report                                                     │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────┐                │
│  │                   CONTEXT GATHERING                     │                │
│  │                                                         │                │
│  │   scan.json ─────┐                                      │                │
│  │   (codebase      │                                      │                │
│  │    structure)    │                                      │                │
│  │                  │     ┌─────────────────┐              │                │
│  │   logs/*.log ────┼────▶│  Report Engine  │              │                │
│  │   (what changed, │     │                 │              │                │
│  │    with diffs)   │     │  Combines all   │              │                │
│  │                  │     │  context into   │              │                │
│  │   purpose.md ────┤     │  single prompt  │              │                │
│  │   (project       │     └────────┬────────┘              │                │
│  │    mission)      │              │                       │                │
│  │                  │              ▼                       │                │
│  │   standards.md ──┘     ┌─────────────────┐              │                │
│  │   (coding rules)       │   OpenAI API    │              │                │
│  │                        │   (GPT-4)       │              │                │
│  │                        └────────┬────────┘              │                │
│  │                                 │                       │                │
│  │                                 ▼                       │                │
│  │                        ┌─────────────────┐              │                │
│  │                        │  Analysis:      │              │                │
│  │                        │  • Deviations   │              │                │
│  │                        │  • Violations   │              │                │
│  │                        │  • Suggestions  │              │                │
│  │                        └────────┬────────┘              │                │
│  │                                 │                       │                │
│  └─────────────────────────────────┼───────────────────────┘                │
│                                    ▼                                        │
│                           ┌─────────────────┐                               │
│                           │  Report Output  │                               │
│                           │  • Console      │                               │
│                           │  • .md file     │                               │
│                           └─────────────────┘                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### What Each Component Provides to the LLM

| Component | Information Provided | Example |
|-----------|---------------------|---------|
| **scan.json** | Codebase structure | "4 files, 670 lines, 46 functions, 3 classes" |
| **logs/*.log** | What changed (with actual code diffs) | "Added flask import, created /status route" |
| **purpose.md** | What the project SHOULD be | "CLI tool only, no web interfaces" |
| **standards.md** | HOW code should be written | "Functions under 50 lines, use snake_case" |

---

## Directory Structure

### After Initialization

```
my-project/
├── agent.py              ← The monitoring agent (single file)
├── .agent/               ← Agent's working directory
│   ├── config.yaml       ← Settings (extensions, model, retention)
│   ├── standards.md      ← Coding standards for your team
│   ├── purpose.md        ← Repository mission & boundaries
│   ├── ignore.yaml       ← Patterns to ignore (node_modules, .env, .git, etc.)
│   ├── scan.json         ← Codebase metadata snapshot
│   ├── logs/             ← Activity logs (agent's memory)
│   │   ├── 2026-01-28.log
│   │   └── 2026-01-29.log
│   └── reports/          ← Generated reports
│       └── report_2026-01-29_11-45-30.md
└── src/                  ← Your actual code
    └── ...
```

### File Purposes

| File | Purpose | Edited By |
|------|---------|-----------|
| `config.yaml` | Agent settings | User (once during setup) |
| `standards.md` | Coding rules to check against | User/Team lead |
| `purpose.md` | Project mission, boundaries, deviation signals | User/Team lead |
| `ignore.yaml` | Files/folders agent should ignore | User |
| `scan.json` | Codebase structure snapshot | Agent (via `scan` command) |
| `logs/*.log` | Activity history | Agent (automatic) |
| `reports/*.md` | Generated analysis reports | Agent (via `report` command) |

---

## Commands Reference

### Quick Reference

```bash
python agent.py init      # Initialize agent in current directory
python agent.py scan      # Index codebase metadata
python agent.py start     # Start monitoring (foreground)
python agent.py stop      # Stop monitoring
python agent.py status    # Check if agent is running
python agent.py logs      # View today's activity logs
python agent.py report    # Generate AI-powered analysis report
```

### Detailed Command Reference

#### `init` - Initialize Agent

```bash
python agent.py init
```

**What it does:**
- Creates `.agent/` directory structure
- Generates default `config.yaml`, `standards.md`, `purpose.md`, `ignore.yaml`
- Creates empty `logs/` and `reports/` directories

**When to use:** Once, when setting up agent in a new repository.

---

#### `scan` - Index Codebase

```bash
python agent.py scan
```

**What it does:**
- Walks through all files matching configured extensions
- Extracts metadata: functions, classes, imports, line counts
- Saves to `scan.json`

**Output (Example):**
```
Scanning codebase...
Scan Complete!
Files: 4
Lines: 1194
Functions: 54
Classes: 6
Saved to: .agent/scan.json
```

**When to use:**
- After `init` to create baseline
- After major codebase changes
- Periodically to update context

---

#### `start` - Begin Monitoring

```bash
python agent.py start
```

**What it does:**
- Starts watchdog file system observer
- Monitors all files with configured extensions
- Logs events to `.agent/logs/YYYY-MM-DD.log`
- Runs in foreground (Ctrl+C to stop)

**Output:**
```
Agent started. Watching: /path/to/project
Press Ctrl+C to stop.
[2026-01-29 11:30:00 FILE_CREATED: ./newfile.py]
[2026-01-29 11:30:05 FILE_MODIFIED: ./newfile.py]
```

**When to use:** When starting development session.

---

#### `stop` - Stop Monitoring

```bash
python agent.py stop
```

**What it does:**
- Reads PID from `.agent/.pid`
- Sends termination signal to background process

**When to use:** When done with development session.

---

#### `status` - Check Agent Status

```bash
python agent.py status
```

**Output:**
```
Agent is running (PID: 12345)
```
or
```
Agent is not running
```

---

#### `logs` - View Activity Logs

```bash
python agent.py logs              # View today's logs
python agent.py logs 2026-01-28   # View specific date
```

**What it shows:**
```
[10:25:42] FILE_CREATED: ./api.py
[10:25:45] FILE_MODIFIED: ./api.py
DIFF:
+ from flask import Flask
+ app = Flask(__name__)
```

---

#### `report` - Generate Analysis

```bash
python agent.py report
```

**What it does:**
1. Reads all logs
2. Reads scan.json, purpose.md, standards.md
3. Sends context to OpenAI API
4. Displays analysis report
5. Saves report to `.agent/reports/report_TIMESTAMP.md`

**Report includes:**
- Summary of activity
- Timeline of key actions
- Alignment check against purpose.md
- Issues and violations detected
- Recommendations

---

## Use Cases

### Use Case 1: New Team Member Onboarding

**Scenario:** New developer joins team, needs to understand codebase quickly.

```bash
# Run scan to get codebase overview
python agent.py scan

# Start monitoring their work
python agent.py start

# After first day, generate report
python agent.py report
```

**Value:** Report shows what they explored, potential misunderstandings, and areas where they might need guidance.

---

### Use Case 2: AI Assistant Code Review

**Scenario:** Developer uses Copilot/Claude/Cursor to generate code. Need to review what AI added.

```bash
# Agent is running, captures all changes including AI-generated code

# At end of session
python agent.py report
```

**Value:** Full visibility into every change AI tools made, checked against your standards.

---

### Use Case 3: Pre-Code Review Preparation

**Scenario:** Before submitting PR, developer wants to self-review.

```bash
python agent.py report
```

**Value:** Catches issues before human reviewer sees them. Developer can fix proactively.

---

### Use Case 4: Detecting Scope Creep

**Scenario:** Project has strict boundaries (e.g., no web interfaces). Need to enforce.

**Setup `purpose.md`:**
```markdown
## Boundaries
- No web interfaces
- No database connections
- CLI only
```

**When developer adds Flask:**
```bash
python agent.py report
```

**Report output:**
```
🚨 DEVIATION DETECTED: api.py
- Imports `flask` (web framework)
- Creates HTTP endpoint `/status`
This DIRECTLY VIOLATES purpose.md: "No web interfaces"
```

---

### Use Case 5: End-of-Sprint Summary

**Scenario:** Sprint ends, need summary of all development activity.

```bash
python agent.py report --from 2026-01-15 --to 2026-01-29
```

**Value:** Comprehensive report of two weeks of activity for sprint retrospective.

---

## Demo Walkthrough

### Step-by-Step Demo Script

#### 1. Initialize Agent 

```bash
cd my-project
python agent.py init
```

Show the created `.agent/` folder structure.

#### 2. Scan Existing Codebase 

```bash
python agent.py scan
```

Show the output with file/function/class counts.

#### 3. Start Monitoring 

```bash
python agent.py start
```

Leave running in terminal.

#### 4. Make Changes 

In a new terminal or editor:
- Create a new file with a violation (e.g., `api.py` with Flask)
- Modify an existing file

Watch the first terminal show events being captured.

#### 5. Generate Report 

```bash
python agent.py report
```

**Show the report highlighting:**
- It detected the new file
- It flagged the Flask violation against purpose.md
- It provided actionable recommendations

#### 6. Show Saved Report

```bash
ls .agent/reports/
cat .agent/reports/report_*.md
```

---

## Configuration Examples

### config.yaml - Watch Different File Types

```yaml
watch_extensions:
  - .py
  - .js
  - .ts
  - .jsx
  - .tsx
  - .java
  - .go
  - .rs

model: gpt-4o
log_retention_days: 30
```

### ignore.yaml - Skip Common Directories

```yaml
- node_modules/
- .git/
- __pycache__/
- .agent/logs/
- venv/
- dist/
- build/
- "*.pyc"
- "*.log"
- .env
```

### purpose.md - Define Project Boundaries

```markdown
# Repository Purpose

## Mission
Build a CLI tool for X. Keep it simple and focused.

## Boundaries - What Does NOT Belong
- No web interfaces (Flask, FastAPI, etc.)
- No database connections
- No external service integrations

## Deviation Signals
- Any import of: flask, fastapi, django, sqlalchemy
- Files named: api.py, server.py, routes.py
```

---

## FAQ

**Q: Does the agent slow down my machine?**
A: No. Watchdog is event-driven (not polling) and uses minimal CPU/memory.

**Q: How much does report generation cost?**
A: One GPT-4 API call per report. Typically $0.01-0.05 depending on log size.

**Q: Can I use a local LLM instead of OpenAI?**
A: Yes, modify `ReportEngine` to use any OpenAI-compatible API (Ollama, LMStudio, etc.)

**Q: What if I don't want certain files logged?**
A: Add patterns to `.agent/ignore.yaml`

**Q: Are logs stored forever?**
A: Configure `log_retention_days` in config.yaml. Default is 30 days.

---

## Summary

| What | How |
|------|-----|
| **Watch files** | `python agent.py start` |
| **Index codebase** | `python agent.py scan` |
| **Generate report** | `python agent.py report` |
| **Define standards** | Edit `.agent/standards.md` |
| **Define purpose** | Edit `.agent/purpose.md` |
| **Ignore files** | Edit `.agent/ignore.yaml` |

**The agent sees everything. It remembers everything. It reports on demand.**

---


