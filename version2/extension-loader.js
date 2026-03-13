// ---- Extension Loader (lives in repo, auto-updates via git pull) ----
// All real logic: setup, Streamlit, agent start/stop, status bar

const vscode = require('vscode');
const { spawn, execFile, execSync, execFileSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');
const net = require('net');

let statusBarItem;
let streamlitProcess = null;

const AGENT_HOME = path.join(os.homedir(), '.agent-monitor');
const IS_WIN = process.platform === 'win32';
const VENV_BIN = IS_WIN ? 'Scripts' : 'bin';
const PYTHON_CMD = IS_WIN ? 'python' : 'python3';
const EXE = IS_WIN ? '.exe' : '';
const MIN_ENV = IS_WIN
    ? { PATH: process.env.PATH, USERPROFILE: process.env.USERPROFILE, HOME: process.env.HOME || process.env.USERPROFILE, SYSTEMROOT: process.env.SYSTEMROOT, TEMP: process.env.TEMP, PATHEXT: process.env.PATHEXT || '.COM;.EXE;.BAT;.CMD', COMSPEC: process.env.COMSPEC || 'C:\\Windows\\System32\\cmd.exe' }
    : { PATH: process.env.PATH, HOME: process.env.HOME, USER: process.env.USER, LANG: process.env.LANG || 'en_US.UTF-8' };

// ---- Helpers ----

function findFreePort(start = 8501) {
    return new Promise((resolve) => {
        const server = net.createServer();
        server.listen(start, '0.0.0.0', () => {
            server.close(() => resolve(start));
        });
        server.on('error', () => resolve(findFreePort(start + 1)));
    });
}

function getWorkspacePath() {
    const folders = vscode.workspace.workspaceFolders;
    if (!folders || folders.length === 0) return null;
    return folders[0].uri.fsPath;
}

function updateStatusBar(state) {
    if (!statusBarItem) return;
    if (state === 'running') {
        statusBarItem.text = '$(eye) Agent: Running';
        statusBarItem.color = '#4EC9B0';
    } else if (state === 'stopped') {
        statusBarItem.text = '$(circle-slash) Agent: Stopped';
        statusBarItem.color = '#F44747';
    } else if (state === 'installing') {
        statusBarItem.text = '$(sync~spin) Agent: Installing...';
        statusBarItem.color = '#DCDCAA';
    } else {
        statusBarItem.text = '$(loading~spin) Agent: Starting...';
        statusBarItem.color = '#DCDCAA';
    }
}

// ---- Setup ----

function ensureSetup(cwd) {
    const streamlitPath = path.join(AGENT_HOME, 'venv', VENV_BIN, 'streamlit' + EXE);
    const agentDir = path.join(cwd, '.agent');

    // Already fully set up? Skip
    if (fs.existsSync(path.join(AGENT_HOME, '.git'))
        && fs.existsSync(streamlitPath)
        && fs.existsSync(agentDir)) {
        return true;
    }

    // Run setup.py for venv, deps, .agent init, service
    const setupPy = path.join(AGENT_HOME, 'version2', 'setup.py');
    if (!fs.existsSync(setupPy)) {
        vscode.window.showErrorMessage('Agent Monitor: setup.py not found.');
        updateStatusBar('stopped');
        return false;
    }

    if (!fs.existsSync(streamlitPath) || !fs.existsSync(agentDir)) {
        updateStatusBar('installing');
        vscode.window.showInformationMessage('Agent Monitor: Running setup...');
        try {
            execFileSync(PYTHON_CMD, [setupPy, cwd], {
                timeout: 300000, env: MIN_ENV
            });
        } catch (e) {
            vscode.window.showErrorMessage(`Agent Monitor: Setup failed - ${e.message}`);
            updateStatusBar('stopped');
            return false;
        }
        vscode.window.showInformationMessage('Agent Monitor: Setup complete.');
    }

    return true;
}

// ---- Streamlit ----

async function launchStreamlit(cwd) {
    if (streamlitProcess && !streamlitProcess.killed) return;

    updateStatusBar('starting');

    const projectName = path.basename(cwd);
    const streamlitCmd = path.join(AGENT_HOME, 'venv', VENV_BIN, 'streamlit' + EXE);
    const uiPy = path.join(AGENT_HOME, 'UI.py');

    const port = await findFreePort(8501);

    streamlitProcess = spawn(streamlitCmd, [
        'run', uiPy,
        '--server.address', '0.0.0.0',
        '--server.port', String(port),
        '--server.baseUrlPath', projectName
    ], {
        cwd: cwd,
        detached: true,
        stdio: ['ignore', 'pipe', 'pipe'],
        env: { ...MIN_ENV, AGENT_PROJECT_DIR: cwd, AGENT_STREAMLIT_PORT: String(port) }
    });

    let stderrData = '';
    if (streamlitProcess.stderr) {
        streamlitProcess.stderr.on('data', (data) => { stderrData += data.toString(); });
    }

    streamlitProcess.unref();

    streamlitProcess.on('error', (err) => {
        vscode.window.showErrorMessage(`Streamlit failed: ${err.message}`);
        updateStatusBar('stopped');
    });

    streamlitProcess.on('exit', (code) => {
        if (code !== 0 && code !== null) {
            const errMsg = stderrData.split('\n').slice(-3).join(' ').trim();
            vscode.window.showErrorMessage(`Streamlit crashed (code ${code}): ${errMsg || 'unknown'}`);
            updateStatusBar('stopped');
            streamlitProcess = null;
        }
    });

    // Explicitly start the agent, then check real status
    setTimeout(() => {
        if (!streamlitProcess || streamlitProcess.killed) return;

        const pythonPath = path.join(AGENT_HOME, 'venv', VENV_BIN, 'python' + EXE);
        const agentPy = path.join(AGENT_HOME, 'agent.py');

        execFile(pythonPath, [agentPy, '--project-dir', cwd, 'start'], { cwd, env: MIN_ENV }, () => {
            setTimeout(() => {
                execFile(pythonPath, [agentPy, '--project-dir', cwd, 'status'], { cwd }, (err, stdout) => {
                    const isRunning = stdout && stdout.includes('running');
                    updateStatusBar(isRunning ? 'running' : 'stopped');
                    vscode.window.showInformationMessage(
                        `Agent Monitor: http://localhost:${port}/${projectName} - Agent ${isRunning ? 'Running' : 'Stopped'}`
                    );
                });
            }, 2000);
        });
    }, 3000);
}

// ---- Commands ----

async function startAgent() {
    const cwd = getWorkspacePath();
    if (!cwd) return;

    if (fs.existsSync(path.join(cwd, 'extension.js'))) {
        updateStatusBar('stopped');
        return;
    }

    if (fs.existsSync(path.join(cwd, '.agent'))) {
        if (!ensureSetup(cwd)) return;
        launchStreamlit(cwd);
        return;
    }

    const choice = await vscode.window.showInformationMessage(
        'Agent Monitor: Initialize monitoring for this project?',
        'Yes', 'No'
    );

    if (choice !== 'Yes') {
        updateStatusBar('stopped');
        return;
    }

    if (!ensureSetup(cwd)) return;
    launchStreamlit(cwd);
}

async function stopAgent() {
    const cwd = getWorkspacePath();
    if (!cwd) return;

    if (streamlitProcess && !streamlitProcess.killed) {
        try {
            if (IS_WIN) {
                execSync(`taskkill /PID ${streamlitProcess.pid} /T /F`, { stdio: 'ignore' });
            } else {
                process.kill(-streamlitProcess.pid);
            }
        } catch (e) {}
        streamlitProcess = null;
    }

    const pythonPath = path.join(AGENT_HOME, 'venv', VENV_BIN, 'python' + EXE);
    if (fs.existsSync(pythonPath)) {
        execFile(pythonPath, [path.join(AGENT_HOME, 'agent.py'), '--project-dir', cwd, 'stop'], { cwd });
    }

    updateStatusBar('stopped');
    vscode.window.showInformationMessage('Agent Monitor stopped.');
}

async function checkStatus() {
    const cwd = getWorkspacePath();
    if (!cwd) return;

    const pythonPath = path.join(AGENT_HOME, 'venv', VENV_BIN, 'python' + EXE);
    if (!fs.existsSync(pythonPath)) {
        vscode.window.showWarningMessage('Agent not installed yet. Open a project to trigger setup.');
        return;
    }

    execFile(pythonPath, [path.join(AGENT_HOME, 'agent.py'), '--project-dir', cwd, 'status'], { cwd }, (err, stdout) => {
        const msg = stdout ? stdout.trim() : 'Agent status unknown';
        vscode.window.showInformationMessage(msg);
        updateStatusBar(msg.includes('running') ? 'running' : 'stopped');
    });
}

// ---- Lifecycle ----

function activate(context) {
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    statusBarItem.command = 'agentMonitor.status';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    context.subscriptions.push(
        vscode.commands.registerCommand('agentMonitor.start', startAgent),
        vscode.commands.registerCommand('agentMonitor.stop', stopAgent),
        vscode.commands.registerCommand('agentMonitor.status', checkStatus)
    );

    startAgent();
}

function deactivate() {
    if (streamlitProcess && !streamlitProcess.killed) {
        try {
            if (IS_WIN) {
                execSync(`taskkill /PID ${streamlitProcess.pid} /T /F`, { stdio: 'ignore' });
            } else {
                process.kill(-streamlitProcess.pid);
            }
        } catch (e) {}
    }
}

module.exports = { activate, deactivate };
