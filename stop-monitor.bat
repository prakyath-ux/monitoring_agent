@echo off
REM ── Stop Agent Monitor ──

set "AGENT_HOME=%USERPROFILE%\.agent-monitor"
if "%~1"=="" (set "PROJECT_DIR=%CD%") else (set "PROJECT_DIR=%~1")
set "PYTHON=%AGENT_HOME%\venv\Scripts\python.exe"

REM Stop agent
"%PYTHON%" "%AGENT_HOME%\agent.py" --project-dir "%PROJECT_DIR%" stop > nul 2>&1

REM Stop Streamlit
taskkill /F /IM streamlit.exe > nul 2>&1

echo Agent stopped.
