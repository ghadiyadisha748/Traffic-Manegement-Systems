@echo off
echo =========================================================
echo   AI Smart Traffic Management System - Complete Launcher
echo =========================================================

cd /d "%~dp0"

IF NOT EXIST "backend\venv\Scripts\python.exe" (
    echo [INFO] Virtual environment not found. Running first-time setup...
    call setup.bat
)

echo [1/2] Launching Backend Server in a new window...
start "AI Traffic Management Backend" cmd /k "cd /d "%~dp0\backend" && venv\Scripts\python.exe main.py"

echo Waiting 4 seconds for Backend API server to start...
timeout /t 4 /nobreak >nul

echo [2/2] Launching Frontend Dashboard in browser...
start "" "%~dp0frontend\index.html"

echo =========================================================
echo   Project running!
echo   - Backend URL: http://localhost:8000
echo   - Video Feed:  http://localhost:8000/video_feed
echo   - WebSocket:   ws://localhost:8000/ws
echo =========================================================
