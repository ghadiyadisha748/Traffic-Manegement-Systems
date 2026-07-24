@echo off
SETLOCAL EnableDelayedExpansion
echo =========================================================
echo   AI Smart Traffic Management System - Automated Setup
echo =========================================================

cd /d "%~dp0"

REM 1. Find Python executable
SET PYTHON_CMD=
WHERE python >nul 2>nul
IF %ERRORLEVEL% EQU 0 (
    SET PYTHON_CMD=python
) ELSE (
    WHERE py >nul 2>nul
    IF %ERRORLEVEL% EQU 0 (
        SET PYTHON_CMD=py
    )
)

IF "%PYTHON_CMD%"=="" (
    echo [ERROR] Python was not found in PATH. Please install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)

echo [1/4] Using Python executable: %PYTHON_CMD%

REM 2. Create virtual environment inside backend/venv
cd backend
IF NOT EXIST "venv\Scripts\python.exe" (
    echo [2/4] Creating virtual environment in backend\venv...
    %PYTHON_CMD% -m venv venv
    IF %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
) ELSE (
    echo [2/4] Virtual environment backend\venv already exists.
)

REM 3. Install requirements
echo [3/4] Installing backend dependencies into virtual environment...
venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
venv\Scripts\python.exe -m pip install -r requirements.txt
IF %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Dependency installation encountered warnings, retrying core packages...
    venv\Scripts\python.exe -m pip install fastapi "uvicorn[standard]" ultralytics opencv-python-headless websockets pydantic sqlalchemy alembic psycopg2-binary python-dotenv shapely lapx
)

REM 4. Initialize database and verify setup
echo [4/4] Verifying setup and initializing database...
venv\Scripts\python.exe -c "import database, db_models; database.Base.metadata.create_all(bind=database.engine); print('[OK] Database initialized successfully.')"
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Database initialization failed.
    pause
    exit /b 1
)

echo =========================================================
echo   Setup completed successfully!
echo =========================================================
pause
