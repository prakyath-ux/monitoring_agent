# Agent Monitor - Deployment Guide

## VS Code Users (Any OS)

1. Get the `.vsix` file
2. Open VS Code
3. `Cmd+Shift+P` (Mac) or `Ctrl+Shift+P` (Windows/Linux)
4. Type: **Install from VSIX** → select the file
5. Reopen VS Code in your project folder
6. Done. Agent runs automatically on every VS Code startup.

---

## Non-VS Code Users (Mac / Linux)

### First Project

Open terminal, go to your project folder, paste this:

```
cd /path/to/your/project
curl -sL https://raw.githubusercontent.com/prakyath-ux/monitoring_agent/version2/start-monitor.sh | bash
```

That's it. Everything installs and starts automatically.

### Additional Projects (Any project after first project where agent is needed)

```
cd /path/to/another/project
bash ~/.agent-monitor/start-monitor.sh
```

### Stop Monitoring

```
cd /path/to/project
bash ~/.agent-monitor/stop-monitor.sh
```

---

## Non-VS Code Users (Windows)

### First Project

Open CMD or PowerShell, go to your project folder, paste this:

```
cd D:\path\to\your\project
curl -sL https://raw.githubusercontent.com/prakyath-ux/monitoring_agent/version2/start-monitor.bat -o %TEMP%\start-monitor.bat && %TEMP%\start-monitor.bat
```

That's it. Everything installs and starts automatically.

### Additional Projects

```
cd D:\path\to\another\project
%USERPROFILE%\.agent-monitor\start-monitor.bat
```

### Stop Monitoring

```
cd D:\path\to\project
%USERPROFILE%\.agent-monitor\stop-monitor.bat
```

---

## What Happens Behind the Scenes

- Installs Git and Python if not found
- Creates a hidden folder `~/.agent-monitor/` in your home directory (one-time)
- Creates `.agent/` inside your project folder (per project)
- Agent monitors file changes silently in the background
- No dashboard, no popups, no browser tabs — just a background process

## Requirements

- Internet connection (first run only)
- Git (auto-installed if missing)
- Python 3.9+ (auto-installed if missing)
