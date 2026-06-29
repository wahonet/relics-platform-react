#!/usr/bin/env bash
# 一键启动文物档案平台(后端 + 两个前端 dev server)。适用于麒麟等 Linux 桌面。
# 用法: ./start-all.sh   (首次需 chmod +x start-all.sh)
set -u

cd "$(dirname "$0")"

# ── 选 Python 解释器(优先虚拟环境)──────────────────────────────
if [ -x ".venv/bin/python" ]; then
    PY=".venv/bin/python"
    echo "[OK] 使用项目虚拟环境 .venv"
elif command -v python3 >/dev/null 2>&1; then
    PY="python3"
    echo "[OK] 使用系统 python3"
elif command -v python >/dev/null 2>&1; then
    PY="python"
    echo "[OK] 使用系统 python"
else
    echo "[错误] 未找到 Python,请安装 Python 3.10+。" >&2
    exit 1
fi

# exec 让 start.py 直接接管本进程,Ctrl+C 干净地传递给它。
exec "$PY" start.py
