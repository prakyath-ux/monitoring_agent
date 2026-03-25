@echo off
REM ── Agent Monitor Startup Script (version2) ──
REM Works with any IDE (IntelliJ, PyCharm, Sublime, Terminal)
REM Matches VS Code extension behavior: silent, heartbeat, auto-pull

setlocal enabledelayedexpansion

set "AGENT_HOME=%USERPROFILE%\.agent-monitor"
set "REPO_URL=https://github.com/prakyath-ux/monitoring_agent.git"
set "BRANCH=version2"
set "DASHBOARD_SERVER=10.0.3.55"
set "DASHBOARD_PORT=5000"

REM ── Check and install prerequisites ──
where git > nul 2>&1
if errorlevel 1 (
    echo Installing Git...
    winget install Git.Git --silent --accept-package-agreements --accept-source-agreements
    set "PATH=%PATH%;C:\Program Files\Git\cmd"
)

where python > nul 2>&1
if errorlevel 1 (
    echo Installing Python...
    winget install Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
    set "PATH=%PATH%;%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts"
)

REM ── Verify installs ──
where git > nul 2>&1
if errorlevel 1 (
    echo Git installation failed. Install manually and re-run.
    exit /b 1
)
where python > nul 2>&1
if errorlevel 1 (
    echo Python installation failed. Close and reopen terminal, then re-run.
    exit /b 1
)

REM ── Project dir: first arg or current directory ──
if "%~1"=="" (
    set "PROJECT_DIR=%CD%"
) else (
    set "PROJECT_DIR=%~1"
)

for %%i in ("%PROJECT_DIR%") do set "PROJECT_NAME=%%~ni"

REM ── Clone if not installed ──
if not exist "%AGENT_HOME%\.git" (
    if exist "%AGENT_HOME%" rmdir /s /q "%AGENT_HOME%"
    echo Installing agent...
    git clone -b %BRANCH% "%REPO_URL%" "%AGENT_HOME%" > nul 2>&1
    if errorlevel 1 (
        echo Clone failed.
        exit /b 1
    )
)

REM ── Auto-pull latest code ──
git -C "%AGENT_HOME%" pull origin %BRANCH% > nul 2>&1

REM ── Run setup.py if venv or .agent missing ──
set "PYTHON=%AGENT_HOME%\venv\Scripts\python.exe"
set "STREAMLIT=%AGENT_HOME%\venv\Scripts\streamlit.exe"
set "SETUP_PY=%AGENT_HOME%\version2\setup.py"

if not exist "%PYTHON%" goto :run_setup
if not exist "%PROJECT_DIR%\.agent" goto :run_setup
goto :skip_setup

:run_setup
echo Running setup...
python "%SETUP_PY%" "%PROJECT_DIR%"
if errorlevel 1 (
    echo Setup failed.
    exit /b 1
)

:skip_setup

REM ── Check if already running for this project ──
if exist "%PROJECT_DIR%\.agent\.pid" (
    echo Agent already running.
    exit /b 0
)

REM ── Find free port starting from 8501 ──
set PORT=8501
:find_port
netstat -an | find ":%PORT% " > nul 2>&1
if not errorlevel 1 (
    set /a PORT+=1
    goto :find_port
)

REM ── Get LAN IP (prefer 10.0.3.x subnet) ──
set "LAN_IP=127.0.0.1"
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    for /f "tokens=1" %%b in ("%%a") do (
        echo %%b | findstr "10\.0\.3\." > nul 2>&1
        if not errorlevel 1 (
            set "LAN_IP=%%b"
            goto :ip_found
        )
        if "!LAN_IP!"=="127.0.0.1" set "LAN_IP=%%b"
    )
)
:ip_found

REM ── Start Streamlit silently in background ──
set "AGENT_PROJECT_DIR=%PROJECT_DIR%"
set "AGENT_STREAMLIT_PORT=%PORT%"
start /b "" "%STREAMLIT%" run "%AGENT_HOME%\UI.py" --server.address 0.0.0.0 --server.port %PORT% --server.headless true --server.baseUrlPath %PROJECT_NAME% > nul 2>&1

timeout /t 2 /nobreak > nul

REM ── Save Streamlit PID for cleanup ──
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    echo %%p > "%PROJECT_DIR%\.agent\.streamlit_pid"
    goto :pid_saved
)
:pid_saved

REM ── Start agent in background ──
start /b "" "%PYTHON%" "%AGENT_HOME%\agent.py" --project-dir "%PROJECT_DIR%" start > nul 2>&1

REM ── Register with central dashboard ──
curl -s -X POST "http://%DASHBOARD_SERVER%:%DASHBOARD_PORT%" -H "Content-Type: application/json" -d "{\"dev_name\":\"%USERNAME%\",\"project_name\":\"%PROJECT_NAME%\",\"network_url\":\"http://%LAN_IP%:%PORT%/%PROJECT_NAME%\",\"machine\":\"%COMPUTERNAME%\"}" > nul 2>&1

REM ── Start heartbeat in background (separate hidden process) ──
start /b "" cmd /c "%AGENT_HOME%\heartbeat.bat" "%DASHBOARD_SERVER%" "%DASHBOARD_PORT%" "%USERNAME%" "%PROJECT_NAME%" "%LAN_IP%" "%PORT%" "%COMPUTERNAME%" > nul 2>&1

echo Agent started.
