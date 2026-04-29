@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
title Build WebGIS (React + three.js)

cd /d "%~dp0platform\webgis-react"

REM -- check npm --
where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm not found. Install Node.js LTS v18 or newer: https://nodejs.org/
    pause
    exit /b 1
)

REM -- decide whether we need npm install --
set NEED_INSTALL=0
if not exist "node_modules\vite" set NEED_INSTALL=1
if not exist "node_modules\.package-lock.json" set NEED_INSTALL=1

REM If package.json is newer than node_modules\.package-lock.json, reinstall.
if "%NEED_INSTALL%"=="0" (
    for %%F in ("package.json") do set PKG_TS=%%~tF
    for %%F in ("node_modules\.package-lock.json") do set LOCK_TS=%%~tF
    if defined PKG_TS if defined LOCK_TS (
        if "!PKG_TS!" GTR "!LOCK_TS!" set NEED_INSTALL=1
    )
)

if "%NEED_INSTALL%"=="1" (
    echo [1/2] Installing/updating dependencies, please wait 2-5 min...
    call npm install
    if errorlevel 1 (
        echo.
        echo [ERROR] npm install failed. Common causes:
        echo        1. Network: npm config set registry https://registry.npmmirror.com
        echo        2. PowerShell: Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
        pause
        exit /b 1
    )
) else (
    echo [1/2] Dependencies up-to-date, skip npm install.
)

REM -- build --
echo [2/2] Building React + three.js WebGIS...
call npm run build
if errorlevel 1 (
    echo [ERROR] Build failed. Check the log above.
    pause
    exit /b 1
)

echo.
echo ====================================================
echo [DONE] WebGIS (React + three.js) built to:
echo        platform\webgis-react\dist\
echo        Next start_platform.bat will serve it at:
echo        http://127.0.0.1:8000/  -^>  /app/
echo ====================================================
echo.
pause
