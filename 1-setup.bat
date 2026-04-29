@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion
title Relics Platform - Setup

cd /d "%~dp0"

echo ============================================
echo   Relics Platform - 初始化向导
echo ============================================
echo.

:: ── 检测 Python ──────────────────────────────────────
if exist "%~dp0python\python.exe" (
    set "PYTHON=%~dp0python\python.exe"
    set "PATH=%~dp0python;%~dp0python\Scripts;%PATH%"
    echo [OK] 使用内嵌 Python: %~dp0python\python.exe
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo [错误] 未找到 Python，请先安装 Python 3.10+ ^(勾选 Add to PATH^)
        echo        或将便携版 Python 放入本目录的 python\ 子目录中。
        echo        下载地址: https://www.python.org/downloads/
        pause
        exit /b 1
    )
    set "PYTHON=python"
    echo [OK] 使用系统 Python
)

:: ── 安装依赖 ─────────────────────────────────────────
echo.
echo [检查] 正在验证 Python 依赖...
%PYTHON% -c "import yaml, fastapi, uvicorn, openpyxl, docx, numpy, tifffile" >nul 2>&1
if errorlevel 1 (
    echo [安装] 正在安装依赖包（约 1-2 分钟）...
    %PYTHON% -m pip install -r platform\webgis\requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请检查网络或手动运行:
        echo        %PYTHON% -m pip install -r platform\webgis\requirements.txt
        pause
        exit /b 1
    )
    echo [OK] 依赖安装完成
) else (
    echo [OK] 所有依赖已就绪
)

:: ── 创建 data 目录 ───────────────────────────────────
echo.
echo [创建] 正在创建数据目录...
%PYTHON% -c "import sys; sys.path.insert(0, r'platform\scripts'); from _common import ensure_data_dirs; ensure_data_dirs()"
if errorlevel 1 (
    echo [错误] 目录创建失败
    pause
    exit /b 1
)
echo [OK] data\ 目录结构已就绪

:: ── 生成 config.yaml ─────────────────────────────────
echo.
if exist "config.yaml" (
    echo [SKIP] config.yaml 已存在，保留现有配置
) else (
    copy /Y "config.example.yaml" "config.yaml" >nul
    echo [OK] 已从模板生成 config.yaml
)

:: ── 打印项目状态 ─────────────────────────────────────
echo.
%PYTHON% platform\scripts\_common.py

:: ── 提示下一步 ───────────────────────────────────────
echo.
echo ============================================
echo   初始化完成！下一步操作：
echo ============================================
echo.
echo   1. 编辑 config.yaml，填写县/区名称、中心坐标、API Key
echo   2. 将数据放入对应目录:
echo        data\input\01_archives\      -- 放文物档案 DOCX
echo        data\input\02_worklogs\      -- 放工作日志 Excel      ^(可选^)
echo        data\input\03_boundaries\    -- 放行政边界 Shapefile/GeoJSON
echo        data\input\04_dem\           -- 放 DEM GeoTIFF        ^(可选^)
echo        data\input\05_models_3d\     -- 放 3D Tiles           ^(可选^)
echo   3. 双击 2-pipeline.bat   运行数据管线生成结构化数据
echo   4. 双击 3-build.bat      构建前端 (Vue 后台 + React 主前端)
echo   5. 双击 4-start.bat      启动 WebGIS 平台
echo.
pause
endlocal
