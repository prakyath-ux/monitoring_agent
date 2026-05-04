# RepoAgent — Architecture Diagram

## System Overview

```
   +------------------------------------------------------+
   |                       GITHUB                         |
   |            monitoring_agent / version2               |
   |          (loaders + agent.py source code)            |
   +------------------------------------------------------+
                            ^
                            |  git pull every 5 min
                            |  self-restart on new code
                            |
   +======================================================+
   ||           DEVELOPER MACHINE   (x30+ devs)          ||
   +======================================================+
   |                                                      |
   |    [ IDE ]   VS Code / JetBrains / Cursor            |
   |       |                                              |
   |       v                                              |
   |    [ Extension / Plugin ]     thin bootstrap         |
   |       |                       (.vsix or .zip)        |
   |       v                                              |
   |    [ Loader ]                 real logic,            |
   |       |                       auto-updates from Git  |
   |       +-------------+----------------+               |
   |       v                              v               |
   |   [ agent.py ]              [ Per-Dev Streamlit ]    |
   |   file watcher              silent, no browser tab   |
   |       |                              |               |
   |       +-----> [ .agent/logs ]    <---+               |
   |       +-----> [ .agent/reports ] <---+               |
   |                                                      |
   +--------+----------------+----------------+-----------+
            |                |                |
            | register +     | upload         | fetch API
            | heartbeat 60s  | report         | key once
            v                v                v
   +======================================================+
   ||         CENTRAL SERVER   172.16.0.146              ||
   ||         (internal network only)                    ||
   +======================================================+
   |                                                      |
   |   [ Registry API ]   Flask :5000                     |
   |       +--> agents.json                               |
   |       +--> reports archive                           |
   |       +--> /env   (API key endpoint)                 |
   |                                                      |
   |   [ Dashboard ]      Streamlit :8503                 |
   |       +--> reads agents.json                         |
   |       +--> reads reports archive                     |
   |                                                      |
   +----------------------+-------------------------------+
                          ^
                          |  login + team filter
                          |  Open dev's project
                          |  View history
                          |
                    +-------------+
                    |  Team Lead  |
                    |  (browser)  |
                    +-------------+


   External AI:

   [ agent.py ] ---- generate report ----> [ OpenAI GPT-4o ]
                                           6 personas:
                                             Guardian
                                             Architect
                                             Architecture Reviewer
                                             Strategist
                                             Mentor
                                             Investigator
```

## How to Read It

- **Developer Machine box** — runs on each of the 30+ developer laptops. The IDE triggers the bootstrap, which loads the real logic, which runs the agent and a silent per-project Streamlit dashboard.
- **Central Server box** — single internal-network host. Holds the fleet registry, the report archive, and the API-key endpoint.
- **GitHub box** — the only place we ship code to. Every dev machine pulls from it every 5 minutes; that is how fixes propagate without reinstalls.
- **Team Lead** — the only human user of the central dashboard. Logs in, filters by team, clicks **Open** to view any developer's per-project dashboard, clicks **History** to read past reports.

## One-Line Flow

```
   Developer writes code
            |
            v
   Agent watches silently
            |
            v
   Logs every change with AI/manual tag
            |
            +-------------------+----------------------+
            |                   |                      |
            v                   v                      v
   IDE extension          Lead opens             Reports uploaded
   self-updates from      dashboard,             to central archive
   Git every 5 min        generates LLM
                          report on demand
```

## Why This Shape

| Design Choice | Why |
|---|---|
| Bootstrap + Loader split | Push fixes to 30+ machines without reinstalls |
| Per-dev Streamlit on each machine | Lead views activity without us shipping data off-machine |
| Heartbeat in two places (IDE + system) | Machine stays visible even when the IDE is closed |
| Single Git source of truth | One commit on `version2` reaches the whole fleet in 5 min |
| Six LLM personas | Same logs, different lenses — Guardian, Architect, Architecture Reviewer, Strategist, Mentor, Investigator |
| Internal network only | All traffic stays on 10.0.3.x / 172.16.0.x; nothing leaves the org |
