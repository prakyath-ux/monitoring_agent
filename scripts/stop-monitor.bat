@echo off
REM ── Stop Agent Monitor ──

set "AGENT_HOME=%USERPROFILE%\.agent-monitor"
if "%~1"=="" (set "PROJECT_DIR=%CD%") else (set "PROJECT_DIR=%~1")
set "PYTHON=%AGENT_HOME%\venv\Scripts\python.exe"

REM Stop agent
"%PYTHON%" "%AGENT_HOME%\agent.py" --project-dir "%PROJECT_DIR%" stop > nul 2>&1

REM Stop Streamlit for this project
if exist "%PROJECT_DIR%\.agent\.streamlit_pid" (
    set /p SPID=<"%PROJECT_DIR%\.agent\.streamlit_pid"
    taskkill /F /PID %SPID% /T > nul 2>&1
    del "%PROJECT_DIR%\.agent\.streamlit_pid" > nul 2>&1
)

echo Agent stopped.
