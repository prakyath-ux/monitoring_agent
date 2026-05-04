# RepoAgent — Technical Overview

## What It Is

RepoAgent is a silent local monitoring agent that runs on every developer's machine. It watches file activity in real time, identifies whether each change came from an AI tool (Claude Code, Cursor, Copilot) or a human, and writes a structured activity log. Team leads access a central dashboard that lists every developer's machine, opens any developer's project view, and generates AI-written reports comparing actual work against the project's stated purpose.

**The product goal is insight, not surveillance** — a graceful evaluation of how a codebase is evolving, not a tool to police developers.

## How It's Structured

Three layers:

1. **Dev Machine Layer** — IDE extension/plugin + monitoring agent + per-project Streamlit dashboard
2. **Central Server Layer** — fleet dashboard, machine registry, API key distribution, report archive
3. **Git Layer** — the single source of truth for agent code; every dev machine pulls from it every 5 minutes

## The Bootstrap + Loader Pattern (key design decision)

We needed to push fixes to 30+ machines without asking developers to reinstall anything.

- **Bootstrap** (.vsix for VS Code, .zip for JetBrains) — installed once, almost never changes. ~70 lines of code. Its only job: clone the loader repo and run it.
- **Loader** (`extension-loader.js`, `jetbrains-loader.py`) — the real logic. Lives in Git. Auto-pulled on every IDE open and every 5 minutes by the running agent.

When we ship a fix, every developer's machine pulls and self-restarts within 5 minutes. No reinstall, no message blast, no version drift.

## What Gets Tracked

For every file change in a watched project:
- File path, change type (created / modified / renamed / deleted)
- Unified diff
- Source classification (Claude Code, Cursor, VS Code, IntelliJ, Manual Edit)
- Git branch
- Timestamp

Noise reduction is aggressive:
- 30 s silence + 5 min max-wait batching collapses auto-save spam
- `ignore.yaml` filters out `node_modules`, `.venv`, `build/`, `target/`, `.next/`, etc.
- Branch-switch detection suppresses the 50+ events that fire on a checkout
- Pause/resume cycle wipes the RAM diff cache after branch operations

## AI vs Manual Detection

Two-step heuristic:
1. Scan running processes (Claude, Cursor, VS Code, IntelliJ)
2. If a bulk change (>10 lines) happens while an AI-capable tool is running, label as that tool's AI output

Not perfect, but reliable enough to surface trends ("Project X is 70% AI-generated this sprint").

## Reports

Generated on demand by GPT-4o using six personas, each reading the same activity logs through a different lens:

| Persona | Lens |
|---|---|
| Guardian | Rule violations from `rules.yaml` |
| Architect | High-level structural changes |
| Architecture Reviewer | Design concerns |
| Strategist | Alignment with `purpose.md` |
| Mentor | Patterns to teach the team |
| Investigator / Source Analysis | AI vs manual breakdown |

Optional context layer: SonarQube findings fetched live during report generation.

## Central Dashboard

Hosted at `172.16.0.146:8503` on the internal network only. Five role-based logins (frontend, backend, mobile, AI, development).

For each registered machine the dashboard shows:
- Status — Running / Stopped / Offline
- **Open** link — opens the dev's per-project Streamlit
- **History** link — past reports, archived even when the dev is offline
- Team / dev / project filters
- Sort: Running first, grouped by dev + machine

## Per-Dev Dashboard

Each developer's machine runs its own Streamlit dashboard silently in the background (no browser tab opens):
- **Activity Logs** — paginated 5 days per page
- **Rule Violations** — from `rules.yaml`
- **Reports** — pick a date range, generate, browse history
- **Settings** — edit `config.yaml`, `rules.yaml`, `purpose.md` remotely from the lead's browser

The lead opens this via the central dashboard's **Open** link.

## Heartbeats

Two heartbeats run in parallel:
1. **Per-project (60 s)** — IDE extension keeps the project's port and IP fresh in the registry
2. **System-level (independent)** — runs whether the IDE is open or not, so the machine stays visible in the registry even after work hours

DHCP IP changes are corrected on the next heartbeat.

## Auto-Update Cycle

Every 5 minutes, on every dev machine:
1. Agent runs `git pull` in `~/.agent-monitor/`
2. If new commits exist, it re-execs itself with the new code (`Popen` on Windows, `execv` on Mac/Linux)
3. Loaders re-load on the next IDE open

A fix pushed to `version2` reaches every developer in under 5 minutes.

## Self-Healing

On every agent start:
- Recreates missing `config.yaml`, `rules.yaml`, `purpose.md`
- Auto-merges new patterns into `ignore.yaml` (handles drift in old installs)
- Detects stale PID files (>5 min mtime = dead process)
- Probes Streamlit port to verify it's serving **this** project, not a stale window

## Privacy & Stealth

- Runs silently on Windows (`CREATE_NO_WINDOW`, `windowsHide`, no console flashing)
- No browser tabs are opened
- All traffic stays on the internal network (10.0.3.x / 172.16.0.x)
- Logs and reports are stored locally; only uploaded to the internal server
- API key distributed via an authenticated `/env` endpoint, restricted to internal subnets

## Deployment Scale (current)

- **35 machines** registered, **30 active**
- **16 developers** across **6 teams**
- **26+ projects** monitored
- IDEs: VS Code (11), JetBrains (12), Cursor (1), Antigravity (2)
- OS: Ubuntu (10), Windows (7), macOS (3), Server (3)

## Tech Stack

| Layer | Tech |
|---|---|
| Monitoring agent | Python 3.9+, watchdog |
| VS Code extension | Node.js / JavaScript |
| JetBrains plugin | Kotlin (bootstrap) + Python (loader) |
| Per-dev dashboard | Streamlit |
| Central dashboard | Streamlit + Flask registry API |
| LLM | OpenAI GPT-4o |
| Config | YAML |
| Persistence | Plain-text logs, JSON registry |

## What's Next

- SonarQube findings woven directly into reports (POC working)
- Crash-recovery watchdog
- Health endpoint to distinguish "unhealthy" from "offline"
- Multi-IDE lockfile — one project, one agent
- Auto-init `.agent` for JetBrains without prompt
