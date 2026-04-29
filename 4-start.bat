@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
title Relics Platform

cd /d "%~dp0"

REM -- detect Python --
if exist "%~dp0python\python.exe" (
    set "PYTHON=%~dp0python\python.exe"
    set "PATH=%~dp0python;%~dp0python\Scripts;%PATH%"
    echo [OK] Using embedded Python
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python not found. Run 1-setup.bat first.
        pause
        exit /b 1
    )
    set "PYTHON=python"
    echo [OK] Using system Python
)

REM -- config.yaml --
if not exist "config.yaml" (
    echo [ERROR] config.yaml missing. Run 1-setup.bat first.
    pause
    exit /b 1
)

REM -- python deps --
%PYTHON% -c "import yaml, fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
    echo [SETUP] Installing Python dependencies...
    %PYTHON% -m pip install -r platform\webgis\requirements.txt -q
    if errorlevel 1 (
        echo [ERROR] pip install failed. Check network.
        pause
        exit /b 1
    )
)

REM -- frontends built? --
if not exist "platform\admin-vue\dist\index.html" (
    echo.
    echo [NOTE] Vue admin UI not built: /admin-ui/ will return 404.
    echo        Run 3-build.bat once to enable it.
    echo.
)
if not exist "platform\webgis-react\dist\index.html" (
    echo.
    echo [NOTE] React webgis not built: / will fall back to legacy Cesium page.
    echo        Run 3-build.bat once to enable the new React + three.js frontend.
    echo        (Main API and legacy /legacy still work either way.)
    echo.
)

REM -- start (host/port read from config.yaml; serve.py opens the browser) --
set "PYTHONIOENCODING=utf-8"
%PYTHON% platform\webgis\serve.py

echo.
echo [STOPPED] Server exited.
pause
