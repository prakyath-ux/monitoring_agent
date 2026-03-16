# Agent Monitor - MVP Architecture

> **Status: MVP Loop COMPLETE - All items verified**
> **Last Updated: 16 March 2026**

---

## Overview

Transition from POC (IDE-dependent, per-dev Streamlit visible) to MVP (silent monitoring, auto-install, auto-update, central dashboard for managers).

---

## What Was Achieved (version2 branch)

| # | Feature | Status | Verified |
|---|---------|--------|----------|
| 1 | Thin loader VS Code extension | DONE | Windows laptop |
| 2 | Clone repo + setup.py auto-install | DONE | Mac, Windows, Linux |
| 3 | OS detection + prerequisite checks | DONE | Mac, Windows, Linux |
| 4 | Venv + requirements.txt install | DONE | All 3 OS |
| 5 | Folder to monitor passed as args | DONE | VS Code workspace path |
| 6 | Register agent as OS service | DONE | launchd, systemd, schtasks |
| 7 | Auto git pull on every VS Code restart | DONE | Verified on Windows |
| 8 | Heartbeat every 60s to central dashboard | DONE | Verified: timestamp updates in agents.json |
| 9 | Silent Streamlit (headless, no URL shown) | DONE | Windows laptop |
| 10 | Windows stealth (no .exe popups) | DONE | Windows laptop |
| 11 | Correct LAN IP registration | DONE | Prefers 10.0.3.x subnet |
| 12 | Agent status bar (real state) | DONE | PID file check |
| 13 | Log noise reduction | DONE | 7 entries -> 4 (debounce + skip empty diffs) |

---

## Dev Machine Flow

### First Time (extension handles everything)

```
Dev installs .vsix (one-time, via Drive or manual)
    |
Dev opens project in VS Code
    |
Extension bootstrap runs:
    1. Clone repo (version2 branch) to ~/.agent-monitor/
    2. Git pull latest
    3. Load extension-loader.js from repo
    |
Loader runs:
    4. Run setup.py (venv, deps, .agent/ init)
    5. Launch Streamlit silently (headless, 0.0.0.0)
    6. Start agent (fire-and-forget, windowsHide)
    7. Register with central dashboard (HTTP POST)
    8. Start heartbeat (every 60s)
    9. Check agent status -> update status bar
    |
Dev works normally, agent watches silently
```

### Every VS Code Restart (automatic)

```
VS Code opens
    |
Bootstrap pulls latest code (auto-update)
    |
Loader starts Streamlit + agent silently
    |
Heartbeat resumes (60s interval)
    |
Central dashboard always has current IP + timestamp
```

---

## Architecture

### Extension (Bootstrap + Loader Split)

```
extension.js (in .vsix, ~70 lines, install once)
    |-- Clone repo if needed
    |-- Git pull origin version2
    |-- Clear require cache
    |-- require(extension-loader.js)

extension-loader.js (in repo, auto-updates via git pull)
    |-- ensureSetup() -> runs setup.py if needed
    |-- launchStreamlit() -> headless, windowsHide
    |-- startAgent() -> fire-and-forget spawn
    |-- registerWithDashboard() -> HTTP POST to 10.0.3.55:5000
    |-- heartbeat -> setInterval 60s
    |-- status bar -> PID file check
    |-- stopAgent() -> taskkill (Win) or kill (Mac/Linux)
```

### File Structure

```
Dev Machine:
~/.agent-monitor/                   <- Cloned by extension (version2 branch)
    +-- agent.py                    <- File watcher
    +-- UI.py                       <- Streamlit dashboard (runs headless)
    +-- requirements.txt
    +-- version2/
    |     +-- setup.py              <- Cross-platform installer
    |     +-- extension/            <- Bootstrap .vsix source
    |     +-- extension-loader.js   <- Real extension logic
    +-- venv/
    +-- install.log

Project Folder:
/path/to/project/
    +-- .agent/
    |     +-- config.yaml
    |     +-- purpose.md
    |     +-- rules.yaml
    |     +-- ignore.yaml
    |     +-- .pid                  <- Agent process ID
    |     +-- logs/                 <- Activity logs
    |     +-- reports/              <- Generated reports
    +-- (dev's code)

Central Server (10.0.3.55):
~/Documents/prakyath/central_dashboard/
    +-- dashboard.py                <- Streamlit UI (port 8503) + API (port 5000)
    +-- agents.json                 <- Fleet registry (updated by heartbeat)
```

---

## Central Dashboard

```
Central Dashboard (http://10.0.3.55:8503)
|
+-- Fleet Status
|     +-- All machines: Online / Offline
|     +-- Heartbeat-based (last registration timestamp)
|     +-- IP + port for each dev's Streamlit
|
+-- Click "Open" -> Dev's Streamlit dashboard
|     +-- Activity logs
|     +-- AI vs Manual source detection
|     +-- Rule violations
|     +-- Generate Report
|
+-- Add Machine manually
```

---

## What Dev Sees

- Status bar: "Agent: Running" or "Agent: Stopped" (bottom-left)
- One-time setup message on first install
- Nothing else. No URL, no browser tab, no .exe windows.

## What Manager Sees

- Central dashboard at http://10.0.3.55:8503
- Fleet of all dev machines with online/offline status
- Click any dev -> their full Streamlit dashboard (logs, reports, analytics)
- Heartbeat timestamps show who's actively working

---

## Cross-Platform Rules

1. Always `encoding="utf-8"` on file operations
2. ASCII only in print() — no emoji (crashes Windows cp437)
3. Use pathlib or os.path.join — never hardcode path separators
4. `windowsHide: true` on all Node.js spawn/execFile (no .exe popups)
5. Never `detached: true` on Windows (forces visible console)
6. `CREATE_NO_WINDOW` on all Python subprocess.run on Windows
7. Never use `pythonw.exe` (crashes on print, no stdout)
8. `process.kill(pid, 0)` unreliable on Windows — use PID file existence check
9. Prefer 10.0.3.x subnet for IP detection (avoid VPN adapter)
10. Bind to `0.0.0.0` for network services

---

## Key Bugs Solved

| Bug | Impact | Fix |
|-----|--------|-----|
| Emoji in print() | Watchdog thread dies silently on Windows | ASCII only |
| detached:true | Console window pops up on Windows | Use windowsHide alone |
| pythonw.exe | Agent crashes before writing PID | Use python.exe + windowsHide |
| tasklist.exe flash | Console flashes on every file event | CREATE_NO_WINDOW flag |
| DHCP IP change | Stale entry in agents.json | Re-register on every startup + heartbeat |
| VPN IP picked | Wrong IP in agents.json | Prefer 10.0.3.x subnet |
| Streamlit registration fail | st.session_state fails headless | Registration in extension-loader.js |
| Log noise (7 for 3) | Inflated context for reports | Debounce 2s + skip empty diffs |
| agent.py start blocks | Status bar stuck on "Starting..." | Fire-and-forget spawn |
| PID check EPERM | Shows "Stopped" for running agent | PID file existence check on Windows |

---

## Deferred (Future)

| Feature | Purpose |
|---------|---------|
| Prompt capturing | Capture what devs typed into AI tools |
| AI vs manual report breakdown | X% AI-generated, Y% manual in reports |
| Conflict detection | Flag changes conflicting with purpose.md |
| Server API / DB | Centralize logs on server (currently local) |
| OS service auto-start | Agent runs without VS Code (currently needs VS Code open) |
