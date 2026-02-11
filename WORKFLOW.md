# Agent Monitor — System Workflow

## Overview

A company-wide code monitoring system that installs silently via a VS Code extension, watches developer activity, and provides dashboards with AI-generated reports.

```
Dev installs extension → Opens project → Agent installs itself → Dashboard launches
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     THREE COMPONENTS                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. VS Code Extension (.vsix)                                │
│     - Installed once by the dev                              │
│     - Triggers everything automatically                      │
│     - Tiny file (~6KB of logic)                              │
│                                                              │
│  2. Central Agent (~/.agent-monitor/)                        │
│     - Cloned from GitHub on first use                        │
│     - Contains agent.py, UI.py, Python venv                 │
│     - One copy per machine, shared across all projects       │
│     - Hidden folder in dev's home directory                  │
│                                                              │
│  3. Project Config (.agent/)                                 │
│     - Created inside each monitored project                  │
│     - Contains rules, purpose, config, logs, reports         │
│     - Unique per project                                     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### What Lives Where

```
GitHub (remote)
└── monitoring_agent repo (agent_scaling branch)
    ├── agent.py              ← monitoring engine
    ├── UI.py                 ← Streamlit dashboard
    └── requirements.txt      ← Python dependencies

Dev's Machine
├── ~/.agent-monitor/         ← CENTRAL INSTALL (one per machine)
│   ├── agent.py              ← cloned from GitHub
│   ├── UI.py                 ← cloned from GitHub
│   ├── requirements.txt      ← cloned from GitHub
│   └── venv/                 ← Python virtual environment
│       ├── bin/python
│       ├── bin/pip
│       └── bin/streamlit
│
├── ~/project-a/              ← Dev's project
│   ├── src/                  ← their code
│   └── .agent/               ← PER-PROJECT CONFIG
│       ├── purpose.md        ← project description
│       ├── rules.yaml        ← coding rules
│       ├── config.yaml       ← monitoring settings
│       ├── standards.md      ← coding standards
│       ├── ignore.yaml       ← paths to ignore
│       ├── scan.json         ← codebase snapshot
│       ├── logs/             ← activity logs
│       └── reports/          ← AI-generated reports
│
└── ~/project-b/              ← Another project
    └── .agent/               ← separate config, logs, reports
```

---

## End-to-End Flow

### Step 1: Distribution

```
Admin creates .vsix file → Shares via Google Drive / email / internal tool
Dev downloads .vsix → Installs in VS Code (Cmd+Shift+P → "Install from VSIX")

Result: Extension installed. Nothing else happens yet.
```

### Step 2: First Project Setup

```
Dev opens any project folder in VS Code
            │
            ▼
   Extension activates automatically
            │
            ▼
   ┌────────────────────────────────────────────┐
   │  "Agent Monitor: Initialize monitoring      │
   │   for this project?"                        │
   │                          [Yes]    [No]      │
   └────────────────────────────────────────────┘
            │                          │
         [Yes]                      [No]
            │                   Nothing happens.
            │                   Extension stays silent.
            ▼
   Does ~/.agent-monitor/ exist?
   ├── YES → skip (already installed)
   └── NO  → FIRST-TIME MACHINE SETUP:
             │
             ├── git clone monitoring_agent repo → ~/.agent-monitor/
             ├── python3 -m venv ~/.agent-monitor/venv
             └── pip install -r requirements.txt
             │
             │   Installs: watchdog, openai, streamlit,
             │             pyyaml, python-dotenv, requests
             │
             │   This happens ONCE per machine (~60 seconds)
             │
            ▼
   Create .agent/ inside the project
             │
             │   Runs: agent.py --project-dir <project> init
             │
             │   Creates: purpose.md, rules.yaml, config.yaml,
             │            standards.md, ignore.yaml, logs/, reports/
             │
            ▼
   Launch Streamlit dashboard
             │
             │   Runs: streamlit run UI.py
             │   URL: http://localhost:8501/<project-name>
             │
            ▼
   ┌────────────────────────────────────────────┐
   │          SETUP WIZARD (first run only)      │
   │                                             │
   │  1. Project Purpose                         │
   │     "Describe what this repo does..."       │
   │                                             │
   │  2. Coding Rules                            │
   │     Max function lines, forbidden imports,  │
   │     forbidden files                         │
   │                                             │
   │  3. Monitoring Config                       │
   │     Watched file extensions                 │
   │                                             │
   │  [Complete Setup]                           │
   └────────────────────────────────────────────┘
             │
             ▼
   Google Sheet registration (silent)
             │
             │   Posts to shared Google Sheet:
             │   - Timestamp
             │   - Dev name
             │   - Project name
             │   - Network URL
             │   - Machine hostname
             │
            ▼
   DASHBOARD READY — dev can start working
```

### Step 3: Returning User

```
Dev opens the same project again in VS Code
            │
            ▼
   .agent/ exists? YES → skip wizard, skip clone
            │
            ▼
   Launch Streamlit dashboard directly
            │
            ▼
   Dashboard loads in seconds — ready to use
```

### Step 4: Second Project (Same Dev)

```
Dev opens a different project in VS Code
            │
            ▼
   "Initialize monitoring for this project?" → [Yes]
            │
            ▼
   ~/.agent-monitor/ exists? YES → skip clone (already installed)
            │
            ▼
   Create .agent/ in this new project → wizard → dashboard
```

---

## Monitoring Flow

```
Dev starts the agent from the dashboard
            │
            ▼
   agent.py starts watchdog file watcher
            │
            ▼
   ┌──────────────────────────────────────────────────┐
   │  CONTINUOUS MONITORING (runs in background)       │
   │                                                    │
   │  Dev edits a file                                  │
   │       │                                            │
   │       ▼                                            │
   │  Detect event type:                                │
   │  FILE_CREATED | FILE_MODIFIED | FILE_DELETED       │
   │  FILE_RENAMED | BRANCH_SWITCHED                    │
   │       │                                            │
   │       ▼                                            │
   │  Detect source:                                    │
   │  ├── Claude Code + bulk change → "Claude Code (AI)"│
   │  ├── VS Code + bulk change    → "VS Code (AI)"    │
   │  ├── VS Code                  → "VS Code"         │
   │  ├── Cursor + bulk change     → "Cursor (AI)"     │
   │  ├── Cursor                   → "Cursor"          │
   │  └── Small manual edit        → "Manual Edit"     │
   │       │                                            │
   │       ▼                                            │
   │  Detect git branch: main | dev | feature-x         │
   │       │                                            │
   │       ▼                                            │
   │  Compute diff (before vs after)                    │
   │       │                                            │
   │       ▼                                            │
   │  Write to .agent/logs/YYYY-MM-DD.log               │
   │                                                    │
   │  [2026-02-10 14:30:00] FILE_MODIFIED               │
   │  PATH: src/main.py                                 │
   │  SOURCE: Claude Code (AI)                          │
   │  BRANCH: dev                                       │
   │  DIFF:                                             │
   │  +import os                                        │
   │  +import sys                                       │
   │   def main():                                      │
   └──────────────────────────────────────────────────┘
```

---

## Dashboard Features

```
┌─────────────────────────────────────────────────────────┐
│  RepoAgent — project-name                    localhost   │
├──────────┬──────────────────────────────────────────────┤
│ SIDEBAR  │  MAIN AREA                                   │
│          │                                               │
│ [Start]  │  Activity Logs (real-time)                   │
│ [Stop]   │  ├── FILE_MODIFIED src/main.py               │
│          │  ├── FILE_CREATED src/utils.py               │
│ [Pause]  │  └── BRANCH_SWITCHED → dev                  │
│ [Resume] │                                               │
│          │  Rule Violations                              │
│ [Scan]   │  ├── main.py: function too long (75 lines)   │
│          │  └── config.py: forbidden import (flask)      │
│          │                                               │
│          │  Analytics                                    │
│          │  ├── Files changed today: 12                  │
│          │  ├── AI-generated changes: 65%                │
│          │  └── Manual changes: 35%                      │
│          │                                               │
│          │  [Generate AI Report]                         │
│          │  └── Sends logs to OpenAI → formatted report  │
└──────────┴──────────────────────────────────────────────┘
```

---

## Google Sheet Registry

Every dashboard instance registers itself on startup:

| Timestamp | Dev Name | Project Name | Network URL | Machine |
|-----------|----------|-------------|-------------|---------|
| 2026-02-10 09:00 | prakyath | web-app | http://192.168.1.10:8501/web-app | Prakyath-2 |
| 2026-02-10 09:15 | john | api-service | http://192.168.1.22:8501/api-service | Johns-Mac |
| 2026-02-10 09:30 | sarah | mobile-app | http://192.168.1.35:8501/mobile-app | Sarahs-Mac |

This gives the team lead a live view of who is running the agent, on which project, at what URL.

---

## Branch Switch Workflow

```
Dev on branch "main" → editing files → clean diffs logged
            │
            ▼
   Click [Pause] in dashboard
            │
            ▼
   Agent pauses — ignores all file events
            │
            ▼
   Dev does: git add → git commit → git checkout feature-x
            │
            ▼
   Click [Resume] in dashboard
            │
            ▼
   Agent refreshes RAM cache from disk (re-reads all files)
            │
            ▼
   Dev on branch "feature-x" → editing files → clean diffs logged
```

Without pause/resume, branch switching produces massive diffs of every file that differs between branches (because the agent's RAM cache is stale).

---

## What the Dev Needs

| Requirement | Details |
|-------------|---------|
| VS Code | Any recent version |
| Python 3.11+ | Must be installed on machine |
| Git | Must be installed on machine |
| Internet | Only for first-time clone + AI reports |
| OpenAI API key | For report generation (optional) |

### Dev Experience

```
1. Receive .vsix file from admin
2. Install in VS Code (Cmd+Shift+P → "Install from VSIX")
3. Open any project → click "Yes" when prompted
4. Wait ~60s for first-time setup
5. Fill in the setup wizard
6. Done — dashboard is running, monitoring is active
```

The dev never touches `agent.py`, `UI.py`, or the terminal. Everything is automatic.

---

## Updating the Agent

When you push changes to the GitHub repo:

```
Option A: Dev runs "cd ~/.agent-monitor && git pull"
Option B: (Future) Extension auto-checks for updates on startup
```

Currently Option A. Auto-update can be added later.

---

## Security Notes

| Concern | Status |
|---------|--------|
| Extension asks permission before init | Yes — "Initialize monitoring?" prompt |
| No code runs until dev clicks "Yes" | Correct |
| GitHub repo is private | Configurable — set to private for internal use |
| Minimal environment passed to child processes | Yes — MIN_ENV (PATH + HOME only) |
| Streamlit binds to localhost | Yes — not exposed to network by default |
| API keys stored in .env | Not committed to git |

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Monitoring Engine | Python 3.11+ (watchdog) |
| Dashboard | Streamlit |
| AI Reports | OpenAI API (GPT-4o) |
| Extension | JavaScript (VS Code Extension API) |
| Config | YAML |
| Registry | Google Sheets (via Apps Script) |
| Distribution | .vsix file (private, no marketplace) |
