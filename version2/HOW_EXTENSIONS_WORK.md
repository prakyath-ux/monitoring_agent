# Agent Monitor - Complete System Documentation

## What Is This?

A silent code monitoring agent that runs on developer machines, watches all file changes, logs everything, and lets team leads generate AI-powered reports on any developer's work from a central dashboard.

```
Dev works normally → Agent watches silently → Logs everything → Lead generates report anytime
```

Developers don't see anything except "Agent: Running" in their IDE status bar. No dashboards, no popups, no interruptions. Team leads access everything from one central dashboard.

---

## How It Works (End to End)

```
1. Dev installs extension (.vsix or .zip) — one time
2. Dev opens a project in their IDE
3. Extension clones agent code to ~/.agent-monitor/ (hidden folder)
4. setup.py creates venv, installs dependencies, creates .agent/ in project
5. Agent starts monitoring all file changes silently
6. Streamlit dashboard runs in background (dev can't see it)
7. Machine registers with central dashboard (IP, project name, port)
8. Heartbeat pings every 60 seconds to keep dashboard updated
9. System heartbeat runs independently — survives IDE close
10. Lead opens central dashboard → sees all devs → clicks Open → views logs/reports
```

---

## Architecture

### On Each Developer Machine

```
~/.agent-monitor/              (hidden in home directory, shared across all IDEs)
    |-- agent.py               Core file monitoring engine
    |-- UI.py                  Streamlit dashboard (headless, silent)
    |-- venv/                  Python packages (~500MB)
    |-- .env                   OpenAI API key (fetched from server automatically)
    |-- .registered_projects.json   List of monitored projects on this machine
    |-- scripts/
    |   |-- heartbeat.py       System-level heartbeat (runs independent of IDE)
    |-- version2/
    |   |-- setup.py           Cross-platform installer
    |   |-- extension-loader.js    VS Code real logic (auto-updates)
    |   |-- jetbrains-loader.py    JetBrains real logic (auto-updates)
```

### Inside Each Monitored Project

```
/path/to/project/.agent/      (created per project)
    |-- config.yaml            What file types to watch, model settings
    |-- purpose.md             What this repo is for (deviation detection)
    |-- rules.yaml             Forbidden files, imports, patterns, limits
    |-- standards.md           Coding standards for reports
    |-- ignore.yaml            Patterns to ignore (node_modules, .git, etc.)
    |-- logs/                  Activity logs (agent's memory)
    |   |-- 2026-03-31.log     One file per day
    |-- reports/               Generated AI reports
    |-- .pid                   Agent process ID
```

### Central Dashboard (Server 10.0.3.55)

```
~/Documents/prakyath/central_dashboard/
    |-- dashboard.py           Streamlit on port 8503, API on port 5000
    |-- agents.json            Registry of all dev machines + projects
    |-- login_log.json         Tracks who logs into the dashboard
    |-- .env                   OpenAI API key (served to dev machines via /env endpoint)
```

---

## What the Agent Monitors

For every file change, the agent logs:
- **Timestamp** — when the change happened
- **Event type** — FILE_CREATED, FILE_MODIFIED, FILE_DELETED, FILE_RENAMED
- **File path** — which file changed
- **Source detection** — Claude Code (AI), VS Code, Cursor, JetBrains, Manual Edit
- **Branch** — which git branch the dev is on
- **Diff** — exact code changes (unified diff format)

### AI Source Detection

```
Claude Code running + bulk change (>10 lines) → "Claude Code (AI)"
VS Code + bulk change → "VS Code (AI Tool)"
Cursor + bulk change → "Cursor (AI)"
Bulk change only → "AI Tool (likely)"
Small change → "Manual Edit" or editor name
```

### Log Batching (Auto-Save Handling)

To prevent log spam from IDE auto-save:
- Changes to the same file are batched
- 30 seconds of silence → log one combined diff
- Maximum 5 minutes → force log even if dev keeps typing
- Result: meaningful diffs instead of single-keystroke entries

### File Types Monitored

Default config watches:
```
.py .js .jsx .ts .tsx .java .kt .kts .go .json .xml
.yaml .yml .properties .gradle .sql .html .css .scss
```

Configurable per project via `.agent/config.yaml` (editable remotely from dashboard).

---

## IDE Extensions

### Why Two Extensions?

- **VS Code** requires JavaScript extensions
- **JetBrains** requires Kotlin/Java plugins

Both use the **Bootstrap + Loader pattern**:
- Bootstrap: installed once, never changes (~50-70 lines)
- Loader: lives in repo, auto-updates via git pull (all real logic)

### VS Code Extension (.vsix)

| Component | Language | File |
|-----------|----------|------|
| Bootstrap | JavaScript | `version2/extension/extension.js` |
| Loader | JavaScript | `version2/extension-loader.js` |

Features:
- Auto-clones repo on first install
- Git pull on every VS Code open
- Auto-installs Python if missing
- Auto-initializes .agent/ (no prompt, detects real projects)
- Fetches API key from server
- Starts system heartbeat
- Status bar shows agent state

### JetBrains Plugin (.zip)

| Component | Language | File |
|-----------|----------|------|
| Bootstrap | Kotlin | `version2/jetbrains-plugin/src/` |
| Loader | Python | `version2/jetbrains-loader.py` |

Works on ALL JetBrains IDEs: IntelliJ, PyCharm, WebStorm, GoLand, PhpStorm, CLion, Rider, RubyMine, DataGrip.

### Non-IDE (Scripts)

For terminal-only devs:
- Mac/Linux: `curl -sL .../start-monitor.sh | bash`
- Windows: `curl -sL .../start-monitor.bat -o %TEMP%\start-monitor.bat && %TEMP%\start-monitor.bat`

---

## Auto-Update System

```
You push changes to version2 branch
    |
    +-- Within 5 minutes: all running agents pull new code + self-restart
    |
    +-- On IDE open: extension pulls + loads updated loader
    |
    +-- Result: every dev machine runs latest code automatically
```

No reinstalling extensions. No manual updates. Push once, 30+ machines update within 5 minutes.

---

## Central Dashboard

Accessible at `http://10.0.3.55:8503`

### Authentication

5 user accounts: `frontend`, `backend`, `mobile`, `AI`, `development`
All logins tracked in `login_log.json`.

### Fleet View

- Sorted: Running first, then Stopped, then Offline
- Grouped by developer + machine
- Shows: dev name, project, machine, IP, network status, dashboard status, Open link
- Auto-refresh option (30 seconds)

### What "Open" Does

Clicking "Open" on any dev's project opens their Streamlit dashboard showing:
- **Dashboard** — overview, agent status
- **Activity Logs** — all file changes with diffs, filterable by source/event
- **Rule Violations** — forbidden files, imports, patterns detected
- **Reports** — generate AI reports, view past reports
- **Settings** — edit config.yaml, rules.yaml, purpose.md remotely

### Report Generation

Leads click Generate Report on any dev's dashboard:
1. Agent reads logs + purpose.md + standards.md + rules.yaml
2. Sends to OpenAI GPT-4o with 5 personas
3. Report evaluates: code quality, alignment with purpose, AI vs manual breakdown
4. Report saved as .md file in `.agent/reports/`

API key lives on server, fetched automatically to dev machines.

---

## Heartbeat System

### Per-Project Heartbeat
- Runs while IDE is open
- Every 60 seconds, POSTs to central dashboard
- Sends: dev_name, project_name, network_url, machine name

### System Heartbeat
- Runs independent of IDE (started once, survives IDE close)
- Keeps all registered projects updated with correct IP
- Only sends real IPs (skips 127.0.0.1)
- Registered projects stored in `~/.agent-monitor/.registered_projects.json`

### IP Detection Priority
1. UDP connect to dashboard server (most reliable)
2. Parse `ip addr` / `ifconfig` (Linux/Mac)
3. Parse `ipconfig` (Windows)
4. `getaddrinfo` fallback
5. Prefer `10.0.3.x` subnet over VPN/secondary adapters

---

## Security

- `.agent/` auto-added to `.gitignore` (prevents accidental push to remote)
- `.agent/` auto-added to `.dockerignore` (prevents inclusion in container builds)
- API key never in git repo (fetched from server at runtime)
- Streamlit runs headless (devs can't see their own dashboard)
- Server rejects junk project registrations (blocks `.agent-monitor`, `.Trash`, etc.)
- Dashboard has auth login

---

## Self-Healing

The agent automatically fixes common issues:
- Missing `config.yaml` / `rules.yaml` / `purpose.md` → recreated on startup
- Missing `.agent/` in `.gitignore` → auto-added
- Broken venv (no pip) → detected and recreated
- Missing firewall ports on Linux → `ufw allow 8501:8510/tcp`
- Wrong IP registered → heartbeat corrects within 60 seconds

---

## Cross-Platform Support

| Feature | Windows | Mac | Linux |
|---------|---------|-----|-------|
| VS Code extension | Yes | Yes | Yes |
| JetBrains plugin | Yes | Yes | Yes |
| Cursor | Yes | Yes | Yes |
| VS Code Remote SSH | N/A | N/A | Yes (server) |
| Agent monitoring | Yes | Yes | Yes |
| Console hiding | windowsHide + CREATE_NO_WINDOW | N/A | N/A |
| OS service | schtasks (needs admin) | launchd | systemd |
| Python auto-install | winget/direct download | brew | apt |
| Firewall auto-open | N/A | N/A | ufw allow |

---

## Deployment

### Pre-Check (before installing)

Mac/Linux:
```
curl -sL https://raw.githubusercontent.com/prakyath-ux/monitoring_agent/version2/scripts/precheck.sh | bash
```

Windows:
```
curl -sL https://raw.githubusercontent.com/prakyath-ux/monitoring_agent/version2/scripts/precheck.bat -o %TEMP%\precheck.bat && %TEMP%\precheck.bat
```

### Install

| IDE | File | Steps |
|-----|------|-------|
| VS Code / Cursor | `.vsix` | Cmd+Shift+P → Install from VSIX |
| JetBrains | `.zip` | Settings → Plugins → Install from Disk |
| Terminal only | One-liner | curl command |

### Current Deployment

- 35 machines, 16 devs, 26 projects, 20 devices
- OS: Ubuntu 10, Windows 7, Mac 3, Server 3
- IDEs: JetBrains 12, VS Code 11, Cursor 1, Antigravity 2

---

## Known Limitations

| Issue | Status |
|-------|--------|
| WSL file watching unreliable | Known watchdog limitation, no fix |
| Spaces in project folder name | Breaks on some platforms, rename as workaround |
| DHCP IP changes when IDE closed | System heartbeat fixes on next IDE open |
| Ubuntu needs python3.X-venv specifically | Version-specific package required |
| JetBrains still shows Yes/No prompt | Needs .zip rebuild to remove |
| schtasks on Windows needs admin | Falls back to manual start |

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.9+ |
| File Watching | watchdog library |
| Dashboard | Streamlit |
| LLM | OpenAI GPT-4o |
| Config | YAML |
| VS Code Extension | JavaScript (Node.js) |
| JetBrains Plugin | Kotlin |
| Central Dashboard | Streamlit + HTTP API |
| Auto-Update | git pull every 5 minutes |
