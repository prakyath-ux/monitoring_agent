// ---- Thin Bootstrap (lives in .vsix, rarely changes) ----
// Only does: clone, pull, then delegates to extension-loader.js from the repo

const { execSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');

const AGENT_HOME = path.join(os.homedir(), '.agent-monitor');
const REPO_URL = 'https://github.com/prakyath-ux/monitoring_agent.git';
const BRANCH = 'version2';
const IS_WIN = process.platform === 'win32';
const MIN_ENV = IS_WIN
    ? { PATH: process.env.PATH, USERPROFILE: process.env.USERPROFILE, HOME: process.env.HOME || process.env.USERPROFILE, SYSTEMROOT: process.env.SYSTEMROOT, TEMP: process.env.TEMP, PATHEXT: process.env.PATHEXT || '.COM;.EXE;.BAT;.CMD', COMSPEC: process.env.COMSPEC || 'C:\\Windows\\System32\\cmd.exe' }
    : { PATH: process.env.PATH, HOME: process.env.HOME, USER: process.env.USER, LANG: process.env.LANG || 'en_US.UTF-8' };

function bootstrap() {
    // Clone if needed
    if (!fs.existsSync(path.join(AGENT_HOME, '.git'))) {
        if (fs.existsSync(AGENT_HOME)) {
            fs.rmSync(AGENT_HOME, { recursive: true, force: true });
        }
        execSync(`git clone -b ${BRANCH} "${REPO_URL}" "${AGENT_HOME}"`, {
            timeout: 120000, env: MIN_ENV
        });
    }

    // Always pull latest
    try {
        execSync(`git -C "${AGENT_HOME}" pull origin ${BRANCH}`, {
            timeout: 30000, env: MIN_ENV, stdio: 'ignore'
        });
    } catch (e) {}
}

function activate(context) {
    try {
        bootstrap();
    } catch (e) {
        const vscode = require('vscode');
        vscode.window.showErrorMessage(`Agent Monitor: Bootstrap failed - ${e.message}`);
        return;
    }

    // Load the real extension from the repo (auto-updates via git pull)
    const loaderPath = path.join(AGENT_HOME, 'version2', 'extension-loader.js');
    if (!fs.existsSync(loaderPath)) {
        const vscode = require('vscode');
        vscode.window.showErrorMessage('Agent Monitor: extension-loader.js not found.');
        return;
    }

    // Clear require cache so we always get the latest version
    delete require.cache[require.resolve(loaderPath)];
    const loader = require(loaderPath);
    loader.activate(context);
}

function deactivate() {
    const loaderPath = path.join(AGENT_HOME, 'version2', 'extension-loader.js');
    if (fs.existsSync(loaderPath)) {
        try {
            const loader = require(loaderPath);
            if (loader.deactivate) loader.deactivate();
        } catch (e) {}
    }
}

module.exports = { activate, deactivate };
