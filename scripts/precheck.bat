@echo off
echo =========================================
echo   Agent Monitor - Pre-Install Check
echo =========================================
echo.

echo --- OS ---
ver
echo.

echo --- Python ---
python --version 2>nul
if %errorlevel%==0 (
    echo   PASS
) else (
    echo   FAIL: Python not found
    echo   Fix: Download from https://python.org - check "Add to PATH"
)
echo.

echo --- pip ---
python -m pip --version 2>nul
if %errorlevel%==0 (
    echo   PASS
) else (
    echo   FAIL: pip not found
    echo   Fix: Reinstall Python with "Add to PATH" checked
)
echo.

echo --- git ---
git --version 2>nul
if %errorlevel%==0 (
    echo   PASS
) else (
    echo   FAIL: git not found
    echo   Fix: Download from https://git-scm.com
)
echo.

echo --- Network: Dashboard Server ---
curl -s --max-time 5 http://10.0.3.55:5000/ >nul 2>&1
if %errorlevel%==0 (
    echo   PASS: 10.0.3.55:5000 reachable
) else (
    echo   FAIL: Cannot reach 10.0.3.55:5000
    echo   Check: Are you on the office network?
)
echo.

echo --- Network: GitHub ---
curl -s --max-time 5 https://github.com >nul 2>&1
if %errorlevel%==0 (
    echo   PASS: github.com reachable
) else (
    echo   FAIL: Cannot reach github.com
    echo   Check: Internet connection or proxy settings
)
echo.

echo =========================================
echo   All PASS = Ready to install extension
echo   Any FAIL = Fix before installing
echo =========================================
pause
