# RepoAgent - Code Monitoring System

## What Is It?

RepoAgent is a silent code monitoring tool that runs in the background on every developer's machine. It tracks all file changes, identifies whether code was written manually or by AI tools, and lets team leads generate detailed reports on any developer's work.

Developers don't need to do anything — it runs automatically when they open their IDE.

---

## What It Does

- Monitors every file change a developer makes (creates, edits, deletes)
- Detects the source — was the code written manually, or by AI tools like Claude Code, Cursor, or Copilot
- Tracks which git branch the developer is working on
- Logs full code diffs (what exactly changed)
- Generates AI-powered reports evaluating code quality, alignment with project goals, and development patterns

---

## How To Use (For Team Leads)

### Step 1: Open the Central Dashboard

Go to: **http://10.0.3.55:8503**

Login with your team credentials:
- Frontend team: `frontend` / `access123`
- Backend team: `backend` / `access123`
- Mobile team: `mobile` / `access123`
- AI team: `AI` / `access123`

### Step 2: Filter Your Team

Use the "Filter by Team" dropdown to see only your team's developers.

You'll see each developer with their projects listed. The status shows:
- **Running + Open** — Developer is actively working, click "Open" to view their dashboard
- **Online + Stopped** — Developer's machine is on but they're working on a different project
- **Offline** — Developer's machine is off or not connected

### Step 3: View Developer Activity

Click **"Open"** next to any developer's project. This opens their dashboard where you can see:

- **Activity Logs** — Every file change with timestamps, diffs, and source detection
- **Rule Violations** — Any coding standard violations detected
- **Reports** — Generate or view AI-powered code review reports

### Step 4: Generate Reports

Inside any developer's dashboard:
1. Go to the **Reports** tab
2. Select a date range (From / To)
3. Click **Generate Report**
4. The report evaluates:
   - Code quality and best practices
   - Alignment with the project's stated purpose
   - How much code was AI-generated vs manually written
   - Security concerns (hardcoded passwords, exposed keys, etc.)

### Step 5: Configure Project Settings

Inside any developer's dashboard, go to the **Settings** tab. Here you can configure how the agent evaluates their project:

- **Config** — Set which file types to monitor (e.g., .java, .py, .ts). Edit and save directly from the dashboard.
- **Rules** — Define forbidden files, forbidden imports, forbidden code patterns, and max function/file length limits. The agent checks code against these rules.
- **Purpose** — Describe what the project is about, its goals, and what would count as a deviation. Reports use this to evaluate whether code changes align with the project's mission.

These settings directly shape the quality of generated reports. A well-written purpose and clear rules produce more useful, specific reports. You can update these settings anytime — changes take effect on the next report generation.

---

## What Developers See

Developers see only a small "Agent: Running" text in their IDE's status bar. Nothing else — no dashboards, no popups, no interruptions. The monitoring is completely transparent to their workflow.

---

## What's Monitored

| What | Details |
|------|---------|
| File changes | Every create, edit, delete, rename |
| Code diffs | Exact lines added/removed |
| Source | Manual edit, Claude Code (AI), Cursor (AI), VS Code |
| Branch | Which git branch the change was on |
| Timestamps | When each change happened |
| File types | .java, .kt, .py, .js, .ts, .tsx, .html, .css, .sql, .xml, .yaml, and more |

---

## Supported IDEs

The agent works with any IDE the developer uses:
- VS Code
- IntelliJ IDEA
- PyCharm
- Antigravity
- Cursor
- Any other JetBrains IDE

---

## How It Updates

The system updates itself automatically. When we push improvements or fixes, every developer's machine picks up the changes within 5 minutes — no action needed from developers or leads.

---

## FAQ

**Q: Can developers disable it?**
A: The agent runs as a background process. Developers can see "Agent: Running" in their status bar but cannot easily disable it without uninstalling the extension.

**Q: Does it affect performance?**
A: No. The agent uses minimal resources — it only activates when a file is saved, not continuously.

**Q: Does it work when developers are offline?**
A: Yes — logs are stored locally on their machine. When they reconnect, the dashboard becomes accessible again.

**Q: What if a developer works on a new project?**
A: For VS Code/Cursor, monitoring starts automatically on any project they open. For JetBrains, they'll see a one-time "Initialize?" prompt.

**Q: Is the data secure?**
A: Logs stay on each developer's machine. The central dashboard accesses them over the local office network only — nothing is sent to external servers. API keys are restricted to the internal network.

---

## Coming Next

- **SonarQube Quality Rules Integration** — Official SonarQube rules for Python, Java, JavaScript, Kotlin, HTML, and CSS are ready and will be integrated into report generation in the next update. Reports will automatically evaluate code against industry-standard quality and security rules.
