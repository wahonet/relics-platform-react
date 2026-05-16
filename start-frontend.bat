@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
title Relics Platform - Frontends

cd /d "%~dp0"

where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm not found. Install Node.js LTS v18 or newer.
    pause
    exit /b 1
)

call :ensure_deps "platform\admin-vue" "Vue admin"
if errorlevel 1 exit /b 1

call :ensure_deps "platform\webgis-react" "React WebGIS"
if errorlevel 1 exit /b 1

echo.
echo [START] Vue admin dev server:   http://127.0.0.1:5173/
echo [START] React WebGIS dev server: http://127.0.0.1:5174/
echo [NOTE]  Start the backend separately with start-backend.bat.
echo.

start "Relics Vue Admin" cmd /k "cd /d %~dp0platform\admin-vue && npm run dev"
start "Relics React WebGIS" cmd /k "cd /d %~dp0platform\webgis-react && npm run dev"

echo Two frontend terminals were opened. Close those terminals to stop the dev servers.
pause
endlocal
exit /b 0

:ensure_deps
set "APP_DIR=%~1"
set "APP_NAME=%~2"

if not exist "%APP_DIR%\package.json" (
    echo [ERROR] %APP_NAME% package.json not found: %APP_DIR%
    exit /b 1
)

if exist "%APP_DIR%\node_modules\vite" (
    echo [OK] %APP_NAME% dependencies found.
    exit /b 0
)

echo [SETUP] Installing %APP_NAME% dependencies...
pushd "%APP_DIR%" >nul
call npm install
set "NPM_RC=%ERRORLEVEL%"
popd >nul
if not "%NPM_RC%"=="0" (
    echo [ERROR] npm install failed in %APP_DIR%.
    exit /b %NPM_RC%
)

echo [OK] %APP_NAME% dependencies installed.
exit /b 0

