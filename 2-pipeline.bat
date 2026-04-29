@echo off
chcp 65001 >nul 2>&1
setlocal
title Relics Platform - Pipeline

cd /d "%~dp0"

:: ── 检测 Python ──────────────────────────────────────
if exist "%~dp0python\python.exe" (
    set "PYTHON=%~dp0python\python.exe"
    set "PATH=%~dp0python;%~dp0python\Scripts;%PATH%"
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo [错误] 未找到 Python。请先运行 setup.bat。
        pause
        exit /b 1
    )
    set "PYTHON=python"
)

:: ── 检查 config.yaml ─────────────────────────────────
if not exist "config.yaml" (
    echo [错误] 未找到 config.yaml，请先双击 setup.bat 初始化。
    pause
    exit /b 1
)

:: ── 执行管线 ─────────────────────────────────────────
echo ============================================
echo   Relics Platform - 数据管线
echo ============================================
echo.

%PYTHON% platform\scripts\run_pipeline.py %*
set RC=%ERRORLEVEL%

echo.
if %RC% EQU 0 (
    echo [OK] 管线执行完成。
) else (
    echo [失败] 管线退出码: %RC%
)
pause
endlocal & exit /b %RC%
