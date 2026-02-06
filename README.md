# Local Directory Monitoring Agent

An autonomous local AI agent that runs on developer machines, monitors all file activity in a working directory, logs everything as context, and generates intelligent reports on demand.

```
Dev works normally → Agent watches silently → Logs everything → Generate report anytime
```

## Quick Start

```bash
# 1. Clone the repo
git clone <repo-url>
cd repo_agent

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate          # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp .env
# Edit .env and add your OpenAI API key

# 5. Initialize the agent
python agent.py init

# 6. Start monitoring
python agent.py start
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `python agent.py init` | Initialize `.agent/` folder with default config |
| `python agent.py start` | Start monitoring (foreground) |
| `python agent.py stop` | Stop monitoring |
| `python agent.py pause` | Pause logging (use before branch switches) |
| `python agent.py resume` | Resume logging (refreshes file cache from disk) |
| `python agent.py status` | Check if the agent is running |
| `python agent.py report` | Generate an AI-powered report from logs |
| `python agent.py logs` | View recent activity logs |
| `python agent.py scan` | Scan existing codebase metadata |
| `python agent.py check` | Validate codebase against `rules.yaml` |

## Dashboard

Launch the Streamlit UI for a visual interface:

```bash
streamlit run UI.py
```

The dashboard provides:
- Start / Stop / Pause / Resume controls
- Live activity log viewer
- Analytics and file change history

## AI Source Detection

The agent automatically detects which editor made each change and whether it was AI-assisted.

**Supported IDEs:** VS Code, Cursor, IntelliJ, PyCharm, Claude Code

| Source Label | Meaning |
|-------------|---------|
| `Claude Code (AI)` | AI-generated changes via Claude Code |
| `VS Code (AI Tool)` | Bulk changes from VS Code (likely AI-assisted) |
| `Cursor (AI)` | AI-generated changes via Cursor |
| `IntelliJ (AI Tool)` | Bulk changes from IntelliJ (likely AI-assisted) |
| `PyCharm (AI Tool)` | Bulk changes from PyCharm (likely AI-assisted) |
| `VS Code` | Manual edits in VS Code |
| `Cursor` | Manual edits in Cursor |
| `IntelliJ` | Manual edits in IntelliJ |
| `PyCharm` | Manual edits in PyCharm |
| `Manual Edit` | No recognized editor detected |

> **Note:** For accurate detection, run only one IDE at a time. The agent uses process detection, so multiple open editors may cause the first match in the priority chain to be reported.

## Configuration

All config lives in the `.agent/` directory (created by `python agent.py init`):

| File | Purpose |
|------|---------|
| `config.yaml` | Watched file extensions, LLM model, log retention days |
| `rules.yaml` | Forbidden imports, files, patterns, function/file line limits |
| `ignore.yaml` | Paths and patterns the agent skips during monitoring and scanning |
| `purpose.md` | Repository mission and boundaries (used for deviation detection) |
| `standards.md` | Coding standards referenced in generated reports |

## Branch Switch Workflow

To avoid noisy diffs when switching branches:

```bash
python agent.py pause       # 1. Pause the agent
git add . && git commit     # 2. Commit your work
git checkout other-branch   # 3. Switch branch
python agent.py resume      # 4. Resume — cache refreshes automatically
```

## Requirements

- Python 3.11+
- OpenAI API key (GPT-4o)
