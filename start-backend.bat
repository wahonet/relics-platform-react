@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
title Relics Platform - Backend

cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON=%~dp0.venv\Scripts\python.exe"
    set "PATH=%~dp0.venv\Scripts;%PATH%"
    echo [OK] Using project virtual environment
) else if exist "%~dp0python\python.exe" (
    set "PYTHON=%~dp0python\python.exe"
    set "PATH=%~dp0python;%~dp0python\Scripts;%PATH%"
    echo [OK] Using embedded Python
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python not found. Run 1-setup.bat first or install Python 3.10+.
        pause
        exit /b 1
    )
    set "PYTHON=python"
    echo [OK] Using system Python
)

if not exist "config.yaml" (
    echo [ERROR] config.yaml missing. Run 1-setup.bat first.
    pause
    exit /b 1
)

%PYTHON% -c "import yaml, fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
    echo [SETUP] Installing Python dependencies...
    %PYTHON% -m pip install -r platform\webgis\requirements.txt
    if errorlevel 1 (
        echo [ERROR] pip install failed. Check network or install dependencies manually.
        pause
        exit /b 1
    )
)

set "NO_PROXY=geo.datav.aliyun.com,overpass-api.de,overpass.kumi.systems,overpass.openstreetmap.fr,overpass.osm.ch,tile.openstreetmap.org,server.arcgisonline.com,wprd01.is.autonavi.com,wprd02.is.autonavi.com,wprd03.is.autonavi.com,wprd04.is.autonavi.com,webst01.is.autonavi.com,webst02.is.autonavi.com,webst03.is.autonavi.com,webst04.is.autonavi.com,127.0.0.1,localhost"
set "no_proxy=%NO_PROXY%"
set "PYTHONIOENCODING=utf-8"

echo.
echo [START] FastAPI backend
echo        Frontend dev servers can be started with start-frontend.bat
echo.

%PYTHON% platform\webgis\serve.py

echo.
echo [STOPPED] Backend server exited.
pause
endlocal
