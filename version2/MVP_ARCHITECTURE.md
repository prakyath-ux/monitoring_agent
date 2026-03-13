# Agent Monitor - MVP Architecture

> **Status: Planning**
> **Date: 13 March 2026**

---

## Overview

Transition from POC (IDE-dependent, per-dev Streamlit) to MVP (OS-level service, centralized data, single dashboard).

---

## Dev Machine Flow

### One-Time Install (any OS)

```
Step 1: git clone -b agent_scaling <repo_url> ~/.agent-monitor
Step 2: python3 ~/.agent-monitor/setup.py /path/to/project
```

### What setup.py Does

```
1. Detect OS (Mac / Linux / Windows)
2. Check prerequisites (Python 3.9+, git, pip, venv)
3. Create virtual environment (~/.agent-monitor/venv/)
4. Install dependencies (requirements.txt, retry on failure)
5. Validate project path (exists, no spaces, writable)
6. Init .agent/ in project folder (config.yaml, purpose.md, rules.yaml)
7. Register agent as OS service:
     Mac     -> launchd (~/Library/LaunchAgents/)
     Linux   -> systemd (~/.config/systemd/user/)
     Windows -> Task Scheduler (schtasks)
8. Start agent immediately
9. First data push to central server
10. Log everything to ~/.agent-monitor/install.log
```

### Adding More Projects (same machine)

```
python3 ~/.agent-monitor/setup.py /path/to/another/project
```

No re-clone, no re-install. Just registers the new project.

---

## Every Boot (Automatic, No Dev Action)

```
Machine boots
    |
OS auto-starts agent service
    |
Agent does git pull ~/.agent-monitor/ (auto-update from GitHub)
    |
Agent watches all registered project folders
    |
File change detected
    |
Logs event locally + pushes to central server
    |
Dev opens any IDE -> works normally (agent already watching)
    |
Dev closes IDE -> agent still running
    |
Dev shuts down -> server already has all data
```

---

## Central Server (10.0.3.55)

### What Runs on Server

| Component | Purpose |
|-----------|---------|
| API endpoint (port 5000) | Receives logs + data from agents |
| Data storage (SQLite/JSON) | Stores all logs, reports, machine info |
| Streamlit dashboard (port 8503) | Single dashboard for manager |
| Report generator | LLM calls happen here, one API key |

### Dashboard Views

```
Central Dashboard (http://10.0.3.55:8503)
|
+-- Fleet Status
|     +-- All machines: Active / Idle / Offline
|     +-- Based on last log timestamp (no heartbeat needed)
|           Active  = log received in last 10 min
|           Idle    = log received in last hour
|           Offline = no logs for 1+ hours
|
+-- Click any project -> Individual Project View
|     +-- Activity logs
|     +-- AI vs Manual stats
|     +-- Rule violations
|     +-- File change timeline
|     +-- Generate Report button
|
+-- Click any dev -> Dev Overview
|     +-- All their projects
|     +-- Activity across projects
|     +-- Reports history
|
+-- Reports section
      +-- Generate for any project anytime
      +-- Historical reports
      +-- Compare across projects
```

---

## What Changes from POC

| Aspect | POC (Current) | MVP |
|--------|---------------|-----|
| Agent trigger | IDE must be open | OS service, always running |
| Streamlit | One per dev machine | One on server only |
| Data location | Dev's local disk | Central server |
| Manager access | Connect to dev's IP | Single dashboard URL |
| Dev offline | Data inaccessible | Data already on server |
| Updates | Redistribute .vsix | Auto git pull on boot |
| API key | .env per dev machine | One key on server |
| IDE support | VS Code only | All IDEs + no IDE |
| Port collisions | Multiple Streamlit instances | No Streamlit on dev machines |
| IP tracking | Registration + DHCP issues | Last log timestamp |

---

## Problems Eliminated

| # | Problem | How Solved |
|---|---------|------------|
| 1 | Dev must have VS Code | OS service, no IDE needed |
| 2 | Dev must have project open | Agent runs on boot |
| 3 | Manager can't see data when dev offline | Data on server |
| 4 | No IntelliJ/PyCharm extension | No extension needed |
| 5 | Silent registration failures | Continuous log push, not one-shot |
| 6 | DHCP IP changes | No dev IPs needed |
| 7 | Port collisions | No Streamlit on dev machines |
| 8 | Distributing .vsix updates | Auto git pull on boot |
| 9 | .env API key per machine | One key on server |
| 10 | Encoding/emoji crashes on Windows | Handled in setup.py per OS |
| 11 | Spaces in folder names | Validated during setup |
| 12 | python3 vs python differences | setup.py detects per OS |
| 13 | Missing python3-venv on Ubuntu | setup.py checks and tells dev |
| 14 | Logs lost on reformat | Logs already on server |
| 15 | Multiple Streamlit eating resources | No Streamlit on dev machines |
| 16 | Startup timing issues | OS service manager handles restarts |

---

## Build Order

| # | Task | Description |
|---|------|-------------|
| 1 | setup.py | Installer: OS detection, venv, deps, service registration |
| 2 | agent.py refactor | Strip to file watcher + push logs to server |
| 3 | Server API | Endpoint to receive logs from agents |
| 4 | Central dashboard | Individual project views from server data |
| 5 | Report generation | Server-side LLM calls, manager triggers anytime |

---

## File Structure

```
Dev Machine:
~/.agent-monitor/
    +-- agent.py            <- File watcher only
    +-- setup.py            <- One-time installer
    +-- requirements.txt
    +-- venv/
    +-- install.log
    +-- service.log

Project Folder (any IDE):
/path/to/project/
    +-- .agent/
    |     +-- config.yaml
    |     +-- purpose.md
    |     +-- rules.yaml
    |     +-- ignore.yaml
    +-- .env                <- Optional, not needed for monitoring
    +-- (dev's code)

Server (10.0.3.55):
~/central_dashboard/
    +-- api.py              <- Receives logs from agents
    +-- dashboard.py        <- Streamlit UI
    +-- report.py           <- LLM report generation
    +-- data/
    |     +-- logs/         <- All logs from all agents
    |     +-- reports/      <- All generated reports
    |     +-- machines.json <- Fleet registry
```

---

## VS Code Extension (Optional)

Extension is no longer required. If kept, it becomes a thin status indicator:
- Shows "Agent: Running" in status bar
- No Streamlit launch, no registration, no agent start
- Pure convenience, not a dependency
