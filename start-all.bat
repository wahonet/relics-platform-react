@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
title Relics Platform - Full Stack (Backend + Frontends)

cd /d "%~dp0"

REM Pick a Python interpreter (.venv / embedded python\ / system).
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON=%~dp0.venv\Scripts\python.exe"
    echo [OK] Using project virtual environment (.venv)
) else if exist "%~dp0python\python.exe" (
    set "PYTHON=%~dp0python\python.exe"
    echo [OK] Using embedded Python
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python not found. Install Python 3.10+ or provide .venv\Scripts\python.exe.
        pause
        exit /b 1
    )
    set "PYTHON=python"
    echo [OK] Using system Python
)

REM start.py launches backend + both Vite dev servers; logs stream into one console.
"%PYTHON%" "%~dp0start.py"

echo.
echo [STOPPED] All services exited.
pause
endlocal
