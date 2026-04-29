@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
title Build Frontends [Vue admin + React webgis]

cd /d "%~dp0"

REM -- check npm --
where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm not found. Install Node.js LTS v18 or newer: https://nodejs.org/
    pause
    exit /b 1
)

REM ===========================================================
REM  Step A: Vue admin panel  (platform\admin-vue)
REM ===========================================================
echo.
echo [A/2] Building Vue admin panel ^(platform\admin-vue^) ...
echo.
cd /d "%~dp0platform\admin-vue"

set NEED_INSTALL=0
if not exist "node_modules\vite" set NEED_INSTALL=1
if not exist "node_modules\.package-lock.json" set NEED_INSTALL=1
if "!NEED_INSTALL!"=="0" (
    for %%F in ("package.json") do set PKG_TS=%%~tF
    for %%F in ("node_modules\.package-lock.json") do set LOCK_TS=%%~tF
    if defined PKG_TS if defined LOCK_TS (
        if "!PKG_TS!" GTR "!LOCK_TS!" set NEED_INSTALL=1
    )
)

if "!NEED_INSTALL!"=="1" (
    echo   Installing/updating admin-vue dependencies, please wait 1-3 min...
    call npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed in admin-vue.
        pause
        exit /b 1
    )
) else (
    echo   admin-vue dependencies up-to-date, skip npm install.
)

call npm run build
if errorlevel 1 (
    echo [ERROR] admin-vue build failed.
    pause
    exit /b 1
)

REM ===========================================================
REM  Step B: React + three.js main webgis  (platform\webgis-react)
REM ===========================================================
echo.
echo [B/2] Building React + three.js main webgis ^(platform\webgis-react^) ...
echo.
cd /d "%~dp0platform\webgis-react"

set NEED_INSTALL=0
if not exist "node_modules\vite" set NEED_INSTALL=1
if not exist "node_modules\.package-lock.json" set NEED_INSTALL=1
if "!NEED_INSTALL!"=="0" (
    for %%F in ("package.json") do set PKG_TS=%%~tF
    for %%F in ("node_modules\.package-lock.json") do set LOCK_TS=%%~tF
    if defined PKG_TS if defined LOCK_TS (
        if "!PKG_TS!" GTR "!LOCK_TS!" set NEED_INSTALL=1
    )
)

if "!NEED_INSTALL!"=="1" (
    echo   Installing/updating webgis-react dependencies, please wait 2-5 min...
    call npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed in webgis-react.
        pause
        exit /b 1
    )
) else (
    echo   webgis-react dependencies up-to-date, skip npm install.
)

call npm run build
if errorlevel 1 (
    echo [ERROR] webgis-react build failed.
    pause
    exit /b 1
)

echo.
echo ====================================================
echo [DONE] Both frontends built successfully.
echo        Vue admin panel  -^>  platform\admin-vue\dist
echo        React main map   -^>  platform\webgis-react\dist
echo        Run 4-start.bat to launch the platform.
echo ====================================================
echo.
pause
