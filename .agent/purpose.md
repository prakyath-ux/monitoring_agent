# Repository Purpose

> This document defines the core intent, direction, and boundaries of this repository.
> The monitoring agent uses this file to evaluate whether code changes align with or deviate from the project's mission.

---

## Mission Statement

Build an **autonomous local AI agent** that runs silently on developer machines, monitors all file activity in a working directory, maintains persistent memory through logs, and generates intelligent reports on demand.

The agent acts as a **silent observer and advisor** - it watches, remembers, and reports, but does not interrupt the developer's workflow unless explicitly asked.

---

## Problem Being Solved

### The Core Pain Points

1. **Lost Context**: Developers forget what they worked on, why they made certain changes, or what state the code was in before modifications.

2. **No Activity Trail**: Teams lack visibility into what actually happened during development sessions - which files were touched, what was added/removed, how code evolved.

3. **Delayed Code Review**: Issues are caught too late in the process. By the time code is reviewed, the developer has moved on and context is lost.

4. **Standard Drift**: Over time, codebases drift from established standards. No one notices until technical debt becomes unmanageable.

5. **AI Tool Blindness**: When AI assistants (Claude Code, Cursor, Copilot) make changes, there's no record of what was modified or why.

### How This Agent Solves Them

| Problem | Solution |
|---------|----------|
| Lost context | Persistent logs capture everything with timestamps |
| No activity trail | File watcher records all create/modify/delete/rename events |
| Delayed review | On-demand reports analyze activity immediately |
| Standard drift | Reports check code against defined standards |
| AI tool blindness | Watchdog captures ALL file changes regardless of source |

---

## Architecture Philosophy

### Design Principles

1. **Local-First**: Everything runs on the developer's machine. No cloud dependencies for core functionality. The only external call is to the LLM API for report generation.

2. **Non-Intrusive**: The agent runs silently in the background. It never blocks, interrupts, or modifies the developer's work unless explicitly commanded.

3. **Memory-Persistent**: All activity is logged to disk. Stopping and restarting the agent does not lose historical data. Logs are the agent's memory.

4. **On-Demand Intelligence**: The agent doesn't constantly call the LLM. It only uses AI when the developer requests a report, keeping costs and latency minimal.

5. **Configuration over Code**: Behavior is controlled through YAML config files, not code changes. Users customize without touching agent.py.

6. **Single-File Simplicity**: The core agent is one Python file. No complex package structure. Easy to understand, modify, and debug.

### Component Responsibilities

| Component | Single Responsibility |
|-----------|----------------------|
| **FileEventHandler** | Detect and classify file system events |
| **LogWriter** | Persist events to disk with timestamps and diffs |
| **ReportEngine** | Transform logs into insights via LLM |
| **CLI Commands** | User interface for controlling the agent |
| **Config Files** | Store user preferences and rules |

---

## Current Capabilities (Phase 1)

### What the Agent Can Do Now

- **Initialize** a `.agent/` folder structure in any directory
- **Start** background monitoring of file changes
- **Stop** the monitoring process gracefully
- **Check status** of whether the agent is running
- **Log events**: FILE_CREATED, FILE_MODIFIED, FILE_DELETED, FILE_RENAMED
- **Capture diffs** showing before/after content for modifications
- **Generate reports** by sending logs + standards to OpenAI API
- **Filter files** by extension (configurable)
- **Ignore paths** matching specified patterns

### What the Agent Cannot Do Yet

- Scan existing codebase for context (planned: `scan` command)
- Check code against rules in real-time (planned: `check` command)
- Auto-fix issues (planned: Phase 3)
- Compare changes against this purpose file (implementing now)
- Understand semantic meaning of code (requires scan)

---

## Planned Evolution (Roadmap)

### Phase 2: Context & Rules (Current Focus)

| Feature | Purpose |
|---------|---------|
| **purpose.md** | Define repo intent for deviation detection |
| **rules.yaml** | Machine-checkable coding rules |
| **scan command** | Build context from existing codebase |
| **check command** | Real-time rule validation on file changes |

### Phase 3: Intelligence

| Feature | Purpose |
|---------|---------|
| **Conflict detection** | Identify when changes conflict with existing code |
| **Solution suggestions** | Propose fixes for detected issues |
| **Auto-fix mode** | Automatically apply safe fixes with user approval |

### Phase 4: Team Features

| Feature | Purpose |
|---------|---------|
| **Report export** | Save reports to files for sharing |
| **Multiple profiles** | Different rule sets for different projects |
| **Integration hooks** | Trigger actions on specific events |

---

## Boundaries: What Belongs Here

### Core Scope

This repository should contain ONLY:

1. **File System Monitoring**
   - Watching directories for changes
   - Detecting file events (create, modify, delete, rename)
   - Capturing file content and diffs
   - Filtering by extension and ignore patterns

2. **Activity Logging**
   - Writing events to log files
   - Timestamping all activity
   - Organizing logs by date
   - Log retention and cleanup

3. **Report Generation**
   - Reading and aggregating logs
   - Building prompts with context
   - Calling LLM APIs
   - Formatting and displaying reports

4. **CLI Interface**
   - Command parsing (init, start, stop, status, report, logs)
   - User feedback and output
   - Error handling and messages

5. **Configuration Management**
   - Loading YAML config files
   - Default value handling
   - Ignore pattern matching
   - Standards and rules loading

6. **Context Building** (Phase 2)
   - Codebase scanning
   - Purpose and rules evaluation
   - Real-time checking

---

## Boundaries: What Does NOT Belong Here

### Explicit Exclusions

The following should NEVER be added to this repository:

1. **Web Interfaces**
   - No HTTP servers
   - No REST APIs
   - No WebSocket endpoints
   - No browser-based dashboards
   - This is a CLI tool, not a web application

2. **Database Systems**
   - No SQL databases (SQLite, PostgreSQL, MySQL)
   - No NoSQL databases (MongoDB, Redis for persistence)
   - Logs are stored as flat files, not database records
   - If persistence needs grow, consider SQLite as a LAST resort

3. **User Authentication**
   - No login systems
   - No user accounts
   - No password management
   - No OAuth/SSO integration
   - This runs locally for a single developer

4. **External Service Integrations**
   - No GitHub/GitLab API integration
   - No Slack/Discord notifications
   - No email sending
   - No cloud storage uploads
   - Exception: LLM API calls for reports are allowed

5. **IDE Plugins**
   - No VS Code extensions
   - No JetBrains plugins
   - No editor integrations
   - The agent is editor-agnostic by design

6. **Build/Deploy Tools**
   - No CI/CD pipeline code
   - No Docker containers
   - No Kubernetes configs
   - No deployment scripts

7. **Testing Frameworks for User Code**
   - The agent does not run user's tests
   - The agent does not validate user's builds
   - The agent only observes and reports

---

## Deviation Signals

### Red Flags for Code Review

When reviewing changes, the agent should flag these as potential deviations:

#### Architecture Deviations

- Adding new external dependencies not related to file watching, logging, or LLM calls
- Creating new Python files that fragment the single-file design without justification
- Adding async/await patterns (current design is synchronous and simple)
- Introducing class hierarchies or complex inheritance
- Adding decorator-heavy patterns or metaprogramming

#### Scope Creep Signals

- Any mention of "server", "endpoint", "route", "API" in new code
- Import statements for web frameworks (flask, fastapi, django, aiohttp)
- Import statements for database libraries (sqlalchemy, pymongo, sqlite3)
- Import statements for authentication (jwt, oauth, passlib)
- Creating files named like: `api.py`, `server.py`, `routes.py`, `models.py`, `auth.py`

#### Feature Creep Signals

- Adding features not mentioned in the roadmap phases
- Building "nice to have" features before core Phase 2 is complete
- Over-engineering simple solutions
- Adding configuration options that no one asked for

#### Code Quality Signals

- Functions exceeding 50 lines
- Files exceeding 600 lines
- Deeply nested logic (more than 3 levels)
- Hardcoded values that should be configurable
- Missing error handling for file operations
- Catching broad exceptions without specific handling

---

## Success Criteria

### How to Know the Agent is Working

1. **Functional Success**
   - Agent starts and stops without errors
   - All file changes in watched extensions are logged
   - Reports are generated successfully
   - Logs persist across restarts

2. **Quality Success**
   - Code remains in single file (agent.py) under 800 lines
   - All functions have clear single responsibilities
   - Configuration drives behavior, not hardcoded values
   - Error messages are helpful and actionable

3. **User Experience Success**
   - Developer never notices agent running (non-intrusive)
   - Commands respond quickly (< 1 second except report)
   - Reports provide actionable insights
   - Setup takes less than 2 minutes

---

## Decision Framework

### When Adding New Features

Ask these questions before adding any new code:

1. **Is this in the roadmap?**
   - If no, it probably shouldn't be added yet
   - Focus on completing current phase first

2. **Does this require new dependencies?**
   - If yes, justify why existing tools can't solve it
   - Prefer standard library over third-party

3. **Does this add to agent.py or create new files?**
   - Prefer keeping logic in agent.py
   - New files only for truly separate concerns

4. **Does this serve the core mission?**
   - Watch files, log activity, generate reports
   - If it doesn't serve this, reconsider

5. **Is this the simplest solution?**
   - Avoid over-engineering
   - POC-level code is acceptable for new features

### When Modifying Existing Code

1. **Does this change break existing functionality?**
   - Test all commands after modifications

2. **Does this change align with existing patterns?**
   - Follow the established code style
   - Match existing function signatures

3. **Is this change reversible?**
   - Avoid destructive changes to log format
   - Maintain backwards compatibility with existing logs

---

## Technical Constraints

### Hard Requirements

- **Python 3.11+**: Using modern Python features
- **Single file architecture**: agent.py is the entire application
- **File-based logging**: No databases for activity storage
- **CLI-only interface**: No GUI, no web, no TUI
- **Local execution**: No remote/cloud components
- **Synchronous design**: No async/await complexity

### Soft Preferences

- Keep dependencies minimal (currently: watchdog, openai, pyyaml, python-dotenv)
- Prefer explicit over implicit
- Prefer readable over clever
- Prefer working over perfect

---

## Context for LLM Analysis

When the agent generates reports, it should understand:

1. **This is a developer productivity tool** - not a security tool, not a testing framework, not a build system

2. **The user is a developer** - they understand code, they want technical feedback, not hand-holding

3. **Changes should be evaluated against**:
   - The coding standards (standards.md)
   - The project purpose (this file)
   - The specific rules (rules.yaml, when implemented)
   - The existing codebase context (scan data, when implemented)

4. **Reports should be actionable** - not just observations, but recommendations

5. **Tone should be direct** - professional, technical, concise

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2024-01-28 | Initial purpose definition |

---

*This document should be updated when the project direction changes significantly.*
