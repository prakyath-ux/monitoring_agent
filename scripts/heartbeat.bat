@echo off
REM ── Heartbeat: registers with central dashboard every 60s ──
REM Called by start-monitor.bat, runs in background

set "SERVER=%~1"
set "PORT=%~2"
set "DEV=%~3"
set "PROJECT=%~4"
set "IP=%~5"
set "SPORT=%~6"
set "MACHINE=%~7"

:loop
curl -s -X POST "http://%SERVER%:%PORT%" -H "Content-Type: application/json" -d "{\"dev_name\":\"%DEV%\",\"project_name\":\"%PROJECT%\",\"network_url\":\"http://%IP%:%SPORT%/%PROJECT%\",\"machine\":\"%MACHINE%\"}" > nul 2>&1
timeout /t 60 /nobreak > nul
goto :loop
