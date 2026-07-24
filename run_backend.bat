@echo off
echo =========================================================
echo   Starting AI Traffic Management System Backend...
echo =========================================================

cd /d "%~dp0\backend"

IF NOT EXIST "venv\Scripts\python.exe" (
    echo [INFO] Virtual environment not found. Running setup.bat...
    call "%~dp0setup.bat"
    cd /d "%~dp0\backend"
)

echo [INFO] Starting FastAPI server on http://127.0.0.1:8000 ...
venv\Scripts\python.exe main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Backend exited with error code %ERRORLEVEL%.
    pause
)
