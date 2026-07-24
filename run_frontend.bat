@echo off
echo =========================================================
echo   Opening AI Traffic Management Dashboard Frontend...
echo =========================================================

cd /d "%~dp0"

IF EXIST "frontend\index.html" (
    echo [INFO] Launching frontend dashboard in default browser...
    start "" "%~dp0frontend\index.html"
) ELSE (
    echo [ERROR] frontend\index.html not found!
    pause
)
